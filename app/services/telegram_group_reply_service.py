"""Configurable automatic replies for authorized Telegram General Groups."""

from __future__ import annotations

import json
import logging
import html as html_lib
import os
from html.parser import HTMLParser
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


DEFAULT_GROUP_REPLY_FEATURES = [
    {
        "key": "location",
        "enabled": True,
        "triggers": [
            "/location",
            "/locations",
            "/map",
            "/address",
            "location",
            "locations",
            "school location",
            "school locations",
            "where is the school",
            "where is school",
            "school map",
            "map",
            "maps",
            "campus",
            "campuses",
            "address",
            "addresses",
            "school address",
            "ទីតាំង",
            "ទីតាំងសាលា",
            "location ទីតាំង",
            "ទីតាំង location",
            "សាលានៅឯណា",
            "ផែនទី",
            "សាខា",
            "អាសយដ្ឋាន",
            "អាស័យដ្ឋាន",
            "អាសយដ្ឋានសាលា",
            "អាស័យដ្ឋានសាលា",
        ],
        "reply_text": "",
    },
    {
        "key": "phone",
        "enabled": True,
        "triggers": [
            "/phone",
            "/contact",
            "phone",
            "phones",
            "telephone",
            "telephone number",
            "tel",
            "hotline",
            "school phone",
            "school phone number",
            "phone number",
            "phone numbers",
            "contact",
            "contacts",
            "contact number",
            "contact numbers",
            "ទូរស័ព្ទ",
            "លេខទូរស័ព្ទ",
            "លេខទូរស័ព្ទសាលា",
            "លេខទំនាក់ទំនង",
            "លេខទំនាក់ទំនងសាលា",
            "លេខសាលា",
            "ទំនាក់ទំនង",
        ],
        "reply_text": "",
    },
    {
        "key": "school",
        "enabled": True,
        "triggers": [
            "/school",
            "/info",
            "school info",
            "school information",
            "school contact",
            "ព័ត៌មានសាលា",
            "ព័ត៌មានអំពីសាលា",
        ],
        "reply_text": "",
    },
    {
        "key": "app",
        "enabled": True,
        "triggers": [
            "/app",
            "/download",
            "/downloadapp",
            "app",
            "school app",
            "school application",
            "pama app",
            "pamais app",
            "mobile app",
            "download app",
            "download the app",
            "download school app",
            "app download",
            "android app",
            "ios app",
            "iphone app",
            "កម្មវិធី",
            "កម្មវិធីសាលា",
            "កម្មវិធីទូរស័ព្ទ",
            "កម្មវិធីប៉ាម៉ា",
            "ទាញយកកម្មវិធី",
            "ទាញយកកម្មវិធីសាលា",
        ],
        "reply_text": "",
    },
]

_FEATURE_KEYS = tuple(feature["key"] for feature in DEFAULT_GROUP_REPLY_FEATURES)
_schema_ready_for: set[int] = set()

_PUBLIC_API_BASE_URL = (
    os.getenv("PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    or "https://pamais.duckdns.org"
)
APP_SMART_DOWNLOAD_URL = f"{_PUBLIC_API_BASE_URL}/app/download"

_TELEGRAM_HTML_TAGS = {
    "a",
    "b",
    "blockquote",
    "code",
    "del",
    "em",
    "i",
    "ins",
    "pre",
    "s",
    "strike",
    "strong",
    "tg-spoiler",
    "u",
}


class _TelegramHTMLValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.output: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _TELEGRAM_HTML_TAGS:
            raise ValueError(f"Unsupported Telegram formatting tag: <{tag}>")
        if tag == "a":
            if len(attrs) != 1 or attrs[0][0] != "href" or not attrs[0][1]:
                raise ValueError("Telegram links must use <a href=\"URL\">text</a>")
            href = str(attrs[0][1]).strip()
            scheme = urlsplit(href).scheme.casefold()
            if scheme not in {"http", "https", "tg", "mailto"}:
                raise ValueError("Telegram links must use http, https, tg, or mailto")
            self.output.append(
                f'<a href="{html_lib.escape(href, quote=True)}">'
            )
        elif attrs:
            raise ValueError(f"Formatting tag <{tag}> does not support attributes")
        else:
            self.output.append(f"<{tag}>")
        self.stack.append(tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        raise ValueError(f"Telegram formatting tag <{tag}> cannot be self-closing")

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            raise ValueError(f"Telegram formatting tag </{tag}> is not balanced")
        self.stack.pop()
        self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.output.append(html_lib.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if name not in {"amp", "gt", "lt", "quot"}:
            raise ValueError(f"Unsupported HTML entity: &{name};")
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")

    def close(self) -> None:
        super().close()
        if self.stack:
            raise ValueError(
                f"Telegram formatting tag <{self.stack[-1]}> is not closed"
            )


def validate_telegram_reply_html(value: str) -> None:
    """Validate the supported Telegram HTML subset before it is saved."""
    parser = _TelegramHTMLValidator()
    try:
        parser.feed(value)
        parser.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Reply message contains invalid Telegram formatting") from exc


def render_telegram_reply_html(value: str) -> str:
    """Return validated Telegram HTML with ordinary text safely escaped."""
    parser = _TelegramHTMLValidator()
    try:
        parser.feed(value)
        parser.close()
        return "".join(parser.output)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Reply message contains invalid Telegram formatting") from exc


def build_default_app_reply_html(
    download_url: str = APP_SMART_DOWNLOAD_URL,
) -> str:
    """Build the safe built-in School App reply around one official smart link."""
    safe_url = html_lib.escape(download_url.strip(), quote=True)
    return f"""📱 <b>Download the PAMA International School App</b>

Stay connected to school from your phone. Depending on your account and available services, the app provides access to:

✅ School activities and announcements
✅ Attendance and academic progress
✅ Events and real-time updates
✅ Services for students, parents, teachers, and employees

🔗 <a href="{safe_url}"><b>Download the School App</b></a>

<i>This is one official smart link:</i>
• iPhone or iPad → opens the App Store
• Android phone or tablet → opens Google Play
• Computer → shows both download choices

🔒 <b>For your safety:</b> use only the official link above. Do not install APK files or apps shared by unknown people in the group."""


def normalize_group_reply_trigger(value: str) -> str:
    """Normalize a short Telegram message for safe exact-trigger matching."""
    normalized = (
        (value or "")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\ufeff", "")
        .casefold()
        .strip()
    )
    normalized = " ".join(normalized.split())
    if normalized.startswith("/") and "@" in normalized:
        command, *rest = normalized.split(" ", 1)
        normalized = command.split("@", 1)[0]
        if rest:
            normalized = f"{normalized} {rest[0]}"
    return normalized.strip(" \t\r\n?!.,，、។៖")


def _copy_default_features() -> list[dict]:
    return [
        {
            "key": feature["key"],
            "enabled": feature["enabled"],
            "triggers": list(feature["triggers"]),
            "reply_text": feature["reply_text"],
        }
        for feature in DEFAULT_GROUP_REPLY_FEATURES
    ]


def default_group_reply_settings(chat_id: str) -> dict:
    return {
        "chat_id": str(chat_id),
        "enabled": True,
        "features": _copy_default_features(),
    }


def normalize_group_reply_settings(settings: dict, chat_id: str) -> dict:
    defaults = default_group_reply_settings(chat_id)
    raw_features = settings.get("features", defaults["features"])
    if not isinstance(raw_features, list):
        raise ValueError("Reply features must be a list")

    raw_by_key: dict[str, dict] = {}
    for raw_feature in raw_features:
        if not isinstance(raw_feature, dict):
            raise ValueError("Each reply feature must be an object")
        key = str(raw_feature.get("key") or "")
        if key not in _FEATURE_KEYS:
            raise ValueError(f"Unsupported reply feature: {key or 'missing key'}")
        if key in raw_by_key:
            raise ValueError(f"Duplicate reply feature: {key}")
        raw_by_key[key] = raw_feature

    normalized_features = []
    trigger_owners: dict[str, str] = {}
    for default_feature in defaults["features"]:
        key = default_feature["key"]
        raw_feature = raw_by_key.get(key, default_feature)
        raw_triggers = raw_feature.get("triggers", default_feature["triggers"])
        if not isinstance(raw_triggers, list):
            raise ValueError(f"Triggers for {key} must be a list")
        if len(raw_triggers) > 50:
            raise ValueError(f"{key} supports at most 50 trigger phrases")

        triggers = []
        seen = set()
        for raw_trigger in raw_triggers:
            trigger = str(raw_trigger).strip()
            normalized_trigger = normalize_group_reply_trigger(trigger)
            if not normalized_trigger:
                continue
            if len(trigger) > 80:
                raise ValueError("Each trigger phrase must be 80 characters or less")
            if normalized_trigger not in seen:
                existing_owner = trigger_owners.get(normalized_trigger)
                if existing_owner and existing_owner != key:
                    raise ValueError(
                        f'Trigger phrase "{trigger}" is already used by '
                        f"{existing_owner}"
                    )
                triggers.append(trigger)
                seen.add(normalized_trigger)
                trigger_owners[normalized_trigger] = key

        feature_enabled = bool(raw_feature.get("enabled", True))
        if feature_enabled and not triggers:
            raise ValueError(f"Add at least one trigger phrase for {key}")

        reply_text = str(raw_feature.get("reply_text") or "").strip()
        if len(reply_text) > 4000:
            raise ValueError(f"Reply text for {key} must be 4000 characters or less")
        if reply_text:
            validate_telegram_reply_html(reply_text)

        normalized_features.append(
            {
                "key": key,
                "enabled": feature_enabled,
                "triggers": triggers,
                "reply_text": reply_text,
            }
        )

    return {
        "chat_id": str(chat_id),
        "enabled": bool(settings.get("enabled", defaults["enabled"])),
        "features": normalized_features,
    }


def match_group_reply_feature(value: str, settings: dict) -> dict | None:
    """Return the enabled feature matching the whole message, if any."""
    if not settings.get("enabled", True):
        return None
    normalized_value = normalize_group_reply_trigger(value)
    if not normalized_value:
        return None
    for feature in settings.get("features") or []:
        if not feature.get("enabled", True):
            continue
        if any(
            normalize_group_reply_trigger(str(trigger)) == normalized_value
            for trigger in feature.get("triggers") or []
        ):
            return feature
    return None


def match_default_group_reply_feature(value: str) -> dict | None:
    return match_group_reply_feature(
        value,
        default_group_reply_settings("private"),
    )


def ensure_group_reply_table(db: Session) -> None:
    bind_key = id(db.get_bind())
    if bind_key in _schema_ready_for:
        return
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_group_reply_settings (
                chat_id VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN NOT NULL,
                features TEXT NOT NULL,
                updated_by INTEGER NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()
        _schema_ready_for.add(bind_key)
    except Exception:
        db.rollback()
        logger.exception("Failed to initialize Telegram group reply settings")
        raise


def get_group_reply_settings(db: Session, chat_id: str) -> dict:
    ensure_group_reply_table(db)
    row = db.execute(text("""
        SELECT enabled, features
        FROM telegram_group_reply_settings
        WHERE chat_id = :chat_id
        LIMIT 1
    """), {"chat_id": str(chat_id)}).fetchone()
    if not row:
        return default_group_reply_settings(str(chat_id))
    try:
        features = json.loads(str(row[1]))
    except (TypeError, ValueError, json.JSONDecodeError):
        features = _copy_default_features()
    return normalize_group_reply_settings(
        {"enabled": bool(row[0]), "features": features},
        str(chat_id),
    )


def save_group_reply_settings(
    db: Session,
    chat_id: str,
    settings: dict,
    updated_by: int | None = None,
) -> dict:
    ensure_group_reply_table(db)
    normalized = normalize_group_reply_settings(settings, str(chat_id))
    params = {
        "chat_id": str(chat_id),
        "enabled": normalized["enabled"],
        "features": json.dumps(normalized["features"], ensure_ascii=False),
        "updated_by": updated_by,
    }
    existing = db.execute(text("""
        SELECT chat_id
        FROM telegram_group_reply_settings
        WHERE chat_id = :chat_id
        LIMIT 1
    """), {"chat_id": str(chat_id)}).fetchone()
    if existing:
        db.execute(text("""
            UPDATE telegram_group_reply_settings
            SET enabled = :enabled,
                features = :features,
                updated_by = :updated_by,
                updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = :chat_id
        """), params)
    else:
        db.execute(text("""
            INSERT INTO telegram_group_reply_settings (
                chat_id, enabled, features, updated_by, created_at, updated_at
            ) VALUES (
                :chat_id, :enabled, :features, :updated_by,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), params)
    db.commit()
    return normalized
