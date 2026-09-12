"""Automatic file and link moderation for authorized Telegram General Groups."""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


DEFAULT_BLOCKED_EXTENSIONS = [
    ".exe",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".tar.gz",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".apk",
    ".ipa",
    ".dmg",
    ".pkg",
    ".deb",
    ".rpm",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".msi",
    ".dll",
    ".so",
    ".app",
    ".lnk",
    ".reg",
    ".ps1",
    ".sh",
    ".vbs",
    ".js",
    ".jar",
    ".iso",
    ".docm",
    ".xlsm",
    ".pptm",
    ".hta",
    ".cpl",
]

DEFAULT_ALLOWED_EXTENSIONS = [
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".csv",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp3",
    ".m4a",
    ".wav",
    ".mp4",
    ".mov",
]

DEFAULT_ALLOWED_DOMAINS = [
    # Official PAMA services.
    "pamais.duckdns.org",
    "pamainternationalschool.com",
    # Google services and their commonly shared short-link hosts.
    "google.com",
    "g.co",
    "goo.gl",
    "maps.app.goo.gl",
    "forms.gle",
    "googleapis.com",
    "googleusercontent.com",
    "gstatic.com",
    # YouTube pages, short links, privacy embeds, thumbnails, and media.
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "ytimg.com",
    "googlevideo.com",
    # Communication, app distribution, and common education services.
    "t.me",
    "telegram.org",
    "apps.apple.com",
    "microsoft.com",
    "office.com",
    "zoom.us",
    "wikipedia.org",
]

# The original Strict preset shipped with exactly these domains. Policies that
# still match this untouched list can safely inherit future trusted defaults;
# customized allowlists must remain exactly as their administrators saved them.
_LEGACY_STRICT_ALLOWED_DOMAINS = [
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "youtube.com",
    "youtu.be",
    "t.me",
]

_DANGEROUS_MIME_TYPES = {
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/vnd.microsoft.portable-executable",
    "application/vnd.android.package-archive",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/x-7z-compressed",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
    "application/x-bzip2",
    "application/x-xz",
    "application/x-apple-diskimage",
    "application/x-msi",
    "application/vnd.debian.binary-package",
    "application/x-rpm",
    "application/x-iso9660-image",
    "application/java-archive",
}

_FILE_POLICIES = {"allow_all", "blocklist", "allowlist"}
_LINK_POLICIES = {"allow_all", "block_all", "allowlist"}
_schema_ready_for: set[int] = set()


def default_moderation_policy(chat_id: str) -> dict:
    """Block dangerous downloads by default and leave normal sharing alone."""
    return {
        "chat_id": str(chat_id),
        "enabled": True,
        "file_policy": "blocklist",
        "blocked_extensions": list(DEFAULT_BLOCKED_EXTENSIONS),
        "allowed_extensions": list(DEFAULT_ALLOWED_EXTENSIONS),
        "link_policy": "allow_all",
        "allowed_domains": list(DEFAULT_ALLOWED_DOMAINS),
        "exempt_admins": False,
        "send_warning": True,
    }


def _json_list(value: object, fallback: list[str]) -> list[str]:
    if value is None:
        return list(fallback)
    try:
        parsed = json.loads(str(value))
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return list(fallback)


def normalize_extension(value: str) -> str:
    extension = (value or "").strip().casefold()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    if not re.fullmatch(r"\.[a-z0-9][a-z0-9._+-]{0,30}", extension):
        raise ValueError(f"Invalid file extension: {value}")
    return extension


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().casefold()
    if domain.startswith("*."):
        domain = domain[2:]
    if "://" in domain:
        domain = urlsplit(domain).hostname or ""
    domain = domain.rstrip(".")
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Invalid domain: {value}") from exc
    if not domain or len(domain) > 253 or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain
    ):
        raise ValueError(f"Invalid domain: {value}")
    return domain


def normalize_policy(policy: dict, chat_id: str) -> dict:
    normalized = default_moderation_policy(chat_id)
    normalized.update(
        {
            "enabled": bool(policy.get("enabled", normalized["enabled"])),
            "file_policy": str(
                policy.get("file_policy", normalized["file_policy"])
            ),
            "link_policy": str(
                policy.get("link_policy", normalized["link_policy"])
            ),
            "exempt_admins": bool(
                policy.get("exempt_admins", normalized["exempt_admins"])
            ),
            "send_warning": bool(
                policy.get("send_warning", normalized["send_warning"])
            ),
        }
    )
    if normalized["file_policy"] not in _FILE_POLICIES:
        raise ValueError("Invalid file policy")
    if normalized["link_policy"] not in _LINK_POLICIES:
        raise ValueError("Invalid link policy")

    blocked = policy.get("blocked_extensions", normalized["blocked_extensions"])
    allowed = policy.get("allowed_extensions", normalized["allowed_extensions"])
    domains = policy.get("allowed_domains", normalized["allowed_domains"])
    if not isinstance(blocked, list) or not isinstance(allowed, list):
        raise ValueError("File extensions must be lists")
    if not isinstance(domains, list):
        raise ValueError("Allowed domains must be a list")

    normalized["blocked_extensions"] = sorted(
        {normalize_extension(str(item)) for item in blocked}
    )
    normalized["allowed_extensions"] = sorted(
        {normalize_extension(str(item)) for item in allowed}
    )
    normalized["allowed_domains"] = sorted(
        {normalize_domain(str(item)) for item in domains}
    )
    return normalized


def _upgrade_legacy_strict_defaults(policy: dict) -> dict:
    """Expand only an untouched copy of the original Strict domain preset."""
    uses_default_files = set(policy["allowed_extensions"]) == set(
        DEFAULT_ALLOWED_EXTENSIONS
    )
    uses_legacy_domains = set(policy["allowed_domains"]) == set(
        _LEGACY_STRICT_ALLOWED_DOMAINS
    )
    if (
        policy["file_policy"] == "allowlist"
        and policy["link_policy"] == "allowlist"
        and uses_default_files
        and uses_legacy_domains
    ):
        return {
            **policy,
            "allowed_domains": sorted(DEFAULT_ALLOWED_DOMAINS),
        }
    return policy


def ensure_moderation_tables(db: Session) -> None:
    """Create moderation tables on older installations before first use."""
    bind = db.get_bind()
    bind_key = id(bind)
    if bind_key in _schema_ready_for:
        return
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_chat_moderation_settings (
                chat_id VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN NOT NULL,
                file_policy VARCHAR(20) NOT NULL,
                blocked_extensions TEXT NOT NULL,
                allowed_extensions TEXT NOT NULL,
                link_policy VARCHAR(20) NOT NULL,
                allowed_domains TEXT NOT NULL,
                exempt_admins BOOLEAN NOT NULL,
                send_warning BOOLEAN NOT NULL,
                updated_by INTEGER NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_moderation_events (
                event_id VARCHAR(36) PRIMARY KEY,
                chat_id VARCHAR(100) NOT NULL,
                message_id VARCHAR(100) NULL,
                telegram_user_id VARCHAR(100) NULL,
                username VARCHAR(255) NULL,
                content_type VARCHAR(50) NOT NULL,
                file_name VARCHAR(500) NULL,
                domain VARCHAR(255) NULL,
                reason VARCHAR(500) NOT NULL,
                action VARCHAR(50) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()
        _schema_ready_for.add(bind_key)
    except Exception:
        db.rollback()
        logger.exception("Failed to initialize Telegram moderation tables")
        raise


def get_moderation_policy(db: Session, chat_id: str) -> dict:
    ensure_moderation_tables(db)
    row = db.execute(text("""
        SELECT enabled, file_policy, blocked_extensions, allowed_extensions,
               link_policy, allowed_domains, exempt_admins, send_warning
        FROM telegram_chat_moderation_settings
        WHERE chat_id = :chat_id
        LIMIT 1
    """), {"chat_id": str(chat_id)}).fetchone()
    if not row:
        return default_moderation_policy(str(chat_id))
    normalized = normalize_policy(
        {
            "enabled": bool(row[0]),
            "file_policy": row[1],
            "blocked_extensions": _json_list(
                row[2], DEFAULT_BLOCKED_EXTENSIONS
            ),
            "allowed_extensions": _json_list(
                row[3], DEFAULT_ALLOWED_EXTENSIONS
            ),
            "link_policy": row[4],
            "allowed_domains": _json_list(row[5], DEFAULT_ALLOWED_DOMAINS),
            "exempt_admins": bool(row[6]),
            "send_warning": bool(row[7]),
        },
        str(chat_id),
    )
    return _upgrade_legacy_strict_defaults(normalized)


def save_moderation_policy(
    db: Session,
    chat_id: str,
    policy: dict,
    updated_by: int | None = None,
) -> dict:
    ensure_moderation_tables(db)
    normalized = normalize_policy(policy, str(chat_id))
    params = {
        **normalized,
        "blocked_extensions": json.dumps(normalized["blocked_extensions"]),
        "allowed_extensions": json.dumps(normalized["allowed_extensions"]),
        "allowed_domains": json.dumps(normalized["allowed_domains"]),
        "updated_by": updated_by,
    }
    existing = db.execute(text("""
        SELECT chat_id
        FROM telegram_chat_moderation_settings
        WHERE chat_id = :chat_id
        LIMIT 1
    """), {"chat_id": str(chat_id)}).fetchone()
    if existing:
        db.execute(text("""
            UPDATE telegram_chat_moderation_settings
            SET enabled = :enabled,
                file_policy = :file_policy,
                blocked_extensions = :blocked_extensions,
                allowed_extensions = :allowed_extensions,
                link_policy = :link_policy,
                allowed_domains = :allowed_domains,
                exempt_admins = :exempt_admins,
                send_warning = :send_warning,
                updated_by = :updated_by,
                updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = :chat_id
        """), params)
    else:
        db.execute(text("""
            INSERT INTO telegram_chat_moderation_settings (
                chat_id, enabled, file_policy, blocked_extensions,
                allowed_extensions, link_policy, allowed_domains,
                exempt_admins, send_warning, updated_by,
                created_at, updated_at
            ) VALUES (
                :chat_id, :enabled, :file_policy, :blocked_extensions,
                :allowed_extensions, :link_policy, :allowed_domains,
                :exempt_admins, :send_warning, :updated_by,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), params)
    db.commit()
    return normalized


def _telegram_text_slice(value: str, offset: int, length: int) -> str:
    """Telegram entity offsets use UTF-16 code units rather than Python indexes."""
    encoded = (value or "").encode("utf-16-le")
    return encoded[offset * 2 : (offset + length) * 2].decode(
        "utf-16-le", errors="ignore"
    )


def _message_urls(message: dict) -> list[str]:
    urls: list[str] = []
    for text_key, entities_key in (
        ("text", "entities"),
        ("caption", "caption_entities"),
    ):
        value = message.get(text_key) or ""
        for entity in message.get(entities_key) or []:
            entity_type = entity.get("type")
            if entity_type == "text_link" and entity.get("url"):
                urls.append(str(entity["url"]))
            elif entity_type == "url":
                urls.append(
                    _telegram_text_slice(
                        value,
                        int(entity.get("offset", 0)),
                        int(entity.get("length", 0)),
                    )
                )
    return urls


def _url_domain(value: str) -> str | None:
    candidate = html.unescape((value or "").strip())
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    elif "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        hostname = urlsplit(candidate).hostname
        if not hostname:
            return None
        return hostname.rstrip(".").encode("idna").decode("ascii").casefold()
    except (ValueError, UnicodeError):
        return None


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    return any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in allowed_domains
    )


def inspect_message(message: dict, policy: dict) -> dict | None:
    """Return the first moderation violation without downloading file contents."""
    document = message.get("document")
    if document and policy["file_policy"] != "allow_all":
        file_name = str(document.get("file_name") or "Unnamed file")
        lowered_name = file_name.casefold()
        mime_type = str(document.get("mime_type") or "").casefold()
        if policy["file_policy"] == "blocklist":
            matched = next(
                (
                    ext
                    for ext in policy["blocked_extensions"]
                    if lowered_name.endswith(ext)
                ),
                None,
            )
            if matched or mime_type in _DANGEROUS_MIME_TYPES:
                label = matched or mime_type or "dangerous file"
                return {
                    "content_type": "document",
                    "file_name": file_name,
                    "domain": None,
                    "reason_code": "blocked_file_type",
                    "blocked_label": label,
                    "reason": f"Blocked file type: {label}",
                }
        elif policy["file_policy"] == "allowlist":
            matched = any(
                lowered_name.endswith(ext)
                for ext in policy["allowed_extensions"]
            )
            if mime_type in _DANGEROUS_MIME_TYPES:
                return {
                    "content_type": "document",
                    "file_name": file_name,
                    "domain": None,
                    "reason_code": "blocked_file_type",
                    "blocked_label": mime_type,
                    "reason": f"Blocked file type: {mime_type}",
                }
            if not matched:
                return {
                    "content_type": "document",
                    "file_name": file_name,
                    "domain": None,
                    "reason_code": "unapproved_file_type",
                    "reason": "This file type is not on the allowed list",
                }

    link_policy = policy["link_policy"]
    if link_policy != "allow_all":
        for raw_url in _message_urls(message):
            domain = _url_domain(raw_url)
            if link_policy == "block_all" or not domain or not _domain_allowed(
                domain, policy["allowed_domains"]
            ):
                return {
                    "content_type": "link",
                    "file_name": None,
                    "domain": domain,
                    "reason_code": (
                        "links_disabled"
                        if link_policy == "block_all"
                        else "unapproved_link"
                    ),
                    "reason": (
                        "Links are not allowed in this group"
                        if link_policy == "block_all"
                        else f"Domain is not allowed: {domain or 'invalid link'}"
                    ),
                }
    return None


def _safe_warning_label(value: object, fallback: str, limit: int = 80) -> str:
    """Escape and shorten user-controlled text before placing it in HTML."""
    label = " ".join(str(value or fallback).split()) or fallback
    if len(label) > limit:
        label = f"{label[: limit - 1].rstrip()}…"
    return html.escape(label)


def _moderation_warning_text(member: str, violation: dict) -> str:
    """Build a concise public warning without repeating unsafe link content."""
    batch_size = max(1, int(violation.get("batch_size") or 1))
    if violation.get("content_type") == "link":
        title = (
            "🔗 <b>Upload removed</b>"
            if batch_size > 1
            else "🔗 <b>Link removed</b>"
        )
        content_line = (
            f"📦 <b>Batch:</b> {batch_size} items; at least one unapproved link"
            if batch_size > 1
            else "🔗 <b>Content:</b> Unapproved link"
        )
        if violation.get("reason_code") == "links_disabled":
            reason = "Links are disabled in this group."
        else:
            reason = (
                "This website is not approved for sharing in this group."
            )
        next_step = (
            "Share information without the link, or ask a group administrator "
            "to approve the website."
        )
        protection_note = (
            "Automatic protection helps prevent phishing, scams, and unsafe "
            "websites."
        )
    else:
        title = (
            "📎 <b>Upload removed</b>"
            if batch_size > 1
            else "📎 <b>File removed</b>"
        )
        file_name = _safe_warning_label(
            violation.get("file_name"),
            "Unnamed file",
        )
        content_line = (
            f"📦 <b>Batch:</b> {batch_size} files; blocked item "
            f"<code>{file_name}</code>"
            if batch_size > 1
            else f"📄 <b>File:</b> <code>{file_name}</code>"
        )
        reason_code = violation.get("reason_code")
        if reason_code == "blocked_file_type":
            blocked_label = _safe_warning_label(
                violation.get("blocked_label"),
                "this file type",
                limit=50,
            )
            reason = (
                f"File type <code>{blocked_label}</code> is blocked by this "
                "group's safety settings."
            )
        elif reason_code == "unapproved_file_type":
            reason = "This file type is not approved for this group."
        else:
            reason = _safe_warning_label(
                violation.get("reason"),
                "This file type is not allowed in this group.",
                limit=160,
            )
        next_step = (
            "Send an approved file type, or ask a group administrator if this "
            "file is required."
        )
        protection_note = (
            "Automatic protection helps prevent malware and unsafe downloads."
        )

    return (
        f"{title}\n\n"
        f"👤 <b>Member:</b> {member}\n"
        f"{content_line}\n"
        f"❓ <b>Why:</b> {reason}\n\n"
        f"✅ <b>What you can do</b>\n"
        f"{next_step}\n\n"
        f"🛡️ <i>{protection_note}</i>"
    )


def _moderation_warning_plain_text(member: str, violation: dict) -> str:
    """Build the same useful warning without Telegram HTML formatting."""
    batch_size = max(1, int(violation.get("batch_size") or 1))
    safe_member = " ".join(str(member or "Member").split())[:100] or "Member"
    if violation.get("content_type") == "link":
        title = "🔗 Upload removed" if batch_size > 1 else "🔗 Link removed"
        content_line = (
            f"📦 Batch: {batch_size} items; at least one unapproved link"
            if batch_size > 1
            else "🔗 Content: Unapproved link"
        )
        reason = (
            "Links are disabled in this group."
            if violation.get("reason_code") == "links_disabled"
            else "This website is not approved for sharing in this group."
        )
        next_step = (
            "Share information without the link, or ask a group administrator "
            "to approve the website."
        )
        protection_note = (
            "Automatic protection helps prevent phishing, scams, and unsafe "
            "websites."
        )
    else:
        title = "📎 Upload removed" if batch_size > 1 else "📎 File removed"
        file_name = " ".join(
            str(violation.get("file_name") or "Unnamed file").split()
        )[:120]
        content_line = (
            f"📦 Batch: {batch_size} files\n📄 Blocked file: {file_name}"
            if batch_size > 1
            else f"📄 File: {file_name}"
        )
        reason_code = violation.get("reason_code")
        if reason_code == "blocked_file_type":
            blocked_label = " ".join(
                str(violation.get("blocked_label") or "this file type").split()
            )[:60]
            reason = (
                f"File type {blocked_label} is blocked by this group's "
                "safety settings."
            )
        elif reason_code == "unapproved_file_type":
            reason = "This file type is not approved for this group."
        else:
            reason = " ".join(
                str(
                    violation.get("reason")
                    or "This file type is not allowed in this group."
                ).split()
            )[:180]
        next_step = (
            "Send an approved file type, or ask a group administrator if this "
            "file is required."
        )
        protection_note = (
            "Automatic protection helps prevent malware and unsafe downloads."
        )

    return (
        f"{title}\n\n"
        f"👤 Member: {safe_member}\n"
        f"{content_line}\n"
        f"❓ Why: {reason}\n\n"
        f"✅ What you can do\n"
        f"{next_step}\n\n"
        f"🛡️ {protection_note}"
    )


async def _telegram_user_is_admin(
    chat_id: int | str,
    user_id: int | str,
    bot_token: str,
) -> bool:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/getChatMember",
                json={"chat_id": chat_id, "user_id": user_id},
            )
        data = response.json()
        return bool(
            data.get("ok")
            and (data.get("result") or {}).get("status")
            in {"creator", "administrator"}
        )
    except Exception:
        logger.exception("Could not check Telegram administrator status")
        return False


async def _delete_telegram_messages(
    chat_id: int | str,
    message_ids: list[int | str],
    bot_token: str,
) -> tuple[bool, str | None]:
    """Delete one or more messages with one Bot API request when possible."""
    normalized_ids = list(
        dict.fromkeys(
            int(message_id)
            for message_id in message_ids
            if str(message_id or "").isdigit()
        )
    )
    if not normalized_ids:
        return False, "No valid Telegram message IDs"
    method = "deleteMessage" if len(normalized_ids) == 1 else "deleteMessages"
    payload = {"chat_id": chat_id}
    if len(normalized_ids) == 1:
        payload["message_id"] = normalized_ids[0]
    else:
        payload["message_ids"] = normalized_ids[:100]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/{method}",
                json=payload,
            )
        response_data = response.json()
        if response_data.get("ok"):
            return True, None
        description = response_data.get("description") or response.text[:300]
        # Duplicate webhook deliveries can try to remove the same violation.
        # Telegram reports an already-deleted item as "message to delete not
        # found"; the message is gone, so moderation already reached its goal.
        if "message to delete not found" in str(description).casefold():
            return True, None
        return False, description
    except Exception as exc:
        return False, str(exc)


async def _send_moderation_warning(
    message: dict,
    violation: dict,
    bot_token: str,
) -> tuple[bool, str | None]:
    sender = message.get("from") or {}
    sender_id = sender.get("id")
    display_name = (
        sender.get("first_name") or sender.get("username") or "Member"
    )
    if sender_id:
        member = (
            f'<a href="tg://user?id={sender_id}">'
            f"{html.escape(str(display_name))}</a>"
        )
    else:
        member = html.escape(str(display_name))
    warning_payload = {
        "chat_id": (message.get("chat") or {}).get("id"),
        "text": _moderation_warning_text(member, violation),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": True,
    }
    if message.get("message_thread_id") is not None:
        warning_payload["message_thread_id"] = message["message_thread_id"]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=warning_payload,
            )
            response_data = response.json()
            if response_data.get("ok"):
                return True, None

            first_error = (
                response_data.get("description") or response.text[:300]
            )
            # HTML parse failures should never suppress the safety notice.
            fallback_payload = {
                "chat_id": warning_payload["chat_id"],
                "text": _moderation_warning_plain_text(
                    str(display_name),
                    violation,
                ),
                "disable_web_page_preview": True,
                "disable_notification": True,
            }
            if message.get("message_thread_id") is not None:
                fallback_payload["message_thread_id"] = message[
                    "message_thread_id"
                ]
            fallback_response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=fallback_payload,
            )
            fallback_data = fallback_response.json()
            if fallback_data.get("ok"):
                logger.warning(
                    "Telegram moderation warning required plain-text fallback: %s",
                    first_error,
                )
                return True, None
            fallback_error = (
                fallback_data.get("description")
                or fallback_response.text[:300]
            )
            logger.warning(
                "Could not send Telegram moderation warning: %s; fallback: %s",
                first_error,
                fallback_error,
            )
            return False, str(fallback_error)
    except Exception as exc:
        logger.exception("Could not send Telegram moderation warning")
        return False, str(exc)


def _record_event(
    db: Session,
    message: dict,
    violation: dict,
    action: str,
) -> None:
    try:
        sender = message.get("from") or {}
        db.execute(text("""
            INSERT INTO telegram_moderation_events (
                event_id, chat_id, message_id, telegram_user_id, username,
                content_type, file_name, domain, reason, action, created_at
            ) VALUES (
                :event_id, :chat_id, :message_id, :telegram_user_id, :username,
                :content_type, :file_name, :domain, :reason, :action,
                CURRENT_TIMESTAMP
            )
        """), {
            "event_id": str(uuid.uuid4()),
            "chat_id": str((message.get("chat") or {}).get("id") or ""),
            "message_id": str(message.get("message_id") or ""),
            "telegram_user_id": str(sender.get("id") or ""),
            "username": sender.get("username"),
            "content_type": violation["content_type"],
            "file_name": violation.get("file_name"),
            "domain": violation.get("domain"),
            "reason": violation["reason"][:500],
            "action": action,
        })
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record Telegram moderation event")


async def moderate_general_group_message(
    db: Session,
    message: dict,
    bot_token: str,
) -> dict:
    """Remove violations in place while leaving every safe message untouched."""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return {"handled": False}

    policy = get_moderation_policy(db, str(chat_id))
    if not policy["enabled"]:
        return {"handled": False}

    sender = message.get("from") or {}
    sender_id = sender.get("id")
    if sender.get("is_bot"):
        return {"handled": False}

    # Telegram delivers album items as separate updates. Do not quarantine,
    # delete, or repost a safe item: inspection is local and only the
    # specific violating update is removed. This preserves its original sender,
    # timestamp, reply context, reactions, and album presentation.
    violation = inspect_message(message, policy)
    if not violation:
        return {"handled": False}

    # Telegram uses sender_chat for anonymous administrator/group posts.
    sender_chat = message.get("sender_chat") or {}
    if policy["exempt_admins"] and (
        str(sender_chat.get("id") or "") == str(chat_id)
        or (
            sender_id
            and await _telegram_user_is_admin(chat_id, sender_id, bot_token)
        )
    ):
        if violation is not None:
            _record_event(db, message, violation, "administrator_exempted")
        return {"handled": False, "exempted": True}

    delete_ok, delete_error = await _delete_telegram_messages(
        chat_id,
        [message.get("message_id")],
        bot_token,
    )

    action = "deleted" if delete_ok else "delete_failed"
    _record_event(db, message, violation, action)

    if delete_ok and policy["send_warning"]:
        await _send_moderation_warning(message, violation, bot_token)

    if delete_error:
        logger.warning(
            "Telegram moderation could not delete message %s in chat %s: %s",
            message.get("message_id"),
            chat_id,
            delete_error,
        )
    return {
        "handled": True,
        "deleted": delete_ok,
        "reason": violation["reason"],
    }


async def get_bot_moderation_permissions(
    chat_id: str,
    bot_token: str | None,
) -> dict:
    result = {
        "is_admin": False,
        "can_delete_messages": False,
        "can_restrict_members": False,
        "checked": False,
    }
    if not bot_token:
        return result
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            me_response = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getMe"
            )
            me_data = me_response.json()
            bot_id = (me_data.get("result") or {}).get("id")
            if not me_data.get("ok") or not bot_id:
                return result
            member_response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/getChatMember",
                json={"chat_id": chat_id, "user_id": bot_id},
            )
        member_data = member_response.json()
        member = member_data.get("result") or {}
        status = member.get("status")
        result.update(
            {
                "checked": True,
                "is_admin": status in {"creator", "administrator"},
                "can_delete_messages": bool(member.get("can_delete_messages")),
                "can_restrict_members": bool(member.get("can_restrict_members")),
            }
        )
    except Exception:
        logger.exception("Could not check bot moderation permissions")
    return result


async def ensure_moderation_webhook_updates(bot_token: str | None) -> bool:
    """Add edited_message delivery while preserving the bot's existing webhook URL."""
    if not bot_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            info_response = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
            )
            info_data = info_response.json()
            if not info_data.get("ok"):
                return False
            webhook = info_data.get("result") or {}
            webhook_url = webhook.get("url")
            if not webhook_url:
                return False
            current_updates = webhook.get("allowed_updates")
            # Telegram omits allowed_updates when every update type is accepted.
            required_updates = {
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
                "my_chat_member",
                "chat_member",
                "callback_query",
            }
            if current_updates is None or required_updates.issubset(
                current_updates
            ):
                return True
            allowed_updates = list(
                dict.fromkeys(
                    [
                        *current_updates,
                        *required_updates,
                    ]
                )
            )
            update_response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={
                    "url": webhook_url,
                    "allowed_updates": allowed_updates,
                },
            )
            return bool(update_response.json().get("ok"))
    except Exception:
        logger.exception("Could not enable Telegram edited-message updates")
        return False
