"""Certificate push image at /uploads/push/notification_certificate.jpg (primary for FCM)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CERTIFICATE_PUSH_IMAGE_RELATIVE = "/uploads/push/notification_certificate.jpg"
CERTIFICATE_PUSH_IMAGE_FILENAME = "notification_certificate.jpg"
CERTIFICATE_PUSH_FOLDER = "push"

_API_ROOT = Path(__file__).resolve().parent.parent
_UPLOADS_DEST = Path("uploads/push/notification_certificate.jpg")
_STATIC_SOURCE = _API_ROOT / "static" / "push" / "notification_certificate.jpg"
_FLUTTER_SOURCE = (
    _API_ROOT.parent.parent
    / "pama_international_school"
    / "assets"
    / "images"
    / "notification_certificate.jpg"
)


def _certificate_push_source_path() -> Optional[Path]:
    """Best on-disk source to publish (static bundle first, then Flutter asset, then existing upload)."""
    for candidate in (_STATIC_SOURCE, _FLUTTER_SOURCE, _UPLOADS_DEST):
        if candidate.is_file():
            return candidate
    return None


def _sync_local_upload_copy(source: Path) -> None:
    """Keep uploads/push/ in sync for local StaticFiles + PUBLIC_API_BASE_URL."""
    try:
        _UPLOADS_DEST.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != _UPLOADS_DEST.resolve():
            shutil.copy2(source, _UPLOADS_DEST)
    except OSError as exc:
        logger.warning("Could not sync local certificate push image: %s", exc)


def seed_certificate_push_image() -> None:
    """
    Startup: copy bundled static image into uploads/push/ for /uploads/... URLs.
    Always refreshes from app/static/push when that file exists (new deploys).
    """
    source = _STATIC_SOURCE if _STATIC_SOURCE.is_file() else _certificate_push_source_path()
    if not source:
        logger.warning(
            "Certificate push image not found; add app/static/push/%s to Git",
            CERTIFICATE_PUSH_IMAGE_FILENAME,
        )
        return
    _sync_local_upload_copy(source)
    logger.info("Certificate push image ready at %s (from %s)", _UPLOADS_DEST, source)


def resolve_certificate_push_image_path() -> Optional[Path]:
    """Path to serve at GET /uploads/push/notification_certificate.jpg."""
    seed_certificate_push_image()
    if _UPLOADS_DEST.is_file():
        return _UPLOADS_DEST
    if _STATIC_SOURCE.is_file():
        return _STATIC_SOURCE
    return _certificate_push_source_path()


def ensure_certificate_push_image_for_push() -> Optional[str]:
    """
    Before sending parent certificate FCM, upload the push artwork via the active
    storage provider (local / S3 / Cloudinary / Firebase) so PUBLIC_API_BASE_URL
    and FCM can load it.

    Returns a storage URL (/uploads/push/... or https://...) or None.
    """
    from ..services.storage_service import StorageService

    source = _certificate_push_source_path()
    if not source:
        logger.warning(
            "[Certificates] Push image missing; notifications may be text-only"
        )
        return None

    try:
        file_data = source.read_bytes()
    except OSError as exc:
        logger.warning("[Certificates] Could not read push image %s: %s", source, exc)
        return None

    if not file_data:
        return None

    url = StorageService.upload_file(
        file_data=file_data,
        folder=CERTIFICATE_PUSH_FOLDER,
        filename=CERTIFICATE_PUSH_IMAGE_FILENAME,
        content_type="image/jpeg",
    )

    if url:
        _sync_local_upload_copy(source)
        logger.info("[Certificates] Push notification image uploaded: %s", url)
        return url

    logger.warning(
        "[Certificates] Storage upload failed; falling back to local uploads/push"
    )
    seed_certificate_push_image()
    return CERTIFICATE_PUSH_IMAGE_RELATIVE if _UPLOADS_DEST.is_file() else None
