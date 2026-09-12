"""Resolve optional workplace-specific Telegram notification destinations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ALL_BRANCHES = "all"
BY_BRANCH = "by_branch"


@dataclass(frozen=True)
class TelegramBranchRoute:
    attendance_chat_id: Optional[str]
    leave_chat_id: Optional[str]


def normalize_branch_routing_mode(value: Any) -> str:
    normalized = str(value or ALL_BRANCHES).strip().lower()
    return BY_BRANCH if normalized == BY_BRANCH else ALL_BRANCHES


def _clean_chat_id(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def branch_notification_route(
    db: Optional[Session],
    *,
    settings_id: Any,
    branch_id: Any,
) -> Optional[TelegramBranchRoute]:
    """Return a branch override, falling back safely on legacy databases."""

    if db is None:
        return None
    try:
        normalized_settings_id = int(settings_id or 0)
        normalized_branch_id = int(branch_id or 0)
    except (TypeError, ValueError):
        return None
    if normalized_settings_id <= 0 or normalized_branch_id <= 0:
        return None

    try:
        row = db.execute(
            text(
                """
                SELECT attendance_chat_id, leave_chat_id
                FROM telegram_branch_notification_routes
                WHERE settings_id = :settings_id
                  AND branch_id = :branch_id
                LIMIT 1
                """
            ),
            {
                "settings_id": normalized_settings_id,
                "branch_id": normalized_branch_id,
            },
        ).fetchone()
    except Exception as exc:
        # During a rolling deployment the new table may not exist yet. Global
        # routing must continue to work instead of losing notifications.
        logger.warning("Could not resolve Telegram branch route: %s", exc)
        return None
    if row is None:
        return None
    return TelegramBranchRoute(
        attendance_chat_id=_clean_chat_id(row[0]),
        leave_chat_id=_clean_chat_id(row[1]),
    )


def resolve_attendance_notification_chat_id(
    settings: Any,
    *,
    db: Optional[Session] = None,
    branch_id: Any = None,
) -> Optional[str]:
    """Resolve Attendance destination with the global chat as fallback."""

    if settings is None:
        return None
    if normalize_branch_routing_mode(
        getattr(settings, "branch_routing_mode", None)
    ) == BY_BRANCH:
        route = branch_notification_route(
            db,
            settings_id=getattr(settings, "id", None),
            branch_id=branch_id,
        )
        if route is not None and route.attendance_chat_id:
            return route.attendance_chat_id
    return _clean_chat_id(getattr(settings, "chat_id", None))


def resolve_branch_leave_notification_chat_id(
    settings: Any,
    *,
    db: Optional[Session] = None,
    branch_id: Any = None,
) -> Optional[str]:
    """Resolve a branch Leave override before the global Leave rules.

    A configured branch Leave chat wins. Otherwise a configured branch
    Attendance chat is shared by Leave for that branch. If neither exists,
    callers should apply the existing global combined/separate behavior.
    """

    if settings is None:
        return None
    if normalize_branch_routing_mode(
        getattr(settings, "branch_routing_mode", None)
    ) != BY_BRANCH:
        return None
    route = branch_notification_route(
        db,
        settings_id=getattr(settings, "id", None),
        branch_id=branch_id,
    )
    if route is None:
        return None
    return route.leave_chat_id or route.attendance_chat_id
