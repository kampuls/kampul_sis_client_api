"""Temporary bridge for released desktop builds that require ``students.image`` bytes.

Only the legacy student photo column is supported here.  Current clients still
receive a StorageService URL and never receive database bytes over JSON.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .storage_service import StorageService


LEGACY_STUDENT_IMAGE_MAX_BYTES = 20 * 1024 * 1024
STUDENT_PLACEHOLDER_SHA256 = frozenset(
    {
        "20540f6d70b83c50118327c1905bdebec2050e8fc2c72d66316675fd8c4b9459",
        "35211a0a93fcce0c523b6e12e6f2138cad4eac39978044339b9ef2b8bd723f75",
    }
)

_RESOURCE_CACHE_LIMIT = 10_000
_resource_cache: OrderedDict[str, str | None] = OrderedDict()
_resource_cache_lock = RLock()


def _image_metadata(content: bytes) -> tuple[str, str]:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if content.startswith(b"BM"):
        return ".bmp", "image/bmp"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return ".tif", "image/tiff"
    raise ValueError("Legacy student image bytes are not a supported image")


def validate_legacy_student_image(content: bytes) -> bytes:
    data = bytes(content)
    if not data:
        raise ValueError("Legacy student image is empty")
    if len(data) > LEGACY_STUDENT_IMAGE_MAX_BYTES:
        raise ValueError("Legacy student image exceeds the 20 MB limit")
    _image_metadata(data)
    return data


def publish_legacy_student_image(content: bytes) -> str | None:
    """Return a stable resource URL for a legacy BLOB without exposing bytes."""

    data = validate_legacy_student_image(content)
    digest = hashlib.sha256(data).hexdigest()
    if digest in STUDENT_PLACEHOLDER_SHA256:
        return None

    with _resource_cache_lock:
        if digest in _resource_cache:
            cached = _resource_cache.pop(digest)
            _resource_cache[digest] = cached
            return cached

    extension, content_type = _image_metadata(data)
    resource_url = StorageService.upload_file(
        data,
        "desktop/legacy-student-images",
        f"{digest}{extension}",
        content_type,
    )
    if not resource_url:
        raise RuntimeError("Could not publish the legacy student image resource")

    with _resource_cache_lock:
        _resource_cache[digest] = resource_url
        while len(_resource_cache) > _RESOURCE_CACHE_LIMIT:
            _resource_cache.popitem(last=False)
    return resource_url


def remember_legacy_student_image_resource(content: bytes, resource_url: str | None) -> str | None:
    """Seed the bounded byte-hash cache from a resource already persisted elsewhere."""

    data = validate_legacy_student_image(content)
    digest = hashlib.sha256(data).hexdigest()
    value = None if digest in STUDENT_PLACEHOLDER_SHA256 else str(resource_url or "").strip()
    if value and not value.startswith(("http://", "https://", "/uploads/", "uploads/")):
        raise ValueError("Legacy student image resource URL is invalid")
    if not value and digest not in STUDENT_PLACEHOLDER_SHA256:
        return None
    with _resource_cache_lock:
        _resource_cache[digest] = value
        while len(_resource_cache) > _RESOURCE_CACHE_LIMIT:
            _resource_cache.popitem(last=False)
    return value


def resource_text_from_bytes(content: bytes) -> str | None:
    try:
        value = bytes(content).decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if not value or "\x00" in value or len(value) > 2_000:
        return None
    if value.startswith(("http://", "https://", "/uploads/", "uploads/")):
        return value
    return None


def _read_limited(stream) -> bytes:
    content = stream.read(LEGACY_STUDENT_IMAGE_MAX_BYTES + 1)
    if len(content) > LEGACY_STUDENT_IMAGE_MAX_BYTES:
        raise ValueError("Legacy student image resource exceeds the 20 MB limit")
    return validate_legacy_student_image(content)


def load_student_image_resource(resource_url: str) -> bytes:
    """Load an existing managed resource while repairing an already-converted DB."""

    value = str(resource_url or "").strip()
    if value.startswith(("/uploads/", "uploads/")):
        uploads_root = (Path.cwd() / "uploads").resolve()
        relative = value.lstrip("/")
        if relative.startswith("uploads/"):
            relative = relative[len("uploads/") :]
        candidate = (uploads_root / relative).resolve()
        if candidate != uploads_root and uploads_root not in candidate.parents:
            raise ValueError("Legacy student image path leaves the uploads directory")
        with candidate.open("rb") as stream:
            return _read_limited(stream)

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Legacy student image resource URL is invalid")
    if parsed.path.startswith("/uploads/"):
        return load_student_image_resource(parsed.path)
    host = (parsed.hostname or "").lower()
    allowed_cloud_host = (
        host == "res.cloudinary.com"
        or host == "firebasestorage.googleapis.com"
        or host == "storage.googleapis.com"
        or host.endswith(".amazonaws.com")
        or host.endswith(".digitaloceanspaces.com")
    )
    if not allowed_cloud_host:
        raise ValueError("Legacy student image resource host is not managed storage")
    request = Request(value, headers={"User-Agent": "PAMA-Desktop-Migration/1.0"})
    with urlopen(request, timeout=30) as response:
        return _read_limited(response)


def clear_legacy_student_image_cache() -> None:
    """Test/deployment helper; normal request handling keeps the bounded cache warm."""

    with _resource_cache_lock:
        _resource_cache.clear()
