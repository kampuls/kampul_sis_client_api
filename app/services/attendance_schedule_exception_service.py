"""
Resolve per-date attendance schedule exceptions (daily overrides).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from ..models.attendance_model import (
    AttendanceRecord,
    AttendanceSchedule,
    AttendanceScheduleException,
    AttendanceScheduleExceptionEnrollment,
)
from ..models.user import User

logger = logging.getLogger(__name__)

CAMBODIA_TZ = timezone(timedelta(hours=7))

DAY_MAP = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
DAY_MAP_FULL = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}

PRESET_SESSIONS: Dict[str, List[Dict[str, str]]] = {
    "morning_only": [{"start": "08:00", "end": "12:00"}],
    "afternoon_only": [{"start": "13:00", "end": "17:00"}],
    "full_day": [
        {"start": "08:00", "end": "12:00"},
        {"start": "13:00", "end": "17:00"},
    ],
}

RECURRENCE_ONCE = "once"
RECURRENCE_DATE_RANGE = "date_range"
RECURRENCE_MONTHLY = "monthly"
VALID_RECURRENCE_TYPES = {
    RECURRENCE_ONCE,
    RECURRENCE_DATE_RANGE,
    RECURRENCE_MONTHLY,
}


def _time_str_to_minutes(value: object) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            parsed = datetime.strptime(raw.upper(), fmt)
            return parsed.hour * 60 + parsed.minute
        except Exception:
            pass
    parts = raw.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1][:2])
        except Exception:
            return None
    return None


def _sessions_from_day_config(day_config: object) -> List[Dict[str, Any]]:
    if not isinstance(day_config, dict):
        return []
    sessions = day_config.get("sessions")
    if isinstance(sessions, list):
        cleaned: List[Dict[str, Any]] = []
        for session in sessions:
            if not isinstance(session, dict):
                continue
            start = session.get("start") or session.get("start_time")
            end = session.get("end") or session.get("end_time")
            if _time_str_to_minutes(start) is None or _time_str_to_minutes(end) is None:
                continue
            cleaned.append({"start": start, "end": end})
        if cleaned:
            return cleaned

    if day_config.get("mode") == "half_day" or day_config.get("type") == "half":
        return [{"start": "08:00", "end": "12:00"}]
    if day_config.get("active", True) and day_config.get("mode") != "not_working":
        return [
            {"start": "08:00", "end": "12:00"},
            {"start": "13:00", "end": "17:00"},
        ]
    return []


def _parse_exception_sessions(raw: object) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, list):
        cleaned: List[Dict[str, Any]] = []
        for session in raw:
            if not isinstance(session, dict):
                continue
            start = session.get("start") or session.get("start_time")
            end = session.get("end") or session.get("end_time")
            if _time_str_to_minutes(start) is None or _time_str_to_minutes(end) is None:
                continue
            cleaned.append({"start": str(start), "end": str(end)})
        return cleaned
    return []


def ensure_schedule_exceptions_table(db: Session) -> None:
    try:
        db.execute(text("SELECT 1 FROM attendance_schedule_exceptions LIMIT 1"))
    except Exception:
        pass
    else:
        _ensure_schedule_exception_metadata_columns(db)
        return

    try:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS attendance_schedule_exceptions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    exception_date DATE NOT NULL,
                    end_date DATE NULL,
                    user_id INT NULL,
                    branch_id INT NULL,
                    department_id INT NULL,
                    is_foreigner INT NULL,
                    recurrence_type VARCHAR(30) NULL,
                    exception_type VARCHAR(50) NOT NULL DEFAULT 'sessions_override',
                    sessions JSON NULL,
                    reason VARCHAR(500) NULL,
                    created_by INT NULL,
                    is_active INT NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_exc_date (exception_date),
                    INDEX idx_exc_end_date (end_date),
                    INDEX idx_exc_user (user_id),
                    INDEX idx_exc_branch (branch_id),
                    INDEX idx_exc_dept (department_id),
                    INDEX idx_exc_foreigner (is_foreigner),
                    INDEX idx_exc_active (is_active)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS attendance_schedule_exceptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        exception_date DATE NOT NULL,
                        end_date DATE NULL,
                        user_id INTEGER NULL,
                        branch_id INTEGER NULL,
                        department_id INTEGER NULL,
                        is_foreigner INTEGER NULL,
                        recurrence_type VARCHAR(30) NULL,
                        exception_type VARCHAR(50) NOT NULL DEFAULT 'sessions_override',
                        sessions TEXT NULL,
                        reason VARCHAR(500) NULL,
                        created_by INTEGER NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to create attendance_schedule_exceptions table")
            return

    _ensure_schedule_exception_metadata_columns(db)


def _ensure_schedule_exception_metadata_columns(db: Session) -> None:
    _ensure_is_foreigner_column(db)
    _ensure_recurrence_type_column(db)
    _ensure_self_enrollment_column(db)
    _ensure_allow_outside_workplace_column(db)
    _ensure_bilingual_content_columns(db)
    _ensure_schedule_exception_enrollments_table(db)


def _ensure_allow_outside_workplace_column(db: Session) -> None:
    try:
        db.execute(
            text(
                "SELECT allow_outside_workplace "
                "FROM attendance_schedule_exceptions LIMIT 1"
            )
        )
        return
    except Exception:
        db.rollback()

    for ddl in (
        "ALTER TABLE attendance_schedule_exceptions "
        "ADD COLUMN allow_outside_workplace INT NOT NULL DEFAULT 0",
        "ALTER TABLE attendance_schedule_exceptions "
        "ADD COLUMN allow_outside_workplace INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            db.execute(text(ddl))
            db.commit()
            return
        except Exception:
            db.rollback()


def _ensure_bilingual_content_columns(db: Session) -> None:
    definitions = {
        "title_en": "VARCHAR(150) NULL",
        "title_km": "VARCHAR(150) NULL",
        "reason_en": "VARCHAR(500) NULL",
        "reason_km": "VARCHAR(500) NULL",
    }
    for column_name, definition in definitions.items():
        try:
            db.execute(
                text(
                    f"SELECT {column_name} FROM "
                    "attendance_schedule_exceptions LIMIT 1"
                )
            )
            continue
        except Exception:
            db.rollback()
        try:
            db.execute(
                text(
                    "ALTER TABLE attendance_schedule_exceptions "
                    f"ADD COLUMN {column_name} {definition}"
                )
            )
            db.commit()
        except Exception:
            db.rollback()


def _ensure_self_enrollment_column(db: Session) -> None:
    try:
        db.execute(
            text(
                "SELECT self_enrollment_enabled "
                "FROM attendance_schedule_exceptions LIMIT 1"
            )
        )
        return
    except Exception:
        db.rollback()

    for ddl in (
        "ALTER TABLE attendance_schedule_exceptions "
        "ADD COLUMN self_enrollment_enabled INT NOT NULL DEFAULT 0",
        "ALTER TABLE attendance_schedule_exceptions "
        "ADD COLUMN self_enrollment_enabled INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            db.execute(text(ddl))
            db.commit()
            return
        except Exception:
            db.rollback()


def _ensure_schedule_exception_enrollments_table(db: Session) -> None:
    try:
        db.execute(
            text(
                "SELECT 1 FROM attendance_schedule_exception_enrollments LIMIT 1"
            )
        )
        return
    except Exception:
        db.rollback()

    mysql_ddl = """
        CREATE TABLE IF NOT EXISTS attendance_schedule_exception_enrollments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            exception_id INT NOT NULL,
            user_id INT NOT NULL,
            occurrence_date DATE NOT NULL,
            enrolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_attendance_exception_enrollment_user_date
                (user_id, occurrence_date),
            INDEX idx_attendance_exception_enrollment_exception (exception_id),
            INDEX idx_attendance_exception_enrollment_date (occurrence_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    sqlite_ddl = """
        CREATE TABLE IF NOT EXISTS attendance_schedule_exception_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exception_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            occurrence_date DATE NOT NULL,
            enrolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_attendance_exception_enrollment_user_date
                UNIQUE (user_id, occurrence_date)
        )
    """
    try:
        db.execute(text(mysql_ddl))
        db.commit()
    except Exception:
        db.rollback()
        try:
            db.execute(text(sqlite_ddl))
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Failed to create attendance schedule exception enrollments table"
            )


def _ensure_is_foreigner_column(db: Session) -> None:
    try:
        db.execute(text("SELECT is_foreigner FROM attendance_schedule_exceptions LIMIT 1"))
        return
    except Exception:
        pass
    for ddl in (
        "ALTER TABLE attendance_schedule_exceptions ADD COLUMN is_foreigner INT NULL",
        "ALTER TABLE attendance_schedule_exceptions ADD COLUMN is_foreigner INTEGER NULL",
    ):
        try:
            db.execute(text(ddl))
            db.commit()
            return
        except Exception:
            db.rollback()


def _ensure_recurrence_type_column(db: Session) -> None:
    try:
        needs_backfill = db.execute(
            text(
                """
                SELECT 1 FROM attendance_schedule_exceptions
                WHERE recurrence_type IS NULL OR recurrence_type = ''
                LIMIT 1
                """
            )
        ).scalar() is not None
    except Exception:
        db.rollback()
        for ddl in (
            "ALTER TABLE attendance_schedule_exceptions ADD COLUMN recurrence_type VARCHAR(30) NULL",
            "ALTER TABLE attendance_schedule_exceptions ADD COLUMN recurrence_type TEXT NULL",
        ):
            try:
                db.execute(text(ddl))
                db.commit()
                break
            except Exception:
                db.rollback()
        else:
            logger.exception("Failed to add schedule-exception recurrence_type column")
            return
        needs_backfill = True

    if not needs_backfill:
        return

    # Preserve the meaning of existing rows. The old editor used end_date only
    # for a bounded date range and left it null for a single date.
    try:
        db.execute(
            text(
                """
                UPDATE attendance_schedule_exceptions
                SET recurrence_type = CASE
                    WHEN end_date IS NOT NULL AND end_date > exception_date
                        THEN 'date_range'
                    ELSE 'once'
                END
                WHERE recurrence_type IS NULL OR recurrence_type = ''
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to backfill schedule-exception recurrence types")


def schedule_exception_recurrence_type(
    row: AttendanceScheduleException,
) -> str:
    raw = str(getattr(row, "recurrence_type", "") or "").strip().lower()
    if raw in VALID_RECURRENCE_TYPES:
        return raw
    if row.end_date is not None and row.exception_date is not None:
        if row.end_date > row.exception_date:
            return RECURRENCE_DATE_RANGE
    return RECURRENCE_ONCE


def schedule_exception_occurs_on(
    row: AttendanceScheduleException,
    target_date: date,
) -> bool:
    start = row.exception_date
    if start is None or target_date < start:
        return False
    end = row.end_date
    if end is not None and target_date > end:
        return False

    recurrence_type = schedule_exception_recurrence_type(row)
    if recurrence_type == RECURRENCE_DATE_RANGE:
        return end is not None
    if recurrence_type == RECURRENCE_MONTHLY:
        # A rule created on the 29th/30th/31st skips shorter months rather than
        # silently moving to a different calendar day.
        return target_date.day == start.day
    return target_date == start


def schedule_exception_occurs_in_range(
    row: AttendanceScheduleException,
    start_date: date,
    end_date: date,
) -> bool:
    if end_date < start_date:
        return False
    current = start_date
    while current <= end_date:
        if schedule_exception_occurs_on(row, current):
            return True
        current += timedelta(days=1)
    return False


def _user_matches_nationality_filter(
    row: AttendanceScheduleException,
    user: User,
) -> bool:
    if row.is_foreigner is None:
        return True
    user_val = getattr(user, "isForeigner", None)
    if user_val is None:
        return False
    return int(row.is_foreigner) == int(user_val)


def _exception_scope_priority(
    row: AttendanceScheduleException,
    user: User,
) -> Optional[Tuple[int, int, int]]:
    if not _user_matches_nationality_filter(row, user):
        return None
    base: Optional[int] = None
    if row.user_id is not None:
        if int(row.user_id) == int(user.id):  # type: ignore[arg-type]
            base = 4
        else:
            return None
    elif row.department_id is not None:
        if user.departmentId is not None and int(row.department_id) == int(user.departmentId):  # type: ignore[arg-type]
            base = 3
        else:
            return None
    elif row.branch_id is not None:
        if user.workplace is not None and int(row.branch_id) == int(user.workplace):  # type: ignore[arg-type]
            base = 2
        else:
            return None
    else:
        base = 1

    nationality_rank = 1 if row.is_foreigner is not None else 0
    return (base, nationality_rank, int(row.id))  # type: ignore[arg-type]


def is_self_enrollment_exception(row: AttendanceScheduleException) -> bool:
    return bool(getattr(row, "self_enrollment_enabled", 0))


def _is_valid_self_enrollment_choice(
    row: AttendanceScheduleException,
) -> bool:
    exception_type = str(row.exception_type or "").strip().lower()
    if exception_type == "day_off":
        return True
    return exception_type == "sessions_override" and bool(
        _parse_exception_sessions(row.sessions)
    )


def get_schedule_exception_enrollment(
    db: Session,
    user_id: int,
    target_date: date,
) -> Optional[AttendanceScheduleExceptionEnrollment]:
    ensure_schedule_exceptions_table(db)
    return (
        db.query(AttendanceScheduleExceptionEnrollment)
        .filter(
            AttendanceScheduleExceptionEnrollment.user_id == int(user_id),
            AttendanceScheduleExceptionEnrollment.occurrence_date == target_date,
        )
        .first()
    )


def resolve_enrolled_schedule_exception(
    db: Session,
    user: User,
    target_date: date,
) -> Optional[AttendanceScheduleException]:
    enrollment = get_schedule_exception_enrollment(db, int(user.id), target_date)
    if enrollment is None:
        return None
    # Once an employee has started attendance using the choice, keep the exact
    # schedule stable even if an administrator later closes the opt-in window.
    return (
        db.query(AttendanceScheduleException)
        .filter(AttendanceScheduleException.id == enrollment.exception_id)
        .first()
    )


def available_self_enrollment_exceptions(
    db: Session,
    user: User,
    target_date: date,
) -> List[AttendanceScheduleException]:
    ensure_schedule_exceptions_table(db)
    rows = (
        db.query(AttendanceScheduleException)
        .filter(
            AttendanceScheduleException.is_active == 1,
            AttendanceScheduleException.self_enrollment_enabled == 1,
            AttendanceScheduleException.exception_date <= target_date,
            or_(
                AttendanceScheduleException.end_date.is_(None),
                AttendanceScheduleException.end_date >= target_date,
            ),
        )
        .all()
    )
    matches = [
        row
        for row in rows
        if schedule_exception_occurs_on(row, target_date)
        and _exception_scope_priority(row, user) is not None
        and _is_valid_self_enrollment_choice(row)
    ]
    matches.sort(
        key=lambda row: (
            _exception_scope_priority(row, user) or (0, 0, 0)
        ),
        reverse=True,
    )
    return matches


def enroll_in_schedule_exception_for_attendance(
    db: Session,
    user: User,
    target_date: date,
    exception_id: int,
) -> AttendanceScheduleExceptionEnrollment:
    """Validate and stage an immutable opt-in inside the check-in transaction."""
    existing = get_schedule_exception_enrollment(db, int(user.id), target_date)
    if existing is not None:
        if int(existing.exception_id) == int(exception_id):
            return existing
        raise ValueError("schedule_exception_selection_locked")

    attendance_started = (
        db.query(AttendanceRecord.id)
        .filter(
            AttendanceRecord.user_id == int(user.id),
            AttendanceRecord.attendance_date == target_date,
        )
        .first()
        is not None
    )
    if attendance_started:
        raise ValueError("attendance_already_started")

    choice = (
        db.query(AttendanceScheduleException)
        .filter(AttendanceScheduleException.id == int(exception_id))
        .first()
    )
    if (
        choice is None
        or not choice.is_active
        or not is_self_enrollment_exception(choice)
        or not schedule_exception_occurs_on(choice, target_date)
        or _exception_scope_priority(choice, user) is None
        or not _is_valid_self_enrollment_choice(choice)
    ):
        raise ValueError("schedule_exception_not_available")

    enrollment = AttendanceScheduleExceptionEnrollment(
        exception_id=int(choice.id),
        user_id=int(user.id),
        occurrence_date=target_date,
    )
    db.add(enrollment)
    db.flush()
    return enrollment


def resolve_schedule_exception(
    db: Session,
    user: User,
    target_date: date,
) -> Optional[AttendanceScheduleException]:
    ensure_schedule_exceptions_table(db)
    enrolled = resolve_enrolled_schedule_exception(db, user, target_date)
    if enrolled is not None:
        return enrolled
    rows = (
        db.query(AttendanceScheduleException)
        .filter(
            AttendanceScheduleException.is_active == 1,
            AttendanceScheduleException.exception_date <= target_date,
            or_(
                AttendanceScheduleException.end_date.is_(None),
                AttendanceScheduleException.end_date >= target_date,
            ),
        )
        .all()
    )
    candidates: List[Tuple[Tuple[int, int, int], AttendanceScheduleException]] = []
    for row in rows:
        if is_self_enrollment_exception(row):
            continue
        if not schedule_exception_occurs_on(row, target_date):
            continue
        priority = _exception_scope_priority(row, user)
        if priority is None:
            continue
        candidates.append((priority, row))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2]))
    return candidates[0][1]


def _weekly_day_config(schedule: AttendanceSchedule, target_date: date) -> Dict[str, Any]:
    wc = schedule.weekly_config  # type: ignore[assignment]
    if isinstance(wc, str):
        try:
            wc = json.loads(wc)
        except Exception:
            wc = {}
    if not isinstance(wc, dict):
        return {}

    wd = target_date.weekday()
    day_config = (
        wc.get(DAY_MAP[wd])
        or wc.get(DAY_MAP_FULL[wd])
        or wc.get(DAY_MAP_FULL[wd].capitalize())
        or {}
    )
    return day_config if isinstance(day_config, dict) else {}


def match_exception_from_rows(
    rows: List[AttendanceScheduleException],
    user: User,
    target_date: date,
    *,
    enrolled_exception_id: Optional[int] = None,
) -> Optional[AttendanceScheduleException]:
    if enrolled_exception_id is not None:
        return next(
            (
                row
                for row in rows
                if int(row.id) == int(enrolled_exception_id)
                and schedule_exception_occurs_on(row, target_date)
            ),
            None,
        )
    candidates: List[Tuple[Tuple[int, int, int], AttendanceScheduleException]] = []
    for row in rows:
        if is_self_enrollment_exception(row):
            continue
        if not schedule_exception_occurs_on(row, target_date):
            continue
        if not row.is_active:
            continue
        priority = _exception_scope_priority(row, user)
        if priority is None:
            continue
        candidates.append((priority, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2]))
    return candidates[0][1]


def get_effective_day_attendance_with_exception(
    user: User,
    target_date: date,
    *,
    schedule: Optional[AttendanceSchedule],
    exception: Optional[AttendanceScheduleException],
) -> Dict[str, Any]:
    """Pure-python day resolution when schedule/exception rows are preloaded."""
    if exception is not None:
        exc_type = (exception.exception_type or "sessions_override").strip().lower()
        if exc_type == "day_off":
            return {
                "is_active_day": False,
                "sessions": [],
                "day_type": "Exception Day Off",
                "source": "exception",
                "exception_id": int(exception.id),  # type: ignore[arg-type]
                "exception_type": exc_type,
                "exception_reason": exception.reason,
                "exception_date": exception.exception_date.isoformat()
                if exception.exception_date
                else None,
            }
        sessions = _parse_exception_sessions(exception.sessions)
        day_type = "Half Day" if len(sessions) == 1 else f"{len(sessions)}-Session"
        return {
            "is_active_day": bool(sessions),
            "sessions": sessions,
            "day_type": day_type if sessions else "Exception (No Sessions)",
            "source": "exception",
            "exception_id": int(exception.id),  # type: ignore[arg-type]
            "exception_type": exc_type,
            "exception_reason": exception.reason,
            "exception_date": exception.exception_date.isoformat()
            if exception.exception_date
            else None,
        }

    if schedule is None:
        return {
            "is_active_day": False,
            "sessions": [],
            "day_type": "No Schedule",
            "source": "none",
            "exception_id": None,
            "exception_type": None,
            "exception_reason": None,
            "exception_date": None,
        }

    day_config = _weekly_day_config(schedule, target_date)
    if not day_config or day_config.get("mode") == "not_working" or not day_config.get("active", True):
        return {
            "is_active_day": False,
            "sessions": [],
            "day_type": "Non-Working Day",
            "source": "weekly",
            "exception_id": None,
            "exception_type": None,
            "exception_reason": None,
            "exception_date": None,
        }

    sessions = _sessions_from_day_config(day_config)
    if not sessions:
        return {
            "is_active_day": False,
            "sessions": [],
            "day_type": "Non-Working Day",
            "source": "weekly",
            "exception_id": None,
            "exception_type": None,
            "exception_reason": None,
            "exception_date": None,
        }

    day_type = "Half Day" if len(sessions) == 1 else f"{len(sessions)}-Session"
    return {
        "is_active_day": True,
        "sessions": sessions,
        "day_type": day_type,
        "source": "weekly",
        "exception_id": None,
        "exception_type": None,
        "exception_reason": None,
        "exception_date": None,
    }


def get_effective_day_attendance(
    db: Session,
    user: User,
    target_date: date,
    *,
    schedule: Optional[AttendanceSchedule] = None,
) -> Dict[str, Any]:
    """
    Effective sessions for a user on a date.
    Schedule exceptions take priority over the recurring weekly template.
    """
    if schedule is None:
        from ..api.v1.employee_attendance import get_effective_schedule

        schedule = get_effective_schedule(db, user, target_date=target_date)

    exception = resolve_schedule_exception(db, user, target_date)
    return get_effective_day_attendance_with_exception(
        user,
        target_date,
        schedule=schedule,
        exception=exception,
    )


def get_weekly_day_attendance(
    db: Session,
    user: User,
    target_date: date,
    *,
    schedule: Optional[AttendanceSchedule] = None,
) -> Dict[str, Any]:
    """Weekly template only — ignores date-specific exceptions."""
    if schedule is None:
        from ..api.v1.employee_attendance import get_effective_schedule

        schedule = get_effective_schedule(db, user, target_date=target_date)
    return get_effective_day_attendance_with_exception(
        user,
        target_date,
        schedule=schedule,
        exception=None,
    )


def representative_user_for_exception_scope(
    db: Session,
    *,
    user_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    department_id: Optional[int] = None,
    is_foreigner: Optional[int] = None,
) -> User:
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user is not None:
            return user

    query = db.query(User).filter(User.status == 1)  # type: ignore
    if branch_id is not None:
        query = query.filter(User.workplace == branch_id)  # type: ignore
    if department_id is not None:
        query = query.filter(User.departmentId == department_id)  # type: ignore
    if is_foreigner is not None:
        query = query.filter(User.isForeigner == is_foreigner)  # type: ignore

    user = query.order_by(User.id.asc()).first()
    if user is not None:
        return user

    stub = User(id=0)  # type: ignore[arg-type]
    if branch_id is not None:
        stub.workplace = branch_id  # type: ignore[assignment]
    elif department_id is not None:
        stub.departmentId = department_id  # type: ignore[assignment]
    if is_foreigner is not None:
        stub.isForeigner = is_foreigner  # type: ignore[assignment]
    return stub


def sessions_for_user_date(
    db: Session,
    user: User,
    target_date: date,
    *,
    schedule: Optional[AttendanceSchedule] = None,
) -> List[Dict[str, Any]]:
    return get_effective_day_attendance(
        db, user, target_date, schedule=schedule
    ).get("sessions", [])
