"""Insert pending parent registration using only columns that exist in the DB."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..schemas.parents import ParentCreate
from .parent_status import ensure_parent_status_column

logger = logging.getLogger(__name__)

# ORM field name -> value builder key (same names as parents table columns)
_PARENT_INSERT_FIELDS = (
    "uniqueid",
    "username",
    "password",
    "fatherName",
    "motherName",
    "fatherPhone",
    "motherPhone",
    "fatherJob",
    "motherJob",
    "pProvince",
    "pDistrict",
    "pCommune",
    "pVillage",
    "pEmail",
    "pTelegramId",
    "gName",
    "gPhone",
    "gIsThe",
    "gHome",
    "gStreet",
    "gGroup",
    "gProvince",
    "gDistrict",
    "gCommune",
    "gVillage",
    "myChilds",
    "created_at",
    "updated_at",
    "status",
)


def _clip(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len] if max_len > 0 else s


def _clip_or_empty(value: Optional[str], max_len: int) -> str:
    return _clip(value, max_len) or ""


def _build_parent_values(
    parent_data: ParentCreate,
    *,
    username: str,
    password_hash: str,
    unique_id: str,
) -> Dict[str, Any]:
    role = (parent_data.parentRole or "father").lower().strip()
    father_name = _clip_or_empty(parent_data.fatherName, 100)
    mother_name = _clip_or_empty(parent_data.motherName, 100)
    g_name = _clip_or_empty(parent_data.gName, 255)

    if role == "mother" and not mother_name:
        mother_name = g_name or father_name or "Parent"
    if role == "father" and not father_name:
        father_name = mother_name or g_name or "Parent"
    if role == "guardian" and not g_name:
        g_name = mother_name or father_name or "Guardian"

    # The parents model/schema stores these as DATE, not DATETIME. Supplying a
    # real date avoids driver-specific coercion and keeps reloads portable.
    now = date.today()
    pwd = (password_hash or "")[:255]

    return {
        "uniqueid": unique_id[:100],
        "username": username[:25],
        "password": pwd,
        "fatherName": father_name,
        "motherName": mother_name,
        "fatherPhone": _clip(parent_data.fatherPhone, 100),
        "motherPhone": _clip(parent_data.motherPhone, 100),
        "fatherJob": _clip(parent_data.fatherJob, 100),
        "motherJob": _clip(parent_data.motherJob, 100),
        "pProvince": _clip(parent_data.pProvince, 100),
        "pDistrict": _clip(parent_data.pDistrict, 100),
        "pCommune": _clip(parent_data.pCommune, 100),
        "pVillage": _clip(parent_data.pVillage, 100),
        "pEmail": _clip(parent_data.pEmail, 100),
        "pTelegramId": _clip(parent_data.pTelegramId, 50),
        "gName": g_name or None,
        "gPhone": _clip(parent_data.gPhone, 50),
        "gIsThe": _clip(parent_data.gIsThe, 100),
        "gHome": _clip(parent_data.gHome, 100),
        "gStreet": _clip(parent_data.gStreet, 100),
        "gGroup": _clip(parent_data.gGroup, 100),
        "gProvince": _clip(parent_data.gProvince, 100),
        "gDistrict": _clip(parent_data.gDistrict, 100),
        "gCommune": _clip(parent_data.gCommune, 100),
        "gVillage": _clip(parent_data.gVillage, 100),
        "myChilds": _clip(parent_data.myChilds, 255),
        "created_at": now,
        "updated_at": now,
        "status": 0,
    }


def _table_column_map(db: Session) -> Dict[str, Dict[str, Any]]:
    # Inspect through the session's active connection. Inspecting the Engine can
    # borrow/close the same physical SQLite connection and roll back the pending
    # one-use OTP claim before the parent insert commits.
    inspector = inspect(db.connection())
    return {c["name"]: c for c in inspector.get_columns("parents")}


def _apply_nullable_defaults(
    insert_data: Dict[str, Any], table_cols: Dict[str, Dict[str, Any]]
) -> None:
    for col_name, col_info in table_cols.items():
        if col_name not in insert_data:
            continue
        val = insert_data[col_name]
        if val is not None:
            continue
        if col_info.get("nullable", True):
            continue
        col_type = str(col_info.get("type", "")).upper()
        if "INT" in col_type or "BOOL" in col_type:
            insert_data[col_name] = 0
        else:
            insert_data[col_name] = ""


def insert_pending_parent(
    db: Session,
    parent_data: ParentCreate,
    *,
    username: str,
    password_hash: str,
    unique_id: str,
) -> int:
    """
    Insert a new parent row (status pending). Uses only columns present in `parents`.
    Raises the underlying DB exception on failure.
    """
    ensure_parent_status_column(db)
    table_cols = _table_column_map(db)
    if not table_cols:
        raise RuntimeError("parents table not found")

    values = _build_parent_values(
        parent_data,
        username=username,
        password_hash=password_hash,
        unique_id=unique_id,
    )

    insert_data = {
        key: values[key]
        for key in _PARENT_INSERT_FIELDS
        if key in table_cols and key in values
    }
    _apply_nullable_defaults(insert_data, table_cols)

    if not insert_data:
        raise RuntimeError("No matching columns to insert into parents")

    col_names = ", ".join(f"`{c}`" for c in insert_data)
    placeholders = ", ".join(f":{c}" for c in insert_data)
    sql = f"INSERT INTO parents ({col_names}) VALUES ({placeholders})"

    try:
        db.execute(text(sql), insert_data)
        db.commit()
    except Exception:
        db.rollback()
        raise

    row = db.execute(
        text("SELECT id FROM parents WHERE username = :u ORDER BY id DESC LIMIT 1"),
        {"u": username},
    ).fetchone()
    if not row:
        row = db.execute(
            text("SELECT id FROM parents WHERE uniqueid = :uid ORDER BY id DESC LIMIT 1"),
            {"uid": unique_id},
        ).fetchone()
    if not row:
        raise RuntimeError("Parent row inserted but id could not be loaded")
    return int(row[0])


def format_parent_save_error(exc: Exception) -> str:
    """User-safe message with a hint when we recognize the DB error."""
    raw = str(exc)
    lower = raw.lower()
    if "unknown column" in lower:
        m = re.search(r"Unknown column '([^']+)'", raw, re.I)
        col = m.group(1) if m else "column"
        return (
            f"Database schema is missing '{col}' on parents table. "
            "Restart the API server to apply migrations, then try again."
        )
    if "duplicate" in lower and "username" in lower:
        return "Username already registered. Please choose another username."
    if "duplicate" in lower:
        return "This registration already exists. Please contact support."
    if "data too long" in lower:
        return "One of the fields is too long. Please shorten and try again."
    if "cannot be null" in lower or "doesn't have a default" in lower:
        return "Required parent information is missing. Please complete all required fields."
    return "Could not save parent registration. Please try again."


def notify_app_admins_new_parent_registration(
    parent_id: int,
    username: str,
) -> None:
    """
    Push + in-app notification to unlocked app admins (super admins included).
    Uses a fresh DB session — safe for BackgroundTasks after the request ends.
    """
    from ..core.database import SessionLocal
    from ..services import notification_service

    db = SessionLocal()
    try:
        admin_targets = notification_service.get_app_admin_user_ids(
            db, super_admin_only=False
        )
        if not admin_targets:
            logger.warning(
                "No unlocked app admins to notify for parent registration %s",
                parent_id,
            )
            return

        tokens = notification_service.get_app_admin_device_tokens(
            db, super_admin_only=False
        )
        display = username or f"Parent #{parent_id}"
        notification_service.send_notification(
            device_tokens=tokens,
            title="New Parent Registration",
            body=f"A new parent ({display}) registered and is pending approval.",
            data={
                "type": "new_user_registration",
                "user_role": "parent",
                "target_user_id": str(parent_id),
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=admin_targets,
            redirect_route="pending_parent_registrations",
        )
        logger.info(
            "Parent registration push: parent_id=%s admins=%s tokens=%s",
            parent_id,
            len(admin_targets),
            len(tokens),
        )
    except Exception as exc:
        logger.error(
            "Failed to notify app admins of parent registration %s: %s",
            parent_id,
            exc,
            exc_info=True,
        )
    finally:
        db.close()


async def notify_telegram_new_parent_registration(parent_id: int) -> None:
    """
    Send Telegram alert using telegram_attendance_settings (same bot/chat as attendance).
    Safe for BackgroundTasks — uses a fresh DB session.
    """
    from ..core.database import SessionLocal
    from ..models.parent import Parent
    from ..models.telegram_attendance_settings import TelegramAttendanceSettings
    from ..services.telegram_notification_service import TelegramNotificationService

    db = SessionLocal()
    try:
        settings = db.query(TelegramAttendanceSettings).first()
        if not settings or not settings.enabled:
            return
        if not settings.bot_token or not settings.chat_id:
            return

        parent = db.query(Parent).filter(Parent.id == parent_id).first()
        if parent is None:
            logger.warning(
                "Parent %s not found for Telegram registration notification", parent_id
            )
            return

        await TelegramNotificationService.send_parent_registration_notification(
            bot_token=settings.bot_token,
            chat_id=settings.chat_id,
            parent_id=parent.id,
            username=parent.username or "",
            father_name=parent.fatherName,
            mother_name=parent.motherName,
            father_phone=parent.fatherPhone,
            mother_phone=parent.motherPhone,
            guardian_name=parent.gName,
            guardian_phone=parent.gPhone,
        )
    except Exception as exc:
        logger.error(
            "Failed Telegram notification for parent registration %s: %s",
            parent_id,
            exc,
            exc_info=True,
        )
    finally:
        db.close()


def notify_parent_registration_approved(
    parent_id: int,
    display_name: str,
) -> None:
    """Push + in-app notification when admin approves a pending parent account."""
    from ..core.database import SessionLocal
    from ..services import notification_service

    db = SessionLocal()
    try:
        tokens = notification_service.get_parent_user_device_tokens(db, parent_id)
        label = display_name or f"Parent #{parent_id}"
        notification_service.send_notification(
            device_tokens=tokens,
            title="Account Approved",
            body=f"Your parent account ({label}) has been approved. You now have full access to the app.",
            data={
                "type": "parent_registration_approved",
                "parent_id": str(parent_id),
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=[{"id": parent_id, "user_type": "parent"}],
            redirect_route="home",
        )
        logger.info(
            "Parent approval push: parent_id=%s tokens=%s",
            parent_id,
            len(tokens),
        )
    except Exception as exc:
        logger.error(
            "Failed to notify parent %s of approval: %s",
            parent_id,
            exc,
            exc_info=True,
        )
    finally:
        db.close()


def notify_parent_registration_rejected(
    parent_id: int,
    display_name: str,
    device_tokens: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Push when admin rejects a pending parent registration.
    Call before the parent row is deleted; pass [device_tokens] captured earlier.
    """
    from ..core.database import SessionLocal
    from ..services import notification_service

    db = SessionLocal()
    try:
        tokens = device_tokens
        if not tokens:
            tokens = notification_service.get_parent_user_device_tokens(db, parent_id)
        label = display_name or f"Parent #{parent_id}"
        notification_service.send_notification(
            device_tokens=tokens,
            title="Registration Not Approved",
            body=f"Your parent account registration ({label}) was not approved. Please contact the school if you have questions.",
            data={
                "type": "parent_registration_rejected",
                "parent_id": str(parent_id),
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=None,
            user_ids=None,
        )
        logger.info(
            "Parent rejection push: parent_id=%s tokens=%s",
            parent_id,
            len(tokens or []),
        )
    except Exception as exc:
        logger.error(
            "Failed to notify parent %s of rejection: %s",
            parent_id,
            exc,
            exc_info=True,
        )
    finally:
        db.close()


def ensure_parent_registration_audit_table(db: Session) -> None:
    """Audit log for parent approve/reject (rejected rows are deleted from parents)."""
    try:
        bind = db.get_bind()
        inspector = inspect(bind)
        if "parent_registration_audit" in inspector.get_table_names():
            return
        dialect = bind.dialect.name
        logger.info("Creating parent_registration_audit table...")
        if dialect == "mysql":
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS parent_registration_audit (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        parent_id INT NOT NULL,
                        action VARCHAR(32) NOT NULL,
                        admin_user_id INT NULL,
                        admin_display VARCHAR(255) NULL,
                        parent_snapshot TEXT NULL,
                        students_count INT NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL,
                        INDEX idx_pra_action (action),
                        INDEX idx_pra_created (created_at),
                        INDEX idx_pra_parent (parent_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            )
        else:
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS parent_registration_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        parent_id INTEGER NOT NULL,
                        action VARCHAR(32) NOT NULL,
                        admin_user_id INTEGER,
                        admin_display VARCHAR(255),
                        parent_snapshot TEXT,
                        students_count INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
        db.commit()
        logger.info("Created parent_registration_audit table")
    except Exception as e:
        db.rollback()
        logger.error("ensure_parent_registration_audit_table failed: %s", e)
        raise


def log_parent_registration_audit(
    db: Session,
    *,
    action: str,
    parent_id: int,
    admin_user_id: Optional[int],
    admin_display: Optional[str],
    parent_snapshot: Dict[str, Any],
    students_count: int,
) -> None:
    """Persist approve/reject for admin history (call before delete on reject)."""
    ensure_parent_registration_audit_table(db)
    try:
        db.execute(
            text(
                """
                INSERT INTO parent_registration_audit (
                    parent_id, action, admin_user_id, admin_display,
                    parent_snapshot, students_count, created_at
                )
                VALUES (
                    :parent_id, :action, :admin_user_id, :admin_display,
                    :parent_snapshot, :students_count, :created_at
                )
                """
            ),
            {
                "parent_id": parent_id,
                "action": action,
                "admin_user_id": admin_user_id,
                "admin_display": admin_display,
                "parent_snapshot": json.dumps(parent_snapshot, default=str),
                "students_count": students_count,
                "created_at": datetime.utcnow(),
            },
        )
    except Exception as e:
        logger.warning("Could not write parent_registration_audit: %s", e)
