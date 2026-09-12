"""Resolve safe Telegram destinations for attendance notifications."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def attendance_notification_chat_ids(
    db: Session,
    *,
    bot_token: str,
    primary_chat_id: Optional[str] = None,
    preferred_chat_id: Optional[str] = None,
) -> list[str]:
    """Return deduplicated Notification Only destinations in fallback order.

    ``preferred_chat_id`` is used for a dedicated support/report destination.
    ``primary_chat_id`` is the legacy/current selected attendance destination.
    Tracked General Groups are intentionally excluded so administrative alerts
    cannot leak into member discussion groups.
    """

    tracked_roles: dict[str, str] = {}
    notification_only: list[str] = []
    tracked_lookup_succeeded = False
    try:
        rows = db.execute(
            text(
                """
                SELECT chat_id, bot_role
                FROM telegram_tracked_chats
                WHERE is_active = TRUE
                  AND (bot_token = :bot_token OR bot_token IS NULL OR bot_token = '')
                ORDER BY added_at DESC
                """
            ),
            {"bot_token": bot_token},
        ).fetchall()
        tracked_lookup_succeeded = True
        for row in rows:
            chat_id = str(row[0] or "").strip()
            role = str(row[1] or "").strip()
            if not chat_id:
                continue
            tracked_roles[chat_id] = role
            if role == "notification_only":
                notification_only.append(chat_id)
    except Exception as exc:
        # Legacy installations may not have the tracked-chat table yet. The
        # selected attendance chat remains a valid fallback in that case.
        logger.warning(
            "Could not resolve tracked Telegram attendance destinations: %s",
            exc,
        )

    candidates: list[str] = []

    def add(value: Optional[str], *, require_notification_role: bool = False) -> None:
        chat_id = str(value or "").strip()
        if not chat_id or chat_id in candidates:
            return
        if require_notification_role and tracked_lookup_succeeded:
            role = tracked_roles.get(chat_id)
            # A legacy selected chat may not be tracked. A tracked General
            # Group, however, must never receive administrative alerts.
            if role not in (None, "notification_only"):
                return
        candidates.append(chat_id)

    add(preferred_chat_id, require_notification_role=True)
    add(primary_chat_id, require_notification_role=True)
    for chat_id in notification_only:
        add(chat_id)
    return candidates
