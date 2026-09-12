"""Resolve the Telegram destination used by leave notifications."""

from typing import Any, Optional

from sqlalchemy.orm import Session

from .telegram_branch_routing import resolve_branch_leave_notification_chat_id


COMBINED_LEAVE_ROUTING = "combined"
SEPARATE_LEAVE_ROUTING = "separate"


def normalize_leave_routing_mode(value: Any) -> str:
    """Treat missing legacy values as the safe, backwards-compatible default."""
    normalized = str(value or COMBINED_LEAVE_ROUTING).strip().lower()
    if normalized == SEPARATE_LEAVE_ROUTING:
        return SEPARATE_LEAVE_ROUTING
    return COMBINED_LEAVE_ROUTING


def resolve_leave_notification_chat_id(
    settings: Any,
    *,
    db: Optional[Session] = None,
    branch_id: Any = None,
) -> Optional[str]:
    """Return the configured leave destination without an implicit fallback.

    Separate mode deliberately does not fall back to the attendance chat. This
    prevents a removed or unfinished leave destination from leaking leave
    messages into the attendance group.
    """
    if settings is None:
        return None
    branch_destination = resolve_branch_leave_notification_chat_id(
        settings,
        db=db,
        branch_id=branch_id,
    )
    if branch_destination:
        return branch_destination
    mode = normalize_leave_routing_mode(
        getattr(settings, "leave_routing_mode", None)
    )
    field = "leave_chat_id" if mode == SEPARATE_LEAVE_ROUTING else "chat_id"
    value = getattr(settings, field, None)
    normalized = str(value or "").strip()
    return normalized or None
