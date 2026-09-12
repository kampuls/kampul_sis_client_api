"""
Telegram Bot Webhook Handler for Attendance System.
Automatically captures chat/group IDs when bot is added.
"""
import logging
import json
import html
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from ...core import get_db
from ...auth import get_current_active_user
from ...models import User
from ...models.telegram_attendance_settings import TelegramAttendanceSettings
from ...services.telegram_analytics_service import TelegramAnalyticsService
from ...services.telegram_moderation_service import (
    DEFAULT_ALLOWED_DOMAINS,
    DEFAULT_ALLOWED_EXTENSIONS,
    DEFAULT_BLOCKED_EXTENSIONS,
    ensure_moderation_webhook_updates,
    get_bot_moderation_permissions,
    get_moderation_policy,
    moderate_general_group_message,
    save_moderation_policy,
)
from ...services.telegram_group_reply_service import (
    build_default_app_reply_html,
    default_group_reply_settings,
    get_group_reply_settings,
    match_default_group_reply_feature,
    match_group_reply_feature,
    render_telegram_reply_html,
    save_group_reply_settings,
)
from ...services.telegram_member_verification_service import (
    get_member_verification_enabled,
    member_chat_permissions,
)
from ...services.telegram_message_format import (
    safe_telegram_html,
    telegram_status_card,
)
from ...services.telegram_webhook_dedupe import (
    claim_telegram_webhook_event,
    telegram_membership_event_key,
    telegram_update_event_key,
)
from ...services.telegram_setup_role_service import (
    APP_ASSIGNABLE_TELEGRAM_ROLES,
    resolve_authorized_chat_role,
    telegram_role_label,
)
from ...services.telegram_leave_routing import normalize_leave_routing_mode

logger = logging.getLogger(__name__)

router = APIRouter()

# No hardcoded bot token — always read from database settings.
# Admin must save their bot token via the Flutter app settings screen.
DEFAULT_BOT_TOKEN = None  # kept for backward compat only; prefer get_active_bot_token(db)


class TelegramModerationPolicyUpdate(BaseModel):
    enabled: bool = True
    file_policy: Literal["allow_all", "blocklist", "allowlist"] = "blocklist"
    blocked_extensions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BLOCKED_EXTENSIONS),
        max_length=100,
    )
    allowed_extensions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_EXTENSIONS),
        max_length=100,
    )
    link_policy: Literal["allow_all", "block_all", "allowlist"] = "allow_all"
    allowed_domains: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_DOMAINS),
        max_length=100,
    )
    exempt_admins: bool = False
    send_warning: bool = True


class TelegramGroupReplyFeatureUpdate(BaseModel):
    key: Literal["location", "phone", "school", "app"]
    enabled: bool = True
    triggers: list[str] = Field(default_factory=list, max_length=50)
    reply_text: str = Field(default="", max_length=4000)


class TelegramGroupReplySettingsUpdate(BaseModel):
    enabled: bool = True
    features: list[TelegramGroupReplyFeatureUpdate] = Field(
        default_factory=list,
        max_length=4,
    )


class TelegramMemberVerificationUpdate(BaseModel):
    enabled: bool = False


def get_active_bot_token(db: Session) -> str | None:
    """Read the bot token configured in DB settings. Returns None if not configured."""
    try:
        settings = db.query(TelegramAttendanceSettings).first()
        if settings and settings.bot_token:
            return settings.bot_token
    except Exception:
        pass
    return None


def _clear_notification_destination_references(
    db: Session,
    chat_id: str,
) -> None:
    """Disable only the notification features that depended on this chat."""
    settings = db.query(TelegramAttendanceSettings).first()
    if settings is None:
        return

    normalized_chat_id = str(chat_id)
    attendance_removed = str(settings.chat_id or "") == normalized_chat_id
    leave_removed = str(settings.leave_chat_id or "") == normalized_chat_id
    leave_mode = normalize_leave_routing_mode(settings.leave_routing_mode)

    if attendance_removed:
        settings.chat_id = None
        settings.enabled = False
        if leave_mode == "combined":
            settings.notify_leave_requests = False
            settings.notify_leave_decisions = False

    if leave_removed:
        settings.leave_chat_id = None
        if leave_mode == "separate":
            settings.notify_leave_requests = False
            settings.notify_leave_decisions = False

    # Remove workplace overrides that point to a chat the bot no longer owns.
    # The route row is deleted when both fields become empty so global fallback
    # applies automatically.
    try:
        if not inspect(db.get_bind()).has_table(
            "telegram_branch_notification_routes"
        ):
            return
        db.execute(
            text(
                """
                UPDATE telegram_branch_notification_routes
                SET attendance_chat_id = CASE
                        WHEN attendance_chat_id = :chat_id THEN NULL
                        ELSE attendance_chat_id
                    END,
                    leave_chat_id = CASE
                        WHEN leave_chat_id = :chat_id THEN NULL
                        ELSE leave_chat_id
                    END
                WHERE attendance_chat_id = :chat_id
                   OR leave_chat_id = :chat_id
                """
            ),
            {"chat_id": normalized_chat_id},
        )
        db.execute(
            text(
                """
                DELETE FROM telegram_branch_notification_routes
                WHERE attendance_chat_id IS NULL AND leave_chat_id IS NULL
                """
            )
        )
    except Exception as exc:
        # Safe during rolling upgrades before the optional route table exists.
        logger.warning("Could not clear Telegram branch routes: %s", exc)



async def get_bot_username(bot_token: str) -> str | None:
    """Fetch the bot username from Telegram API."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = res.json()
            if data.get("ok"):
                return data["result"].get("username")
    except Exception:
        pass
    return None


def upsert_group_member(db, member: dict, group_chat_id: int, group_title: str, is_verified: bool = False):
    """Insert or update a Telegram group member record."""
    from sqlalchemy import text
    from datetime import datetime, timezone

    uid = member.get("id")
    if not uid:
        return
    try:
        verified_at_val = "NOW()" if is_verified else "NULL"
        db.execute(text(f"""
            INSERT INTO telegram_group_members
                (telegram_user_id, group_chat_id, first_name, last_name, username,
                 language_code, is_bot, group_title, is_verified, verified_at, joined_at)
            VALUES
                (:uid, :gid, :fn, :ln, :un, :lc, :ib, :gt, :iv, {verified_at_val}, NOW())
            ON DUPLICATE KEY UPDATE
                first_name     = VALUES(first_name),
                last_name      = VALUES(last_name),
                username       = VALUES(username),
                language_code  = VALUES(language_code),
                group_title    = VALUES(group_title),
                is_verified    = GREATEST(is_verified, VALUES(is_verified)),
                verified_at    = CASE WHEN VALUES(is_verified) = 1 AND verified_at IS NULL
                                      THEN {verified_at_val} ELSE verified_at END,
                updated_at     = NOW()
        """), {
            "uid": uid,
            "gid": group_chat_id,
            "fn":  member.get("first_name"),
            "ln":  member.get("last_name"),
            "un":  member.get("username"),
            "lc":  member.get("language_code"),
            "ib":  1 if member.get("is_bot") else 0,
            "gt":  group_title,
            "iv":  1 if is_verified else 0,
        })
        db.commit()
    except Exception as e:
        logger.error(f"Error upserting group member: {e}")


def ensure_telegram_auth_codes_table(db: Session) -> None:
    """Create the auth-code table if a live database missed startup migration."""
    bind = db.get_bind()
    is_mysql = bind.dialect.name == "mysql"
    if is_mysql:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_bot_auth_codes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                code VARCHAR(6) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                used_at DATETIME NULL,
                used_for_chat_id VARCHAR(100) NULL,
                intended_role VARCHAR(50) NOT NULL DEFAULT 'pending',
                INDEX idx_tbac_code (code),
                INDEX idx_tbac_expires_at (expires_at),
                INDEX idx_tbac_used_at (used_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
    else:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_bot_auth_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(6) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                used_at DATETIME NULL,
                used_for_chat_id VARCHAR(100) NULL,
                intended_role VARCHAR(50) NOT NULL DEFAULT 'pending'
            )
        """))
    from sqlalchemy import inspect

    column_names = {
        column["name"]
        for column in inspect(bind).get_columns("telegram_bot_auth_codes")
    }
    if "intended_role" not in column_names:
        db.execute(text("""
            ALTER TABLE telegram_bot_auth_codes
            ADD COLUMN intended_role VARCHAR(50) NOT NULL DEFAULT 'pending'
        """))
    db.commit()


def ensure_telegram_login_sessions_table(db: Session) -> None:
    """Create Telegram login session table if live DB missed startup migration."""
    bind = db.get_bind()
    is_mysql = bind.dialect.name == "mysql"
    if is_mysql:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_login_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                token VARCHAR(96) NOT NULL UNIQUE,
                telegram_user_id BIGINT NULL,
                private_chat_id BIGINT NULL,
                phone VARCHAR(50) NULL,
                first_name VARCHAR(255) NULL,
                last_name VARCHAR(255) NULL,
                username VARCHAR(255) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                verified_at DATETIME NULL,
                consumed_at DATETIME NULL,
                INDEX idx_tls_token (token),
                INDEX idx_tls_telegram_user_id (telegram_user_id),
                INDEX idx_tls_status_expires (status, expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
    else:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_login_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token VARCHAR(96) NOT NULL UNIQUE,
                telegram_user_id BIGINT NULL,
                private_chat_id BIGINT NULL,
                phone VARCHAR(50) NULL,
                first_name VARCHAR(255) NULL,
                last_name VARCHAR(255) NULL,
                username VARCHAR(255) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                verified_at DATETIME NULL,
                consumed_at DATETIME NULL
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_tls_token ON telegram_login_sessions(token)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_tls_telegram_user_id ON telegram_login_sessions(telegram_user_id)"))
    db.commit()


def extract_telegram_login_token(text_value: str | None) -> str | None:
    """Extract app login token from Telegram command text in any supported shape."""
    if not text_value:
        return None
    import re
    match = re.search(r"(login_[A-Za-z0-9_-]{12,96})", text_value.strip())
    token = match.group(1) if match else None
    logger.info(
        "Telegram login token extraction: has_text=%s text_prefix=%r matched=%s",
        bool(text_value),
        text_value.strip()[:120],
        bool(token),
    )
    return token


@router.post("/")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Telegram webhook endpoint for bot updates.
    Automatically captures chat/group IDs when bot is added.
    """
    try:
        body = await request.json()
        logger.info(f"📬 Telegram webhook received!")
        logger.info(f"Webhook data: {json.dumps(body, indent=2)}")

        # Resolve the active bot token from DB settings (not hardcoded)
        active_token = get_active_bot_token(db)
        if not active_token:
            logger.warning("Telegram webhook ignored: no bot token configured")
            return {"ok": False, "error": "No bot token configured"}
        logger.info(f"Using bot token: ...{active_token[-10:]}")

        # Telegram retries updates when a webhook response is interrupted or too
        # slow. Claim the update in the database so only one API worker performs
        # its external side effects (sendMessage, restrictChatMember, etc.).
        update_id = body.get("update_id")
        if update_id is not None and not claim_telegram_webhook_event(
            db,
            event_key=telegram_update_event_key(active_token, update_id),
            event_type="update",
            update_id=update_id,
        ):
            logger.info("Ignoring duplicate Telegram update_id=%s", update_id)
            return {"ok": True, "duplicate": True}

        # Handle different update types
        if any(
            key in body
            for key in (
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
            )
        ):
            message = (
                body.get("message")
                or body.get("edited_message")
                or body.get("channel_post")
                or body.get("edited_channel_post")
                or {}
            )
            is_edited_message = (
                "edited_message" in body or "edited_channel_post" in body
            )
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type")
            chat_title = chat.get("title", "Private Chat")

            logger.info(f"Message in chat: {chat_title} ({chat_id}) - Type: {chat_type}")

            bot_role = "general"
            if chat_type != "private":
                bot_role = get_chat_role(db, str(chat_id))

            # Authorized General Groups can enforce their saved moderation policy.
            # Inspect edits too, preventing a safe message being changed into a
            # blocked link after it originally passed moderation.
            if chat_type != "private" and bot_role == "general":
                moderation_result = await moderate_general_group_message(
                    db,
                    message,
                    active_token,
                )
                if moderation_result.get("handled"):
                    return {
                        "ok": True,
                        "message": (
                            "Edited message moderated"
                            if is_edited_message
                            else "Message moderated"
                        ),
                        "moderation": moderation_result,
                    }
            
            pending_text = message.get("text", "").strip()
            pending_command = pending_text.split()[0] if pending_text else ""
            if "@" in pending_command:
                pending_command = pending_command.split("@")[0]

            if chat_type == "private":
                logger.info(
                    "Telegram private message received: chat_id=%s text=%r command=%r has_contact=%s",
                    chat_id,
                    pending_text,
                    pending_command,
                    bool(message.get("contact")),
                )

            if chat_type == "private":
                login_payload = extract_telegram_login_token(pending_text)
                if login_payload:
                    logger.info(
                        f"Telegram app login token detected before command handling from private chat {chat_id}: {login_payload[:18]}..."
                    )
                    await handle_telegram_login_start(
                        db,
                        chat_id,
                        message,
                        login_payload,
                        active_token,
                    )
                    return {"ok": True, "message": "Telegram login handled"}

            # If role is pending, ignore normal chatter but still allow setup commands.
            if (
                bot_role == "pending"
                and "new_chat_members" not in message
                and "left_chat_member" not in message
                and pending_command not in {
                    "/start",
                    "/login",
                    "/groupid",
                    "/getid",
                    "/id",
                    "/myid",
                    "/help",
                }
            ):
                return {"ok": True, "message": "Role pending, ignoring message"}

            if chat_type == "private" and message.get("contact"):
                handled = await handle_telegram_login_contact(
                    db,
                    chat_id,
                    message,
                    active_token,
                )
                if handled:
                    return {"ok": True}

            # Handle "bot added to group" event
            if "new_chat_members" in message:
                # Delete the "X joined the group" service message
                try:
                    import httpx as _httpx
                    svc_msg_id = message.get("message_id")
                    if svc_msg_id and bot_role == "general":
                        async with _httpx.AsyncClient(timeout=5.0) as _cl:
                            await _cl.post(
                                f"https://api.telegram.org/bot{active_token}/deleteMessage",
                                json={"chat_id": chat_id, "message_id": svc_msg_id}
                            )
                except Exception:
                    pass
                logger.info(f"New chat members detected!")
                new_members = message["new_chat_members"]
                for member in new_members:
                    member_username = member.get("username", "")
                    is_bot = member.get("is_bot", False)
                    logger.info(f"New member: @{member_username} (is_bot={is_bot})")
                    
                    is_this_bot = (
                        is_bot
                        and str(member.get("id"))
                        == active_token.split(":", 1)[0]
                    )
                    if is_this_bot:
                        # Our bot was added to a group!
                        logger.info(f"✅ BOT @{member_username} added to {chat_type}: {chat_title} (ID: {chat_id})")

                        if not claim_telegram_webhook_event(
                            db,
                            event_key=telegram_membership_event_key(
                                active_token,
                                "bot_join",
                                chat_id,
                                member.get("id"),
                            ),
                            event_type="bot_join",
                            update_id=update_id,
                            chat_id=chat_id,
                            telegram_user_id=member.get("id"),
                            cooldown_seconds=300,
                        ):
                            logger.info(
                                "Skipping duplicate bot-join event in chat %s",
                                chat_id,
                            )
                            continue

                        # Store the chat ID with auth_pending role
                        stored = await store_chat_id(
                            db,
                            chat_id=str(chat_id),
                            chat_title=chat_title,
                            chat_type=chat_type,
                            bot_token=active_token,
                        )
                        # Set role to auth_pending — must provide OTP before activation
                        set_chat_role(db, str(chat_id), "auth_pending")
                        logger.info(f"Chat stored with auth_pending role: {stored}")

                        # Prompt for authorization code
                        await send_bot_authorization_prompt(
                            chat_id,
                            bot_token=active_token,
                        )
                        logger.info("Authorization prompt sent")
                    
                    elif not is_bot and bot_role == "general":
                        if not claim_telegram_webhook_event(
                            db,
                            event_key=telegram_membership_event_key(
                                active_token,
                                "join",
                                chat_id,
                                member.get("id"),
                            ),
                            event_type="member_join",
                            update_id=update_id,
                            chat_id=chat_id,
                            telegram_user_id=member.get("id"),
                            cooldown_seconds=30,
                        ):
                            logger.info(
                                "Skipping overlapping member-join event for %s in %s",
                                member.get("id"),
                                chat_id,
                            )
                            continue
                        verification_enabled = get_member_verification_enabled(
                            db,
                            chat_id,
                        )
                        if verification_enabled:
                            try:
                                restrict_url = f"https://api.telegram.org/bot{active_token}/restrictChatMember"
                                restrict_payload = {
                                    "chat_id": chat_id,
                                    "user_id": member.get("id"),
                                    "permissions": member_chat_permissions(
                                        can_chat=False
                                    ),
                                    "use_independent_chat_permissions": True,
                                }
                                import httpx
                                async with httpx.AsyncClient(timeout=5.0) as client:
                                    res = await client.post(
                                        restrict_url,
                                        json=restrict_payload,
                                    )
                                    logger.info(
                                        "Restricted new member %s pending "
                                        "verification. Response: %s",
                                        member.get("id"),
                                        res.text,
                                    )
                            except Exception as e:
                                logger.error(f"Error restricting user: {e}")

                        # Record member in database
                        upsert_group_member(
                            db,
                            member,
                            chat_id,
                            chat_title,
                            is_verified=not verification_enabled,
                        )
                        logger.info(f"Member {member.get('id')} recorded in DB")

                        # Human user joined - send welcome message only in general groups
                        await send_member_welcome_message(
                            db,
                            chat_id,
                            chat_title,
                            member,
                            bot_token=active_token,
                            group_chat_id=chat_id,
                            verification_enabled=verification_enabled,
                        )
                        logger.info(f"Member welcome sent to @{member_username}")

            # Handle commands / auth code input
            if message.get("text"):
                text_input = message.get("text", "").strip()

                # ── AUTH CODE CHECK (before any other command) ──────────────
                # If group is waiting for authorization, handle OTP & 15-min auto-leave
                if bot_role == "auth_pending" and chat_type != "private":
                    import httpx as _hx_auth
                    from datetime import datetime, timedelta

                    try:
                        ensure_telegram_auth_codes_table(db)
                        # ── 15-minute auto-leave check (naive local time) ────
                        added_row = db.execute(text("""
                            SELECT added_at FROM telegram_tracked_chats
                            WHERE chat_id = :cid AND is_active = TRUE
                            LIMIT 1
                        """), {"cid": str(chat_id)}).fetchone()

                        if added_row and added_row[0]:
                            added_at = added_row[0]  # naive local datetime from DB
                            elapsed = datetime.now() - added_at  # both naive local
                            if elapsed > timedelta(minutes=15):
                                logger.info(f"Group {chat_id}: 15-min timeout, leaving...")
                                async with _hx_auth.AsyncClient(timeout=5.0) as _cl:
                                    await _cl.post(
                                        f"https://api.telegram.org/bot{active_token}/sendMessage",
                                        json={
                                            "chat_id": chat_id,
                                            "text": telegram_status_card(
                                                "⏳",
                                                "Authorization expired",
                                                message=(
                                                    "No valid code was entered within "
                                                    "15 minutes, so the bot will now "
                                                    "leave this chat."
                                                ),
                                                action_title="Connect again",
                                                steps=(
                                                    "Remove the bot from this chat.",
                                                    "Choose the group type in the PAMA app.",
                                                    "Add the bot again and send the new 6-digit code.",
                                                ),
                                            ),
                                            "parse_mode": "HTML",
                                        }
                                    )
                                    await _cl.post(
                                        f"https://api.telegram.org/bot{active_token}/leaveChat",
                                        json={"chat_id": chat_id}
                                    )
                                db.execute(text("""
                                    UPDATE telegram_tracked_chats
                                    SET is_active = FALSE, updated_at = NOW()
                                    WHERE chat_id = :cid
                                """), {"cid": str(chat_id)})
                                db.commit()
                                return {"ok": True}

                        # ── Extract code: accept plain "123456" OR "/auth 123456" ──
                        # Privacy Mode must be OFF in BotFather for plain text to arrive.
                        # Strip /auth prefix if used, then extract the digits.
                        raw = text_input.strip()
                        # Handle /auth CODE or /auth@bot CODE
                        if raw.lower().startswith("/auth"):
                            parts = raw.split(None, 1)
                            entered_code = parts[1].strip() if len(parts) > 1 else ""
                        else:
                            entered_code = raw  # plain text e.g. "483599"

                        if not entered_code.isdigit() or len(entered_code) != 6:
                            # Not a 6-digit code — remind how to authorize
                            async with _hx_auth.AsyncClient(timeout=5.0) as _cl:
                                await _cl.post(
                                    f"https://api.telegram.org/bot{active_token}/sendMessage",
                                    json={
                                        "chat_id": chat_id,
                                        "text": telegram_status_card(
                                            "🔐",
                                            "Authorization required",
                                            message=(
                                                "This chat needs the 6-digit code "
                                                "generated for it in the PAMA app."
                                            ),
                                            action_title="Authorize this chat",
                                            steps=(
                                                "Open Telegram Setup in the PAMA app.",
                                                "Choose General Group or Notification Only.",
                                                "Generate a code and send the 6 digits here.",
                                            ),
                                            note=(
                                                "The code expires after 3 minutes and "
                                                "can be used only once."
                                            ),
                                        ),
                                        "parse_mode": "HTML",
                                    }
                                )
                        else:
                            # Validate against DB
                            valid_code = db.execute(text("""
                                SELECT id, intended_role
                                FROM telegram_bot_auth_codes
                                WHERE code = :code
                                  AND used_at IS NULL
                                  AND expires_at > NOW()
                                LIMIT 1
                            """), {"code": entered_code}).fetchone()

                            if valid_code:
                                consume_result = db.execute(text("""
                                    UPDATE telegram_bot_auth_codes
                                    SET used_at = NOW(), used_for_chat_id = :cid
                                    WHERE id = :id
                                      AND used_at IS NULL
                                      AND expires_at > NOW()
                                """), {"cid": str(chat_id), "id": valid_code[0]})
                                if consume_result.rowcount == 1:
                                    db.commit()
                                else:
                                    # Another worker/group consumed this one-time
                                    # code between SELECT and UPDATE.
                                    db.rollback()
                                    valid_code = None

                            if valid_code:
                                assigned_role = resolve_authorized_chat_role(
                                    valid_code[1]
                                )
                                if not set_chat_role(
                                    db,
                                    str(chat_id),
                                    assigned_role,
                                ):
                                    raise RuntimeError(
                                        "Could not apply the app-selected Telegram role"
                                    )

                                enabled_reply_features = None
                                if assigned_role == "general":
                                    reply_settings = get_group_reply_settings(
                                        db,
                                        str(chat_id),
                                    )
                                    enabled_reply_features = {
                                        feature["key"]
                                        for feature in reply_settings["features"]
                                        if reply_settings["enabled"]
                                        and feature["enabled"]
                                    }
                                await sync_chat_command_menu(
                                    chat_id,
                                    assigned_role,
                                    bot_token=active_token,
                                    enabled_reply_features=enabled_reply_features,
                                )
                                if assigned_role == "general":
                                    await ensure_moderation_webhook_updates(
                                        active_token
                                    )

                                if assigned_role in APP_ASSIGNABLE_TELEGRAM_ROLES:
                                    success_text = telegram_status_card(
                                        "✅",
                                        "Setup complete",
                                        message=(
                                            "The bot is connected and ready to use "
                                            "in this chat."
                                        ),
                                        fields=((
                                            "👥",
                                            "Group type",
                                            telegram_role_label(assigned_role),
                                        ),),
                                        action_title="Manage settings",
                                        action=(
                                            "Use Telegram Setup in the PAMA app for "
                                            "future changes."
                                        ),
                                    )
                                else:
                                    success_text = telegram_status_card(
                                        "✅",
                                        "Authorization successful",
                                        message=(
                                            "The bot is connected, but this chat still "
                                            "needs a group type."
                                        ),
                                        action_title="Finish setup",
                                        action=(
                                            "Open Telegram Setup in the PAMA app and "
                                            "assign this chat as General Group or "
                                            "Notification Only."
                                        ),
                                    )
                                async with _hx_auth.AsyncClient(timeout=5.0) as _cl:
                                    auth_message_id = message.get("message_id")
                                    if auth_message_id:
                                        try:
                                            await _cl.post(
                                                f"https://api.telegram.org/bot{active_token}/deleteMessage",
                                                json={
                                                    "chat_id": chat_id,
                                                    "message_id": auth_message_id,
                                                },
                                            )
                                        except Exception:
                                            logger.debug(
                                                "Could not remove used Telegram auth code message",
                                                exc_info=True,
                                            )
                                    await _cl.post(
                                        f"https://api.telegram.org/bot{active_token}/sendMessage",
                                        json={
                                            "chat_id": chat_id,
                                            "text": success_text,
                                            "parse_mode": "HTML",
                                        }
                                    )
                                logger.info(
                                    "Group %s authorized via OTP with app role %s",
                                    chat_id,
                                    assigned_role,
                                )
                            else:
                                async with _hx_auth.AsyncClient(timeout=5.0) as _cl:
                                    await _cl.post(
                                        f"https://api.telegram.org/bot{active_token}/sendMessage",
                                        json={
                                            "chat_id": chat_id,
                                            "text": telegram_status_card(
                                                "❌",
                                                "Code not accepted",
                                                message=(
                                                    "This code is incorrect, expired, or "
                                                    "has already been used."
                                                ),
                                                action_title="Try a new code",
                                                action=(
                                                    "Generate a new code for this group "
                                                    "type in the PAMA app, then send it here."
                                                ),
                                                note=(
                                                    "Codes expire after 3 minutes and can "
                                                    "be used only once."
                                                ),
                                            ),
                                            "parse_mode": "HTML",
                                        }
                                    )
                                logger.info(f"Wrong auth code in group {chat_id}: {entered_code}")
                    except Exception as _auth_err:
                        logger.error(f"Auth pending handler error: {_auth_err}")
                        try:
                            async with _hx_auth.AsyncClient(timeout=5.0) as _cl:
                                await _cl.post(
                                    f"https://api.telegram.org/bot{active_token}/sendMessage",
                                    json={
                                        "chat_id": chat_id,
                                        "text": telegram_status_card(
                                            "⚠️",
                                            "Authorization unavailable",
                                            message=(
                                                "The bot could not check the code right now."
                                            ),
                                            action_title="Try again",
                                            action=(
                                                "Wait a moment, then send a newly generated "
                                                "code from the PAMA app."
                                            ),
                                        ),
                                        "parse_mode": "HTML",
                                    }
                                )
                        except Exception:
                            pass
                    return {"ok": True}
                # ── END AUTH CODE CHECK ─────────────────────────────────────
                # ── END AUTH CODE CHECK (old duplicate removed) ─────────────

                cmd_text = text_input
                if chat_type == "private":
                    login_payload = extract_telegram_login_token(cmd_text)
                    if login_payload:
                        logger.info(
                            f"Telegram app login token received from private chat {chat_id}"
                        )
                        await handle_telegram_login_start(
                            db,
                            chat_id,
                            message,
                            login_payload,
                            active_token,
                        )
                        return {"ok": True}

                # Remove bot username from command if present (e.g., /getid@PAMAISNotify_Bot -> /getid)
                if " " in cmd_text:
                    command = cmd_text.split()[0]  # Get first word
                else:
                    command = cmd_text

                # Remove @botname suffix
                if "@" in command:
                    command = command.split("@")[0]

                group_reply_feature = None
                reply_settings = None
                if chat_type == "private":
                    group_reply_feature = match_default_group_reply_feature(
                        text_input
                    )
                elif bot_role == "general":
                    try:
                        reply_settings = get_group_reply_settings(
                            db,
                            str(chat_id),
                        )
                    except Exception:
                        logger.exception(
                            "Could not load Telegram auto replies for chat %s; "
                            "using defaults",
                            chat_id,
                        )
                        reply_settings = default_group_reply_settings(str(chat_id))
                    group_reply_feature = match_group_reply_feature(
                        text_input,
                        reply_settings,
                    )

                public_info_kind = (
                    group_reply_feature.get("key")
                    if group_reply_feature
                    else None
                )

                # Only support these commands for now
                if command == "/start":
                    # Check for verify deep link payload: /start verify_{user_id}_{group_id}
                    full_text = message.get("text", "").strip()
                    start_param = full_text[len("/start"):].strip() if full_text.startswith("/start") else ""
                    # Handle @botname suffix in start param
                    if " " in start_param:
                        start_param = start_param.split(" ", 1)[1].strip()
                    
                    if start_param.startswith("verify_") and chat_type == "private":
                        await handle_verify_via_private(
                            db, chat_id, message, start_param, active_token
                        )
                    else:
                        await handle_start_command(
                            db,
                            chat_id,
                            chat_type,
                            chat_title,
                            bot_token=active_token,
                            message_obj=message,
                        )
                elif command in {"/myid", "/id"}:
                    await handle_myid_command(chat_id, message, bot_token=active_token)
                elif command in {"/groupid", "/getid"}:
                    await handle_groupid_command(db, chat_id, message, bot_token=active_token)
                elif command == "/login":
                    await handle_login_command(chat_id, bot_token=active_token)
                elif command == "/help":
                    enabled_reply_features = None
                    if reply_settings is not None:
                        enabled_reply_features = {
                            feature["key"]
                            for feature in reply_settings["features"]
                            if reply_settings["enabled"] and feature["enabled"]
                        }
                    await handle_help_command(
                        chat_id,
                        chat_type,
                        bot_token=active_token,
                        enabled_reply_features=enabled_reply_features,
                        chat_role=bot_role,
                    )
                elif public_info_kind and (
                    chat_type == "private" or bot_role == "general"
                ):
                    await handle_public_school_info_command(
                        db,
                        chat_id,
                        public_info_kind,
                        bot_token=active_token,
                        custom_reply_text=(
                            group_reply_feature.get("reply_text") or None
                        ),
                    )
                elif command in ["/stats", "/report", "/analytics", "/late", "/top"]:
                    # Admin commands: ONLY in notification_only groups
                    if bot_role == "notification_only" and chat_type != "private":
                        if command == "/stats":
                            await handle_stats_command(db, chat_id, bot_token=active_token)
                        elif command == "/report":
                            await handle_report_command(db, chat_id, bot_token=active_token)
                        elif command == "/analytics":
                            await handle_analytics_command(db, chat_id, bot_token=active_token)
                        elif command == "/late":
                            await handle_late_command(db, chat_id, bot_token=active_token)
                        elif command == "/top":
                            await handle_top_command(db, chat_id, bot_token=active_token)
                    else:
                        logger.info(f"Admin command {command} ignored in {bot_role} group")
                elif chat_type == "private":
                    # Provide a friendly response to text in 1-to-1 chats
                    await handle_unknown_message(chat_id, bot_token=active_token)

            # Handle member leaving
            if "left_chat_member" in message and bot_role == "general":
                # Delete the "X left the group" service message
                try:
                    import httpx as _httpx_l
                    svc_left_msg_id = message.get("message_id")
                    if svc_left_msg_id:
                        async with _httpx_l.AsyncClient(timeout=5.0) as _cl_l:
                            await _cl_l.post(
                                f"https://api.telegram.org/bot{active_token}/deleteMessage",
                                json={"chat_id": chat_id, "message_id": svc_left_msg_id}
                            )
                except Exception:
                    pass
                left_member = message["left_chat_member"]
                if not left_member.get("is_bot", False):
                    if not claim_telegram_webhook_event(
                        db,
                        event_key=telegram_membership_event_key(
                            active_token,
                            "leave",
                            chat_id,
                            left_member.get("id"),
                        ),
                        event_type="member_leave",
                        update_id=update_id,
                        chat_id=chat_id,
                        telegram_user_id=left_member.get("id"),
                        cooldown_seconds=30,
                    ):
                        logger.info(
                            "Skipping overlapping member-leave event for %s in %s",
                            left_member.get("id"),
                            chat_id,
                        )
                        return {"ok": True, "duplicate_membership": True}
                    await send_member_goodbye_message(
                        chat_id,
                        chat_title,
                        left_member,
                        bot_token=active_token,
                    )
                    logger.info(f"Member goodbye sent for @{left_member.get('username', 'user')}")

        # Handle regular member status updates (User joins or leaves silently)
        if "chat_member" in body:
            chat_member_update = body["chat_member"]
            chat = chat_member_update.get("chat", {})
            cm_chat_id = chat.get("id")
            cm_chat_title = chat.get("title", "Private Chat")
            cm_chat_type = chat.get("type")
            
            # Find the bot_role for this group
            cm_bot_role = "general"
            if cm_chat_type != "private":
                cm_bot_role = get_chat_role(db, str(cm_chat_id))

            new_member = chat_member_update.get("new_chat_member", {})
            old_member = chat_member_update.get("old_chat_member", {})
            status = new_member.get("status")
            user = new_member.get("user", {})
            is_bot = user.get("is_bot", False)
            user_id = user.get("id")
            
            if status == "member" and old_member.get("status") in ["left", "kicked"]:
                logger.info(f"User {user_id} joined group {cm_chat_id} via chat_member update")
                if cm_bot_role == "general" and not is_bot:
                    if not claim_telegram_webhook_event(
                        db,
                        event_key=telegram_membership_event_key(
                            active_token,
                            "join",
                            cm_chat_id,
                            user_id,
                        ),
                        event_type="member_join",
                        update_id=update_id,
                        chat_id=cm_chat_id,
                        telegram_user_id=user_id,
                        cooldown_seconds=30,
                    ):
                        logger.info(
                            "Skipping overlapping chat_member join for %s in %s",
                            user_id,
                            cm_chat_id,
                        )
                        return {"ok": True, "duplicate_membership": True}
                    verification_enabled = get_member_verification_enabled(
                        db,
                        cm_chat_id,
                    )
                    if verification_enabled:
                        try:
                            restrict_url = f"https://api.telegram.org/bot{active_token}/restrictChatMember"
                            restrict_payload = {
                                "chat_id": cm_chat_id,
                                "user_id": user_id,
                                "permissions": member_chat_permissions(
                                    can_chat=False
                                ),
                                "use_independent_chat_permissions": True,
                            }
                            import httpx
                            async with httpx.AsyncClient(timeout=5.0) as client:
                                res = await client.post(
                                    restrict_url,
                                    json=restrict_payload,
                                )
                                logger.info(
                                    "Restricted new member %s pending "
                                    "verification. Response: %s",
                                    user_id,
                                    res.text,
                                )
                        except Exception as e:
                            logger.error(f"Error restricting user: {e}")

                    upsert_group_member(
                        db,
                        user,
                        cm_chat_id,
                        cm_chat_title,
                        is_verified=not verification_enabled,
                    )
                    logger.info(f"Member {user_id} recorded in DB via chat_member")

                    await send_member_welcome_message(
                        db,
                        cm_chat_id,
                        cm_chat_title,
                        user,
                        bot_token=active_token,
                        group_chat_id=cm_chat_id,
                        verification_enabled=verification_enabled,
                    )
            elif status == "left":
                logger.info(f"User {user_id} left group {cm_chat_id} via chat_member update")
                if cm_bot_role == "general" and not is_bot:
                    if not claim_telegram_webhook_event(
                        db,
                        event_key=telegram_membership_event_key(
                            active_token,
                            "leave",
                            cm_chat_id,
                            user_id,
                        ),
                        event_type="member_leave",
                        update_id=update_id,
                        chat_id=cm_chat_id,
                        telegram_user_id=user_id,
                        cooldown_seconds=30,
                    ):
                        logger.info(
                            "Skipping overlapping chat_member leave for %s in %s",
                            user_id,
                            cm_chat_id,
                        )
                        return {"ok": True, "duplicate_membership": True}
                    await send_member_goodbye_message(
                        cm_chat_id,
                        cm_chat_title,
                        user,
                        bot_token=active_token,
                    )

        # Handle group status updates (left, kicked, etc.)
        if "my_chat_member" in body:
            chat_member_update = body["my_chat_member"]
            chat = chat_member_update.get("chat", {})
            chat_id = chat.get("id")
            chat_title = chat.get("title") or chat.get("username") or "Private Chat"
            chat_type = chat.get("type")
            old_status = chat_member_update.get("old_chat_member", {}).get("status")
            new_status = chat_member_update.get("new_chat_member", {}).get("status")

            if (
                chat_type != "private"
                and new_status in {"member", "administrator"}
                and old_status in {None, "left", "kicked"}
            ):
                logger.info(f"Bot added/enabled in chat: {chat_title} ({chat_id})")
                bot_user_id = (
                    chat_member_update.get("new_chat_member", {})
                    .get("user", {})
                    .get("id")
                    or active_token.split(":", 1)[0]
                )
                if not claim_telegram_webhook_event(
                    db,
                    event_key=telegram_membership_event_key(
                        active_token,
                        "bot_join",
                        chat_id,
                        bot_user_id,
                    ),
                    event_type="bot_join",
                    update_id=update_id,
                    chat_id=chat_id,
                    telegram_user_id=bot_user_id,
                    cooldown_seconds=300,
                ):
                    logger.info(
                        "Skipping overlapping my_chat_member bot join in %s",
                        chat_id,
                    )
                    return {"ok": True, "duplicate_membership": True}
                stored = await store_chat_id(
                    db,
                    chat_id=str(chat_id),
                    chat_title=chat_title,
                    chat_type=chat_type,
                    bot_token=active_token,
                )
                set_chat_role(db, str(chat_id), "auth_pending")
                logger.info(f"Chat stored from my_chat_member with auth_pending role: {stored}")
                await send_bot_authorization_prompt(
                    chat_id,
                    bot_token=active_token,
                )
            elif new_status == "left":
                logger.info(f"Bot left group: {chat_id}")
                await mark_chat_inactive(db, str(chat_id))
            elif new_status == "kicked":
                logger.info(f"Bot kicked from group: {chat_id}")
                await mark_chat_inactive(db, str(chat_id))

        # Handle button clicks (callback queries)
        if "callback_query" in body:
            import httpx

            callback = body["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback.get("data", "")
            message_id = callback["message"]["message_id"]
            
            if data == "cmd_help":
                await handle_help_command(chat_id, "private", bot_token=active_token)
            elif data == "cmd_stats":
                await handle_stats_command(db, chat_id, bot_token=active_token)
            elif data == "cmd_report":
                await handle_report_command(db, chat_id, bot_token=active_token)
            elif data == "cmd_analytics":
                await handle_analytics_command(db, chat_id, bot_token=active_token)
            elif data in {"set_role_notification", "set_role_general"}:
                # Old setup messages may still contain these buttons. Remove
                # them, but never allow Telegram to change a chat's role.
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"https://api.telegram.org/bot{active_token}/editMessageReplyMarkup",
                        json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": {"inline_keyboard": []},
                        },
                    )
                    await client.post(
                        f"https://api.telegram.org/bot{active_token}/answerCallbackQuery",
                        json={
                            "callback_query_id": callback["id"],
                            "text": (
                                "⚙️ Group type is managed in the PAMA app. "
                                "Generate the correct setup code there."
                            ),
                            "show_alert": True,
                        },
                    )
                return {"ok": True, "role_selection": "app_only"}
            elif data.startswith("verify_"):
                target_user_id = int(data.split("_")[1])
                clicker_user_id = callback["from"]["id"]
                
                if clicker_user_id == target_user_id:
                    # Unlock
                    restrict_url = f"https://api.telegram.org/bot{active_token}/restrictChatMember"
                    restrict_payload = {
                        "chat_id": chat_id,
                        "user_id": target_user_id,
                        "permissions": {
                            "can_send_messages": True,
                            "can_send_audios": True,
                            "can_send_documents": True,
                            "can_send_photos": True,
                            "can_send_videos": True,
                            "can_send_video_notes": True,
                            "can_send_voice_notes": True,
                            "can_send_polls": True,
                            "can_send_other_messages": True,
                            "can_add_web_page_previews": True,
                            "can_invite_users": True
                        },
                        "use_independent_chat_permissions": False
                    }
                    import httpx
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        res = await client.post(restrict_url, json=restrict_payload)
                        logger.info(f"Unlock response: {res.text}")

                    try:
                        unlock_ok = bool(res.json().get("ok"))
                    except Exception:
                        unlock_ok = False
                    if not unlock_ok:
                        answer_url = (
                            f"https://api.telegram.org/bot{active_token}/"
                            "answerCallbackQuery"
                        )
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            await client.post(
                                answer_url,
                                json={
                                    "callback_query_id": callback["id"],
                                    "text": (
                                        "⚠️ Verification could not unlock the chat. "
                                        "Ask an admin to check the bot's permissions."
                                    ),
                                    "show_alert": True,
                                },
                            )
                        return {"ok": True, "verified": False}
                    
                    # Update database to mark as verified
                    try:
                        db.execute(text("""
                            UPDATE telegram_group_members 
                            SET is_verified = 1, verified_at = NOW(), updated_at = NOW() 
                            WHERE telegram_user_id = :uid AND group_chat_id = :gid
                        """), {"uid": target_user_id, "gid": chat_id})
                        db.commit()
                        logger.info(f"User {target_user_id} successfully marked as verified in DB")
                    except Exception as e:
                        logger.error(f"Error marking user as verified: {e}")

                    # Remove the verify button by replacing it with just the download links
                    edit_url = f"https://api.telegram.org/bot{active_token}/editMessageReplyMarkup"
                    new_markup = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "📥 Download the School App",
                                    "url": "https://pamais.duckdns.org/app/download",
                                }
                            ]
                        ]
                    }
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        res_edit = await client.post(edit_url, json={"chat_id": chat_id, "message_id": message_id, "reply_markup": new_markup})
                        logger.info(f"Edit message response: {res_edit.text}")
                        
                    # Show success
                    answer_url = f"https://api.telegram.org/bot{active_token}/answerCallbackQuery"
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(
                            answer_url,
                            json={
                                "callback_query_id": callback["id"],
                                "text": (
                                    "✅ Verification complete. Return to the "
                                    "group and start chatting."
                                ),
                                "show_alert": True,
                            },
                        )
                else:
                    # Wrong user
                    answer_url = f"https://api.telegram.org/bot{active_token}/answerCallbackQuery"
                    import httpx
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(
                            answer_url,
                            json={
                                "callback_query_id": callback["id"],
                                "text": (
                                    "🔐 This Verify button belongs to the new "
                                    "member named in the welcome message."
                                ),
                                "show_alert": True,
                            },
                        )
                
                return {"ok": True}
            
            # Acknowledge the callback using the active bot token
            if active_token:
                url = f"https://api.telegram.org/bot{active_token}/answerCallbackQuery"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(url, json={"callback_query_id": callback["id"]})

        return {"ok": True}

    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        return {"ok": False, "error": str(e)}


async def store_chat_id(
    db: Session,
    chat_id: str,
    chat_title: str,
    chat_type: str,
    bot_token: str | None = None,
):
    """Store chat ID in database when bot is added to a group."""
    try:
        from sqlalchemy import text

        # Insert/update the chat record, associating it with the bot token
        db.execute(text("""
            INSERT INTO telegram_tracked_chats (
                chat_id, chat_title, chat_type, bot_role, bot_token,
                member_verification_enabled
            )
            VALUES (
                :chat_id, :chat_title, :chat_type, 'pending', :bot_token, FALSE
            )
            ON DUPLICATE KEY UPDATE
                chat_title = VALUES(chat_title),
                chat_type = VALUES(chat_type),
                bot_token = VALUES(bot_token),
                is_active = TRUE,
                added_at = NOW(),
                updated_at = CURRENT_TIMESTAMP
        """), {
            "chat_id": chat_id,
            "chat_title": chat_title,
            "chat_type": chat_type,
            "bot_token": bot_token,
        })

        db.commit()
        logger.info(f"Stored chat: {chat_title} ({chat_id}) for token ...{bot_token[-10:]}")

        # Also update the main settings if this is the first chat
        settings = db.query(TelegramAttendanceSettings).first()
        if not settings:
            db.execute(text("""
                INSERT INTO telegram_attendance_settings (bot_token, chat_id, enabled)
                VALUES (:bot_token, :chat_id, FALSE)
            """), {
                "bot_token": bot_token,
                "chat_id": chat_id,
            })
            db.commit()
            logger.info(f"Created default settings with chat: {chat_id}")

        return True

    except Exception as e:
        logger.error(f"Error storing chat ID: {e}")
        db.rollback()
        return False


async def send_bot_authorization_prompt(chat_id: int, bot_token: str | None = None):
    """Ask an admin to authorize the bot after it is added to a group/channel."""
    if not bot_token:
        return

    import httpx

    auth_msg = telegram_status_card(
        "🔐",
        "Authorization required",
        message=(
            "Choose this chat's purpose in the PAMA app before using the bot."
        ),
        action_title="Connect this chat",
        steps=(
            "Open Telegram Setup in the PAMA app.",
            "Choose General Group or Notification Only.",
            "Tap Add, then generate the 6-digit authorization code.",
            "Send that code in this chat.",
        ),
        note=(
            "The code expires after 3 minutes. The bot leaves this chat if setup "
            "is not completed within 15 minutes."
        ),
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": auth_msg, "parse_mode": "HTML"},
            )
    except Exception as e:
        logger.error(f"Error sending bot authorization prompt: {e}")


def get_chat_role(db: Session, chat_id: str) -> str:
    """Get the current role of the bot in the specified chat."""
    from sqlalchemy import text
    try:
        result = db.execute(text(
            "SELECT bot_role FROM telegram_tracked_chats WHERE chat_id = :chat_id AND is_active = TRUE"
        ), {"chat_id": chat_id}).fetchone()
        
        if result:
            return result[0]
        return "pending" # default if not found
    except Exception as e:
        logger.error(f"Error getting chat role: {e}")
        return "general" # fallback to general on error

def set_chat_role(db: Session, chat_id: str, bot_role: str) -> bool:
    """Set the role of the bot in the specified chat."""
    from sqlalchemy import text
    try:
        db.execute(text(
            "UPDATE telegram_tracked_chats SET bot_role = :bot_role WHERE chat_id = :chat_id"
        ), {"bot_role": bot_role, "chat_id": chat_id})
        if bot_role != "notification_only":
            _clear_notification_destination_references(db, chat_id)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting chat role: {e}")
        db.rollback()
        return False


def _telegram_commands_for_role(
    role: str,
    enabled_reply_features: set[str] | None = None,
) -> list[dict[str, str]]:
    if role == "notification_only":
        return [
            {"command": "myid", "description": "Get your personal Telegram ID"},
            {"command": "groupid", "description": "Get this group's ID"},
            {"command": "help", "description": "Show help message"},
            {"command": "stats", "description": "Today's attendance summary"},
            {"command": "report", "description": "Daily attendance report"},
            {"command": "analytics", "description": "Monthly analytics"},
            {"command": "late", "description": "Late arrivals today"},
            {"command": "top", "description": "Top 10 performers today"},
        ]
    if role == "general":
        enabled = (
            {"location", "phone", "school", "app"}
            if enabled_reply_features is None
            else enabled_reply_features
        )
        commands = [
            {"command": "myid", "description": "Get your personal Telegram ID"},
            {"command": "groupid", "description": "Get this group's ID"},
            {"command": "help", "description": "Show help message"},
        ]
        if "location" in enabled:
            commands.extend(
                [
                    {
                        "command": "location",
                        "description": "School locations and maps",
                    },
                    {
                        "command": "address",
                        "description": "School branch addresses",
                    },
                ]
            )
        if "phone" in enabled:
            commands.append(
                {"command": "phone", "description": "School contact numbers"}
            )
        if "school" in enabled:
            commands.append(
                {"command": "school", "description": "Public school information"}
            )
        if "app" in enabled:
            commands.append(
                {"command": "app", "description": "Download the official school app"}
            )
        return commands
    return []


async def sync_chat_command_menu(
    chat_id: int | str,
    role: str,
    bot_token: str | None = None,
    enabled_reply_features: set[str] | None = None,
) -> None:
    """Synchronize Telegram's slash-command menu after a role change."""
    import httpx

    if not bot_token:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setMyCommands",
                json={
                    "scope": {"type": "chat", "chat_id": chat_id},
                    "commands": _telegram_commands_for_role(
                        role,
                        enabled_reply_features,
                    ),
                },
            )
            if not response.is_success:
                logger.warning(
                    "Failed to sync Telegram command menu for chat %s: %s",
                    chat_id,
                    response.text[:500],
                )
    except Exception as e:
        logger.warning("Failed to sync Telegram command menu for chat %s: %s", chat_id, e)


async def send_member_welcome_message(
    db: Session,
    chat_id: int,
    chat_title: str,
    new_member: dict,
    bot_token: str | None = None,
    group_chat_id: int | None = None,
    verification_enabled: bool = False,
):
    """Welcome a member and optionally require them to unlock group chat."""
    import httpx
    from sqlalchemy import text

    try:
        user_id = new_member.get("id")
        username = new_member.get("username")
        first_name = new_member.get("first_name", "User")
        
        # Build user mention
        if username:
            user_mention = f"@{safe_telegram_html(username, 'member', limit=64)}"
        else:
            user_mention = (
                f"<b>{safe_telegram_html(first_name, 'Member', limit=100)}</b>"
            )
            
        # 1. Query Branches
        branch_res = db.execute(text("""
            SELECT id, COALESCE(app_display_name, branch_name) as name, 
                   app_branch_google_map_url, map_latitude, map_longitude
            FROM branch
            ORDER BY id
        """)).fetchall()

        # 2. Query Contacts
        contacts_res = db.execute(text("""
            SELECT branch_id, label, value 
            FROM branch_contacts 
            ORDER BY branch_id, sort_order
        """)).fetchall()

        # Group contacts by branch_id
        from collections import defaultdict
        contacts_by_branch = defaultdict(list)
        for c in contacts_res:
            val = c[2].strip()
            # Basic phone validation if it looks like phone numbers
            if val and not val.lower().startswith('http'):
                contacts_by_branch[c[0]].append(val)

        # 3. Build Branches Text
        branch_sections = []
        for b in branch_res:
            b_id = b[0]
            b_name = b[1]
            b_map_url = b[2]
            b_lat = b[3]
            b_lng = b[4]
            
            branch_lines = [
                f"📍 <b>{safe_telegram_html(b_name, 'Campus', limit=120)}</b>"
            ]
            
            # Contacts
            b_contacts = contacts_by_branch.get(b_id, [])
            if b_contacts:
                safe_contacts = " • ".join(
                    safe_telegram_html(contact, limit=60)
                    for contact in b_contacts[:4]
                )
                branch_lines.append(f"📞 {safe_contacts}")
            
            # Map Link
            map_link = ""
            if b_map_url and str(b_map_url).strip():
                map_link = str(b_map_url).strip()
                if not map_link.startswith('http'):
                    map_link = 'https://' + map_link
            elif b_lat is not None and b_lng is not None:
                map_link = f"https://www.google.com/maps/search/?api=1&query={b_lat},{b_lng}"
                
            if map_link:
                branch_lines.append(
                    "🗺️ "
                    f'<a href="{html.escape(map_link, quote=True)}">'
                    "Open in Google Maps</a>"
                )

            branch_sections.append("\n".join(branch_lines))

        branches_text = (
            "\n\n".join(branch_sections)
            if branch_sections
            else "Campus information is available in the PAMA app."
        )

        access_text = (
            "🔐 <b>One step before you chat</b>\n"
            "Tap <b>Verify & Unlock Chat</b> below. Only the new member can "
            "complete this step."
            if verification_enabled
            else "✅ <b>You're ready to chat</b>\n"
            "No member verification is required in this group."
        )

        # 4. Construct Final Message
        message = f"""👋 <b>Welcome to {safe_telegram_html(chat_title, 'the group', limit=150)}</b>

👤 <b>New member:</b> {user_mention}

{access_text}

🏫 <b>School campuses</b>
{branches_text}

📱 <i>Use the PAMA app for attendance, permissions, school updates, marks, and results.</i>"""

        # 5. Add verification only when this General Group requires it.
        keyboard_rows = []
        if verification_enabled:
            bot_username = await get_bot_username(bot_token) if bot_token else None
            group_id_for_link = group_chat_id if group_chat_id else chat_id
            if bot_username:
                verify_url = (
                    f"https://t.me/{bot_username}?start="
                    f"verify_{user_id}_{group_id_for_link}"
                )
                verify_row = [
                    {
                        "text": "✅ Tap to Verify & Unlock Chat",
                        "url": verify_url,
                    }
                ]
            else:
                verify_row = [
                    {
                        "text": "✅ Tap to Verify & Unlock Chat",
                        "callback_data": f"verify_{user_id}",
                    }
                ]
            keyboard_rows.append(verify_row)

        keyboard_rows.append(
            [
                {
                    "text": "📥 Download the School App",
                    "url": "https://pamais.duckdns.org/app/download",
                }
            ]
        )
        reply_markup = {"inline_keyboard": keyboard_rows}

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
            "disable_web_page_preview": True
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp_data = resp.json()
            if resp_data.get("ok") and verification_enabled:
                sent_msg_id = resp_data["result"]["message_id"]
                # Store welcome message_id so we can remove the verify button later
                try:
                    from sqlalchemy import text as _sql_text
                    db.execute(_sql_text("""
                        UPDATE telegram_group_members
                        SET welcome_message_id = :mid
                        WHERE telegram_user_id = :uid AND group_chat_id = :gid
                    """), {"mid": sent_msg_id, "uid": user_id, "gid": group_chat_id or chat_id})
                    db.commit()
                    logger.info(f"Stored welcome_message_id={sent_msg_id} for user {user_id}")
                except Exception as e:
                    logger.warning(f"Could not store welcome_message_id: {e}")

    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")

async def send_member_goodbye_message(chat_id: int, chat_title: str, left_member: dict, bot_token: str | None = None):
    """Send goodbye message when a member leaves the group."""
    import httpx

    try:
        user_id = left_member.get("id")
        username = left_member.get("username")
        first_name = left_member.get("first_name", "User")
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # Build user mention
        if username:
            user_mention = f"@{safe_telegram_html(username, 'member', limit=64)}"
        else:
            user_mention = (
                f"<b>{safe_telegram_html(first_name, 'Member', limit=100)}</b>"
            )

        message = (
            "👋 <b>Member left</b>\n\n"
            f"👤 <b>Member:</b> {user_mention}\n"
            f"🏫 <b>Group:</b> "
            f"{safe_telegram_html(chat_title, 'This group', limit=150)}\n\n"
            "ℹ️ <i>Thank you for being part of the community.</i>"
        )

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

        logger.info(f"Sent member goodbye for {user_id}")

    except Exception as e:
        logger.error(f"Error sending member goodbye: {e}")


async def send_attendance_telegram_notification(
    db: Session,
    employee_name: str,
    action_type: str,
    check_time,
    status: str = None,
    late_minutes: int = None,
    location_name: str = None,
    latitude: float = None,
    longitude: float = None,
    notes: str = None,
):
    """Send attendance notification to Telegram chat with beautiful tree format."""
    import httpx
    from datetime import datetime
    
    try:
        # Get the chat ID from settings
        settings_result = db.execute(text("""
            SELECT chat_id FROM telegram_attendance_settings WHERE enabled = TRUE LIMIT 1
        """))
        settings_row = settings_result.fetchone()
        
        if not settings_row or not settings_row[0]:
            logger.info("Telegram notifications not enabled")
            return
        
        chat_id = settings_row[0]
        
        # Format time
        time_str = check_time.strftime("%H:%M") if check_time else "N/A"
        date_str = check_time.strftime("%Y-%m-%d") if check_time else "N/A"
        
        # Determine status and format late/early duration
        status_emoji = ""
        status_text = ""
        status_detail = ""
        
        if status == "late":
            status_emoji = "⏰"
            if late_minutes:
                # Format late duration as hours and minutes
                if late_minutes >= 60:
                    hours = late_minutes // 60
                    mins = late_minutes % 60
                    status_text = f"Late {hours}h {mins}m"
                else:
                    status_text = f"Late {late_minutes}m"
            else:
                status_text = "Late"
        elif status == "early_leave":
            status_emoji = "🏃"  # Running person leaving early
            if late_minutes:  # Reusing late_minutes parameter for early duration
                # Format early leave duration as hours and minutes
                if late_minutes >= 60:
                    hours = late_minutes // 60
                    mins = late_minutes % 60
                    status_text = f"Early Leave {hours}h {mins}m"
                else:
                    status_text = f"Early Leave {late_minutes}m"
            else:
                status_text = "Early Leave"
        elif status == "present":
            status_emoji = "✅"
            status_text = "On Time"
        else:
            status_emoji = "👋"
            status_text = "Check-Out"
        
        # Build beautiful tree-style message
        header_emoji = "🎉" if status == "present" else "⏰" if status == "late" else "👋"

        message = f"""{header_emoji} <b>Attendance notification</b>

👤 <b>Employee</b>
├ Name: {safe_telegram_html(employee_name, 'Employee', limit=120)}
└ {status_emoji} {status_text}

📋 <b>Details</b>
├ Action: {safe_telegram_html(action_type.replace('_', ' ').title(), limit=50)}
├ Time: {time_str}
└ Date: {date_str}"""
        
        if location_name or (latitude and longitude):
            message += f"""
📍 <b>Location</b>
"""
            if location_name:
                message += (
                    "├ Location: "
                    f"{safe_telegram_html(location_name, 'Not provided', limit=160)}\n"
                )
            if latitude and longitude:
                map_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
                message += f"└ Map: <a href='{map_link}'>View on Google Maps</a>\n"
        
        if notes:
            message += f"""
📝 <b>Notes</b>
└ {safe_telegram_html(notes, limit=800)}
"""
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━
<i>PAMA Attendance System</i>
"""

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

        logger.info(f"Sent attendance notification for {employee_name} ({action_type})")

    except Exception as e:
        logger.error(f"Error sending attendance notification: {e}")


async def handle_unknown_message(chat_id: int, bot_token: str | None = None):
    """Fallback response for private chats when they type normal text."""
    import httpx
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        message = telegram_status_card(
            "🤖",
            "I didn't understand that message",
            message="I can respond to commands and configured school questions.",
            action_title="See available options",
            action="Tap Telegram's Menu button or send /help.",
        )
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.error(f"Error handling unknown message: {e}")



async def handle_verify_via_private(db: Session, private_chat_id: int, message_obj: dict, start_param: str, bot_token: str | None = None):
    """Handle verification when user opens private chat with /start verify_{user_id}_{group_id}."""
    import httpx
    if not bot_token:
        return

    try:
        # Parse payload: verify_{user_id}_{group_id}
        parts = start_param.split("_")
        if len(parts) < 3:
            return
        
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        clicker_user_id = message_obj.get("from", {}).get("id")

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        if clicker_user_id != target_user_id:
            # Wrong user
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": private_chat_id,
                    "text": telegram_status_card(
                        "❌",
                        "Verification link not available",
                        message=(
                            "This secure link belongs to another group member."
                        ),
                        action_title="Verify your own account",
                        action=(
                            "Return to the group and use the Verify button on "
                            "your own welcome message."
                        ),
                    ),
                    "parse_mode": "HTML",
                })
            return

        # Unlock the user in the group
        restrict_url = f"https://api.telegram.org/bot{bot_token}/restrictChatMember"
        unlock_payload = {
            "chat_id": group_chat_id,
            "user_id": target_user_id,
            "permissions": {
                "can_send_messages": True,
                "can_send_audios": True,
                "can_send_documents": True,
                "can_send_photos": True,
                "can_send_videos": True,
                "can_send_video_notes": True,
                "can_send_voice_notes": True,
                "can_send_polls": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True,
                "can_invite_users": True
            },
            "use_independent_chat_permissions": False
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(restrict_url, json=unlock_payload)
            logger.info(f"Unlock via private chat: {res.text}")

        try:
            unlock_ok = bool(res.json().get("ok"))
        except Exception:
            unlock_ok = False
        if not unlock_ok:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    url,
                    json={
                        "chat_id": private_chat_id,
                        "text": telegram_status_card(
                            "⚠️",
                            "Verification could not finish",
                            message=(
                                "Your identity was confirmed, but the bot could "
                                "not unlock group access."
                            ),
                            action_title="Ask a group administrator",
                            action=(
                                "The bot needs permission to restrict and restore "
                                "member access."
                            ),
                        ),
                        "parse_mode": "HTML",
                    },
                )
            return

        # Fetch group info for the clickable link
        first_name = message_obj.get("from", {}).get("first_name", "")
        group_title = "the group"
        group_link = None

        async with httpx.AsyncClient(timeout=5.0) as client:
            chat_res = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getChat",
                params={"chat_id": group_chat_id}
            )
            chat_data = chat_res.json()
            if chat_data.get("ok"):
                chat_info = chat_data["result"]
                group_title = chat_info.get("title", group_title)
                # Use existing invite link or username-based link
                if chat_info.get("username"):
                    group_link = f"https://t.me/{chat_info['username']}"
                elif chat_info.get("invite_link"):
                    group_link = chat_info["invite_link"]

        if group_link:
            group_ref = (
                f'<a href="{html.escape(group_link, quote=True)}">'
                f"{safe_telegram_html(group_title, 'the group', limit=150)}</a>"
            )
        else:
            group_ref = (
                f"<b>{safe_telegram_html(group_title, 'the group', limit=150)}</b>"
            )

        success_msg = f"""✅ <b>Verification complete</b>

👤 <b>Member:</b> {safe_telegram_html(first_name, 'Member', limit=100)}
🔓 <b>Group:</b> {group_ref}

✅ <b>You're ready</b>
You can return to the group and start chatting.

🛡️ <i>This verification applies only to your Telegram account.</i>"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json={
                "chat_id": private_chat_id,
                "text": success_msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })

        # Update DB record to mark verified
        try:
            from sqlalchemy import text as _text
            db.execute(_text("""
                UPDATE telegram_group_members
                SET is_verified = 1, verified_at = NOW(), updated_at = NOW()
                WHERE telegram_user_id = :uid AND group_chat_id = :gid
            """), {"uid": target_user_id, "gid": group_chat_id})
            db.commit()
            logger.info(f"User {target_user_id} marked verified in DB for group {group_chat_id}")
        except Exception as e:
            logger.error(f"Error updating verified status: {e}")

        # Remove verify button from the welcome message in the group
        try:
            from sqlalchemy import text as _sql_text2
            row = db.execute(_sql_text2("""
                SELECT welcome_message_id FROM telegram_group_members
                WHERE telegram_user_id = :uid AND group_chat_id = :gid
            """), {"uid": target_user_id, "gid": group_chat_id}).fetchone()
            welcome_msg_id = row[0] if row else None
            logger.info(f"welcome_message_id for user {target_user_id}: {welcome_msg_id}")
            if welcome_msg_id:
                edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
                clean_markup = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "\U0001f4e5 Download the School App",
                                "url": "https://pamais.duckdns.org/app/download",
                            }
                        ]
                    ]
                }
                async with httpx.AsyncClient(timeout=5.0) as client:
                    edit_res = await client.post(edit_url, json={
                        "chat_id": group_chat_id,
                        "message_id": welcome_msg_id,
                        "reply_markup": clean_markup,
                    })
                    logger.info(f"editMessageReplyMarkup response: {edit_res.text}")
        except Exception as e:
            logger.error(f"Could not edit welcome message button: {e}")

        logger.info(f"User {target_user_id} verified via private chat for group {group_chat_id}")

    except Exception as e:
        logger.error(f"Error in handle_verify_via_private: {e}")


async def handle_telegram_login_start(db: Session, private_chat_id: int, message_obj: dict, login_token: str, bot_token: str) -> None:
    """Attach a private Telegram chat/user to an app login session and ask for contact."""
    import httpx

    try:
        ensure_telegram_login_sessions_table(db)
        from_user = message_obj.get("from", {}) or {}
        telegram_user_id = from_user.get("id")
        logger.info(
            "Telegram login start handler entered: private_chat_id=%s telegram_user_id=%s token_prefix=%s",
            private_chat_id,
            telegram_user_id,
            login_token[:18] if login_token else None,
        )
        if not telegram_user_id:
            logger.warning("Telegram login start missing telegram_user_id")
            return

        row = db.execute(text("""
            SELECT id FROM telegram_login_sessions
            WHERE token = :token
              AND expires_at > NOW()
              AND consumed_at IS NULL
            LIMIT 1
        """), {"token": login_token}).fetchone()
        logger.info(
            "Telegram login session lookup: token_prefix=%s found=%s",
            login_token[:18] if login_token else None,
            bool(row),
        )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        if not row:
            logger.warning(
                "Telegram login session not found or expired for token_prefix=%s",
                login_token[:18] if login_token else None,
            )
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": private_chat_id,
                    "text": telegram_status_card(
                        "⏳",
                        "Login request expired",
                        message=(
                            "This secure Telegram login session is no longer active."
                        ),
                        action_title="Start again",
                        action=(
                            "Return to the PAMA app and tap Sign in with Telegram."
                        ),
                    ),
                    "parse_mode": "HTML",
                })
            return

        db.execute(text("""
            UPDATE telegram_login_sessions
            SET telegram_user_id = :uid,
                private_chat_id = :cid,
                first_name = :fn,
                last_name = :ln,
                username = :un,
                status = 'waiting_contact'
            WHERE id = :id
        """), {
            "uid": telegram_user_id,
            "cid": private_chat_id,
            "fn": from_user.get("first_name"),
            "ln": from_user.get("last_name"),
            "un": from_user.get("username"),
            "id": row[0],
        })
        db.commit()
        logger.info(
            "Telegram login session set to waiting_contact: session_id=%s chat_id=%s user_id=%s",
            row[0],
            private_chat_id,
            telegram_user_id,
        )

        async with httpx.AsyncClient(timeout=5.0) as client:
            send_res = await client.post(url, json={
                "chat_id": private_chat_id,
                "text": telegram_status_card(
                    "🔐",
                    "Login with Telegram",
                    message=(
                        "Share your own Telegram phone number so PAMA can match "
                        "it with your existing school account."
                    ),
                    action_title="Continue securely",
                    action="Tap the Share my phone number button below.",
                    note=(
                        "Your number is used only to find your existing PAMA account."
                    ),
                ),
                "parse_mode": "HTML",
                "reply_markup": {
                    "keyboard": [[{
                        "text": "📱 Share my phone number",
                        "request_contact": True,
                    }]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            })
            logger.info(
                "Telegram login phone request sent: status=%s body=%s",
                send_res.status_code,
                send_res.text[:500],
            )
    except Exception as e:
        logger.error(f"Error starting Telegram app login: {e}", exc_info=True)


async def handle_telegram_login_contact(db: Session, private_chat_id: int, message_obj: dict, bot_token: str) -> bool:
    """Store contact phone for the latest waiting Telegram login session."""
    import httpx

    try:
        ensure_telegram_login_sessions_table(db)
        from_user = message_obj.get("from", {}) or {}
        contact = message_obj.get("contact", {}) or {}
        telegram_user_id = from_user.get("id")
        contact_user_id = contact.get("user_id")
        phone = (contact.get("phone_number") or "").strip()
        logger.info(
            "Telegram login contact received: chat_id=%s from_user_id=%s contact_user_id=%s phone_present=%s",
            private_chat_id,
            telegram_user_id,
            contact_user_id,
            bool(phone),
        )
        if not telegram_user_id or not phone:
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        if contact_user_id and int(contact_user_id) != int(telegram_user_id):
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": private_chat_id,
                    "text": telegram_status_card(
                        "⚠️",
                        "Use your own phone number",
                        message=(
                            "The shared contact belongs to a different Telegram account."
                        ),
                        action_title="Try again",
                        action="Tap the button and share your own Telegram contact.",
                    ),
                    "parse_mode": "HTML",
                })
            return True

        row = db.execute(text("""
            SELECT id FROM telegram_login_sessions
            WHERE telegram_user_id = :uid
              AND private_chat_id = :cid
              AND status = 'waiting_contact'
              AND expires_at > NOW()
              AND consumed_at IS NULL
            ORDER BY id DESC
            LIMIT 1
        """), {"uid": telegram_user_id, "cid": private_chat_id}).fetchone()
        logger.info(
            "Telegram login waiting_contact lookup: chat_id=%s user_id=%s found=%s",
            private_chat_id,
            telegram_user_id,
            bool(row),
        )

        if not row:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": private_chat_id,
                    "text": telegram_status_card(
                        "⏳",
                        "No active login request",
                        message=(
                            "The previous PAMA login request expired or was already used."
                        ),
                        action_title="Start again",
                        action=(
                            "Return to the PAMA app and tap Sign in with Telegram."
                        ),
                    ),
                    "parse_mode": "HTML",
                    "reply_markup": {"remove_keyboard": True},
                })
            return True

        db.execute(text("""
            UPDATE telegram_login_sessions
            SET phone = :phone,
                status = 'verified',
                verified_at = NOW()
            WHERE id = :id
        """), {"phone": phone, "id": row[0]})
        db.commit()
        logger.info(
            "Telegram login contact verified: session_id=%s phone_suffix=%s",
            row[0],
            phone[-4:] if phone else None,
        )

        async with httpx.AsyncClient(timeout=5.0) as client:
            send_res = await client.post(url, json={
                "chat_id": private_chat_id,
                "text": telegram_status_card(
                    "✅",
                    "Phone number verified",
                    message=(
                        "Telegram has securely confirmed the phone number for this login."
                    ),
                    action_title="Finish signing in",
                    action="Return to the PAMA app. It will continue automatically.",
                ),
                "parse_mode": "HTML",
                "reply_markup": {"remove_keyboard": True},
            })
            logger.info(
                "Telegram login verified message sent: status=%s body=%s",
                send_res.status_code,
                send_res.text[:500],
            )
        return True
    except Exception as e:
        logger.error(f"Error handling Telegram login contact: {e}", exc_info=True)
        return False


async def handle_start_command(db: Session, chat_id: int, chat_type: str, chat_title: str, bot_token: str | None = None, message_obj: dict | None = None):
    """Handle /start command."""
    import httpx

    if not bot_token:
        return  # No bot token configured — skip silently

    try:
        if chat_type == "private" and message_obj:
            raw_text = (message_obj.get("text") or "").strip()
            login_payload = extract_telegram_login_token(raw_text)
            if login_payload:
                logger.info(
                    f"Telegram app login token received through /start from private chat {chat_id}"
                )
                await handle_telegram_login_start(db, chat_id, message_obj, login_payload, bot_token)
                return

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        if chat_type in ["group", "supergroup", "channel"]:
            # Store the chat
            await store_chat_id(db, str(chat_id), chat_title, chat_type, bot_token=bot_token)

            message = telegram_status_card(
                "✅",
                "Bot ready",
                message="The PAMA bot is active in this chat.",
                fields=(
                    ("🏫", "Chat", chat_title or "Unnamed chat"),
                    ("🆔", "Chat ID", chat_id),
                ),
                action_title="Manage this chat",
                action=(
                    "Use Telegram Setup in the PAMA app to manage its group type "
                    "and settings."
                ),
            )
        else:
            message = telegram_status_card(
                "👋",
                "Welcome to the PAMA bot",
                message=(
                    "I help with secure PAMA login, school information, group "
                    "tools, and attendance notifications."
                ),
                action_title="Choose an option",
                steps=(
                    "Send /login to see how Telegram login works.",
                    "Send /myid to view your Telegram ID.",
                    "Send /help to see every available command.",
                ),
                note=(
                    "Group setup and bot settings are managed in the PAMA app."
                ),
            )

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /start: {e}")


async def handle_login_command(chat_id: int, bot_token: str | None = None):
    """Handle /login in private chat when the app has not created a login token."""
    import httpx

    if not bot_token:
        return

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        message = telegram_status_card(
            "🔐",
            "Login with Telegram",
            message="For security, every Telegram login starts in the PAMA app.",
            action_title="Sign in",
            steps=(
                "Open the PAMA app.",
                "Tap Sign in with Telegram.",
                "Return here and share your phone number when requested.",
            ),
            note=(
                "Your Telegram number is used only to match your existing "
                "PAMA account."
            ),
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
    except Exception as e:
        logger.error(f"Error handling /login: {e}")


async def handle_myid_command(chat_id: int, message_obj: dict, bot_token: str | None = None):
    """Handle /myid command - returns the user's Telegram ID in a tree structure."""
    import httpx
    from datetime import datetime

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        user_info = message_obj.get("from", {})
        user_id = user_info.get("id", "")
        is_bot = user_info.get("is_bot", False)
        first_name = user_info.get("first_name", "")
        username = user_info.get("username", "")
        language_code = user_info.get("language_code", "")
        
        msg_id = message_obj.get("message_id", "")
        msg_date = message_obj.get("date", 0)
        formatted_date = datetime.fromtimestamp(msg_date).strftime('%Y-%m-%d %H:%M:%S') if msg_date else ""

        message = f"""👤 <b>Your Telegram information</b>

🆔 <b>User ID:</b> <code>{safe_telegram_html(user_id)}</code>
👤 <b>Name:</b> {safe_telegram_html(first_name, 'Not provided', limit=100)}
🔗 <b>Username:</b> {safe_telegram_html('@' + username if username else 'Not set', limit=70)}
🌐 <b>Language:</b> {safe_telegram_html(language_code, 'Not provided', limit=20)}
🤖 <b>Bot account:</b> {'Yes' if is_bot else 'No'}

ℹ️ <i>Message {safe_telegram_html(msg_id)} received {safe_telegram_html(formatted_date, 'just now')}.</i>"""
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /myid: {e}")


async def handle_groupid_command(db: Session, chat_id: int, message_obj: dict, bot_token: str | None = None):
    """Handle /groupid command and save the group as a detected chat."""
    import httpx
    from datetime import datetime

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        chat_info = message_obj.get("chat", {})
        chat_type = chat_info.get("type", "")
        chat_title = chat_info.get("title", "")
        
        msg_id = message_obj.get("message_id", "")
        msg_date = message_obj.get("date", 0)
        formatted_date = datetime.fromtimestamp(msg_date).strftime('%Y-%m-%d %H:%M:%S') if msg_date else ""

        if chat_type == "private":
            message = telegram_status_card(
                "ℹ️",
                "Group command only",
                message="The /groupid command works only inside a group or channel.",
                action_title="Need your personal ID?",
                action="Send /myid in this private chat.",
            )
        else:
            await store_chat_id(
                db,
                chat_id=str(chat_id),
                chat_title=chat_title or "Unnamed Group",
                chat_type=chat_type,
                bot_token=bot_token,
            )
            message = f"""🏫 <b>Telegram group information</b>

🆔 <b>Group ID:</b> <code>{safe_telegram_html(chat_id)}</code>
🏷️ <b>Name:</b> {safe_telegram_html(chat_title, 'Unnamed group', limit=150)}
💬 <b>Chat type:</b> {safe_telegram_html(str(chat_type).replace('_', ' ').title(), limit=40)}
✅ <b>PAMA status:</b> Saved

ℹ️ <i>Message {safe_telegram_html(msg_id)} received {safe_telegram_html(formatted_date, 'just now')}.</i>"""

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /groupid: {e}")


async def handle_help_command(
    chat_id: int,
    chat_type: str,
    bot_token: str | None = None,
    enabled_reply_features: set[str] | None = None,
    chat_role: str | None = None,
):
    """Handle /help command - show all available commands."""
    import httpx

    if not bot_token:
        return  # No bot token configured — skip silently

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        enabled = (
            {"location", "phone", "school", "app"}
            if enabled_reply_features is None
            else enabled_reply_features
        )
        public_commands = []
        if "location" in enabled:
            public_commands.extend(
                [
                    "/location - School locations and Google Maps links",
                    "/address - School branch addresses",
                ]
            )
        if "phone" in enabled:
            public_commands.append("/phone - School contact numbers")
        if "school" in enabled:
            public_commands.append("/school - All public school information")
        if "app" in enabled:
            public_commands.append("/app - Download the official school app")
        public_commands_text = (
            "\n".join(public_commands)
            if public_commands
            else "No public automatic replies are enabled for this group."
        )

        common_commands = (
            "/help — Show this guide\n"
            "/myid — Show your Telegram ID"
        )
        if chat_type == "private":
            message = f"""📚 <b>PAMA bot help</b>

👤 <b>Private chat commands</b>
{common_commands}
/login — Start secure PAMA login

🏫 <b>School information</b>
{public_commands_text}

✅ <b>Need to configure a group?</b>
Open Telegram Setup in the PAMA app, choose the group type, and follow the Add steps.

ℹ️ <i>For account or access support, contact your system administrator.</i>"""
        elif chat_role == "notification_only":
            message = f"""📚 <b>PAMA bot help</b>

💬 <b>Group commands</b>
{common_commands}
/groupid — Show this chat's ID

📊 <b>Attendance reports</b>
/stats — Today's summary
/report — Today's detailed report
/analytics — This month's analytics
/late — Today's late arrivals
/top — Top attendance performers

🔔 <i>Notification delivery and this chat's settings are managed in the PAMA app.</i>"""
        else:
            message = f"""📚 <b>PAMA bot help</b>

💬 <b>Group commands</b>
{common_commands}
/groupid — Show this chat's ID

🏫 <b>Configured public replies</b>
{public_commands_text}

⚙️ <b>Manage replies</b>
General Group administrators can change trigger phrases and reply text in Telegram Setup inside the PAMA app.

ℹ️ <i>Use Telegram's Menu button to open commands quickly.</i>"""

        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /help: {e}")


async def handle_public_school_info_command(
    db: Session,
    chat_id: int,
    info_kind: str,
    bot_token: str | None = None,
    custom_reply_text: str | None = None,
):
    """Reply with public branch contact/location data in private or General chats."""
    import httpx
    from collections import defaultdict

    if not bot_token:
        return

    try:
        if custom_reply_text:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": render_telegram_reply_html(custom_reply_text),
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
            if not response.is_success:
                logger.warning(
                    "Telegram custom group reply failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
            return

        if info_kind == "app":
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": build_default_app_reply_html(),
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
            if not response.is_success:
                logger.warning(
                    "Telegram School App reply failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
            return

        branch_rows = db.execute(text("""
            SELECT id,
                   COALESCE(NULLIF(TRIM(app_display_name), ''), branch_name) AS name,
                   address_english,
                   app_branch_google_map_url,
                   map_latitude,
                   map_longitude,
                   open_at,
                   close_at
            FROM branch
            ORDER BY id
        """)).fetchall()

        contact_rows = db.execute(text("""
            SELECT branch_id, label, value
            FROM branch_contacts
            WHERE value IS NOT NULL AND TRIM(value) <> ''
            ORDER BY branch_id, sort_order, id
        """)).fetchall()

        contacts_by_branch = defaultdict(list)
        for branch_id, label, value in contact_rows:
            contact_value = str(value).strip()
            # Social links are not phone/contact-number replies.
            if contact_value.lower().startswith(("http://", "https://")):
                continue
            contacts_by_branch[branch_id].append((label, contact_value))

        if not branch_rows:
            response_text = telegram_status_card(
                "🏫",
                "School information unavailable",
                message="Public campus information has not been configured yet.",
                action_title="Need help?",
                action="Please contact the school administration.",
            )
            chunks = [response_text]
        else:
            title = {
                "phone": "📞 <b>School contact numbers</b>",
                "location": "📍 <b>School locations and addresses</b>",
                "school": "🏫 <b>PAMA school information</b>",
            }.get(info_kind, "🏫 <b>PAMA school information</b>")

            sections = []
            for row in branch_rows:
                (
                    branch_id,
                    branch_name,
                    address,
                    configured_map_url,
                    latitude,
                    longitude,
                    open_at,
                    close_at,
                ) = row
                lines = [f"🏫 <b>{html.escape(str(branch_name or 'Branch'))}</b>"]

                if info_kind in {"location", "school"}:
                    if address and str(address).strip():
                        lines.append(f"📮 {html.escape(str(address).strip())}")

                    if open_at is not None and close_at is not None:
                        open_text = str(open_at)[:5]
                        close_text = str(close_at)[:5]
                        lines.append(
                            f"🕒 {html.escape(open_text)} – {html.escape(close_text)}"
                        )

                    map_url = str(configured_map_url or "").strip()
                    if map_url and not map_url.lower().startswith(("http://", "https://")):
                        map_url = f"https://{map_url}"
                    if not map_url and latitude is not None and longitude is not None:
                        map_url = (
                            "https://www.google.com/maps/search/?api=1&query="
                            f"{latitude},{longitude}"
                        )
                    if map_url:
                        lines.append(
                            f'🗺️ <a href="{html.escape(map_url, quote=True)}">Open in Google Maps</a>'
                        )

                if info_kind in {"phone", "school"}:
                    branch_contacts = contacts_by_branch.get(branch_id, [])
                    if branch_contacts:
                        for label, contact_value in branch_contacts:
                            label_text = html.escape(str(label).strip()) if label else "Contact"
                            value_text = html.escape(contact_value)
                            lines.append(f"📞 <b>{label_text}:</b> <code>{value_text}</code>")
                    else:
                        lines.append("📞 No public contact number recorded")

                sections.append("\n".join(lines))

            # Keep each Telegram message safely below its 4096-character limit.
            chunks = []
            current = title
            for section in sections:
                candidate = f"{current}\n\n{section}"
                if len(candidate) > 3800 and current != title:
                    chunks.append(current)
                    current = f"{title} <i>(continued)</i>\n\n{section}"
                else:
                    current = candidate
            chunks.append(current)

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as client:
            for response_text in chunks:
                response = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": response_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
                if not response.is_success:
                    logger.warning(
                        "Telegram public school info reply failed: status=%s body=%s",
                        response.status_code,
                        response.text[:500],
                    )

    except Exception as e:
        logger.error("Error handling public school information: %s", e, exc_info=True)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": telegram_status_card(
                            "⚠️",
                            "School information unavailable",
                            message=(
                                "The bot could not load school contact information "
                                "right now."
                            ),
                            action_title="Try again",
                            action="Wait a moment, then send the same request again.",
                        ),
                        "parse_mode": "HTML",
                    },
                )
        except Exception:
            pass


async def _send_command_error(
    chat_id: int,
    bot_token: str | None,
    *,
    title: str,
    command: str,
) -> None:
    """Send one consistent, non-technical error reply for report commands."""
    if not bot_token:
        return
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": telegram_status_card(
                        "⚠️",
                        title,
                        message=(
                            "The requested attendance information could not be "
                            "generated right now."
                        ),
                        action_title="Try again",
                        action=f"Wait a moment, then send {command} again.",
                    ),
                    "parse_mode": "HTML",
                },
            )
    except Exception:
        logger.exception("Could not send Telegram command error for %s", command)


async def handle_stats_command(db: Session, chat_id: int, bot_token: str | None = None):
    """Handle /stats command - today's attendance summary."""
    import httpx
    from datetime import datetime

    try:
        from sqlalchemy import text
        
        today = datetime.now().date()
        
        # Get total employees from users table, not attendance_records
        total_result = db.execute(text("""
            SELECT COUNT(*) as total FROM users WHERE status = 1
        """))
        total_row = total_result.fetchone()
        total_employees = total_row[0] if total_row else 0
        
        # Get attendance stats
        result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT user_id) as checked_in,
                SUM(CASE WHEN status IN ('present', 'late') THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as absent,
                AVG(work_hours) as avg_hours
            FROM attendance_records
            WHERE attendance_date = :today
        """), {"today": today})
        
        row = result.fetchone()
        
        if row and row[0]:
            # Calculate attendance rate correctly
            attendance_rate = ((row[1] or 0) / max(1, total_employees) * 100)
            # Cap at 100%
            attendance_rate = min(100.0, attendance_rate)
            
            message = f"""📊 <b>Today's attendance</b>

📅 <b>Date:</b> {today.strftime('%d %B %Y')}
✅ <b>Attendance rate:</b> {attendance_rate:.1f}%
⏱️ <b>Average hours:</b> {(row[4] or 0):.1f}h

👥 <b>Employees</b>
├ Total: {total_employees}
├ Present: {row[1] or 0}
├ Late: {row[2] or 0}
└ Absent: {total_employees - (row[1] or 0)}"""
        else:
            message = telegram_status_card(
                "📊",
                "No attendance data yet",
                message="No employee attendance has been recorded today.",
                fields=(("👥", "Active employees", total_employees),),
                note="The summary will update after the first attendance record.",
            )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /stats: {e}")
        await _send_command_error(
            chat_id,
            bot_token,
            title="Attendance summary unavailable",
            command="/stats",
        )


async def handle_report_command(db: Session, chat_id: int, bot_token: str | None = None):
    """Handle /report command - daily attendance report."""
    import httpx
    from datetime import datetime

    try:
        from sqlalchemy import text
        
        today = datetime.now().date()
        
        # Get total employees
        total_result = db.execute(text("""
            SELECT COUNT(*) as total FROM users WHERE status = 1
        """))
        total_employees = total_result.fetchone()[0] if total_result else 0
        
        # Get attendance stats
        result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT user_id) as present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late,
                AVG(work_hours) as avg_hours
            FROM attendance_records
            WHERE attendance_date = :today
            AND status IN ('present', 'late')
        """), {"today": today})
        
        row = result.fetchone()
        
        if not row or not row[0]:
            message = telegram_status_card(
                "📋",
                "Daily attendance report",
                message="No attendance has been recorded today.",
                fields=(
                    ("📅", "Date", today.strftime('%d %B %Y')),
                    ("👥", "Active employees", total_employees),
                ),
            )
        else:
            present = row[0] or 0
            absent = total_employees - present
            rate = min(100.0, (present / max(1, total_employees) * 100))
            
            message = f"""📋 <b>Daily attendance report</b>

📅 <b>Date:</b> {today.strftime('%d %B %Y')}
✅ <b>Attendance rate:</b> {rate:.1f}%
⏱️ <b>Average hours:</b> {(row[2] or 0):.1f}h

👥 <b>Employees</b>
├ Total: {total_employees}
├ Present: {present}
└ Absent: {absent}"""

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /report: {str(e)}")
        logger.exception("Full traceback:")
        await _send_command_error(
            chat_id,
            bot_token,
            title="Daily report unavailable",
            command="/report",
        )


async def handle_analytics_command(db: Session, chat_id: int, bot_token: str | None = None):
    """Handle /analytics command - monthly analytics."""
    import httpx
    from datetime import datetime

    try:
        from sqlalchemy import text
        
        now = datetime.now()
        year = now.year
        month = now.month
        month_name = now.strftime('%B')
        
        # Get monthly statistics
        result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT user_id) as total_users,
                COUNT(DISTINCT DATE(attendance_date)) as working_days,
                SUM(CASE WHEN status IN ('present', 'late') THEN 1 ELSE 0 END) as total_present,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as total_late,
                SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END) as total_absent,
                AVG(work_hours) as avg_hours,
                SUM(work_hours) as total_hours
            FROM attendance_records
            WHERE YEAR(attendance_date) = :year 
            AND MONTH(attendance_date) = :month
        """), {"year": year, "month": month})
        
        row = result.fetchone()
        
        if not row or not row[0]:
            message = telegram_status_card(
                "📈",
                "No monthly analytics yet",
                message=f"No attendance data is available for {month_name} {year}.",
                note="Analytics will appear after attendance records are created.",
            )
        else:
            # Get top performers this month
            top_result = db.execute(text("""
                SELECT 
                    COALESCE(NULLIF(u.kName, ''), u.eName, u.username) as full_name,
                    COUNT(ar.id) as days_present,
                    AVG(ar.work_hours) as avg_hours,
                    SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END) as late_count
                FROM attendance_records ar
                JOIN users u ON ar.user_id = u.id
                WHERE YEAR(ar.attendance_date) = :year 
                AND MONTH(ar.attendance_date) = :month
                AND ar.status IN ('present', 'late')
                GROUP BY u.id, u.kName, u.eName, u.username
                ORDER BY days_present DESC, avg_hours DESC
                LIMIT 5
            """), {"year": year, "month": month})
            
            top_list = []
            for i, r in enumerate(top_result, 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                avg_hours = r[2] if r[2] is not None else 0.0
                top_list.append(
                    f" ├ {emoji} {safe_telegram_html(r[0], 'Employee', limit=100)} "
                    f"— {r[1]} days ({avg_hours:.1f}h)"
                )
            
            # Get attendance trend (weekly breakdown)
            trend_result = db.execute(text("""
                SELECT 
                    WEEK(attendance_date, 1) as week_num,
                    COUNT(DISTINCT user_id) as users,
                    AVG(work_hours) as avg_hours
                FROM attendance_records
                WHERE YEAR(attendance_date) = :year 
                AND MONTH(attendance_date) = :month
                GROUP BY WEEK(attendance_date, 1)
                ORDER BY week_num
                LIMIT 4
            """), {"year": year, "month": month})
            
            trend_list = []
            for i, r in enumerate(trend_result, 1):
                avg_hours = r[2] if r[2] is not None else 0.0
                trend_list.append(f" ├ Week {i}: {r[1]} emp, {avg_hours:.1f}h")
            
            # Get perfect attendance employees
            perfect_result = db.execute(text("""
                SELECT 
                    COALESCE(NULLIF(u.kName, ''), u.eName, u.username) as full_name,
                    COUNT(ar.id) as days_present
                FROM attendance_records ar
                JOIN users u ON ar.user_id = u.id
                WHERE YEAR(ar.attendance_date) = :year 
                AND MONTH(ar.attendance_date) = :month
                AND ar.status = 'present'
                AND ar.late_reason IS NULL
                GROUP BY u.id, u.kName, u.eName, u.username
                HAVING days_present >= 15
                ORDER BY days_present DESC
                LIMIT 3
            """), {"year": year, "month": month})
            
            perfect_list = []
            for r in perfect_result:
                perfect_list.append(
                    f" ├ {safe_telegram_html(r[0], 'Employee', limit=100)} "
                    f"— {r[1]} days"
                )
            
            attendance_rate = ((row[2] or 0) / max(1, (row[2] or 0) + (row[4] or 0)) * 100)
            
            if top_list: top_list[-1] = top_list[-1].replace(" ├ ", " └ ")
            if trend_list: trend_list[-1] = trend_list[-1].replace(" ├ ", " └ ")
            if perfect_list: perfect_list[-1] = perfect_list[-1].replace(" ├ ", " └ ")
            
            message = f"""📈 <b>Monthly attendance analytics</b>

📅 <b>Month:</b> {month_name} {year}
✅ <b>Attendance rate:</b> {attendance_rate:.1f}%
🕐 <b>Generated:</b> {datetime.now().strftime('%H:%M')}

📊 <b>Overall statistics</b>
 ├ Employees: {row[0] or 0}
 ├ Working days: {row[1] or 0}
 ├ Present records: {row[2] or 0}
 ├ Late records: {row[3] or 0}
 ├ Absent records: {row[4] or 0}
 ├ Average hours: {(row[5] or 0):.1f}h
 └ Total hours: {(row[6] or 0):.1f}h

🏆 <b>Top performers</b>
{chr(10).join(top_list) if top_list else ' └ No data'}

📈 <b>Weekly trend</b>
{chr(10).join(trend_list) if trend_list else ' └ No data'}

⭐ <b>Perfect attendance</b>
{chr(10).join(perfect_list) if perfect_list else ' └ No data'}
"""

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /analytics: {e}")
        await _send_command_error(
            chat_id,
            bot_token,
            title="Monthly analytics unavailable",
            command="/analytics",
        )


async def handle_late_command(db: Session, chat_id: int, bot_token: str | None = None):
    """Handle /late command - late arrivals today."""
    import httpx
    from datetime import datetime

    try:
        from sqlalchemy import text
        
        today = datetime.now().date()
        
        result = db.execute(text("""
            SELECT 
                u.username,
                COALESCE(NULLIF(u.kName, ''), u.eName, u.username) as full_name,
                ar.check_in_time,
                ar.work_hours
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.attendance_date = :today
            AND ar.status = 'late'
            ORDER BY ar.check_in_time DESC
        """), {"today": today})
        
        late_list = []
        for row in result:
            check_in = row[2].strftime("%H:%M") if row[2] else "N/A"
            work_h = row[3] if row[3] is not None else 0.0
            late_list.append(
                f" ├ {safe_telegram_html(row[1], 'Employee', limit=100)} "
                f"— {check_in} ({work_h:.1f}h)"
            )
        
        if late_list:
            if len(late_list) > 0:
                late_list[-1] = late_list[-1].replace(" ├ ", " └ ")
            message = f"""⏰ <b>Late arrivals</b>

📅 <b>Date:</b> {today.strftime('%d %B %Y')}
👥 <b>Total late:</b> {len(late_list)}

📋 <b>Employees</b>
{chr(10).join(late_list)}
"""
        else:
            message = telegram_status_card(
                "✅",
                "Everyone is on time",
                message="No late arrivals have been recorded today.",
            )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /late: {e}")
        await _send_command_error(
            chat_id,
            bot_token,
            title="Late-arrival report unavailable",
            command="/late",
        )



async def handle_top_command(db: Session, chat_id: int, bot_token: str | None = None):
    """Handle /top command - top performers."""
    import httpx

    try:
        from sqlalchemy import text
        
        result = db.execute(text("""
            SELECT 
                u.username,
                COALESCE(NULLIF(u.kName, ''), u.eName, u.username) as full_name,
                COUNT(ar.id) as days_present,
                AVG(ar.work_hours) as avg_hours
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.status IN ('present', 'late')
            GROUP BY u.id, u.username, u.kName, u.eName
            ORDER BY days_present DESC, avg_hours DESC
            LIMIT 10
        """))
        
        performers = []
        for i, row in enumerate(result, 1):
            avg_hours = row[3] if row[3] is not None else 0.0
            performers.append(
                f" ├ {i}. {safe_telegram_html(row[1], 'Employee', limit=100)} "
                f"— {row[2]} days ({avg_hours:.1f}h)"
            )
        
        if performers:
            if len(performers) > 0:
                performers[-1] = performers[-1].replace(" ├ ", " └ ")
            message = """🏆 <b>Top attendance performers</b>

📊 <b>Ranking:</b> Attendance days and average hours
👥 <b>Showing:</b> Up to 10 employees

📋 <b>Employees</b>
""" + chr(10).join(performers) + """
"""
        else:
            message = telegram_status_card(
                "📊",
                "No attendance ranking yet",
                message="There is not enough attendance data to rank employees.",
            )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)

    except Exception as e:
        logger.error(f"Error handling /top: {e}")
        await _send_command_error(
            chat_id,
            bot_token,
            title="Attendance ranking unavailable",
            command="/top",
        )


async def mark_chat_inactive(db: Session, chat_id: str):
    """Mark chat as inactive when bot leaves."""
    try:
        from sqlalchemy import text

        db.execute(text("""
            UPDATE telegram_tracked_chats
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = :chat_id
        """), {"chat_id": chat_id})

        _clear_notification_destination_references(db, chat_id)

        db.commit()
        logger.info(f"Marked chat {chat_id} as inactive")

    except Exception as e:
        logger.error(f"Error marking chat inactive: {e}")
        db.rollback()


@router.get("/set")
async def set_webhook(webhook_url: str = None, db: Session = Depends(get_db)):
    """
    Set Telegram webhook URL.
    Call this once to register the webhook with Telegram.

    Optional query param:
      ?webhook_url=https://your-ngrok-url.ngrok-free.app/api/v1/telegram/

    Falls back to WEBHOOK_URL env var, then the live production URL.
    """
    import httpx
    import os

    try:
        bot_token = get_active_bot_token(db)
        if not bot_token:
            return {"success": False, "error": "No bot token configured"}
            
        # Priority: query param → env var → hardcoded live URL
        resolved_url = (
            webhook_url
            or os.environ.get("TELEGRAM_WEBHOOK_URL")
            or "https://pamais.duckdns.org/api/v1/telegram/"
        )

        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        payload = {
            "url": resolved_url,
            "allowed_updates": [
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
                "my_chat_member",
                "chat_member",
                "callback_query",
            ],
        }

        # Setup the autocomplete commands menu with scopes
        commands_url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
        
        # 1. Clear global default commands
        default_payload = {
            "scope": {"type": "default"},
            "commands": []
        }
        
        # 2. Set commands for private 1-to-1 chats
        private_payload = {
            "scope": {"type": "all_private_chats"},
            "commands": [
                {"command": "login", "description": "Login to PAMA app"},
                {"command": "myid", "description": "Get your personal Telegram ID"},
                {"command": "help", "description": "Show help message"}
            ]
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Set webhook
            response = await client.post(url, json=payload)
            # Clear default commands
            await client.post(commands_url, json=default_payload)
            # Set private commands
            await client.post(commands_url, json=private_payload)

        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return {
                    "success": True,
                    "message": "Webhook & Commands set successfully",
                    "webhook_url": resolved_url,
                }
            else:
                return {
                    "success": False,
                    "error": data.get("description", "Unknown error setting webhook"),
                }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
            }

    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return {"success": False, "error": str(e)}



@router.get("/info")
async def get_webhook_info(db: Session = Depends(get_db)):
    """Get current webhook info from Telegram."""
    import httpx

    try:
        bot_token = get_active_bot_token(db)
        if not bot_token:
            return {"error": "No bot token configured"}
            
        url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        return {"error": str(e)}


@router.get("/tracked-chats")
async def get_tracked_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    bot_token: str = None,
):
    """Get list of tracked Telegram chats, optionally filtered by bot token."""
    try:
        from sqlalchemy import text

        if bot_token:
            result = db.execute(text("""
                SELECT chat_id, chat_title, chat_type, is_active, added_at,
                       bot_role, member_verification_enabled
                FROM telegram_tracked_chats
                WHERE is_active = TRUE AND bot_token = :bot_token
                ORDER BY added_at DESC
            """), {"bot_token": bot_token})
        else:
            result = db.execute(text("""
                SELECT chat_id, chat_title, chat_type, is_active, added_at,
                       bot_role, member_verification_enabled
                FROM telegram_tracked_chats
                WHERE is_active = TRUE
                ORDER BY added_at DESC
            """))

        chats = []
        for row in result:
            chats.append({
                "chat_id": row[0],
                "chat_title": row[1],
                "chat_type": row[2],
                "is_active": row[3],
                "added_at": row[4].isoformat() if row[4] else None,
                "bot_role": row[5],
                "member_verification_enabled": (
                    False if row[6] is None else bool(row[6])
                ),
            })

        return {"chats": chats}

    except Exception as e:
        logger.error(f"Error fetching tracked chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tracked-chats")
async def delete_tracked_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Clear all tracked Telegram chats and their notification settings."""
    try:
        from sqlalchemy import text
        
        # Clear tracked chats table
        db.execute(text("DELETE FROM telegram_tracked_chats"))
        
        # Reset current setting
        db.execute(text("""
            UPDATE telegram_attendance_settings
            SET chat_id = NULL,
                leave_chat_id = NULL,
                enabled = FALSE,
                notify_leave_requests = FALSE,
                notify_leave_decisions = FALSE
        """))
        
        db.commit()
        return {"ok": True, "message": "All tracked chats cleared"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing tracked chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tracked-chats/{chat_id}/leave")
async def leave_tracked_chat(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Leave a Telegram chat and remove from tracked chats."""
    try:
        import httpx
        from sqlalchemy import text
        
        bot_token = get_active_bot_token(db)
        if not bot_token:
            raise HTTPException(status_code=400, detail="No bot token configured")
            
        # 1. Call Telegram API to leave chat
        url = f"https://api.telegram.org/bot{bot_token}/leaveChat"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"chat_id": chat_id})
            
        if response.status_code != 200:
            logger.warning(f"Failed to leave chat {chat_id}: {response.text}")

        # 2. Remove from tracked chats
        db.execute(text("DELETE FROM telegram_tracked_chats WHERE chat_id = :chat_id"), {"chat_id": chat_id})
        
        # 3. Clear any attendance/leave routing that depended on this chat.
        _clear_notification_destination_references(db, chat_id)
        
        db.commit()
        return {"ok": True, "message": f"Left chat {chat_id}"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error leaving chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tracked-chats/{chat_id}/role")
async def update_tracked_chat_role(
    chat_id: str,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Set a tracked chat role from the Flutter admin app."""
    _require_telegram_admin(current_user)
    allowed_roles = {"notification_only", "general", "pending"}
    if role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail="Invalid role. Use notification_only, general, or pending.",
        )

    try:
        from sqlalchemy import text

        row = db.execute(text("""
            SELECT chat_title, bot_role FROM telegram_tracked_chats
            WHERE chat_id = :chat_id AND is_active = TRUE
            LIMIT 1
        """), {"chat_id": chat_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Tracked chat not found")

        ok = set_chat_role(db, chat_id, role)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update chat role")

        enabled_reply_features = None
        if role == "general":
            reply_settings = get_group_reply_settings(db, chat_id)
            enabled_reply_features = {
                feature["key"]
                for feature in reply_settings["features"]
                if reply_settings["enabled"] and feature["enabled"]
            }
        await sync_chat_command_menu(
            chat_id,
            role,
            bot_token=get_active_bot_token(db),
            enabled_reply_features=enabled_reply_features,
        )
        if role == "general":
            await ensure_moderation_webhook_updates(get_active_bot_token(db))

        previous_role = row[1]
        if (
            role in APP_ASSIGNABLE_TELEGRAM_ROLES
            and previous_role in {None, "pending", "auth_pending"}
        ):
            bot_token = get_active_bot_token(db)
            if bot_token:
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=8.0) as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": telegram_status_card(
                                    "✅",
                                    "Setup complete",
                                    message=(
                                        "An administrator finished this chat's "
                                        "setup in the PAMA app."
                                    ),
                                    fields=((
                                        "👥",
                                        "Group type",
                                        telegram_role_label(role),
                                    ),),
                                    note=(
                                        "No Telegram role selection or "
                                        "authorization code is needed now."
                                    ),
                                ),
                                "parse_mode": "HTML",
                                "disable_notification": True,
                            },
                        )
                except Exception:
                    logger.exception(
                        "Could not send app quick-setup confirmation to %s",
                        chat_id,
                    )

        return {
            "ok": True,
            "chat_id": chat_id,
            "chat_title": row[0],
            "bot_role": role,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating chat role {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _require_telegram_admin(current_user: User) -> None:
    if getattr(current_user, "role", None) != 1:
        raise HTTPException(status_code=403, detail="Admin access required")


def _require_general_tracked_chat(db: Session, chat_id: str) -> None:
    row = db.execute(text("""
        SELECT bot_role
        FROM telegram_tracked_chats
        WHERE chat_id = :chat_id AND is_active = TRUE
        LIMIT 1
    """), {"chat_id": str(chat_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tracked chat not found")
    if row[0] != "general":
        raise HTTPException(
            status_code=400,
            detail="These settings are available only for General Groups",
        )


@router.get("/tracked-chats/{chat_id}/member-verification")
async def get_tracked_chat_member_verification(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return whether new members must verify before they can chat."""
    _require_telegram_admin(current_user)
    _require_general_tracked_chat(db, chat_id)
    return {
        "chat_id": str(chat_id),
        "enabled": get_member_verification_enabled(db, chat_id),
    }


@router.put("/tracked-chats/{chat_id}/member-verification")
async def update_tracked_chat_member_verification(
    chat_id: str,
    payload: TelegramMemberVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Toggle join verification and release waiting members when turned off."""
    _require_telegram_admin(current_user)
    _require_general_tracked_chat(db, chat_id)

    try:
        db.execute(text("""
            UPDATE telegram_tracked_chats
            SET member_verification_enabled = :enabled,
                updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = :chat_id AND is_active = TRUE
        """), {"enabled": bool(payload.enabled), "chat_id": str(chat_id)})
        db.commit()

        unlocked_count = 0
        unlock_failed_count = 0
        release_error = None
        if not payload.enabled:
            try:
                waiting_members = db.execute(text("""
                    SELECT telegram_user_id
                    FROM telegram_group_members
                    WHERE group_chat_id = :chat_id
                      AND is_bot = 0
                      AND is_verified = 0
                """), {"chat_id": str(chat_id)}).fetchall()

                bot_token = get_active_bot_token(db)
                if bot_token:
                    import httpx

                    async with httpx.AsyncClient(timeout=8.0) as client:
                        for member_row in waiting_members:
                            member_id = member_row[0]
                            try:
                                response = await client.post(
                                    f"https://api.telegram.org/bot{bot_token}/restrictChatMember",
                                    json={
                                        "chat_id": chat_id,
                                        "user_id": member_id,
                                        "permissions": member_chat_permissions(
                                            can_chat=True
                                        ),
                                        "use_independent_chat_permissions": False,
                                    },
                                )
                                response_data = response.json()
                                if response_data.get("ok"):
                                    unlocked_count += 1
                                    db.execute(text("""
                                        UPDATE telegram_group_members
                                        SET is_verified = 1,
                                            verified_at = CURRENT_TIMESTAMP,
                                            updated_at = CURRENT_TIMESTAMP
                                        WHERE telegram_user_id = :user_id
                                          AND group_chat_id = :chat_id
                                    """), {
                                        "user_id": member_id,
                                        "chat_id": str(chat_id),
                                    })
                                    continue

                                unlock_failed_count += 1
                                logger.warning(
                                    "Could not release Telegram member %s in chat %s: %s",
                                    member_id,
                                    chat_id,
                                    response_data.get("description")
                                    or response.text[:300],
                                )
                            except Exception as exc:
                                unlock_failed_count += 1
                                logger.warning(
                                    "Could not release Telegram member %s in chat %s: %s",
                                    member_id,
                                    chat_id,
                                    exc,
                                )
                    db.commit()
                else:
                    unlock_failed_count = len(waiting_members)
            except Exception as exc:
                db.rollback()
                release_error = str(exc)
                logger.warning(
                    "Verification was disabled for chat %s, but waiting "
                    "members could not be released: %s",
                    chat_id,
                    exc,
                )

        return {
            "ok": True,
            "chat_id": str(chat_id),
            "enabled": bool(payload.enabled),
            "unlocked_member_count": unlocked_count,
            "unlock_failed_count": unlock_failed_count,
            "release_error": release_error,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            "Could not update member verification for chat %s: %s",
            chat_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update member verification",
        )


@router.get("/tracked-chats/{chat_id}/auto-replies")
async def get_tracked_chat_auto_replies(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return configurable automatic replies for a General Group."""
    _require_telegram_admin(current_user)
    _require_general_tracked_chat(db, chat_id)
    try:
        return get_group_reply_settings(db, chat_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Could not load auto replies for %s: %s", chat_id, e)
        raise HTTPException(status_code=500, detail="Failed to load auto replies")


@router.put("/tracked-chats/{chat_id}/auto-replies")
async def update_tracked_chat_auto_replies(
    chat_id: str,
    payload: TelegramGroupReplySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Save trigger phrases and reply text for a General Group."""
    _require_telegram_admin(current_user)
    _require_general_tracked_chat(db, chat_id)
    try:
        settings = save_group_reply_settings(
            db,
            chat_id,
            payload.model_dump(),
            updated_by=getattr(current_user, "id", None),
        )
        enabled_reply_features = {
            feature["key"]
            for feature in settings["features"]
            if settings["enabled"] and feature["enabled"]
        }
        await sync_chat_command_menu(
            chat_id,
            "general",
            bot_token=get_active_bot_token(db),
            enabled_reply_features=enabled_reply_features,
        )
        return settings
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Could not save auto replies for %s: %s", chat_id, e)
        raise HTTPException(status_code=500, detail="Failed to save auto replies")


@router.get("/tracked-chats/{chat_id}/moderation")
async def get_tracked_chat_moderation(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return a General Group's moderation policy and live bot permissions."""
    _require_telegram_admin(current_user)
    _require_general_tracked_chat(db, chat_id)
    try:
        policy = get_moderation_policy(db, chat_id)
        permissions = await get_bot_moderation_permissions(
            chat_id,
            get_active_bot_token(db),
        )
        return {**policy, "bot_permissions": permissions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Could not load moderation settings for %s: %s", chat_id, e)
        raise HTTPException(status_code=500, detail="Failed to load moderation settings")


@router.put("/tracked-chats/{chat_id}/moderation")
async def update_tracked_chat_moderation(
    chat_id: str,
    payload: TelegramModerationPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Save automatic file/link moderation for an authorized General Group."""
    _require_telegram_admin(current_user)
    _require_general_tracked_chat(db, chat_id)
    try:
        policy = save_moderation_policy(
            db,
            chat_id,
            payload.model_dump(),
            updated_by=getattr(current_user, "id", None),
        )
        await ensure_moderation_webhook_updates(get_active_bot_token(db))
        permissions = await get_bot_moderation_permissions(
            chat_id,
            get_active_bot_token(db),
        )
        return {**policy, "bot_permissions": permissions}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Could not save moderation settings for %s: %s", chat_id, e)
        raise HTTPException(status_code=500, detail="Failed to save moderation settings")


# =============================================================================
# Telegram Analytics Endpoints
# =============================================================================

@router.get("/analytics/today")
async def get_today_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get today's attendance analytics."""
    try:
        analytics = TelegramAnalyticsService.get_today_summary(db)
        return analytics
    except Exception as e:
        logger.error(f"Error in today analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/monthly")
async def get_monthly_analytics(
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get monthly attendance analytics."""
    try:
        if not year or not month:
            now = datetime.now()
            year = year or now.year
            month = month or now.month
            
        analytics = TelegramAnalyticsService.get_monthly_summary(db, year, month)
        return analytics
    except Exception as e:
        logger.error(f"Error in monthly analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/top-performers")
async def get_top_performers(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get top performers by attendance."""
    try:
        performers = TelegramAnalyticsService.get_top_performers(db, limit)
        return {"performers": performers}
    except Exception as e:
        logger.error(f"Error fetching top performers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/late-today")
async def get_late_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get employees who arrived late today."""
    try:
        late = TelegramAnalyticsService.get_late_arrivals_today(db)
        return {"late_arrivals": late, "count": len(late)}
    except Exception as e:
        logger.error(f"Error fetching late arrivals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/absent-today")
async def get_absent_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get employees absent today."""
    try:
        absent = TelegramAnalyticsService.get_absent_today(db)
        return {"absent": absent, "count": len(absent)}
    except Exception as e:
        logger.error(f"Error fetching absent employees: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/trend")
async def get_attendance_trend(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get attendance trend for the last N days."""
    try:
        trend = TelegramAnalyticsService.get_attendance_trend(db, days)
        return {"trend": trend, "days": days}
    except Exception as e:
        logger.error(f"Error fetching attendance trend: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Bot Authorization Code Endpoints ──────────────────────────────────────────

@router.post("/auth-code/generate")
async def generate_bot_auth_code(
    intended_role: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate a new 6-digit one-time authorization code for adding the bot to a group.
    The code expires in 3 minutes and can only be used once. New app versions
    attach the selected setup role so Telegram never needs role-choice buttons.
    Requires App Admin privileges.
    """
    import random
    import string
    from datetime import datetime, timedelta

    if intended_role not in {
        *APP_ASSIGNABLE_TELEGRAM_ROLES,
        "pending",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid intended role. Use notification_only or general.",
        )

    try:
        ensure_telegram_auth_codes_table(db)

        # Invalidate any existing unused codes first (clean up)
        db.execute(text("""
            UPDATE telegram_bot_auth_codes
            SET used_at = NOW()
            WHERE used_at IS NULL AND expires_at > NOW()
        """))
        db.commit()

        # Generate a fresh 6-digit code — valid for 3 minutes only
        code = ''.join(random.choices(string.digits, k=6))
        # Use naive local datetime to match MySQL NOW() which returns local time
        expires_at = datetime.now() + timedelta(minutes=3)

        db.execute(text("""
            INSERT INTO telegram_bot_auth_codes (
                code, expires_at, intended_role
            ) VALUES (
                :code, :expires_at, :intended_role
            )
        """), {
            "code": code,
            "expires_at": expires_at,
            "intended_role": intended_role,
        })
        db.commit()

        return {
            "code": code,
            "expires_at": expires_at.isoformat(),
            "expires_in_seconds": 3 * 60,
            "seconds_remaining": 3 * 60,
            "intended_role": intended_role,
        }
    except Exception as e:
        logger.error(f"Error generating auth code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth-code/status")
async def get_bot_auth_code_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the status of the most recently generated authorization code.
    Returns None if no code has ever been generated.
    """
    from datetime import datetime

    try:
        ensure_telegram_auth_codes_table(db)

        row = db.execute(text("""
            SELECT code, created_at, expires_at, used_at, used_for_chat_id,
                   intended_role
            FROM telegram_bot_auth_codes
            ORDER BY created_at DESC
            LIMIT 1
        """)).fetchone()

        if not row:
            return {"has_code": False}

        (
            code,
            created_at,
            expires_at,
            used_at,
            used_for_chat_id,
            intended_role,
        ) = row
        # Use naive local datetime to match the stored expires_at (also naive local)
        now = datetime.now()

        is_used = used_at is not None
        is_expired = now > expires_at
        seconds_remaining = max(0, int((expires_at - now).total_seconds())) if not is_used else 0

        return {
            "has_code": True,
            "code": code,
            "expires_at": expires_at.isoformat(),
            "seconds_remaining": seconds_remaining,
            "is_used": is_used,
            "is_expired": is_expired,
            "used_for_chat_id": used_for_chat_id,
            "intended_role": intended_role,
        }
    except Exception as e:
        logger.error(f"Error getting auth code status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
