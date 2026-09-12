"""Per-General-Group controls for Telegram new-member verification."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

DEFAULT_MEMBER_VERIFICATION_ENABLED = False


def get_member_verification_enabled(db: Session, chat_id: str | int) -> bool:
    """Return the saved join-verification policy, defaulting to Off."""
    try:
        row = db.execute(
            text("""
                SELECT member_verification_enabled
                FROM telegram_tracked_chats
                WHERE chat_id = :chat_id AND is_active = TRUE
                LIMIT 1
            """),
            {"chat_id": str(chat_id)},
        ).fetchone()
        if not row or row[0] is None:
            return DEFAULT_MEMBER_VERIFICATION_ENABLED
        return bool(row[0])
    except Exception:
        logger.exception(
            "Could not load Telegram member verification for chat %s; "
            "using the default",
            chat_id,
        )
        return DEFAULT_MEMBER_VERIFICATION_ENABLED


def member_chat_permissions(*, can_chat: bool) -> dict[str, bool]:
    """Build Telegram permissions used to lock or release a joining member."""
    permissions = {
        "can_send_messages": can_chat,
        "can_send_audios": can_chat,
        "can_send_documents": can_chat,
        "can_send_photos": can_chat,
        "can_send_videos": can_chat,
        "can_send_video_notes": can_chat,
        "can_send_voice_notes": can_chat,
        "can_send_polls": can_chat,
        "can_send_other_messages": can_chat,
        "can_add_web_page_previews": can_chat,
    }
    if can_chat:
        permissions["can_invite_users"] = True
    return permissions
