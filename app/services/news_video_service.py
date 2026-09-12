"""Validation and stream-optimization helpers for news video media."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from app.core.auto_deps import ensure_package


ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
    "application/octet-stream",
}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_youtube_video_id(value: Optional[str]) -> Optional[str]:
    """Return a safe 11-character YouTube ID from common URL formats."""
    raw = (value or "").strip()
    if YOUTUBE_ID_PATTERN.fullmatch(raw):
        return raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    candidate: Optional[str] = None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            parts = parsed.path.strip("/").split("/")
            candidate = parts[1] if len(parts) > 1 else None
    return candidate if candidate and YOUTUBE_ID_PATTERN.fullmatch(candidate) else None


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def youtube_thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def validate_video_upload(filename: Optional[str], content_type: Optional[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise ValueError("Only MP4, MOV, M4V, or WebM video files are allowed")
    if content_type and content_type.lower() not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise ValueError("Unsupported video content type")
    return suffix


def _resolve_yt_dlp_cmd() -> list[str]:
    downloader = shutil.which("yt-dlp")
    if downloader:
        return [downloader]

    venv_bin = Path(sys.executable).parent / "yt-dlp"
    if venv_bin.exists() and venv_bin.is_file():
        return [str(venv_bin)]

    for candidate in ["/usr/bin/yt-dlp", "/usr/local/bin/yt-dlp", "/opt/homebrew/bin/yt-dlp"]:
        if Path(candidate).is_file():
            return [candidate]

    if ensure_package("yt_dlp", "yt-dlp>=2026.6.9"):
        return [sys.executable, "-m", "yt_dlp"]

    raise RuntimeError("YouTube import is unavailable; install yt-dlp")


def _resolve_ffmpeg() -> Optional[str]:
    downloader = shutil.which("ffmpeg")
    if downloader:
        return downloader
    for candidate in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        if Path(candidate).is_file():
            return candidate
    venv_bin = Path(sys.executable).parent / "ffmpeg"
    if venv_bin.exists() and venv_bin.is_file():
        return str(venv_bin)
    return None


def _resolve_ffprobe() -> Optional[str]:
    downloader = shutil.which("ffprobe")
    if downloader:
        return downloader
    for candidate in ["/usr/bin/ffprobe", "/usr/local/bin/ffprobe", "/opt/homebrew/bin/ffprobe"]:
        if Path(candidate).is_file():
            return candidate
    venv_bin = Path(sys.executable).parent / "ffprobe"
    if venv_bin.exists() and venv_bin.is_file():
        return str(venv_bin)
    return None


def download_youtube_video(
    youtube_url: str,
    output_directory: Path,
    max_bytes: int,
) -> Path:
    """
    Download a school-owned YouTube video for first-party playback.

    The original URL is retained by the caller for rollback. The resulting
    file is only an input to ``optimize_video`` and is never served directly.
    """
    video_id = extract_youtube_video_id(youtube_url)
    if not video_id:
        raise ValueError("Invalid YouTube video URL")
    yt_cmd = _resolve_yt_dlp_cmd()
    ffmpeg = _resolve_ffmpeg()
    output_directory.mkdir(parents=True, exist_ok=True)
    output_template = output_directory / "youtube-source.%(ext)s"

    cmd = list(yt_cmd) + [
        "--no-playlist",
        "--no-cache-dir",
        "--no-part",
        "--max-filesize",
        str(max_bytes),
        "--format",
        (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        ),
        "--merge-output-format",
        "mp4",
    ]
    if ffmpeg:
        cmd.extend(["--ffmpeg-location", ffmpeg])

    cmd.extend([
        "--output",
        str(output_template),
        "--print",
        "after_move:filepath",
        canonical_youtube_url(video_id),
    ])
    result = _run(cmd)
    candidates = [
        Path(line.strip())
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    source = next(
        (
            path
            for path in reversed(candidates)
            if path.exists() and path.is_file()
        ),
        None,
    )
    if source is None:
        source = next(
            (
                path
                for path in output_directory.glob("youtube-source.*")
                if path.is_file()
            ),
            None,
        )
    if source is None:
        raise RuntimeError("YouTube did not return a playable video")
    if source.stat().st_size > max_bytes:
        source.unlink(missing_ok=True)
        raise ValueError("Imported YouTube video exceeds the upload size limit")
    return source


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def _duration_seconds(path: Path) -> Optional[int]:
    ffprobe = _resolve_ffprobe()
    if not ffprobe:
        return None
    try:
        result = _run([
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ])
        duration = float(json.loads(result.stdout)["format"]["duration"])
        return max(0, round(duration))
    except (KeyError, TypeError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def optimize_video(
    source: Path,
    output: Path,
    thumbnail: Path,
) -> tuple[Path, Optional[Path], Optional[int]]:
    """
    Produce H.264/AAC MP4 with fast-start metadata plus a JPEG thumbnail.

    When FFmpeg is unavailable, an already-MP4 upload is kept as-is. Other
    containers are rejected because they cannot be guaranteed to play smoothly
    on both iOS and Android.
    """
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        if source.suffix.lower() != ".mp4":
            raise RuntimeError(
                "Video processing is unavailable; install FFmpeg or upload MP4"
            )
        return source, None, _duration_seconds(source)

    scale = "scale=w='min(1280,iw)':h=-2:force_original_aspect_ratio=decrease"
    _run([
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-map_metadata",
        "-1",
        "-vf",
        scale,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ])
    try:
        _run([
            ffmpeg,
            "-y",
            "-ss",
            "1",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-vf",
            "scale=w='min(1280,iw)':h=-2",
            "-q:v",
            "3",
            str(thumbnail),
        ])
        thumbnail_path: Optional[Path] = thumbnail if thumbnail.exists() else None
    except subprocess.SubprocessError:
        thumbnail_path = None
    return output, thumbnail_path, _duration_seconds(output)
