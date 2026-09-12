"""Pure helpers for de-duplicating push-notification recipients."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List


_LOGICAL_ID_FIELDS = (
    "message_id",
    "request_id",
    "ad_id",
    "news_id",
    "event_id",
    "cer_id",
    "order_id",
    "listing_id",
    "schedule_id",
    "student_id",
    "parent_id",
    "target_user_id",
    "sender_id",
)


def logical_notification_key(
    title: str,
    body: str,
    data: Dict[str, Any],
) -> str | None:
    """Build a stable key for retried sends that identify a logical event.

    The title/body digest keeps legitimate updates to the same entity distinct,
    while an exact retry (including chunked broadcasts) receives one identity.
    Payloads without a meaningful event identifier intentionally remain unique.
    """
    notification_type = str(data.get("type") or "").strip().lower()
    if not notification_type:
        return None
    for field in _LOGICAL_ID_FIELDS:
        value = str(data.get(field) or "").strip()
        if not value:
            continue
        content_digest = hashlib.sha256(
            f"{title}\0{body}".encode("utf-8")
        ).hexdigest()[:16]
        return f"{notification_type}:{field}:{value}:{content_digest}"
    return None


def _recency(row: Dict[str, Any]) -> tuple[float, int]:
    last_used = row.get("last_used_at")
    timestamp = 0.0
    if hasattr(last_used, "timestamp"):
        try:
            timestamp = float(last_used.timestamp())
        except (TypeError, ValueError, OSError):
            timestamp = 0.0
    try:
        row_id = int(row.get("id") or 0)
    except (TypeError, ValueError):
        row_id = 0
    return timestamp, row_id


def dedupe_device_tokens(rows: Iterable[Any]) -> List[Any]:
    """Keep one recipient per FCM token and per known physical device.

    Exact token de-duplication is always safe. Physical-device de-duplication
    is applied only when the row includes a recipient id, role, device type,
    and a usable device name; this avoids merging two different users who own
    phones with the same model/name. The most recently used row wins.
    """
    best_by_token: Dict[str, Any] = {}
    for row in rows:
        token = row.get("token") if isinstance(row, dict) else str(row or "")
        token = str(token or "").strip()
        if not token:
            continue
        current = best_by_token.get(token)
        if current is None:
            best_by_token[token] = row
            continue
        if isinstance(row, dict) and isinstance(current, dict):
            if _recency(row) > _recency(current):
                best_by_token[token] = row

    best_by_device: Dict[tuple[str, str, str, str], Dict[str, Any]] = {}
    passthrough: List[Any] = []
    for row in best_by_token.values():
        if not isinstance(row, dict):
            passthrough.append(row)
            continue
        user_id = row.get("user_id")
        user_type = str(row.get("user_type") or "").strip().lower()
        device_type = str(row.get("device_type") or "").strip().lower()
        device_name = str(row.get("device_name") or "").strip().lower()
        if (
            user_id is None
            or not user_type
            or not device_type
            or not device_name
            or device_name == "unknown"
        ):
            passthrough.append(row)
            continue
        key = (str(user_id), user_type, device_type, device_name)
        current = best_by_device.get(key)
        if current is None or _recency(row) > _recency(current):
            best_by_device[key] = row

    return passthrough + list(best_by_device.values())
