"""
Marks API endpoints for entering and managing student marks.
Based on the Python Telegram bot implementation.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional, List, Dict, Any
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
import logging

from ...services.marks_utils import (
    get_input_monthly_subject_ids,
    INPUT_SUBJECTS_FORMULA_REFERENCE,
    SUBJECTS_REFERENCE_EXAM_CODES,
)
from ...core import get_db
from ...auth import get_current_active_user
from ...services.utils import get_password_hash, verify_password

router = APIRouter()
logger = logging.getLogger(__name__)


def _user_field(current_user, field: str, default=None):
    if isinstance(current_user, dict):
        return current_user.get(field, default)
    return getattr(current_user, field, default)


def _current_user_id(current_user) -> int:
    user_id = _user_field(current_user, "id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authenticated user id missing")
    return int(user_id)


def _ensure_mark_lock_tables(db: Session) -> None:
    """Create mark lock support tables if this live DB missed startup migration."""
    db.execute(
        text("""
            CREATE TABLE IF NOT EXISTS mark_lock_passcodes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                passcode_hash VARCHAR(255) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_mark_lock_passcodes_user (user_id)
            )
        """)
    )
    db.execute(
        text("""
            CREATE TABLE IF NOT EXISTS mark_entry_locks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                program_id INT NOT NULL,
                grade_id INT NOT NULL,
                grade_type_id INT NULL,
                academic_id INT NOT NULL,
                marks_system_id INT NOT NULL,
                subject_id INT NOT NULL,
                locked_by INT NOT NULL,
                locked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                unlocked_at DATETIME NULL,
                unlocked_by INT NULL,
                is_locked TINYINT(1) NOT NULL DEFAULT 1,
                INDEX idx_mark_entry_locks_context (
                    program_id, grade_id, grade_type_id, academic_id,
                    marks_system_id, subject_id
                ),
                INDEX idx_mark_entry_locks_locked_by (locked_by)
            )
        """)
    )
    db.execute(
        text("""
            CREATE TABLE IF NOT EXISTS mark_lock_attempts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                failed_attempts INT NOT NULL DEFAULT 0,
                penalty_level INT NOT NULL DEFAULT 0,
                locked_until DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_mark_lock_attempts_user (user_id),
                INDEX idx_mark_lock_attempts_locked_until (locked_until)
            )
        """)
    )
    db.commit()


def _has_marks_for_context(
    db: Session,
    program_id: int,
    grade_id: int,
    academic_id: int,
    marks_system_id: int,
    subject_id: int,
) -> bool:
    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM marks_input
            WHERE program_id = :program_id
              AND grade_id = :grade_id
              AND academic_id = :academic_id
              AND marks_system_id = :marks_system_id
              AND subject_id = :subject_id
              AND marks IS NOT NULL
        """),
        {
            "program_id": program_id,
            "grade_id": grade_id,
            "academic_id": academic_id,
            "marks_system_id": marks_system_id,
            "subject_id": subject_id,
        },
    ).scalar()
    return int(count or 0) > 0


def _get_active_mark_lock(
    db: Session,
    program_id: int,
    grade_id: int,
    grade_type_id: Optional[int],
    academic_id: int,
    marks_system_id: int,
    subject_id: int,
):
    return db.execute(
        text("""
            SELECT ml.id, ml.locked_by, ml.locked_at,
                   COALESCE(NULLIF(CONCAT_WS(' ', NULLIF(u.kName, ''), NULLIF(u.eName, '')), ''), u.username, 'Unknown') AS locked_by_name,
                   COALESCE(u.kName, '') AS locked_by_kname,
                   COALESCE(u.eName, '') AS locked_by_ename
            FROM mark_entry_locks ml
            LEFT JOIN users u ON u.id = ml.locked_by
            WHERE ml.program_id = :program_id
              AND ml.grade_id = :grade_id
              AND (
                    (:grade_type_id IS NULL AND ml.grade_type_id IS NULL)
                    OR ml.grade_type_id = :grade_type_id
                  )
              AND ml.academic_id = :academic_id
              AND ml.marks_system_id = :marks_system_id
              AND ml.subject_id = :subject_id
              AND ml.is_locked = 1
              AND ml.unlocked_at IS NULL
            ORDER BY ml.id DESC
            LIMIT 1
        """),
        {
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "academic_id": academic_id,
            "marks_system_id": marks_system_id,
            "subject_id": subject_id,
        },
    ).fetchone()


def _verify_user_mark_passcode(db: Session, user_id: int, passcode: Optional[str]) -> bool:
    if not passcode:
        return False
    row = db.execute(
        text("SELECT passcode_hash FROM mark_lock_passcodes WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).fetchone()
    if not row or not row[0]:
        return False
    try:
        return verify_password(str(passcode), row[0])
    except Exception:
        return False


def _is_weak_mark_passcode(passcode: str) -> bool:
    if len(passcode) != 6 or not passcode.isdigit():
        return True
    if len(set(passcode)) == 1:
        return True
    sequential = "0123456789"
    reverse_sequential = "9876543210"
    return passcode in sequential or passcode in reverse_sequential


def _format_wait_message(seconds: int) -> str:
    seconds = max(1, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = (seconds + 59) // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = (minutes + 59) // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = (hours + 23) // 24
    return f"{days} day{'s' if days != 1 else ''}"


def _assert_mark_passcode_not_blocked(db: Session, user_id: int) -> None:
    row = db.execute(
        text("""
            SELECT GREATEST(0, TIMESTAMPDIFF(SECOND, NOW(), locked_until)) AS remaining_seconds
            FROM mark_lock_attempts
            WHERE user_id = :user_id
              AND locked_until IS NOT NULL
              AND locked_until > NOW()
        """),
        {"user_id": user_id},
    ).fetchone()
    if not row:
        return
    remaining = int(row[0] or 0)
    raise HTTPException(
        status_code=429,
        detail=f"Too many incorrect passcode attempts. Please wait {_format_wait_message(remaining)} and try again.",
    )


def _clear_mark_passcode_attempts(db: Session, user_id: int) -> None:
    db.execute(
        text("DELETE FROM mark_lock_attempts WHERE user_id = :user_id"),
        {"user_id": user_id},
    )


def _record_failed_mark_passcode_attempt(db: Session, user_id: int) -> None:
    row = db.execute(
        text("""
            SELECT failed_attempts, penalty_level
            FROM mark_lock_attempts
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).fetchone()

    failed_attempts = int(row[0] or 0) if row else 0
    penalty_level = int(row[1] or 0) if row else 0
    lock_minutes = 0
    next_penalty_level = penalty_level

    if penalty_level <= 0:
        failed_attempts += 1
        if failed_attempts >= 3:
            lock_minutes = 3
            failed_attempts = 0
            next_penalty_level = 1
    elif penalty_level == 1:
        lock_minutes = 60
        failed_attempts = 0
        next_penalty_level = 2
    else:
        lock_minutes = 1440
        failed_attempts = 0
        next_penalty_level = 3

    if row:
        if lock_minutes:
            db.execute(
                text(f"""
                    UPDATE mark_lock_attempts
                    SET failed_attempts = 0,
                        penalty_level = :penalty_level,
                        locked_until = DATE_ADD(NOW(), INTERVAL {lock_minutes} MINUTE)
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id, "penalty_level": next_penalty_level},
            )
        else:
            db.execute(
                text("""
                    UPDATE mark_lock_attempts
                    SET failed_attempts = :failed_attempts,
                        penalty_level = :penalty_level,
                        locked_until = NULL
                    WHERE user_id = :user_id
                """),
                {
                    "user_id": user_id,
                    "failed_attempts": failed_attempts,
                    "penalty_level": next_penalty_level,
                },
            )
    else:
        if lock_minutes:
            db.execute(
                text(f"""
                    INSERT INTO mark_lock_attempts (
                        user_id, failed_attempts, penalty_level, locked_until
                    )
                    VALUES (
                        :user_id, 0, :penalty_level,
                        DATE_ADD(NOW(), INTERVAL {lock_minutes} MINUTE)
                    )
                """),
                {"user_id": user_id, "penalty_level": next_penalty_level},
            )
        else:
            db.execute(
                text("""
                    INSERT INTO mark_lock_attempts (
                        user_id, failed_attempts, penalty_level, locked_until
                    )
                    VALUES (:user_id, :failed_attempts, :penalty_level, NULL)
                """),
                {
                    "user_id": user_id,
                    "failed_attempts": failed_attempts,
                    "penalty_level": next_penalty_level,
                },
            )

    db.commit()

    if lock_minutes:
        raise HTTPException(
            status_code=429,
            detail=f"Incorrect passcode too many times. Please wait {_format_wait_message(lock_minutes * 60)} before trying again.",
        )
    remaining = max(0, 3 - failed_attempts) if penalty_level <= 0 else 0
    if remaining:
        raise HTTPException(
            status_code=403,
            detail=f"Incorrect lock passcode. {remaining} attempt{'s' if remaining != 1 else ''} left.",
        )
    raise HTTPException(status_code=403, detail="Incorrect lock passcode")


def _assert_mark_context_writable(
    db: Session,
    program_id: int,
    grade_id: int,
    grade_type_id: Optional[int],
    academic_id: int,
    marks_system_id: int,
    subject_id: int,
    passcode: Optional[str],
) -> None:
    _ensure_mark_lock_tables(db)
    lock = _get_active_mark_lock(
        db, program_id, grade_id, grade_type_id, academic_id, marks_system_id, subject_id
    )
    if not lock:
        return
    locked_by = int(lock[1])
    if _verify_user_mark_passcode(db, locked_by, passcode):
        return
    raise HTTPException(
        status_code=423,
        detail={
            "code": "MARK_CONTEXT_LOCKED",
            "message": "This mark entry is locked. Enter the locker passcode to continue.",
            "locked_by": locked_by,
            "locked_by_name": lock[3] or "Unknown",
            "locked_by_kname": lock[4] or "",
            "locked_by_ename": lock[5] or "",
        },
    )


def safe_decimal(value, default=Decimal("0")):
    """Safely convert value to Decimal."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace(" ", "").strip()
            if not value:
                return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def round_decimal_to_2_places(value: Decimal) -> Decimal:
    """Round decimal to 2 decimal places."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_to_audit_value(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(round_decimal_to_2_places(safe_decimal(value)))
    except Exception:
        return str(value)


def _mark_values_equal(old_value, new_value) -> bool:
    if old_value is None and new_value is None:
        return True
    if old_value is None or new_value is None:
        return False
    return round_decimal_to_2_places(safe_decimal(old_value)) == round_decimal_to_2_places(
        safe_decimal(new_value)
    )


def _get_current_user_name(current_user) -> str:
    khmer_name = (getattr(current_user, "kName", None) or "").strip()
    english_name = (getattr(current_user, "eName", None) or "").strip()
    username = (getattr(current_user, "username", None) or "").strip()
    return " ".join([p for p in [khmer_name, english_name] if p]) or username or "Unknown"


def _log_mark_audit(
    db: Session,
    current_user,
    action_type: str,
    entity_id: int,
    student_id: int,
    program_id: int,
    grade_id: int,
    grade_type_id: Optional[int],
    academic_id: int,
    subject_id: int,
    marks_system_id: int,
    old_mark,
    new_mark,
):
    """Insert a mark change row into the shared audit table."""
    try:
        from .attendance_audit import format_cambodia_datetime
        import json

        now_utc = datetime.utcnow()
        khmer_time = format_cambodia_datetime(now_utc)

        student_row = db.execute(
            text("SELECT kName, eName FROM students WHERE id = :student_id"),
            {"student_id": student_id},
        ).fetchone()
        student_kname = ""
        student_ename = ""
        student_name = ""
        if student_row:
            student_kname = student_row[0] or ""
            student_ename = student_row[1] or ""
            student_name = " ".join([p for p in [student_kname, student_ename] if p])

        grade_row = db.execute(
            text("SELECT branch_id, grade_name FROM grade WHERE id = :grade_id"),
            {"grade_id": grade_id},
        ).fetchone()
        branch_id = grade_row[0] if grade_row else None
        class_description = grade_row[1] if grade_row else f"Grade {grade_id}"
        if grade_type_id is not None:
            grade_type_row = db.execute(
                text("SELECT type_name FROM grade_type WHERE id = :grade_type_id"),
                {"grade_type_id": grade_type_id},
            ).fetchone()
            grade_type_name = (grade_type_row[0] if grade_type_row else "") or ""
            if grade_type_name.strip():
                class_description = f"{class_description} - {grade_type_name}"

        subject_row = db.execute(
            text("SELECT subject_name, subject_name_us FROM subjects WHERE id = :subject_id"),
            {"subject_id": subject_id},
        ).fetchone()
        subject_name = subject_row[0] if subject_row else f"Subject {subject_id}"
        subject_name_en = (subject_row[1] if subject_row else None) or subject_name

        exam_row = db.execute(
            text("SELECT marks_name FROM marks_system WHERE id = :marks_system_id"),
            {"marks_system_id": marks_system_id},
        ).fetchone()
        exam_name = exam_row[0] if exam_row else f"Exam {marks_system_id}"

        old_display = _decimal_to_audit_value(old_mark)
        new_display = _decimal_to_audit_value(new_mark)
        if action_type == "CREATE":
            change_description = (
                f"Entered {new_display} for {subject_name} ({exam_name})"
            )
        elif action_type == "DELETE":
            change_description = (
                f"Cleared mark {old_display} for {subject_name} ({exam_name})"
            )
        else:
            change_description = (
                f"Changed {subject_name} ({exam_name}) from {old_display} to {new_display}"
            )

        old_payload = {
            "mark": old_display,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "academic_id": academic_id,
            "subject_id": subject_id,
            "subject_name": subject_name,
            "subject_name_en": subject_name_en,
            "marks_system_id": marks_system_id,
            "exam_name": exam_name,
            "actor_kname": getattr(current_user, "kName", None) or "",
            "actor_ename": getattr(current_user, "eName", None) or "",
            "student_kname": student_kname,
            "student_ename": student_ename,
        }
        new_payload = dict(old_payload)
        new_payload["mark"] = new_display

        db.execute(
            text("""
                INSERT INTO attendance_audit_log (
                    user_id, user_name, user_role, action_type, entity_type, entity_id,
                    student_id, student_name, class_id, class_description,
                    created_at_khmer, change_description, branch_id,
                    old_value, new_value
                ) VALUES (
                    :user_id, :user_name, :user_role, :action_type, 'mark_input', :entity_id,
                    :student_id, :student_name, :class_id, :class_description,
                    :created_at_khmer, :change_description, :branch_id,
                    :old_value, :new_value
                )
            """),
            {
                "user_id": getattr(current_user, "id", 0) or 0,
                "user_name": _get_current_user_name(current_user),
                "user_role": str(getattr(current_user, "role", "") or ""),
                "action_type": action_type,
                "entity_id": entity_id or 0,
                "student_id": student_id,
                "student_name": student_name,
                "class_id": grade_id,
                "class_description": class_description,
                "created_at_khmer": khmer_time,
                "change_description": change_description,
                "branch_id": branch_id,
                "old_value": json.dumps(old_payload, ensure_ascii=False),
                "new_value": json.dumps(new_payload, ensure_ascii=False),
            },
        )
    except Exception as audit_error:
        logger.warning(f"Mark audit log skipped: {audit_error}")


@router.get("/marks/exams")
async def get_exams(
    program_id: int = Query(...),
    grade_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    academic_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get available exams (marks systems) for a class with month-based validation."""
    try:
        # Get grade_group_id from grade table
        grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
        grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()

        if not grade_result:
            raise HTTPException(status_code=404, detail="Grade not found")

        grade_group_id = grade_result[0]

        # Get marks_extraday setting
        # Get marks_extraday setting
        extra_days_query = text("SELECT marks_extraday FROM settings LIMIT 1")
        extra_days_result = db.execute(extra_days_query).fetchone()
        try:
            extra_days = (
                int(extra_days_result[0])
                if extra_days_result and extra_days_result[0] is not None
                else 0
            )
        except (ValueError, TypeError):
            extra_days = 0

        # Get current date in Cambodia timezone (UTC+7)
        try:
            if ZoneInfo:
                cambodia_tz = ZoneInfo("Asia/Phnom_Penh")
                current_datetime = datetime.now(cambodia_tz)
            else:
                # Fallback: Use UTC+7 manually
                current_datetime = datetime.utcnow() + timedelta(hours=7)
                cambodia_tz = None
            current_date = current_datetime.date()
        except Exception as e:
            logger.warning(f"Timezone error, using UTC+7: {e}")
            # Fallback to UTC+7 manually if zoneinfo fails
            current_datetime = datetime.utcnow() + timedelta(hours=7)
            current_date = current_datetime.date()
            cambodia_tz = None

        # Get marks systems for this class with for_month
        query = text("""
            SELECT DISTINCT ms.id, ms.marks_name, ms.academic_id, ms.for_month, ms.marks_code
            FROM marks_system ms
            WHERE ms.program_id = :program_id
            AND ms.academic_id = :academic_id
            AND (ms.grade_group_id = :grade_group_id OR ms.grade_group_id IS NULL)
            ORDER BY ms.for_month ASC, ms.marks_name
        """)

        results = db.execute(
            query,
            {
                "program_id": program_id,
                "academic_id": academic_id,
                "grade_group_id": grade_group_id,
            },
        ).fetchall()

        exams = []
        for row in results:
            exam_id = row[0]
            exam_name = row[1]
            academic_id_val = row[2]
            for_month = row[3]  # This is a date object or None
            marks_code = row[4]

            # Calculate availability status
            is_available = False
            reason = None
            start_date = None
            deadline = None

            if for_month:
                # Convert for_month to date if it's datetime
                if isinstance(for_month, datetime):
                    for_month_date = for_month.date()
                elif isinstance(for_month, date):
                    for_month_date = for_month
                else:
                    for_month_date = None

                if for_month_date:
                    # Calculate start date (exam date) and deadline (10 days + extra days from exam date)
                    start_date = for_month_date
                    deadline = start_date + timedelta(days=10 + extra_days - 1)

                    # Make deadline end of day (23:59:59)
                    deadline_datetime = datetime.combine(deadline, time(23, 59, 59))
                    try:
                        if cambodia_tz:
                            deadline_datetime = deadline_datetime.replace(
                                tzinfo=cambodia_tz
                            )
                    except:
                        pass  # Keep datetime without timezone if setting fails

                    # Check if current datetime is within the allowed period
                    # Compare dates first, then datetime if dates match
                    if current_date < start_date:
                        reason = "not_open"  # Before exam date
                    elif current_date > deadline:
                        reason = "deadline_passed"  # After deadline date
                    elif current_date == deadline:
                        # On deadline date, check time
                        if current_datetime <= deadline_datetime:
                            is_available = True
                        else:
                            reason = "deadline_passed"  # After deadline time
                    else:
                        # Between start_date and deadline
                        is_available = True
                else:
                    reason = "no_date"  # No for_month set
            else:
                reason = "no_date"  # No for_month set

            exams.append(
                {
                    "id": exam_id,
                    "name": exam_name,
                    "academic_id": academic_id_val,
                    "is_available": is_available,
                    "reason": reason,
                    "for_month": for_month.isoformat() if for_month else None,
                    "start_date": start_date.isoformat() if start_date else None,
                    "deadline": deadline.isoformat() if deadline else None,
                    "extra_days": extra_days,
                    "code": marks_code,
                }
            )

        # Sort exams based on specific order
        EXAM_ORDER = [
            "MON1",
            "MON2",
            "MON3",
            "MON4",
            "SEM1",
            "RSEM1",
            "MON5",
            "MON6",
            "MON7",
            "MON8",
            "SEM2",
            "RSEM2",
            "YEAR",
        ]

        exams.sort(
            key=lambda x: (
                EXAM_ORDER.index(x["code"]) if x["code"] in EXAM_ORDER else 999,
                x["for_month"] or "",  # Secondary sort by date
                x["name"],  # Tertiary sort by name
            )
        )

        # Get allowed decimals for this program
        allowed_decimals_query = text("""
            SELECT allow FROM decimal_marks_allow 
            WHERE program_id = :program_id
            ORDER BY allow
        """)
        allowed_decimals_result = db.execute(
            allowed_decimals_query, {"program_id": program_id}
        ).fetchall()
        allowed_decimals = (
            [float(row[0]) for row in allowed_decimals_result]
            if allowed_decimals_result
            else []
        )

        return {"success": True, "exams": exams, "allowed_decimals": allowed_decimals}

    except Exception as e:
        logger.error(f"Error fetching exams: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marks/subjects")
async def get_subjects(
    program_id: int = Query(...),
    grade_id: int = Query(...),
    academic_id: int = Query(...),
    marks_system_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Get available subjects for a class.
    If marks_system_id is provided, filters subjects based on that exam's configuration
    (e.g., specific subjects for MON7, MON8).
    """
    try:
        # Get grade_group_id from grade table
        grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
        grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()

        if not grade_result:
            raise HTTPException(status_code=404, detail="Grade not found")

        grade_group_id = grade_result[0]

        subject_ids_filter = []
        is_filtered = False

        if marks_system_id:
            # Check for specific exam subject configuration
            try:
                # Get marks_code for the system
                ms_query = text("SELECT marks_code FROM marks_system WHERE id = :id")
                ms_result = db.execute(ms_query, {"id": marks_system_id}).fetchone()
                marks_code = ms_result[0] if ms_result else ""

                # Get LATEST rule for this context
                rule_query = text("""
                    SELECT id, formula_expression 
                    FROM exam_calculate_sign 
                    WHERE academic_id = :academic_id 
                    AND program_id = :program_id 
                    AND grade_group_id = :grade_group_id 
                    AND marks_system_id = :marks_system_id 
                    AND exam_type = 'input' 
                    AND is_active = 1
                    ORDER BY id DESC
                    LIMIT 1
                """)
                rule_result = db.execute(
                    rule_query,
                    {
                        "academic_id": academic_id,
                        "program_id": program_id,
                        "grade_group_id": grade_group_id,
                        "marks_system_id": marks_system_id,
                    },
                ).fetchone()

                if rule_result:
                    rule_id = rule_result[0]
                    formula = str(rule_result[1] or "").strip()

                    # 1. Check if configured for reference subjects (e.g. MON7, MON8)
                    if (
                        marks_code in SUBJECTS_REFERENCE_EXAM_CODES
                        and formula.lower() == INPUT_SUBJECTS_FORMULA_REFERENCE
                    ):
                        # Use utility helper logic
                        query = text(
                            "SELECT subject_id FROM exam_calculate_sign_subjects WHERE exam_calculate_sign_id = :ecs_id"
                        )
                        sub_result = db.execute(query, {"ecs_id": rule_id}).fetchall()
                        subject_ids_filter = [
                            int(r[0]) for r in sub_result if r[0] is not None
                        ]

                        if subject_ids_filter:
                            is_filtered = True
                        else:
                            # Fallback 1: marks_system_subjects
                            mss_query = text(
                                "SELECT subject_id FROM marks_system_subjects WHERE marks_system_id = :marks_system_id"
                            )
                            mss_result = db.execute(
                                mss_query, {"marks_system_id": marks_system_id}
                            ).fetchall()
                            subject_ids_filter = [
                                int(r[0]) for r in mss_result if r[0] is not None
                            ]
                            if subject_ids_filter:
                                is_filtered = True

            except Exception as e:
                logger.warning(
                    f"Error determining subject filter for marks_system_id {marks_system_id}: {e}"
                )

        # Build query
        base_query = """
            SELECT sg.subject_id, s.subject_name, s.subject_name_us, sg.full_marks, sg.calculate_marks
            FROM subjects_group sg
            JOIN subjects s ON sg.subject_id = s.id
            WHERE sg.academic_id = :academic_id
            AND sg.program_id = :program_id
            AND sg.grade_group_id = :grade_group_id
        """

        params = {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
        }

        if is_filtered and subject_ids_filter:
            base_query += " AND sg.subject_id IN :subject_ids"
            params["subject_ids"] = tuple(subject_ids_filter)

        base_query += " ORDER BY s.subject_name"

        results = db.execute(text(base_query), params).fetchall()

        subjects = []
        for row in results:
            subjects.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "name_en": row[2] or row[1],
                    "full_marks": float(row[3]) if row[3] else 100.0,
                    "calculate_marks": float(row[4]) if row[4] else 100.0,
                }
            )

        return {"success": True, "subjects": subjects}

    except Exception as e:
        logger.error(f"Error fetching subjects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marks/students")
async def get_students_for_marking(
    program_id: int = Query(...),
    grade_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    academic_id: int = Query(...),
    marks_system_id: int = Query(...),
    subject_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get students for marking with their current marks if any."""
    try:
        from ...utils.academic_year import is_historical_academic_year

        # Historical years include now-inactive students
        historical = 1 if is_historical_academic_year(db, academic_id) else 0

        # Get students from learning table
        if grade_type_id:
            student_query = text("""
                SELECT l.studentid, s.id, s.kName, s.eName, s.gender, COALESCE(ur.avatar, '') as avatar
                FROM learning l
                JOIN students s ON l.studentid = s.id
                LEFT JOIN (
                    SELECT user_id, MIN(avatar) AS avatar
                    FROM users_resource
                    WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                    GROUP BY user_id
                ) ur ON ur.user_id = s.id
                WHERE l.programid = :program_id
                AND l.gradeid = :grade_id
                AND l.academicid = :academic_id
                AND l.grade_type_id = :grade_type_id
                AND (s.status = 1 OR :historical = 1)
                ORDER BY s.kName, s.eName
            """)
            params = {
                "program_id": program_id,
                "grade_id": grade_id,
                "academic_id": academic_id,
                "grade_type_id": grade_type_id,
                "historical": historical,
            }
        else:
            student_query = text("""
                SELECT l.studentid, s.id, s.kName, s.eName, s.gender, COALESCE(ur.avatar, '') as avatar
                FROM learning l
                JOIN students s ON l.studentid = s.id
                LEFT JOIN (
                    SELECT user_id, MIN(avatar) AS avatar
                    FROM users_resource
                    WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                    GROUP BY user_id
                ) ur ON ur.user_id = s.id
                WHERE l.programid = :program_id
                AND l.gradeid = :grade_id
                AND l.academicid = :academic_id
                AND l.grade_type_id IS NULL
                AND (s.status = 1 OR :historical = 1)
                ORDER BY s.kName, s.eName
            """)
            params = {
                "program_id": program_id,
                "grade_id": grade_id,
                "academic_id": academic_id,
                "historical": historical,
            }

        students_result = db.execute(student_query, params).fetchall()

        if not students_result:
            return {"success": True, "students": []}

        students = []
        student_ids = [row[1] for row in students_result]

        # Get existing marks if subject_id is provided
        existing_marks = {}
        if subject_id and student_ids:
            marks_query = text("""
                SELECT student_id, marks, id
                FROM marks_input
                WHERE student_id IN :student_ids
                AND program_id = :program_id
                AND grade_id = :grade_id
                AND subject_id = :subject_id
                AND academic_id = :academic_id
                AND marks_system_id = :marks_system_id
                ORDER BY id DESC
            """)
            marks_params = {
                "student_ids": tuple(student_ids),
                "program_id": program_id,
                "grade_id": grade_id,
                "subject_id": subject_id,
                "academic_id": academic_id,
                "marks_system_id": marks_system_id,
            }
            marks_result = db.execute(marks_query, marks_params).fetchall()
            for row in marks_result:
                # ORDER BY id DESC: keep latest row per student only
                if row[0] in existing_marks:
                    continue
                mark_val = row[1]
                existing_marks[row[0]] = {
                    "mark": float(mark_val) if mark_val is not None else None,
                    "id": row[2],
                }

        # Build student list with marks
        for row in students_result:
            student_id = row[1]
            mark_data = existing_marks.get(student_id, {})
            # Convert student_id to string if it's not already
            student_id_str = str(row[0]) if row[0] is not None else None
            students.append(
                {
                    "id": student_id,
                    "student_id": student_id_str,
                    "kName": row[2],
                    "eName": row[3],
                    "gender": row[4],
                    "avatar": row[5] if len(row) > 5 and row[5] else None,
                    "current_mark": mark_data.get("mark"),
                    "mark_id": mark_data.get("id"),
                }
            )

        return {"success": True, "students": students}

    except Exception as e:
        logger.error(f"Error fetching students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marks/lock-status")
def get_mark_lock_status(
    program_id: int = Query(...),
    grade_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    academic_id: int = Query(...),
    marks_system_id: int = Query(...),
    subject_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Return lock status for one class/exam/subject marking context."""
    try:
        _ensure_mark_lock_tables(db)
        lock = _get_active_mark_lock(
            db,
            program_id,
            grade_id,
            grade_type_id,
            academic_id,
            marks_system_id,
            subject_id,
        )
        has_marks = _has_marks_for_context(
            db, program_id, grade_id, academic_id, marks_system_id, subject_id
        )
        current_user_id = _current_user_id(current_user)
        current_user_has_passcode = db.execute(
            text("SELECT 1 FROM mark_lock_passcodes WHERE user_id = :user_id LIMIT 1"),
            {"user_id": current_user_id},
        ).fetchone() is not None
        if not lock:
            return {
                "success": True,
                "is_locked": False,
                "has_marks": has_marks,
                "current_user_has_passcode": current_user_has_passcode,
                "locked_by": None,
                "locked_by_name": None,
                "locked_by_kname": None,
                "locked_by_ename": None,
                "locked_at": None,
                "current_user_is_locker": False,
            }
        return {
            "success": True,
            "is_locked": True,
            "has_marks": has_marks,
            "current_user_has_passcode": current_user_has_passcode,
            "locked_by": int(lock[1]),
            "locked_by_name": lock[3] or "Unknown",
            "locked_by_kname": lock[4] or "",
            "locked_by_ename": lock[5] or "",
            "locked_at": lock[2].isoformat()
            if hasattr(lock[2], "isoformat")
            else str(lock[2]),
            "current_user_is_locker": int(lock[1]) == current_user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading mark lock status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marks/lock-passcode/reset")
def reset_mark_lock_passcode(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Change the current user's one mark-lock passcode."""
    try:
        _ensure_mark_lock_tables(db)
        current_user_id = _current_user_id(current_user)
        current_passcode = str(payload.get("current_passcode") or "").strip()
        new_passcode = str(payload.get("new_passcode") or "").strip()

        if _is_weak_mark_passcode(new_passcode):
            raise HTTPException(
                status_code=400,
                detail="New passcode is too easy. Please use a different 6-digit passcode.",
            )

        row = db.execute(
            text("SELECT passcode_hash FROM mark_lock_passcodes WHERE user_id = :user_id"),
            {"user_id": current_user_id},
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="You do not have a saved lock passcode yet. Create one by locking marks first.",
            )
        if not verify_password(current_passcode, row[0]):
            raise HTTPException(status_code=403, detail="Current passcode is incorrect.")
        if verify_password(new_passcode, row[0]):
            raise HTTPException(
                status_code=400,
                detail="New passcode must be different from your current passcode.",
            )

        db.execute(
            text("""
                UPDATE mark_lock_passcodes
                SET passcode_hash = :passcode_hash
                WHERE user_id = :user_id
            """),
            {
                "user_id": current_user_id,
                "passcode_hash": get_password_hash(new_passcode),
            },
        )
        _clear_mark_passcode_attempts(db, current_user_id)
        db.commit()
        return {"success": True, "message": "Lock passcode updated."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting mark lock passcode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marks/lock-passcode/force-reset")
def force_reset_mark_lock_passcode(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Reset the current user's mark-lock passcode without requiring the old passcode (forgot passcode flow)."""
    try:
        _ensure_mark_lock_tables(db)
        current_user_id = _current_user_id(current_user)
        new_passcode = str(payload.get("new_passcode") or "").strip()

        if _is_weak_mark_passcode(new_passcode):
            raise HTTPException(
                status_code=400,
                detail="New passcode is too easy. Please use a different 6-digit passcode.",
            )

        row = db.execute(
            text("SELECT passcode_hash FROM mark_lock_passcodes WHERE user_id = :user_id"),
            {"user_id": current_user_id},
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="You do not have a saved lock passcode yet. Create one by locking marks first.",
            )

        db.execute(
            text("""
                UPDATE mark_lock_passcodes
                SET passcode_hash = :passcode_hash
                WHERE user_id = :user_id
            """),
            {
                "user_id": current_user_id,
                "passcode_hash": get_password_hash(new_passcode),
            },
        )
        _clear_mark_passcode_attempts(db, current_user_id)
        db.commit()
        return {"success": True, "message": "Lock passcode reset successfully."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error force resetting mark lock passcode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marks/lock")
def lock_mark_context(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Lock one class/exam/subject marking context using the user's one passcode."""
    try:
        _ensure_mark_lock_tables(db)
        program_id = int(payload.get("program_id"))
        grade_id = int(payload.get("grade_id"))
        grade_type_id = payload.get("grade_type_id")
        grade_type_id = int(grade_type_id) if grade_type_id is not None else None
        academic_id = int(payload.get("academic_id"))
        marks_system_id = int(payload.get("marks_system_id"))
        subject_id = int(payload.get("subject_id"))
        passcode = str(payload.get("passcode") or "").strip()
        if _is_weak_mark_passcode(passcode):
            raise HTTPException(
                status_code=400,
                detail="Passcode is too easy. Please use a different 6-digit passcode.",
            )

        if not _has_marks_for_context(
            db, program_id, grade_id, academic_id, marks_system_id, subject_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Cannot lock this mark entry because no student has a saved mark yet.",
            )

        current_user_id = _current_user_id(current_user)
        existing_passcode = db.execute(
            text("SELECT passcode_hash FROM mark_lock_passcodes WHERE user_id = :user_id"),
            {"user_id": current_user_id},
        ).fetchone()
        if existing_passcode:
            if not verify_password(passcode, existing_passcode[0]):
                raise HTTPException(
                    status_code=403,
                    detail="This does not match your saved lock passcode. Use your existing passcode to lock another subject.",
                )
        else:
            db.execute(
                text("""
                    INSERT INTO mark_lock_passcodes (user_id, passcode_hash)
                    VALUES (:user_id, :passcode_hash)
                """),
                {
                    "user_id": current_user_id,
                    "passcode_hash": get_password_hash(passcode),
                },
            )

        active_lock = _get_active_mark_lock(
            db,
            program_id,
            grade_id,
            grade_type_id,
            academic_id,
            marks_system_id,
            subject_id,
        )
        if active_lock:
            db.commit()
            return {
                "success": True,
                "is_locked": True,
                "locked_by": int(active_lock[1]),
                "locked_by_name": active_lock[3] or "Unknown",
                "locked_by_kname": active_lock[4] or "",
                "locked_by_ename": active_lock[5] or "",
                "message": "Mark entry is already locked.",
            }

        db.execute(
            text("""
                INSERT INTO mark_entry_locks (
                    program_id, grade_id, grade_type_id, academic_id,
                    marks_system_id, subject_id, locked_by
                )
                VALUES (
                    :program_id, :grade_id, :grade_type_id, :academic_id,
                    :marks_system_id, :subject_id, :locked_by
                )
            """),
            {
                "program_id": program_id,
                "grade_id": grade_id,
                "grade_type_id": grade_type_id,
                "academic_id": academic_id,
                "marks_system_id": marks_system_id,
                "subject_id": subject_id,
                "locked_by": current_user_id,
            },
        )
        db.commit()
        return {
            "success": True,
            "is_locked": True,
            "locked_by": current_user_id,
            "locked_by_name": _get_current_user_name(current_user),
            "locked_by_kname": (_user_field(current_user, "kName", "") or ""),
            "locked_by_ename": (_user_field(current_user, "eName", "") or ""),
            "message": "Mark entry locked.",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error locking mark context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marks/unlock")
def unlock_mark_context(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Unlock one class/exam/subject marking context with the locker's passcode."""
    try:
        _ensure_mark_lock_tables(db)
        program_id = int(payload.get("program_id"))
        grade_id = int(payload.get("grade_id"))
        grade_type_id = payload.get("grade_type_id")
        grade_type_id = int(grade_type_id) if grade_type_id is not None else None
        academic_id = int(payload.get("academic_id"))
        marks_system_id = int(payload.get("marks_system_id"))
        subject_id = int(payload.get("subject_id"))
        passcode = str(payload.get("passcode") or "").strip()
        current_user_id = _current_user_id(current_user)
        _assert_mark_passcode_not_blocked(db, current_user_id)

        lock = _get_active_mark_lock(
            db,
            program_id,
            grade_id,
            grade_type_id,
            academic_id,
            marks_system_id,
            subject_id,
        )
        if not lock:
            return {
                "success": True,
                "is_locked": False,
                "message": "Mark entry is not locked.",
            }
        locked_by = int(lock[1])
        if not _verify_user_mark_passcode(db, locked_by, passcode):
            _record_failed_mark_passcode_attempt(db, current_user_id)
        _clear_mark_passcode_attempts(db, current_user_id)
        db.execute(
            text("""
                UPDATE mark_entry_locks
                SET is_locked = 0, unlocked_at = NOW(), unlocked_by = :unlocked_by
                WHERE id = :lock_id
            """),
            {"lock_id": int(lock[0]), "unlocked_by": current_user_id},
        )
        db.commit()
        return {"success": True, "is_locked": False, "message": "Mark entry unlocked."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error unlocking mark context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marks/save")
def save_marks(
    marks_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Save marks for students.
    Expected format:
    {
        "program_id": int,
        "grade_id": int,
        "grade_type_id": int | null,
        "academic_id": int,
        "marks_system_id": int,
        "subject_id": int,
        "marks": [
            {"student_id": int, "mark": float | null}
        ]
    }
    """
    try:
        program_id = marks_data.get("program_id")
        grade_id = marks_data.get("grade_id")
        grade_type_id = marks_data.get("grade_type_id")
        academic_id = marks_data.get("academic_id")
        marks_system_id = marks_data.get("marks_system_id")
        subject_id = marks_data.get("subject_id")
        marks_list = marks_data.get("marks", [])
        lock_passcode = marks_data.get("lock_passcode")

        if (
            program_id is None
            or grade_id is None
            or academic_id is None
            or marks_system_id is None
            or subject_id is None
        ):
            raise HTTPException(status_code=400, detail="Missing required fields")

        program_id = int(program_id)
        grade_id = int(grade_id)
        academic_id = int(academic_id)
        marks_system_id = int(marks_system_id)
        subject_id = int(subject_id)
        grade_type_id = int(grade_type_id) if grade_type_id is not None else None

        # Validate month-based access
        try:
            if ZoneInfo:
                cambodia_tz = ZoneInfo("Asia/Phnom_Penh")
                current_datetime = datetime.now(cambodia_tz)
            else:
                # Fallback: Use UTC+7 manually
                current_datetime = datetime.utcnow() + timedelta(hours=7)
                cambodia_tz = None
            current_date = current_datetime.date()
        except Exception as e:
            logger.warning(f"Timezone error during validation, using UTC+7: {e}")
            # Fallback to UTC+7 manually if zoneinfo fails
            current_datetime = datetime.utcnow() + timedelta(hours=7)
            current_date = current_datetime.date()
            cambodia_tz = None

        # Get for_month and extra_days
        marks_system_query = text(
            "SELECT for_month FROM marks_system WHERE id = :marks_system_id"
        )
        marks_system_result = db.execute(
            marks_system_query, {"marks_system_id": marks_system_id}
        ).fetchone()

        # Get marks_extraday setting
        extra_days_query = text("SELECT marks_extraday FROM settings LIMIT 1")
        extra_days_result = db.execute(extra_days_query).fetchone()
        try:
            extra_days = (
                int(extra_days_result[0])
                if extra_days_result and extra_days_result[0] is not None
                else 0
            )
        except (ValueError, TypeError):
            extra_days = 0

        if marks_system_result and marks_system_result[0]:
            for_month = marks_system_result[0]
            if isinstance(for_month, datetime):
                for_month_date = for_month.date()
            elif isinstance(for_month, date):
                for_month_date = for_month
            else:
                for_month_date = None

            if for_month_date:
                start_date = for_month_date
                deadline = start_date + timedelta(days=10 + extra_days - 1)
                deadline_datetime = datetime.combine(deadline, time(23, 59, 59))
                try:
                    if cambodia_tz:
                        deadline_datetime = deadline_datetime.replace(
                            tzinfo=cambodia_tz
                        )
                except:
                    pass  # Keep datetime without timezone if setting fails

                # Check if current datetime is within allowed period
                if current_date < start_date:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Marks entry is not yet open. Start date: {start_date.isoformat()}",
                    )
                elif current_date > deadline:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Marks entry deadline has passed. Deadline: {deadline.isoformat()}",
                    )
                elif current_date == deadline:
                    # On deadline date, check time
                    if current_datetime > deadline_datetime:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Marks entry deadline has passed. Deadline: {deadline.isoformat()}",
                        )

        # Get grade_group_id
        grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
        grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()
        if not grade_result:
            raise HTTPException(status_code=404, detail="Grade not found")
        grade_group_id = grade_result[0]

        # Get subject full_marks
        subject_query = text("""
            SELECT full_marks FROM subjects_group
            WHERE subject_id = :subject_id
            AND academic_id = :academic_id
            AND program_id = :program_id
            AND grade_group_id = :grade_group_id
        """)
        subject_result = db.execute(
            subject_query,
            {
                "subject_id": subject_id,
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id,
            },
        ).fetchone()

        if not subject_result:
            raise HTTPException(
                status_code=404, detail="Subject not found for this class"
            )

        full_marks = safe_decimal(subject_result[0], Decimal("100"))

        full_marks = safe_decimal(subject_result[0], Decimal("100"))

        _assert_mark_context_writable(
            db=db,
            program_id=program_id,
            grade_id=grade_id,
            grade_type_id=grade_type_id,
            academic_id=academic_id,
            marks_system_id=marks_system_id,
            subject_id=subject_id,
            passcode=str(lock_passcode).strip() if lock_passcode is not None else None,
        )

        # Import calculation functions
        from ...services.marks_calculations import (
            calculate_and_store_monthly_marks,
            calculate_and_store_semester_marks,
            calculate_and_store_yearly_marks,
        )

        results = []

        # DEDUPLICATE marks_list by student_id (keep last occurrence per student)
        # Prevents duplicate saves and redundant cascades when frontend sends same student multiple times
        seen_student_ids = {}
        for i, m in enumerate(marks_list):
            sid = m.get("student_id")
            if sid is not None:
                seen_student_ids[int(sid)] = m
        marks_list_deduped = list(seen_student_ids.values())
        if len(marks_list_deduped) < len(marks_list):
            logger.info(
                f"Marks save: deduplicated {len(marks_list)} -> {len(marks_list_deduped)} entries by student_id"
            )

        # Pre-save cleanup: remove duplicate marks_input rows for this context (keep latest per student)
        # Matches kortra_env auto-cleanup before marking
        try:
            cleanup_check = text("""
                SELECT student_id, COUNT(*) as cnt, MAX(id) as keep_id
                FROM marks_input
                WHERE academic_id = :academic_id AND program_id = :program_id
                AND grade_id = :grade_id AND subject_id = :subject_id AND marks_system_id = :marks_system_id
                GROUP BY student_id
                HAVING COUNT(*) > 1
            """)
            dup_rows = db.execute(
                cleanup_check,
                {
                    "academic_id": academic_id,
                    "program_id": program_id,
                    "grade_id": grade_id,
                    "subject_id": subject_id,
                    "marks_system_id": marks_system_id,
                },
            ).fetchall()
            if dup_rows:
                total_extra = sum(r[1] - 1 for r in dup_rows)
                # Delete older marks per duplicate student (keep highest id)
                for row in dup_rows:
                    cleanup_delete = text("""
                        DELETE FROM marks_input
                        WHERE student_id = :student_id AND academic_id = :academic_id
                        AND program_id = :program_id AND grade_id = :grade_id
                        AND subject_id = :subject_id AND marks_system_id = :marks_system_id
                        AND id != :keep_id
                    """)
                    db.execute(
                        cleanup_delete,
                        {
                            "student_id": row[0],
                            "academic_id": academic_id,
                            "program_id": program_id,
                            "grade_id": grade_id,
                            "subject_id": subject_id,
                            "marks_system_id": marks_system_id,
                            "keep_id": row[2],
                        },
                    )
                logger.info(
                    f"Marks save: cleaned {total_extra} duplicate marks_input rows"
                )
        except Exception as cleanup_err:
            logger.warning(f"Marks save: pre-cleanup failed (non-fatal): {cleanup_err}")

        # Process each student (flow matches kortra_env)
        for mark_entry in marks_list_deduped:
            student_id = mark_entry.get("student_id")
            mark_value = mark_entry.get("mark")

            if student_id is None:
                continue

            student_result = {
                "student_id": student_id,
                "status": "pending",
                "message": None,
            }

            try:
                is_clear = mark_value is None or mark_value == ""
                existing_mark_id = None
                existing_mark_value = None
                existing_lookup = db.execute(
                    text("""
                        SELECT id, marks
                        FROM marks_input
                        WHERE student_id = :student_id AND academic_id = :academic_id
                        AND program_id = :program_id AND grade_id = :grade_id
                        AND subject_id = :subject_id AND marks_system_id = :marks_system_id
                        ORDER BY id DESC
                        LIMIT 1
                    """),
                    {
                        "student_id": student_id,
                        "academic_id": academic_id,
                        "program_id": program_id,
                        "grade_id": grade_id,
                        "subject_id": subject_id,
                        "marks_system_id": marks_system_id,
                    },
                ).fetchone()
                if existing_lookup:
                    existing_mark_id = existing_lookup[0]
                    existing_mark_value = existing_lookup[1]

                # 1. Save/Clear input mark (kortra style: SELECT-deduplicate for save, DELETE for clear)
                if is_clear:
                    # Clear: delete all existing marks for this student+subject+context (kortra style)
                    delete_clear = text("""
                        DELETE FROM marks_input
                        WHERE student_id = :student_id AND academic_id = :academic_id
                        AND program_id = :program_id AND grade_id = :grade_id
                        AND subject_id = :subject_id AND marks_system_id = :marks_system_id
                    """)
                    db.execute(
                        delete_clear,
                        {
                            "student_id": student_id,
                            "academic_id": academic_id,
                            "program_id": program_id,
                            "grade_id": grade_id,
                            "subject_id": subject_id,
                            "marks_system_id": marks_system_id,
                        },
                    )
                    if existing_mark_id is not None:
                        _log_mark_audit(
                            db=db,
                            current_user=current_user,
                            action_type="DELETE",
                            entity_id=existing_mark_id,
                            student_id=student_id,
                            program_id=program_id,
                            grade_id=grade_id,
                            grade_type_id=grade_type_id,
                            academic_id=academic_id,
                            subject_id=subject_id,
                            marks_system_id=marks_system_id,
                            old_mark=existing_mark_value,
                            new_mark=None,
                        )
                    student_result["mark"] = None
                    student_result["mark_id"] = None
                else:
                    # Save: validate, then SELECT-deduplicate (kortra style)
                    mark_decimal = safe_decimal(mark_value)
                    if mark_decimal < 0 or mark_decimal > full_marks:
                        raise ValueError(f"Mark must be between 0 and {full_marks}")
                    mark_decimal = round_decimal_to_2_places(mark_decimal)

                    select_existing = text("""
                        SELECT id FROM marks_input
                        WHERE student_id = :student_id AND academic_id = :academic_id
                        AND program_id = :program_id AND grade_id = :grade_id
                        AND subject_id = :subject_id AND marks_system_id = :marks_system_id
                        ORDER BY id ASC
                    """)
                    existing_rows = db.execute(
                        select_existing,
                        {
                            "student_id": student_id,
                            "academic_id": academic_id,
                            "program_id": program_id,
                            "grade_id": grade_id,
                            "subject_id": subject_id,
                            "marks_system_id": marks_system_id,
                        },
                    ).fetchall()

                    if existing_rows:
                        # UPDATE the LATEST record (highest id), DELETE older duplicates (kortra logic)
                        existing_rows_sorted = sorted(
                            existing_rows, key=lambda r: r[0], reverse=True
                        )
                        latest_id = existing_rows_sorted[0][0]
                        db.execute(
                            text("""
                            UPDATE marks_input SET marks = :marks, updated_at = NOW()
                            WHERE id = :id
                        """),
                            {"marks": mark_decimal, "id": latest_id},
                        )
                        if len(existing_rows_sorted) > 1:
                            dup_ids = [r[0] for r in existing_rows_sorted[1:]]
                            for dup_id in dup_ids:
                                db.execute(
                                    text("DELETE FROM marks_input WHERE id = :id"),
                                    {"id": dup_id},
                                )
                            logger.info(
                                f"AUTO-CLEANUP: removed {len(dup_ids)} duplicate marks for student {student_id}, subject {subject_id}"
                            )
                        if not _mark_values_equal(existing_mark_value, mark_decimal):
                            _log_mark_audit(
                                db=db,
                                current_user=current_user,
                                action_type="UPDATE",
                                entity_id=latest_id,
                                student_id=student_id,
                                program_id=program_id,
                                grade_id=grade_id,
                                grade_type_id=grade_type_id,
                                academic_id=academic_id,
                                subject_id=subject_id,
                                marks_system_id=marks_system_id,
                                old_mark=existing_mark_value,
                                new_mark=mark_decimal,
                            )
                        student_result["mark_id"] = latest_id
                    else:
                        # INSERT new record
                        db.execute(
                            text("""
                            INSERT INTO marks_input
                            (student_id, program_id, grade_id, grade_group_id, academic_id,
                             subject_id, marks_system_id, marks)
                            VALUES
                            (:student_id, :program_id, :grade_id, :grade_group_id, :academic_id,
                             :subject_id, :marks_system_id, :marks)
                        """),
                            {
                                "student_id": student_id,
                                "program_id": program_id,
                                "grade_id": grade_id,
                                "grade_group_id": grade_group_id,
                                "academic_id": academic_id,
                                "subject_id": subject_id,
                                "marks_system_id": marks_system_id,
                                "marks": mark_decimal,
                            },
                        )
                        new_mark_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                        _log_mark_audit(
                            db=db,
                            current_user=current_user,
                            action_type="CREATE",
                            entity_id=new_mark_id,
                            student_id=student_id,
                            program_id=program_id,
                            grade_id=grade_id,
                            grade_type_id=grade_type_id,
                            academic_id=academic_id,
                            subject_id=subject_id,
                            marks_system_id=marks_system_id,
                            old_mark=None,
                            new_mark=mark_decimal,
                        )
                        student_result["mark_id"] = new_mark_id
                    student_result["mark"] = float(mark_decimal)

                # 2. Trigger Calculations (Cascade) - ALWAYS run (kortra: monthly->semester->yearly on save AND clear)
                logger.info("--- STARTING CALCULATION CHAIN ---")
                monthly_ids = calculate_and_store_monthly_marks(
                    db=db,
                    student_id=student_id,
                    program_id=program_id,
                    grade_id=grade_id,
                    grade_group_id=grade_group_id,
                    academic_id=academic_id,
                    marks_system_id=marks_system_id,
                    auto_commit=False,
                )

                if monthly_ids:
                    # Semester calculation
                    semester_ids = calculate_and_store_semester_marks(
                        db=db,
                        student_id=student_id,
                        program_id=program_id,
                        grade_id=grade_id,
                        grade_group_id=grade_group_id,
                        academic_id=academic_id,
                        triggered_by_monthly_ids=monthly_ids,
                        auto_commit=False,
                    )
                    # Yearly calculation - run whenever monthly ran (semester may have created RSEM from MON5)
                    calculate_and_store_yearly_marks(
                        db=db,
                        student_id=student_id,
                        program_id=program_id,
                        grade_id=grade_id,
                        grade_group_id=grade_group_id,
                        academic_id=academic_id,
                        triggered_by_semester_ids=semester_ids
                        if semester_ids
                        else None,
                        auto_commit=False,
                    )

                logger.info("--- CALCULATION CHAIN COMPLETE ---")

                # 3. Commit per student
                db.commit()
                student_result["status"] = "success"

            except Exception as e:
                db.rollback()
                logger.error(
                    f"Error saving marks for student {student_id}: {e}", exc_info=True
                )
                student_result["status"] = "error"
                student_result["message"] = str(e)

            results.append(student_result)

        # Calculate summary stats
        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] == "error")

        return {
            "success": True,
            "results": results,
            "summary": {
                "total": len(results),
                "saved": success_count,
                "failed": error_count,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving marks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/marks/audit-log")
async def get_marks_audit_log(
    student_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    grade_id: Optional[int] = Query(None),
    grade_type_id: Optional[int] = Query(None),
    grade_type_is_null: Optional[bool] = Query(None),
    program_id: Optional[int] = Query(None),
    academic_id: Optional[int] = Query(None),
    marks_system_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    action_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get mark-entry audit rows for the Enter Mark screen."""
    try:
        filters = ["entity_type = 'mark_input'"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}

        if student_id is not None:
            filters.append("student_id = :student_id")
            params["student_id"] = student_id
        if teacher_id is not None:
            filters.append("user_id = :teacher_id")
            params["teacher_id"] = teacher_id
        if branch_id is not None:
            filters.append("branch_id = :branch_id")
            params["branch_id"] = branch_id
        if grade_id is not None:
            filters.append("class_id = :grade_id")
            params["grade_id"] = grade_id
        if action_type:
            filters.append("action_type = :action_type")
            params["action_type"] = action_type

        json_filters = {
            "program_id": program_id,
            "academic_id": academic_id,
            "marks_system_id": marks_system_id,
            "subject_id": subject_id,
        }
        if grade_type_id is not None:
            filters.append(
                "JSON_UNQUOTE(JSON_EXTRACT(new_value, '$.grade_type_id')) = :grade_type_id"
            )
            params["grade_type_id"] = str(grade_type_id)
        elif grade_type_is_null:
            filters.append("JSON_EXTRACT(new_value, '$.grade_type_id') IS NULL")

        for key, value in json_filters.items():
            if value is not None:
                filters.append(
                    f"JSON_UNQUOTE(JSON_EXTRACT(new_value, '$.{key}')) = :{key}"
                )
                params[key] = str(value)

        where_sql = " AND ".join(filters)
        rows = db.execute(
            text(f"""
                SELECT id, user_id, user_name, user_role, action_type, entity_type,
                       entity_id, student_id, student_name, class_id,
                       class_description, change_description, old_value, new_value,
                       created_at, created_at_khmer, branch_id
                FROM attendance_audit_log
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        result = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "user_id": row[1],
                    "user_name": row[2],
                    "user_role": row[3],
                    "action_type": row[4],
                    "entity_type": row[5],
                    "entity_id": row[6],
                    "student_id": row[7],
                    "student_name": row[8],
                    "class_id": row[9],
                    "class_description": row[10],
                    "change_description": row[11],
                    "old_value": row[12],
                    "new_value": row[13],
                    "created_at": row[14],
                    "created_at_khmer": row[15],
                    "branch_id": row[16],
                }
            )
        return result
    except Exception as e:
        logger.error(f"Error retrieving marks audit log: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving marks audit log: {str(e)}",
        )


@router.post("/marks/exams/active-contexts")
async def check_active_contexts(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Bulk check for active exams across multiple contexts.
    Payload: {"contexts": [{"program_id": 1, "grade_id": 2, "grade_type_id": 3, "academic_id": 2}, ...]}
    Returns: {"results": [{"key": "p_g_gt", "has_active_exam": true, "closest_date": "ISO8601"}]}
    """
    try:
        contexts = payload.get("contexts", [])
        if not contexts:
            return {"success": True, "results": []}

        # Common settings
        # Get marks_extraday setting
        extra_days_query = text("SELECT marks_extraday FROM settings LIMIT 1")
        extra_days_result = db.execute(extra_days_query).fetchone()
        try:
            extra_days = (
                int(extra_days_result[0])
                if extra_days_result and extra_days_result[0] is not None
                else 0
            )
        except (ValueError, TypeError):
            extra_days = 0

        # Timezone setup
        try:
            if ZoneInfo:
                cambodia_tz = ZoneInfo("Asia/Phnom_Penh")
                current_datetime = datetime.now(cambodia_tz)
            else:
                current_datetime = datetime.utcnow() + timedelta(hours=7)
                cambodia_tz = None
            current_date = current_datetime.date()
        except Exception:
            current_datetime = datetime.utcnow() + timedelta(hours=7)
            current_date = current_datetime.date()
            cambodia_tz = None

        results = []

        # Cache Grade -> Group ID to avoid repetitive queries if multiple contexts use same grade
        grade_group_cache = {}

        for ctx in contexts:
            program_id = ctx.get("program_id")
            grade_id = ctx.get("grade_id")
            grade_type_id = ctx.get(
                "grade_type_id"
            )  # Not strictly used for filtering exams but part of key
            academic_id = ctx.get("academic_id")

            key = f"{program_id}_{grade_id}_{grade_type_id}"

            if not (program_id and grade_id and academic_id):
                continue

            # Get Grade Group ID
            if grade_id not in grade_group_cache:
                grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
                grade_result = db.execute(
                    grade_query, {"grade_id": grade_id}
                ).fetchone()
                if grade_result:
                    grade_group_cache[grade_id] = grade_result[0]
                else:
                    grade_group_cache[grade_id] = None  # Or handle error?

            grade_group_id = grade_group_cache[grade_id]
            if grade_group_id is None:
                continue

            # Get Exams
            query = text("""
                SELECT ms.for_month
                FROM marks_system ms
                WHERE ms.program_id = :program_id
                AND ms.academic_id = :academic_id
                AND (ms.grade_group_id = :grade_group_id OR ms.grade_group_id IS NULL)
            """)

            exam_rows = db.execute(
                query,
                {
                    "program_id": program_id,
                    "academic_id": academic_id,
                    "grade_group_id": grade_group_id,
                },
            ).fetchall()

            has_active_exam = False
            closest_date = None

            for row in exam_rows:
                for_month = row[0]
                if not for_month:
                    continue

                # Logic mirroring get_exams
                if isinstance(for_month, datetime):
                    start_date = for_month.date()
                elif isinstance(for_month, date):
                    start_date = for_month
                else:
                    continue

                # Calculate Deadline
                deadline = start_date + timedelta(days=10 + extra_days - 1)

                # Availability Logic
                is_available = False

                # Simple date check first
                if current_date >= start_date and current_date <= deadline:
                    is_available = True
                elif current_date == deadline:
                    # Granular check if needed, but for stats simple date check is usually enough
                    # Or replicate exact logic:
                    deadline_datetime = datetime.combine(deadline, time(23, 59, 59))
                    # skipping timezone exact check for speed, usually date is enough
                    if current_datetime <= deadline_datetime:
                        is_available = True

                # Dashboard Filter Logic:
                # Count if:
                # 1. Available (Open for marking)
                # OR
                # 2. In current month (even if closed/future)
                # OR
                # 3. Within next 3 days (future)

                include_exam = False

                # Check current month
                if (
                    start_date.year == current_date.year
                    and start_date.month == current_date.month
                ):
                    include_exam = True

                # Check near future (+3 days)
                diff_days = (start_date - current_date).days
                if diff_days >= 0 and diff_days <= 3:
                    include_exam = True

                if is_available:
                    include_exam = True

                if include_exam:
                    has_active_exam = True
                    # Update closest date (future or today only)
                    if start_date >= current_date:
                        if closest_date is None or start_date < closest_date:
                            closest_date = start_date

            results.append(
                {
                    "key": key,
                    "has_active_exam": has_active_exam,
                    "closest_date": closest_date.isoformat() if closest_date else None,
                }
            )

        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Error checking active contexts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
