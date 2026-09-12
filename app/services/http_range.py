"""Small RFC 7233 single-byte-range parser used by local news video streaming."""

from __future__ import annotations

from typing import Optional


def parse_single_byte_range(
    header: Optional[str],
    file_size: int,
) -> Optional[tuple[int, int]]:
    """Return inclusive `(start, end)`, None, or raise ValueError."""
    if not header:
        return None
    if file_size <= 0 or not header.lower().startswith("bytes="):
        raise ValueError("Invalid byte range")
    raw = header.split("=", 1)[1].strip()
    if "," in raw or "-" not in raw:
        raise ValueError("Only one byte range is supported")
    start_raw, end_raw = (part.strip() for part in raw.split("-", 1))
    try:
        if not start_raw:
            suffix_length = int(end_raw)
            if suffix_length <= 0:
                raise ValueError("Invalid suffix range")
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
            if start < 0 or start >= file_size:
                raise ValueError("Range start is outside the file")
            end = min(end, file_size - 1)
            if end < start:
                raise ValueError("Range end precedes start")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid byte range") from exc
    return start, end
