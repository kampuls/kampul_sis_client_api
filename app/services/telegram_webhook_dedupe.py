"""Database-backed idempotency for Telegram webhook side effects.

Telegram retries webhook updates when a response is delayed or interrupted. It can
also describe one membership change using both a service ``message`` and a
``chat_member`` update.  The API runs multiple workers, so an in-memory set cannot
reliably prevent either form of duplicate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

_READY_BINDS: set[int] = set()
_EVENT_RETENTION_DAYS = 7


def _utc_now_naive() -> datetime:
    """Return UTC in the naive format used by the existing MySQL schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bot_token_fingerprint(bot_token: str) -> str:
    """Identify a bot without persisting any part of its secret token."""
    return hashlib.sha256(bot_token.encode("utf-8")).hexdigest()[:16]


def telegram_update_event_key(bot_token: str, update_id: int | str) -> str:
    return f"update:{bot_token_fingerprint(bot_token)}:{update_id}"


def telegram_membership_event_key(
    bot_token: str,
    action: str,
    chat_id: int | str,
    user_id: int | str,
) -> str:
    """Build the shared key used by message and chat_member update shapes."""
    return (
        f"membership:{action}:{bot_token_fingerprint(bot_token)}:"
        f"{chat_id}:{user_id}"
    )


def ensure_telegram_webhook_events_table(db: Session) -> bool:
    """Create the event-claim table when a deployment missed its migration."""
    bind = db.get_bind()
    bind_id = id(bind)
    if bind_id in _READY_BINDS:
        return True

    try:
        if bind.dialect.name == "mysql":
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS telegram_webhook_events (
                    event_key VARCHAR(255) PRIMARY KEY,
                    event_type VARCHAR(50) NOT NULL,
                    update_id BIGINT NULL,
                    chat_id VARCHAR(100) NULL,
                    telegram_user_id VARCHAR(100) NULL,
                    claim_token VARCHAR(32) NOT NULL,
                    processed_at DATETIME(6) NOT NULL,
                    INDEX idx_twe_processed_at (processed_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """))
        else:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS telegram_webhook_events (
                    event_key VARCHAR(255) PRIMARY KEY,
                    event_type VARCHAR(50) NOT NULL,
                    update_id BIGINT NULL,
                    chat_id VARCHAR(100) NULL,
                    telegram_user_id VARCHAR(100) NULL,
                    claim_token VARCHAR(32) NOT NULL,
                    processed_at DATETIME NOT NULL
                )
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_twe_processed_at
                ON telegram_webhook_events(processed_at)
            """))

        # Telegram retries are short-lived. Retaining a week provides a generous
        # safety window without allowing this table to grow forever.
        db.execute(
            text("""
                DELETE FROM telegram_webhook_events
                WHERE processed_at < :retention_cutoff
            """),
            {
                "retention_cutoff": _utc_now_naive()
                - timedelta(days=_EVENT_RETENTION_DAYS)
            },
        )
        db.commit()
        _READY_BINDS.add(bind_id)
        return True
    except Exception:
        db.rollback()
        logger.exception("Could not initialize Telegram webhook event deduplication")
        return False


def claim_telegram_webhook_event(
    db: Session,
    *,
    event_key: str,
    event_type: str,
    update_id: int | None = None,
    chat_id: int | str | None = None,
    telegram_user_id: int | str | None = None,
    cooldown_seconds: int | None = None,
) -> bool:
    """Atomically claim an event before performing an external side effect.

    Returns ``True`` only for the worker that owns the claim. A cooldown is used
    for semantic membership events so a genuine later rejoin can be processed,
    while exact Telegram update IDs remain unique for the retention period.

    The function deliberately fails open if the dedupe table is unavailable: a
    schema problem must not disable every bot response.
    """
    if not event_key or len(event_key) > 255:
        logger.warning("Invalid Telegram webhook event key; processing without dedupe")
        return True
    if not ensure_telegram_webhook_events_table(db):
        return True

    now = _utc_now_naive()
    try:
        claim_token = uuid.uuid4().hex
        values = {
            "event_key": event_key,
            "event_type": event_type[:50],
            "update_id": update_id,
            "chat_id": str(chat_id) if chat_id is not None else None,
            "telegram_user_id": (
                str(telegram_user_id)
                if telegram_user_id is not None
                else None
            ),
            "claim_token": claim_token,
            "processed_at": now,
        }
        dialect = db.get_bind().dialect.name
        if cooldown_seconds is not None:
            values["cooldown_cutoff"] = now - timedelta(
                seconds=max(0, cooldown_seconds)
            )
            if dialect == "mysql":
                # Keep processed_at last: MySQL evaluates assignments from left
                # to right, and every condition must inspect the old timestamp.
                insert_sql = """
                    INSERT INTO telegram_webhook_events (
                        event_key, event_type, update_id, chat_id,
                        telegram_user_id, claim_token, processed_at
                    ) VALUES (
                        :event_key, :event_type, :update_id, :chat_id,
                        :telegram_user_id, :claim_token, :processed_at
                    ) ON DUPLICATE KEY UPDATE
                        event_type = IF(
                            processed_at < :cooldown_cutoff,
                            VALUES(event_type), event_type
                        ),
                        update_id = IF(
                            processed_at < :cooldown_cutoff,
                            VALUES(update_id), update_id
                        ),
                        chat_id = IF(
                            processed_at < :cooldown_cutoff,
                            VALUES(chat_id), chat_id
                        ),
                        telegram_user_id = IF(
                            processed_at < :cooldown_cutoff,
                            VALUES(telegram_user_id), telegram_user_id
                        ),
                        claim_token = IF(
                            processed_at < :cooldown_cutoff,
                            VALUES(claim_token), claim_token
                        ),
                        processed_at = IF(
                            processed_at < :cooldown_cutoff,
                            VALUES(processed_at), processed_at
                        )
                """
            else:
                insert_sql = """
                    INSERT INTO telegram_webhook_events (
                        event_key, event_type, update_id, chat_id,
                        telegram_user_id, claim_token, processed_at
                    ) VALUES (
                        :event_key, :event_type, :update_id, :chat_id,
                        :telegram_user_id, :claim_token, :processed_at
                    ) ON CONFLICT (event_key) DO UPDATE SET
                        event_type = excluded.event_type,
                        update_id = excluded.update_id,
                        chat_id = excluded.chat_id,
                        telegram_user_id = excluded.telegram_user_id,
                        claim_token = excluded.claim_token,
                        processed_at = excluded.processed_at
                    WHERE telegram_webhook_events.processed_at
                          < :cooldown_cutoff
                """
        else:
            if dialect == "mysql":
                insert_sql = """
                    INSERT IGNORE INTO telegram_webhook_events (
                        event_key, event_type, update_id, chat_id,
                        telegram_user_id, claim_token, processed_at
                    ) VALUES (
                        :event_key, :event_type, :update_id, :chat_id,
                        :telegram_user_id, :claim_token, :processed_at
                    )
                """
            elif dialect == "postgresql":
                insert_sql = """
                    INSERT INTO telegram_webhook_events (
                        event_key, event_type, update_id, chat_id,
                        telegram_user_id, claim_token, processed_at
                    ) VALUES (
                        :event_key, :event_type, :update_id, :chat_id,
                        :telegram_user_id, :claim_token, :processed_at
                    ) ON CONFLICT (event_key) DO NOTHING
                """
            else:
                insert_sql = """
                    INSERT OR IGNORE INTO telegram_webhook_events (
                        event_key, event_type, update_id, chat_id,
                        telegram_user_id, claim_token, processed_at
                    ) VALUES (
                        :event_key, :event_type, :update_id, :chat_id,
                        :telegram_user_id, :claim_token, :processed_at
                    )
                """

        db.execute(text(insert_sql), values)
        owner = db.execute(
            text("""
                SELECT claim_token
                FROM telegram_webhook_events
                WHERE event_key = :event_key
            """),
            {"event_key": event_key},
        ).scalar()
        claimed = owner == claim_token
        db.commit()
        return claimed
    except Exception:
        db.rollback()
        _READY_BINDS.discard(id(db.get_bind()))
        logger.exception(
            "Could not claim Telegram webhook event %s; processing without dedupe",
            event_key,
        )
        return True
