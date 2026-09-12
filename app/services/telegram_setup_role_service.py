"""Role rules for app-controlled Telegram chat setup."""

from __future__ import annotations


APP_ASSIGNABLE_TELEGRAM_ROLES = frozenset({"notification_only", "general"})
UNASSIGNED_TELEGRAM_ROLE = "pending"


def resolve_authorized_chat_role(intended_role: str | None) -> str:
    """Use an app-selected role, or leave legacy authorization unassigned."""
    if intended_role in APP_ASSIGNABLE_TELEGRAM_ROLES:
        return str(intended_role)
    return UNASSIGNED_TELEGRAM_ROLE


def telegram_role_label(role: str) -> str:
    if role == "notification_only":
        return "Notification Only"
    if role == "general":
        return "General Group"
    return "Awaiting App Setup"

