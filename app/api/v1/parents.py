from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Any, Dict, List, Optional, cast
import json
from datetime import date, datetime, timedelta
from fastapi.concurrency import run_in_threadpool
from starlette.concurrency import run_in_threadpool as starlette_run_in_threadpool
import asyncio
import logging
import random
import secrets
import string

from ...core import get_db
from ...core.parent_status import ensure_parent_status_column
from ...core.parent_registration import (
    ensure_parent_registration_audit_table,
    log_parent_registration_audit,
    notify_parent_registration_approved,
    notify_parent_registration_rejected,
)
from ...auth import get_current_active_user
from ...services import notification_service
from ...models import User, Holiday
from ...models.parent_permission_interaction import ParentPermissionInteraction
from ...schemas.parents import (
    AskPermissionRequest,
    AskPermissionResponse,
    AskPermissionBatchRequest,
    CancelPermissionRequest,
    CancelPermissionResponse,
    CheckAttendanceStatusRequest,
    AttendanceSummaryResponse,
    StudentAttendanceSummaryRequest,
    StudentAttendanceDailyResponse,
    DailyAttendanceRecord,
    UpdateMyChildRequest,
    LinkChildRequest,
    LinkChildResponse,
    PendingLinkRequestItem,
    AdminPendingLinkRequestItem,
    AdminProcessLinkRequest,
    AdminPendingParentRegistrationItem,
    AdminParentRegistrationAction,
    AdminParentRegistrationHistoryItem,
    LinkedStudentSummary,
)
from ...models.app_admin import AppAdmin
from ...models.parent import Parent
from ...services import notification_service
import bcrypt
import base64

router = APIRouter()
logger = logging.getLogger(__name__)


def _json_safe_student_image(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, memoryview):
        val = val.tobytes()
    if isinstance(val, bytes):
        if not val:
            return ""
        try:
            text = val.decode("utf-8")
            if text.isascii() and (
                text.startswith(("http://", "https://", "/"))
                or text.startswith("uploads/")
                or ("/" in text and "\x00" not in text and len(text) < 512)
            ):
                return text
        except UnicodeDecodeError:
            pass
        return base64.b64encode(val).decode("ascii")
    return ""


def _to_ymd(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _format_dates_range(date_strings: List[str]) -> str:
    cleaned = [d for d in date_strings if d]
    if not cleaned:
        return ""
    parsed: List[date] = []
    for raw in cleaned:
        try:
            parsed.append(date.fromisoformat(raw[:10]))
        except Exception:
            continue
    if not parsed:
        return ", ".join(cleaned)
    parsed.sort()
    first = parsed[0]
    last = parsed[-1]
    if first == last:
        return f"{first.strftime('%B')} {first.day}"
    if first.year == last.year:
        return f"{first.strftime('%B')} {first.day} - {last.strftime('%B')} {last.day}"
    return (
        f"{first.strftime('%B')} {first.day}, {first.year} - "
        f"{last.strftime('%B')} {last.day}, {last.year}"
    )

@router.post("/ask-permission", response_model=AskPermissionResponse)
async def ask_permission(
    request: AskPermissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Parent requests permission for their child.
    Creates daily_attendance records with status 'IsPermission'.
    Notifies the homeroom teacher.
    """
    # 1. Validate request
    if not request.dates:
        raise HTTPException(status_code=400, detail="At least one date is required")
    
    if len(request.dates) > 7:
        raise HTTPException(status_code=400, detail="Cannot request permission for more than 7 days at a time")

    # Block permission requests on configured holidays.
    holiday_rows = (
        db.query(Holiday.date)
        .filter(Holiday.date.in_(request.dates))
        .all()
    )
    if holiday_rows:
        holiday_dates = sorted({_to_ymd(row[0]) for row in holiday_rows})
        raise HTTPException(
            status_code=400,
            detail=(
                "HOLIDAY_CONFLICT: Cannot request permission on holiday dates: "
                f"{', '.join(holiday_dates)}"
            ),
        )

    # 2. Verify Parent-Child Relationship
    # current_user is the parent. We need to check if student_id is one of their children.
    # We assume current_user.id links to parents table via user_id or similar, 
    # BUT based on existing code (get_parent_info), parents table has its own ID.
    # Let's check if the logged in user is a parent and get their parent record.
    
    # In pama_api, mapping often happens via phone/telegram or directly if they are the same user.
    # However, for now, let's assume strict verification: check if student is in parent's myChilds list.
    # First, find the parent record associated with this user (if any).
    # If the login *is* a parent login, maybe we can direct query.
    # Let's verify if 'current_user' is indeed a parent and has access.
    
    # Simplified check: Check if the student exists and fetch their details + learning record in one go
    # to ensure the learning_id belongs to the student.
    
    learning_query = text("""
        SELECT 
            l.id, l.programid, l.gradeid, l.shiftid, l.academicid, l.grade_type_id,
            s.kName, s.eName, s.id as student_id,
            g.grade_name, gt.type_name as grade_type_name, sh.shift_name
        FROM learning l
        JOIN students s ON l.studentid = s.id
        LEFT JOIN grade g ON l.gradeid = g.id
        LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
        LEFT JOIN shift sh ON l.shiftid = sh.id
        WHERE l.id = :learning_id AND l.studentid = :student_id
    """)
    
    learning_result = db.execute(learning_query, {
        "learning_id": request.learning_id,
        "student_id": request.student_id
    }).fetchone()
    
    if not learning_result:
        raise HTTPException(status_code=404, detail="Student class information not found")
    
    # helper for safe access
    def get_val(row, idx):
        return row[idx]

    program_id = get_val(learning_result, 1)
    grade_id = get_val(learning_result, 2)
    shift_id = get_val(learning_result, 3)
    academic_id = get_val(learning_result, 4)
    grade_type_id = get_val(learning_result, 5)
    student_name_kh = get_val(learning_result, 6)
    student_name_en = get_val(learning_result, 7)
    grade_name = get_val(learning_result, 9)
    grade_type_name = get_val(learning_result, 10)
    shift_name = get_val(learning_result, 11)
    
    # Check if parent has already interacted with this learning today
    parent_id = cast(int, getattr(current_user, "id", 0))
    has_interacted_today = check_parent_interaction_today(
        db, parent_id, request.student_id, request.learning_id
    )

    if has_interacted_today:
        raise HTTPException(
            status_code=400,
            detail="ALREADY_INTERACTED: You have already requested or cancelled permission for this class today. Each class can only be used once per day."
        )

    # Check if attendance is already marked for any of the requested dates (batched query)
    if request.dates:
        date_strings = [d.strftime("%Y-%m-%d") for d in request.dates]
        attendance_check = text("""
            SELECT id, status, created_by_type, DATE(attendance_date) as att_date
            FROM daily_attendance
            WHERE student_id = :student_id
                AND DATE(attendance_date) IN :attendance_dates
                AND program_id = :program_id
                AND grade_id = :grade_id
                AND shift_id = :shift_id
                AND academic_id = :academic_id
                AND (grade_type_id = :grade_type_id OR (grade_type_id IS NULL AND :grade_type_id IS NULL))
        """)

        existing_attendances = db.execute(attendance_check, {
            "student_id": request.student_id,
            "attendance_dates": tuple(date_strings),
            "program_id": program_id,
            "grade_id": grade_id,
            "shift_id": shift_id,
            "academic_id": academic_id,
            "grade_type_id": grade_type_id
        }).fetchall()

        if existing_attendances:
            # Return all conflicting dates
            conflict_dates = [row[3] for row in existing_attendances]
            conflict_details = [f"{row[1]} on {row[3]}" for row in existing_attendances]
            raise HTTPException(
                status_code=400,
                detail=f"ATTENDANCE_CONFLICT: Attendance already marked for dates: {', '.join(conflict_dates)}. Details: {', '.join(conflict_details)}"
            )

    # 3. Find the Teacher for this class to notify/assign
    # Logic extracted from students.py/get_student_by_id join
    teacher_query = text("""
        SELECT teacher_id 
        FROM class_teachers
        WHERE program_id = :program_id 
          AND grade_id = :grade_id 
          AND shift_id = :shift_id 
          AND academic_id = :academic_id
          AND branch_id = (SELECT branch_id FROM grade WHERE id = :grade_id)
        LIMIT 1
    """)
    
    # We need branch_id to be precise. Let's get it from grade table first or join in teacher_query
    # Re-writing teacher query to be safer
    teacher_query_v2 = text("""
        SELECT ct.teacher_id
        FROM class_teachers ct
        JOIN grade g ON ct.grade_id = g.id
        WHERE ct.program_id = :program_id 
          AND ct.grade_id = :grade_id 
          AND ct.shift_id = :shift_id 
          AND ct.academic_id = :academic_id
          AND (ct.grade_type_id = :grade_type_id OR (ct.grade_type_id IS NULL AND :grade_type_id IS NULL))
        LIMIT 1
    """)
    
    # Handle NULL grade_type_id carefully in SQL
    teacher_params = {
        "program_id": program_id,
        "grade_id": grade_id,
        "shift_id": shift_id,
        "academic_id": academic_id,
        "grade_type_id": grade_type_id
    }
    
    # If grade_type_id is None, the SQL above `ct.grade_type_id = :grade_type_id` will fail (NULL = NULL is false).
    # We need to handle it based on value.
    if grade_type_id is None:
        teacher_sql = """
            SELECT ct.teacher_id
            FROM class_teachers ct
            WHERE ct.program_id = :program_id 
              AND ct.grade_id = :grade_id 
              AND ct.shift_id = :shift_id 
              AND ct.academic_id = :academic_id
              AND ct.grade_type_id IS NULL
            LIMIT 1
        """
    else:
        teacher_sql = """
            SELECT ct.teacher_id
            FROM class_teachers ct
            WHERE ct.program_id = :program_id 
              AND ct.grade_id = :grade_id 
              AND ct.shift_id = :shift_id 
              AND ct.academic_id = :academic_id
              AND ct.grade_type_id = :grade_type_id
            LIMIT 1
        """

    teacher_result = db.execute(text(teacher_sql), teacher_params).fetchone()
    teacher_id = teacher_result[0] if teacher_result else None

    # 4. Insert into daily_attendance (batched check)
    created_count = 0
    realtime_events: List[Dict[str, Any]] = []

    # Basic info for logging/notification
    parent_name = current_user.eName or current_user.kName or "Parent"

    # Batch check for existing records
    if request.dates:
        date_strings = [d.strftime("%Y-%m-%d") if isinstance(d, date) else str(d)[:10] for d in request.dates]
        check_query = text("""
            SELECT id, DATE(attendance_date) as att_date
            FROM daily_attendance
            WHERE student_id = :student_id
              AND DATE(attendance_date) IN :dates
              AND shift_id = :shift_id
              AND academic_id = :academic_id
        """)

        existing_records = db.execute(check_query, {
            "student_id": request.student_id,
            "dates": tuple(date_strings),
            "shift_id": shift_id,
            "academic_id": academic_id
        }).fetchall()
        
        existing_map = {row[1]: row[0] for row in existing_records}  # date -> id mapping
    else:
        existing_map = {}

    for attendance_date in request.dates:
        date_str = attendance_date.strftime("%Y-%m-%d") if isinstance(attendance_date, date) else str(attendance_date)[:10]
        existing_id = existing_map.get(date_str)

        if existing_id:
            # Update existing record
            update_query = text("""
                UPDATE daily_attendance
                SET status = 'IsPermission',
                    note = :note,
                    updated_at = NOW(),
                    updated_by = :updated_by,
                    teacher_id = COALESCE(teacher_id, :teacher_id)
                WHERE id = :id
            """)
            db.execute(update_query, {
                "note": request.reason,
                "updated_by": current_user.id,
                "teacher_id": teacher_id,
                "id": existing_id
            })
        else:
            # Insert new record
            insert_query = text("""
                INSERT INTO daily_attendance (
                    student_id, program_id, grade_id, grade_type_id, shift_id,
                    status, attendance_date, academic_id, note,
                    created_at, updated_at, created_by, updated_by, teacher_id, created_by_type
                ) VALUES (
                    :student_id, :program_id, :grade_id, :grade_type_id, :shift_id,
                    'IsPermission', :attendance_date, :academic_id, :note,
                    NOW(), NOW(), :created_by, :updated_by, :teacher_id, 'parent'
                )
            """)
            db.execute(insert_query, {
                "student_id": request.student_id,
                "program_id": program_id,
                "grade_id": grade_id,
                "grade_type_id": grade_type_id,
                "shift_id": shift_id,
                "attendance_date": attendance_date,
                "academic_id": academic_id,
                "note": request.reason,
                "created_by": current_user.id,
                "updated_by": current_user.id,
                "teacher_id": teacher_id
            })
        
        created_count += 1
        realtime_events.append({
            "academic_id": academic_id,
            "attendance_date": date_str,
            "student_id": request.student_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "shift_id": shift_id,
            "status": "IsPermission",
        })

    # Record the permission interaction
    record_parent_interaction(
        db, parent_id, request.student_id, request.learning_id, 'requested'
    )

    db.commit()

    # Realtime push so teacher/attendance screens refresh immediately.
    try:
        from .websocket import broadcast_attendance_update
        for ev in realtime_events:
            await broadcast_attendance_update(
                academic_id=ev["academic_id"],
                attendance_date=ev["attendance_date"],
                student_id=ev["student_id"],
                program_id=ev["program_id"],
                grade_id=ev["grade_id"],
                grade_type_id=ev["grade_type_id"],
                shift_id=ev["shift_id"],
                status=ev["status"],
            )
    except Exception as e:
        logger.error(f"Failed to broadcast permission realtime update: {e}")

    # 5. Notify Teacher
    if teacher_id:
        # Get teacher's FCM token or user ID to send notification
        # The notification_service.send_notification takes a list of user_ids
        
        try:
            message_title = f"Permission Request: {student_name_en}"
            exact_dates = [_to_ymd(d) for d in request.dates]
            dates_str = _format_dates_range(exact_dates)
            
            # Construct body with class info
            class_info = f"{grade_name or ''}"
            if grade_type_name:
                class_info += f" {grade_type_name}"
            if shift_name:
                class_info += f" ({shift_name})"
                
            message_body = (
                f"{parent_name} requested permission for {len(request.dates)} day(s) for {class_info}."
                f"\nDates: {dates_str}"
                f"\nReason: {request.reason}"
            )
            
            # Get teacher device tokens
            tokens = notification_service.get_teacher_device_tokens(db, teacher_id)
            
            # Send push notification (and save to DB) — offloaded to thread to avoid blocking event loop
            await asyncio.to_thread(
                notification_service.send_notification,
                device_tokens=tokens,
                title=message_title,
                body=message_body,
                data={
                     "type": "permission_request",
                     "student_id": str(request.student_id),
                     "dates": exact_dates,
                     "reason": request.reason,
                     "grade": grade_name or "",
                     "grade_type": grade_type_name or "",
                     "shift": shift_name or ""
                },
                db=db,
                user_ids=[{"id": teacher_id, "user_type": "teacher"}]
            )
            
            # Optionally send Push Notification immediately if service supports it
            # notification_service.send_push_notification(...) 
            # Assuming save_notification might handle it or we call a separate function
            # But based on prev tasks, we just saved it. The user task log says 'update send_notification'.
            # Let's assume save_notification handles DB and we might need to trigger push separately if needed.
            # For now, saving to DB is the critical part for the feed.
            
        except Exception as e:
            logger.error(f"Failed to send notification to teacher {teacher_id}: {e}")

    return AskPermissionResponse(
        success=True, 
        message="Permission requested successfully",
        created_count=created_count
    )

@router.post("/ask-permission-batch", response_model=AskPermissionResponse)
async def ask_permission_batch(
    request: AskPermissionBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Parent requests permission for multiple children/classes at once.
    Creates daily_attendance records with status 'IsPermission' for all selections.
    Notifies the relevant homeroom teachers.
    """
    # 1. Validate request
    if not request.dates:
        raise HTTPException(status_code=400, detail="At least one date is required")
    
    if len(request.dates) > 7:
        raise HTTPException(status_code=400, detail="Cannot request permission for more than 7 days at a time")
    
    if not request.selections:
        raise HTTPException(status_code=400, detail="At least one student/class selection is required")

    # Block permission requests on configured holidays.
    holiday_rows = (
        db.query(Holiday.date)
        .filter(Holiday.date.in_(request.dates))
        .all()
    )
    if holiday_rows:
        holiday_dates = sorted({_to_ymd(row[0]) for row in holiday_rows})
        raise HTTPException(
            status_code=400,
            detail=(
                "HOLIDAY_CONFLICT: Cannot request permission on holiday dates: "
                f"{', '.join(holiday_dates)}"
            ),
        )

    total_created = 0
    realtime_events: List[Dict[str, Any]] = []
    blocked_selections = []  # Track which selections were blocked
    teachers_to_notify = {}  # {teacher_id: [student_names]}
    parent_name = current_user.eName or current_user.kName or "Parent"
    parent_id = cast(int, getattr(current_user, "id", 0))

    # Process each selection
    for selection in request.selections:
        # Check if parent has already interacted with this learning today
        has_interacted_today = check_parent_interaction_today(
            db, parent_id, selection.student_id, selection.learning_id
        )

        if has_interacted_today:
            logger.warning(f"Parent {current_user.id} has already interacted with learning {selection.learning_id} for student {selection.student_id} today")
            blocked_selections.append({
                "student_id": selection.student_id,
                "learning_id": selection.learning_id,
                "reason": "ALREADY_INTERACTED",
                "message": "Already requested or cancelled permission for this class today"
            })
            continue

        # Fetch learning details
        learning_query = text("""
            SELECT
                l.id, l.programid, l.gradeid, l.shiftid, l.academicid, l.grade_type_id,
                s.kName, s.eName, s.id as student_id,
                g.grade_name, gt.type_name as grade_type_name, sh.shift_name
            FROM learning l
            JOIN students s ON l.studentid = s.id
            LEFT JOIN grade g ON l.gradeid = g.id
            LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
            LEFT JOIN shift sh ON l.shiftid = sh.id
            WHERE l.id = :learning_id AND l.studentid = :student_id
        """)

        learning_result = db.execute(learning_query, {
            "learning_id": selection.learning_id,
            "student_id": selection.student_id
        }).fetchone()

        if not learning_result:
            logger.warning(f"Skipping invalid selection: student_id={selection.student_id}, learning_id={selection.learning_id}")
            continue
        
        program_id = learning_result[1]
        grade_id = learning_result[2]
        shift_id = learning_result[3]
        academic_id = learning_result[4]
        grade_type_id = learning_result[5]
        student_name_en = learning_result[7]
        grade_name = learning_result[9]
        grade_type_name = learning_result[10]
        shift_name = learning_result[11]

        # Batch check if attendance is already marked for any of the requested dates
        if request.dates:
            date_strings = [d.strftime("%Y-%m-%d") for d in request.dates]
            conflict_check = text("""
                SELECT id, status, created_by_type, DATE(attendance_date) as att_date
                FROM daily_attendance
                WHERE student_id = :student_id
                    AND DATE(attendance_date) IN :attendance_dates
                    AND program_id = :program_id
                    AND grade_id = :grade_id
                    AND shift_id = :shift_id
                    AND academic_id = :academic_id
                    AND (grade_type_id = :grade_type_id OR (grade_type_id IS NULL AND :grade_type_id IS NULL))
            """)

            conflicts = db.execute(conflict_check, {
                "student_id": selection.student_id,
                "attendance_dates": tuple(date_strings),
                "program_id": program_id,
                "grade_id": grade_id,
                "shift_id": shift_id,
                "academic_id": academic_id,
                "grade_type_id": grade_type_id
            }).fetchall()

            if conflicts:
                attendance_conflicts = [
                    {
                        "date": row[3],
                        "existing_status": row[1],
                        "marked_by": row[2]
                    }
                    for row in conflicts
                ]
                conflict_details = [f"{c['existing_status']} on {c['date']}" for c in attendance_conflicts]
                logger.warning(f"Skipping permission request for student {selection.student_id} - attendance already marked for dates: {', '.join(conflict_details)}")

                blocked_selections.append({
                    "student_id": selection.student_id,
                    "learning_id": selection.learning_id,
                    "reason": "ATTENDANCE_CONFLICT",
                    "message": f"Attendance already marked: {', '.join(conflict_details)}",
                    "conflicts": attendance_conflicts
                })
                continue
        
        # Find teacher
        if grade_type_id is None:
            teacher_sql = """
                SELECT ct.teacher_id
                FROM class_teachers ct
                WHERE ct.program_id = :program_id 
                  AND ct.grade_id = :grade_id 
                  AND ct.shift_id = :shift_id 
                  AND ct.academic_id = :academic_id
                  AND ct.grade_type_id IS NULL
                LIMIT 1
            """
        else:
            teacher_sql = """
                SELECT ct.teacher_id
                FROM class_teachers ct
                WHERE ct.program_id = :program_id 
                  AND ct.grade_id = :grade_id 
                  AND ct.shift_id = :shift_id 
                  AND ct.academic_id = :academic_id
                  AND ct.grade_type_id = :grade_type_id
                LIMIT 1
            """

        teacher_result = db.execute(text(teacher_sql), {
            "program_id": program_id,
            "grade_id": grade_id,
            "shift_id": shift_id,
            "academic_id": academic_id,
            "grade_type_id": grade_type_id
        }).fetchone()
        
        teacher_id = teacher_result[0] if teacher_result else None
        
        # Track teachers for notification
        if teacher_id:
            if teacher_id not in teachers_to_notify:
                teachers_to_notify[teacher_id] = []
            
            # Store student name AND class info
            teachers_to_notify[teacher_id].append({
                "student_name": student_name_en,
                "grade": grade_name,
                "grade_type": grade_type_name,
                "shift": shift_name
            })

        # Batch check for existing records
        if request.dates:
            date_strings = [d.strftime("%Y-%m-%d") if isinstance(d, date) else str(d)[:10] for d in request.dates]
            check_query = text("""
                SELECT id, DATE(attendance_date) as att_date
                FROM daily_attendance
                WHERE student_id = :student_id
                  AND DATE(attendance_date) IN :dates
                  AND shift_id = :shift_id
                  AND academic_id = :academic_id
            """)

            existing_records = db.execute(check_query, {
                "student_id": selection.student_id,
                "dates": tuple(date_strings),
                "shift_id": shift_id,
                "academic_id": academic_id
            }).fetchall()
            
            existing_map = {row[1]: row[0] for row in existing_records}
        else:
            existing_map = {}

        # Insert/update attendance for each date
        for attendance_date in request.dates:
            date_str = attendance_date.strftime("%Y-%m-%d") if isinstance(attendance_date, date) else str(attendance_date)[:10]
            existing_id = existing_map.get(date_str)

            if existing_id:
                update_query = text("""
                    UPDATE daily_attendance
                    SET status = 'IsPermission',
                        note = :note,
                        updated_at = NOW(),
                        updated_by = :updated_by,
                        teacher_id = COALESCE(teacher_id, :teacher_id)
                    WHERE id = :id
                """)
                db.execute(update_query, {
                    "note": request.reason,
                    "updated_by": current_user.id,
                    "teacher_id": teacher_id,
                    "id": existing_id
                })
            else:
                insert_query = text("""
                    INSERT INTO daily_attendance (
                        student_id, program_id, grade_id, grade_type_id, shift_id,
                        status, attendance_date, academic_id, note,
                        created_at, updated_at, created_by, updated_by, teacher_id, created_by_type
                    ) VALUES (
                        :student_id, :program_id, :grade_id, :grade_type_id, :shift_id,
                        'IsPermission', :attendance_date, :academic_id, :note,
                        NOW(), NOW(), :created_by, :updated_by, :teacher_id, 'parent'
                    )
                """)
                db.execute(insert_query, {
                    "student_id": selection.student_id,
                    "program_id": program_id,
                    "grade_id": grade_id,
                    "grade_type_id": grade_type_id,
                    "shift_id": shift_id,
                    "attendance_date": attendance_date,
                    "academic_id": academic_id,
                    "note": request.reason,
                    "created_by": current_user.id,
                    "updated_by": current_user.id,
                    "teacher_id": teacher_id
                })
            
            total_created += 1
            realtime_events.append({
                "academic_id": academic_id,
                "attendance_date": date_str,
                "student_id": selection.student_id,
                "program_id": program_id,
                "grade_id": grade_id,
                "grade_type_id": grade_type_id,
                "shift_id": shift_id,
                "status": "IsPermission",
            })

            # Record the permission interaction
            record_parent_interaction(
                db, parent_id, selection.student_id, selection.learning_id, 'requested'
            )

    db.commit()

    # Realtime push so teacher/attendance screens refresh immediately.
    try:
        from .websocket import broadcast_attendance_update
        for ev in realtime_events:
            await broadcast_attendance_update(
                academic_id=ev["academic_id"],
                attendance_date=ev["attendance_date"],
                student_id=ev["student_id"],
                program_id=ev["program_id"],
                grade_id=ev["grade_id"],
                grade_type_id=ev["grade_type_id"],
                shift_id=ev["shift_id"],
                status=ev["status"],
            )
    except Exception as e:
        logger.error(f"Failed to broadcast batch permission realtime update: {e}")

    # Notify teachers
    for teacher_id, students_info in teachers_to_notify.items():
        try:
            student_names = [s["student_name"] for s in students_info]
            students_list = ", ".join(student_names)
            message_title = f"Permission Request: {len(student_names)} Student(s)"
            exact_dates = [_to_ymd(d) for d in request.dates]
            dates_str = _format_dates_range(exact_dates)
            
            # Use info from the first student for the main class display (simplification for batch)
            # Or formatted list
            first_student = students_info[0]
            grade_name = first_student.get("grade") or ""
            grade_type = first_student.get("grade_type") or ""
            shift = first_student.get("shift") or ""
            
            message_body = (
                f"{parent_name} requested permission for {len(request.dates)} day(s) for: {students_list}."
                f"\nDates: {dates_str}"
                f"\nReason: {request.reason}"
            )
            
            # Get teacher device tokens
            tokens = notification_service.get_teacher_device_tokens(db, teacher_id)
            
            # Send push notification (and save to DB) — offloaded to thread to avoid blocking event loop
            await asyncio.to_thread(
                notification_service.send_notification,
                device_tokens=tokens,
                title=message_title,
                body=message_body,
                data={
                    "type": "permission_request_batch",
                    "student_count": str(len(student_names)),
                    "dates": exact_dates,
                    "reason": request.reason,
                    "grade": grade_name,
                    "grade_type": grade_type,
                    "shift": shift
                },
                db=db,
                user_ids=[{"id": teacher_id, "user_type": "teacher"}]
            )
        except Exception as e:
            logger.error(f"Failed to send notification to teacher {teacher_id}: {e}")

    # Determine overall success and message
    total_requested = len(request.selections)
    total_blocked = len(blocked_selections)

    logger.info(f"Batch permission result: {total_created} created, {total_blocked} blocked out of {total_requested} total")

    if total_created == 0 and total_blocked > 0:
        # All requests were blocked
        success = False
        message = f"All {total_blocked} permission request(s) were blocked. {blocked_selections[0]['message']}"
    elif total_blocked > 0:
        # Some requests were blocked
        success = True
        message = f"Created {total_created} permission(s), but {total_blocked} request(s) were blocked due to conflicts."
    else:
        # All requests successful
        success = True
        message = f"Permission requested successfully for {total_created} student/class selection(s)"

    return AskPermissionResponse(
        success=success,
        message=message,
        created_count=total_created,
        # Note: blocked_selections could be added to response schema if needed
    )

@router.post("/cancel-permission", response_model=CancelPermissionResponse)
async def cancel_permission(
    request: CancelPermissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Cancel permission requests created within the last 24 hours.
    Only allows cancellation of permissions that:
    - Belong to the parent's children
    - Have status 'IsPermission'
    - Were created ≤24 hours ago
    """
    if not request.attendance_ids:
        raise HTTPException(status_code=400, detail="At least one attendance ID is required")

    cancelled_count = 0
    realtime_events: List[Dict[str, Any]] = []
    total_attempted = len(request.attendance_ids)
    now = datetime.now()
    one_day_ago = now - timedelta(hours=24)
    teachers_to_notify = {}  # {teacher_id: [student_names]}
    parent_name = current_user.eName or current_user.kName or "Parent"

    logger.info(f"Current time: {now}, 24 hours ago: {one_day_ago}")

    for attendance_id in request.attendance_ids:
        # Fetch the attendance record with student and learning info
        check_query = text("""
            SELECT
                da.id, da.student_id, da.status, da.created_at, da.teacher_id,
                da.attendance_date, da.note, da.created_by, da.created_by_type,
                da.academic_id, da.program_id, da.grade_id, da.grade_type_id, da.shift_id,
                s.eName, s.kName, l.id as learning_id
            FROM daily_attendance da
            JOIN students s ON da.student_id = s.id
            JOIN learning l ON da.student_id = l.studentid
                AND da.program_id = l.programid
                AND da.grade_id = l.gradeid
                AND da.shift_id = l.shiftid
                AND da.academic_id = l.academicid
            WHERE da.id = :attendance_id
            LIMIT 1
        """)

        record = db.execute(check_query, {"attendance_id": attendance_id}).fetchone()

        if not record:
            logger.warning(f"Attendance record {attendance_id} not found")
            continue

        status = record[2]
        created_at = record[3]
        teacher_id = record[4]
        attendance_date = record[5]
        created_by = record[7]
        created_by_type = record[8]
        academic_id = record[9]
        program_id = record[10]
        grade_id = record[11]
        grade_type_id = record[12]
        shift_id = record[13]
        student_name_en = record[14]
        learning_id = record[16]

        # Validate status
        if status != 'IsPermission':
            logger.warning(f"Attendance {attendance_id} is not a permission (status: {status})")
            continue

        # Validate that only the creator can cancel their own permissions
        if created_by != current_user.id:
            logger.warning(f"User {current_user.id} cannot cancel permission {attendance_id} created by {created_by}")
            continue

        # Additional validation: only parents can cancel permissions they created
        if created_by_type != 'parent':
            logger.warning(f"Cannot cancel permission {attendance_id} created by {created_by_type}")
            continue

        # Validate time (≤24 hours)
        if created_at < one_day_ago:
            logger.warning(f"Attendance {attendance_id} is too old to cancel (created: {created_at}, age: {(now - created_at).total_seconds() / 3600:.2f} hours)")
            continue

        # TODO: Validate parent-child relationship
        # For now, we trust the frontend only sends valid IDs

        # Delete the record
        delete_query = text("DELETE FROM daily_attendance WHERE id = :id")
        result = db.execute(delete_query, {"id": attendance_id})
        rowcount = getattr(result, "rowcount", 0) or 0

        # Check if the delete actually affected a row
        if rowcount > 0:
            cancelled_count += 1
            logger.info(f"Successfully cancelled permission {attendance_id} for student {record[1]} on {attendance_date}")
            att_date_str = (
                attendance_date.strftime("%Y-%m-%d")
                if hasattr(attendance_date, "strftime")
                else str(attendance_date)[:10]
            )
            realtime_events.append({
                "academic_id": academic_id,
                "attendance_date": att_date_str,
                "student_id": record[1],
                "program_id": program_id,
                "grade_id": grade_id,
                "grade_type_id": grade_type_id,
                "shift_id": shift_id,
                "status": "CancelledPermission",
            })

            # Record the cancellation interaction
            cancel_parent_id = cast(int, getattr(current_user, "id", 0))
            record_parent_interaction(
                db, cancel_parent_id, record[1], learning_id, 'cancelled'
            )
        else:
            logger.warning(f"No rows affected when cancelling permission {attendance_id} - record may not exist or constraints prevented deletion")
        
        # Track teachers for notification
        if teacher_id:
            if teacher_id not in teachers_to_notify:
                teachers_to_notify[teacher_id] = []
            teachers_to_notify[teacher_id].append({
                "student_name": student_name_en,
                "date": attendance_date
            })
    
    db.commit()

    # Realtime push so teacher/attendance screens refresh immediately.
    try:
        from .websocket import broadcast_attendance_update
        for ev in realtime_events:
            await broadcast_attendance_update(
                academic_id=ev["academic_id"],
                attendance_date=ev["attendance_date"],
                student_id=ev["student_id"],
                program_id=ev["program_id"],
                grade_id=ev["grade_id"],
                grade_type_id=ev["grade_type_id"],
                shift_id=ev["shift_id"],
                status=ev["status"],
            )
    except Exception as e:
        logger.error(f"Failed to broadcast cancel permission realtime update: {e}")
    
    # Notify teachers about cancellations
    for teacher_id, cancellations in teachers_to_notify.items():
        try:
            student_names = [c["student_name"] for c in cancellations]
            students_list = ", ".join(student_names)
            cancelled_dates = sorted(
                {
                    _to_ymd(c.get("date"))
                    for c in cancellations
                    if c.get("date") is not None
                }
            )
            message_title = f"Permission Cancelled: {len(student_names)} Student(s)"
            dates_label = _format_dates_range(cancelled_dates)
            dates_line = f"\nDates: {dates_label}" if dates_label else ""
            message_body = (
                f"{parent_name} cancelled permission requests for: {students_list}."
                f"{dates_line}"
            )
            
            # Get teacher device tokens
            tokens = notification_service.get_teacher_device_tokens(db, teacher_id)
            
            # Send push notification (and save to DB) — offloaded to thread to avoid blocking event loop
            await asyncio.to_thread(
                notification_service.send_notification,
                device_tokens=tokens,
                title=message_title,
                body=message_body,
                data={
                    "type": "permission_cancelled",
                    "student_count": str(len(student_names)),
                    "dates": cancelled_dates,
                },
                db=db,
                user_ids=[{"id": teacher_id, "user_type": "teacher"}]
            )
        except Exception as e:
            logger.error(f"Failed to send cancellation notification to teacher {teacher_id}: {e}")
    
    # Determine success based on whether any permissions were actually cancelled
    success = cancelled_count > 0
    message = f"Successfully cancelled {cancelled_count} out of {total_attempted} permission(s)"

    if cancelled_count == 0:
        message = "No permissions could be cancelled (may be too old or invalid)"
    elif cancelled_count < total_attempted:
        message += ". Some permissions may be too old to cancel (over 24 hours)"

    return CancelPermissionResponse(
        success=success,
        message=message,
        cancelled_count=cancelled_count
    )

@router.post("/check-attendance-status")
async def check_attendance_status(
    request: CheckAttendanceStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Check if attendance is already marked by teacher for a specific student and date.
    Returns whether permission can be requested.
    """
    try:
        # Check if attendance already exists for this student and date
        attendance_check = text("""
            SELECT id, status, created_by_type, teacher_id
            FROM daily_attendance
            WHERE student_id = :student_id
                AND DATE(attendance_date) = :attendance_date
        """)

        result = db.execute(attendance_check, {
            "student_id": request.student_id,
            "attendance_date": request.attendance_date.strftime("%Y-%m-%d")
        }).fetchone()

        if result:
            # Attendance already exists
            attendance_id, status, created_by_type, teacher_id = result
            return {
                "can_request_permission": False,
                "reason": "attendance_already_marked",
                "existing_status": status,
                "marked_by": created_by_type,
                "teacher_id": teacher_id
            }
        else:
            # No attendance marked yet, permission can be requested
            return {
                "can_request_permission": True,
                "reason": "no_attendance_marked"
            }

    except Exception as e:
        logger.error(f"Error checking attendance status: {e}")
        return {
            "can_request_permission": False,
            "reason": "error_checking_status",
            "error": str(e)
        }

def check_parent_interaction_today(db: Session, parent_id: int, student_id: int, learning_id: int) -> bool:
    """
    Check if parent has already interacted with this learning today.
    Returns True if interaction exists (should block), False if allowed.
    """
    try:
        today = date.today()
        interaction = db.query(ParentPermissionInteraction).filter(
            ParentPermissionInteraction.parent_id == parent_id,
            ParentPermissionInteraction.student_id == student_id,
            ParentPermissionInteraction.learning_id == learning_id,
            ParentPermissionInteraction.interaction_date == today
        ).first()

        return interaction is not None
    except Exception as e:
        logger.error(f"Error checking parent interaction: {e}")
        return False  # Allow on error to avoid blocking legitimate requests

def record_parent_interaction(db: Session, parent_id: int, student_id: int, learning_id: int, interaction_type: str):
    """
    Record a parent permission interaction.
    """
    try:
        today = date.today()
        interaction = ParentPermissionInteraction(
            parent_id=parent_id,
            student_id=student_id,
            learning_id=learning_id,
            interaction_date=today,
            interaction_type=interaction_type
        )
        db.add(interaction)
        db.flush()  # Get the ID if needed
        logger.info(f"Recorded {interaction_type} interaction for parent {parent_id}, student {student_id}, learning {learning_id}")
    except Exception as e:
        logger.error(f"Error recording parent interaction: {e}")
        # Don't fail the main operation if logging fails

@router.get("/get-recent-permissions")
async def get_recent_permissions(
    academic_id: Optional[int] = None,
    program_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    grade_type_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    date: Optional[str] = None,  # YYYY-MM-DD format
    month: Optional[int] = None,
    year: Optional[int] = None,
    start_date: Optional[str] = None,  # YYYY-MM-DD — explicit range start (admin report)
    end_date: Optional[str] = None,    # YYYY-MM-DD — explicit range end (admin report)
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get permissions for parent's children (or all, for admins).

    By default returns the rolling last 30 days. When both [start_date] and
    [end_date] are given, that explicit window is used instead (no 30-day cap) —
    used by the admin report screen for arbitrary periods.
    Returns permission data grouped by student_id and learning_id.
    """
    try:
        is_parent = getattr(current_user, "user_type", "") == "parent"
        thirty_days_ago = datetime.now() - timedelta(days=30)

        # Attendance-date window: explicit range (admin) OR rolling 30 days.
        use_range = bool(start_date and end_date)
        params: dict[str, Any] = {}
        if use_range:
            date_window_clause = "DATE(da.attendance_date) BETWEEN :start_date AND :end_date"
            params['start_date'] = start_date
            params['end_date'] = end_date
        else:
            date_window_clause = "da.attendance_date >= :thirty_days_ago AND da.created_at >= :thirty_days_ago"
            params['thirty_days_ago'] = thirty_days_ago

        where_clauses = [
            "da.status = 'IsPermission'",
            "da.created_by_type = 'parent'",
            date_window_clause,
        ]

        if is_parent:
            # Get parent's children
            parent_query = text("SELECT myChilds FROM parents WHERE id = :user_id")
            parent_result = db.execute(parent_query, {"user_id": current_user.id}).fetchone()
            
            if not parent_result or not parent_result[0]:
                return {"permissions": []}
            
            # Parse myChilds
            my_childs_str = parent_result[0]
            if isinstance(my_childs_str, str):
                student_ids = [int(x.strip()) for x in my_childs_str.split(',') if x.strip()]
            else:
                student_ids = []
            
            if not student_ids:
                return {"permissions": []}
            
            placeholders = ','.join([f':id{i}' for i in range(len(student_ids))])
            for i, sid in enumerate(student_ids):
                params[f'id{i}'] = sid
            
            where_clauses.append(f"da.student_id IN ({placeholders})")
            where_clauses.append("da.created_by = :user_id")
            params['user_id'] = current_user.id
            logger.info(f"Fetching permissions for parent user {current_user.id} with {len(student_ids)} students")
        else:
            logger.info(f"Fetching permissions for teacher/admin user {current_user.id}")

        # Day / month / year filters only apply in the default (rolling) mode —
        # an explicit start/end range supersedes them.
        if not use_range:
            if date is not None and date != "":
                where_clauses.append("DATE(da.attendance_date) = :filter_date")
                params['filter_date'] = date
            if month is not None:
                where_clauses.append("EXTRACT(MONTH FROM da.attendance_date) = :filter_month")
                params['filter_month'] = month
            if year is not None:
                where_clauses.append("EXTRACT(YEAR FROM da.attendance_date) = :filter_year")
                params['filter_year'] = year

        # Add class filters if provided
        if academic_id is not None:
            where_clauses.append("da.academic_id = :academic_id")
            params['academic_id'] = academic_id
        if program_id is not None:
            where_clauses.append("da.program_id = :program_id")
            params['program_id'] = program_id
        if grade_id is not None:
            where_clauses.append("da.grade_id = :grade_id")
            params['grade_id'] = grade_id
        if grade_type_id is not None:
            where_clauses.append("da.grade_type_id = :grade_type_id")
            params['grade_type_id'] = grade_type_id
        if shift_id is not None:
            where_clauses.append("da.shift_id = :shift_id")
            params['shift_id'] = shift_id

        where_clause = " AND ".join(where_clauses)

        # First, get all permission records for the user within the time frame
        simple_query = text(f"""
            SELECT DISTINCT
                da.student_id,
                l.id as learning_id,
                da.note as reason,
                da.created_by_type,
                s.eName, s.kName, ur.avatar AS student_image,
                p.program_name,
                g.grade_name,
                gt.type_name as grade_type_name,
                pt.fatherName,
                pt.motherName,
                pt.gName,
                COALESCE(NULLIF(p.short_code, ''), p.program_name) as program_short_code
            FROM daily_attendance da
            JOIN learning l ON da.student_id = l.studentid
                AND da.program_id = l.programid
                AND da.grade_id = l.gradeid
                AND da.shift_id = l.shiftid
                AND da.academic_id = l.academicid
            JOIN students s ON da.student_id = s.id
            LEFT JOIN (
                SELECT user_id, MIN(avatar) AS avatar
                FROM users_resource
                WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                GROUP BY user_id
            ) ur ON ur.user_id = s.id
            LEFT JOIN parents pt ON da.created_by = pt.id
            LEFT JOIN program p ON da.program_id = p.id
            LEFT JOIN grade g ON da.grade_id = g.id
            LEFT JOIN grade_type gt ON da.grade_type_id = gt.id
            WHERE {where_clause}
            LIMIT 200
        """)

        try:
            basic_results = db.execute(simple_query, params).fetchall()
            logger.info(f"Found {len(basic_results)} basic permission records")
        except Exception as e:
            logger.error(f"Error executing basic permissions query: {e}")
            return {"permissions": []}

        # Group by student/learning/note combination in application code
        permission_groups = {}
        for row in basic_results:
            key = f"{row[0]}_{row[1]}_{row[2]}"  # student_id_learning_id_note
            if key not in permission_groups:
                permission_groups[key] = {
                    'student_id': row[0],
                    'learning_id': row[1],
                    'reason': row[2],
                    'created_by_type': row[3],
                    'student_name': row[4] or row[5] or "Student",
                    'student_image': row[6] or "",
                    'program_name': row[7] or "",
                    'grade_name': row[8] or "",
                    'grade_type_name': row[9] or "",
                    'creator_name': row[10] or row[11] or row[12] or "Parent",
                    'program_short_code': row[13] or "",
                }

        # Convert to list and limit
        permission_list = list(permission_groups.values())[:50]

        # Now get detailed information for each permission group
        permissions = []
        for perm in permission_list:
            try:
                student_id = perm['student_id']
                learning_id = perm['learning_id']
                note = perm['reason']

                # Window params shared by the detail query (same window as above).
                window_params = (
                    {'start_date': start_date, 'end_date': end_date}
                    if use_range else {'thirty_days_ago': thirty_days_ago}
                )

                # Get all attendance records for this permission group
                if is_parent:
                    detail_query = text(f"""
                        SELECT da.id, da.attendance_date, da.created_at
                        FROM daily_attendance da
                        WHERE da.student_id = :student_id
                            AND da.status = 'IsPermission'
                            AND da.note = :note
                            AND da.created_by = :user_id
                            AND {date_window_clause}
                        ORDER BY da.attendance_date
                        LIMIT 100
                    """)
                    detail_params = {
                        'student_id': student_id,
                        'note': note,
                        'user_id': current_user.id,
                        **window_params,
                    }
                else:
                    detail_query = text(f"""
                        SELECT da.id, da.attendance_date, da.created_at
                        FROM daily_attendance da
                        WHERE da.student_id = :student_id
                            AND da.status = 'IsPermission'
                            AND da.note = :note
                            AND da.created_by_type = 'parent'
                            AND {date_window_clause}
                        ORDER BY da.attendance_date
                        LIMIT 100
                    """)
                    detail_params = {
                        'student_id': student_id,
                        'note': note,
                        **window_params,
                    }

                detail_result = db.execute(detail_query, detail_params).fetchall()

                if detail_result:
                    attendance_dates = [r[1] for r in detail_result]
                    attendance_ids = [r[0] for r in detail_result]
                    latest_created_at = max(r[2] for r in detail_result)

                    # Check if cancellation is allowed (within 24 hours)
                    can_cancel = latest_created_at > (datetime.now() - timedelta(hours=24))

                    permissions.append({
                        "student_id": student_id,
                        "learning_id": learning_id,
                        "start_date": min(attendance_dates).isoformat(),
                        "days_count": len(set(attendance_dates)),  # Count distinct dates
                        "attendance_dates": sorted({_to_ymd(d) for d in attendance_dates}),
                        "reason": note,
                        "attendance_ids": attendance_ids,
                        "can_cancel": can_cancel,
                        "created_at": latest_created_at.isoformat() if latest_created_at else None,
                        "student_name": perm['student_name'],
                        "student_image": perm['student_image'],
                        "program_name": perm.get('program_name') or "",
                        "program_short_code": perm.get('program_short_code') or "",
                        "grade_name": perm.get('grade_name') or "",
                        "grade_type_name": perm.get('grade_type_name') or "",
                        "creator_name": perm.get('creator_name') or "Parent",
                    })
            except Exception as e:
                logger.error(f"Error processing permission group for student {perm['student_id']}: {e}")
                continue

        # Sort by start_date descending in application code
        permissions.sort(key=lambda x: x['start_date'], reverse=True)

        logger.info(f"Returning {len(permissions)} processed permissions")
        return {"permissions": permissions}
        
    except Exception as e:
        logger.error(f"Error fetching recent permissions: {e}")
        return {"permissions": []}


def _send_profile_edit_request_bg(
    request_id: int,
    student_id: int,
    requester_name: str,
    effective_eName: str,
    current_eName: str
):
    from ...core.database import SessionLocal
    db = SessionLocal()
    try:
        review_targets = notification_service.get_app_admin_user_ids(db)
        review_targets.extend(
            notification_service.get_role_permission_user_ids(
                db,
                "ReviewStudentProfileEdits",
            )
        )
        review_targets = list(
            {
                (int(target["id"]), str(target.get("user_type") or "teacher")): {
                    "id": int(target["id"]),
                    "user_type": str(target.get("user_type") or "teacher"),
                }
                for target in review_targets
                if target.get("id")
            }.values()
        )

        if review_targets:
            student_name = effective_eName or current_eName or f"Student #{student_id}"
            message_title = "Profile Edit Request"
            message_body = f"{requester_name} requested to edit profile of {student_name}."

            tokens = notification_service.resolve_device_tokens_for_users(
                db,
                review_targets,
            )

            notification_service.send_notification(
                device_tokens=tokens,
                title=message_title,
                body=message_body,
                data={
                    "type": "profile_edit_request",
                    "request_id": str(request_id),
                    "student_id": str(student_id),
                    "notification_key": f"profile_edit_request:{request_id}",
                },
                channel_id="message_channel",
                android_show_system_notification=True,
                db=db,
                user_ids=review_targets,
                redirect_route="profile_edit_requests",
                redirect_args={"request_id": request_id, "student_id": student_id},
                collapse_id=f"profile_edit_request_{request_id}",
            )
    except Exception as e:
        logger.error(f"Error sending profile edit request notification in background: {e}")
    finally:
        db.close()

def _resolve_requester_name(db: Session, requested_by: int, requested_by_type: Optional[str]) -> str:
    """Resolve a profile-edit requester's display name from the CORRECT table.

    Parents live in the `parents` table and, for a parent, ``requested_by`` stores
    ``parents.id`` (see :func:`update_my_child`). Teachers/admins live in ``users``.
    Looking a parent up in ``users`` returns the wrong row (or nothing), which is
    why requester names previously showed as "Unknown". We query the table that
    matches ``requested_by_type`` first, then fall back to the other table so a
    mislabelled request can still resolve.
    """
    parent_sql = "SELECT fatherName, motherName FROM parents WHERE id = :rid"
    user_sql = "SELECT kName, eName FROM users WHERE id = :rid"
    is_parent = (requested_by_type or "").lower() == "parent"
    for sql in ([parent_sql, user_sql] if is_parent else [user_sql, parent_sql]):
        try:
            row = db.execute(text(sql), {"rid": requested_by}).fetchone()
            if row and (row[0] or row[1]):
                return row[0] or row[1]
        except Exception as e:
            logger.error(
                f"Error resolving requester name for {requested_by} ({requested_by_type}): {e}"
            )
    return f"ID:{requested_by}"


@router.get("/my-children/{student_id}/pending-edit")
async def get_child_pending_edit(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Check if there is a pending profile edit request for a student.
    Returns the pending request details or null if none exists.
    """
    from ...models.student_profile_edit_request import StudentProfileEditRequest
    from ...services.child_access import assert_can_access_student

    # Staff may check any student; a parent only their own. Without this a parent
    # could walk the student ID space and read other children's names and the
    # name of whoever requested the edit.
    assert_can_access_student(db, current_user, student_id, action="view pending edits for")

    req = db.query(StudentProfileEditRequest).filter(
        StudentProfileEditRequest.student_id == student_id,
        StudentProfileEditRequest.status == 'pending'
    ).first()

    if not req:
        return {"has_pending": False, "request": None}

    req_name = _resolve_requester_name(db, req.requested_by, req.requested_by_type)

    return {
        "has_pending": True,
        "request": {
            "id": req.id,
            "requested_by_name": req_name,
            "requested_by_type": req.requested_by_type,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "kName": req.kName,
            "eName": req.eName,
        }
    }

@router.patch("/my-children/{student_id}")
async def update_my_child(
    student_id: int,
    body: UpdateMyChildRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Allow a parent to update their child's information (username, password, names, gender, dob, phone, address only).
    Verifies the student is in the parent's myChilds list.
    """
    # Check admin access: role==1 is superadmin, otherwise check permission table
    is_admin = getattr(current_user, "role", 0) == 1
    if not is_admin:
        perm_check = text("""
            SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
        """)
        perm_count = db.execute(perm_check, {"role_id": getattr(current_user, "role", 0)}).scalar()
        is_admin = bool(perm_count and perm_count > 0)

    if not is_admin:
        parent_id = cast(int, getattr(current_user, "id", 0))
        parent_row = db.execute(
            text("SELECT myChilds FROM parents WHERE id = :pid"),
            {"pid": parent_id}
        ).fetchone()
        if not parent_row or not parent_row[0]:
            raise HTTPException(status_code=404, detail="Parent or children not found")
        my_childs_str = str(parent_row[0]).strip()
        child_ids = [int(x.strip()) for x in my_childs_str.split(",") if x.strip()]
        if student_id not in child_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only update your own children"
            )

    # Fetch current student eName (for username generation when not provided)
    # plus the existing credentials, so a plain profile save never overwrites them.
    student_row = db.execute(
        text("SELECT eName, username, password FROM students WHERE id = :sid"),
        {"sid": student_id}
    ).fetchone()
    current_eName = (student_row[0] if student_row and student_row[0] else "").strip()
    current_username = (student_row[1] if student_row and student_row[1] else "").strip()
    current_password = (student_row[2] if student_row and student_row[2] else "").strip()
    effective_eName = (body.eName or current_eName or "").strip()
    generated_username: Optional[str] = None
    generated_password: Optional[str] = None

    def _generate_username() -> str:
        """First letter of first name + last name (lowercase). E.g. 'RORN Pisith' -> 'rpisith'."""
        parts = [p.strip() for p in effective_eName.split() if p.strip()]
        if len(parts) >= 2:
            first_letter = (parts[0][:1] or "").lower()
            last_name = parts[-1].lower().replace(" ", "")
            return (first_letter + last_name) or f"p{student_id}"
        if len(parts) == 1:
            return parts[0].lower()[:20] or f"p{student_id}"
        return f"p{student_id}"

    def _random_username(length: int = 8) -> str:
        """Random lowercase letters + digits."""
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choices(chars, k=length))

    def _username_exists(username: str, exclude_student_id: int) -> bool:
        r = db.execute(
            text("SELECT 1 FROM students WHERE username = :u AND id != :sid LIMIT 1"),
            {"u": username, "sid": exclude_student_id}
        ).fetchone()
        return r is not None

    # Build dynamic update: only set provided fields
    updates = []
    params: Dict[str, Any] = {"student_id": student_id}

    # Credentials are only touched when the caller actually supplied them, or
    # when the student has none yet.
    #
    # This used to rewrite BOTH fields on every save: saving the form without
    # typing anything regenerated the username from the student's name and reset
    # the password to "123456". That silently changed the student's login and
    # gave every student the same guessable password, so anyone who guessed a
    # classmate's name-derived username could sign in as them.
    if body.username is not None and (body.username or "").strip():
        updates.append("username = :username")
        params["username"] = body.username.strip()
    elif not current_username:
        proposed = _generate_username()
        if _username_exists(proposed, student_id):
            proposed = _random_username(8)
            while _username_exists(proposed, student_id):
                proposed = _random_username(8)
        updates.append("username = :username")
        params["username"] = proposed
        generated_username = proposed

    if body.password is not None and (body.password or "").strip():
        hashed = await run_in_threadpool(
            lambda: bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt())
        )
        updates.append("password = :password")
        params["password"] = hashed.decode("utf-8")
    elif not current_password:
        # First-time credentials: a random password, returned once to the caller
        # so they can pass it on. Never a shared constant.
        generated_password = secrets.token_urlsafe(9)
        hashed = await run_in_threadpool(
            lambda: bcrypt.hashpw(generated_password.encode("utf-8"), bcrypt.gensalt())
        )
        updates.append("password = :password")
        params["password"] = hashed.decode("utf-8")
    if body.kName is not None:
        updates.append("kName = :kName")
        params["kName"] = body.kName
    if body.eName is not None:
        updates.append("eName = :eName")
        params["eName"] = body.eName
    if body.gender is not None:
        updates.append("gender = :gender")
        params["gender"] = body.gender
    if body.dob is not None:
        updates.append("dob = :dob")
        params["dob"] = body.dob
    if body.is_foreigner is not None:
        updates.append("is_foreigner = :is_foreigner")
        params["is_foreigner"] = body.is_foreigner
    if body.student_phone is not None:
        updates.append("student_phone = :student_phone")
        params["student_phone"] = body.student_phone
    if body.province is not None:
        updates.append("province = :province")
        params["province"] = body.province
    if body.district is not None:
        updates.append("district = :district")
        params["district"] = body.district
    if body.commune is not None:
        updates.append("commune = :commune")
        params["commune"] = body.commune
    if body.village is not None:
        updates.append("village = :village")
        params["village"] = body.village
    if body.previousSchool is not None:
        updates.append("previousSchool = :previousSchool")
        params["previousSchool"] = body.previousSchool
    if body.student_noted is not None:
        updates.append("student_noted = :student_noted")
        params["student_noted"] = body.student_noted
    # branch: admin-only — silently ignored for non-admin callers
    if is_admin and body.branch is not None:
        updates.append("branch = :branch")
        params["branch"] = body.branch


    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if is_admin:
        updates.append("updated_at = NOW()")
        set_clause = ", ".join(updates)
        update_query = text(f"""
            UPDATE students
            SET {set_clause}
            WHERE id = :student_id
        """)
        try:
            result = db.execute(update_query, params)
            db.commit()
            if getattr(result, "rowcount", 0) == 0:
                raise HTTPException(status_code=404, detail="Student not found")
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating child {student_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to update child information")
            
        response: Dict[str, Any] = {
            "success": True,
            "message": "Child information updated successfully",
        }
        # Newly issued credentials are shown once so they can be handed over.
        if generated_username:
            response["generated_username"] = generated_username
        if generated_password:
            response["generated_password"] = generated_password
        return response
    else:
        # Create a StudentProfileEditRequest instead
        requester_id = getattr(current_user, "id", 0)
        # Determine if it's parent or teacher
        requester_type = getattr(current_user, "role_name", "") or "parent"
        
        # Check if an existing pending request exists for this student
        existing_request = db.execute(text("""
            SELECT id FROM student_profile_edit_requests
            WHERE student_id = :student_id AND status = 'pending'
        """), {"student_id": student_id}).fetchone()

        # Snapshot the student's CURRENT values so the history view can show a
        # real before -> after diff. The request row otherwise only stores the
        # NEW values, so without this we'd never know what was actually changed.
        snap = db.execute(text("""
            SELECT kName, eName, gender, dob, is_foreigner, student_phone,
                   province, district, commune, village, previousSchool, student_noted, branch
            FROM students WHERE id = :sid
        """), {"sid": student_id}).fetchone()
        snap_avatar = db.execute(text(
            "SELECT avatar FROM users_resource WHERE user_id = :sid AND user_type = 'student' LIMIT 1"
        ), {"sid": student_id}).fetchone()
        previous_values_json = json.dumps({
            "kName": snap[0] if snap else None,
            "eName": snap[1] if snap else None,
            "gender": snap[2] if snap else None,
            "dob": snap[3].isoformat() if snap and snap[3] else None,
            "is_foreigner": snap[4] if snap else None,
            "student_phone": snap[5] if snap else None,
            "province": snap[6] if snap else None,
            "district": snap[7] if snap else None,
            "commune": snap[8] if snap else None,
            "village": snap[9] if snap else None,
            "previousSchool": snap[10] if snap else None,
            "student_noted": snap[11] if snap else None,
            "branch": snap[12] if snap else None,
            "avatar": snap_avatar[0] if snap_avatar else None,
        }, default=str)

        if existing_request:
            upsert_query = text("""
                UPDATE student_profile_edit_requests SET
                    requested_by = :requested_by,
                    requested_by_type = :requested_by_type,
                    kName = :kName,
                    eName = :eName,
                    gender = :gender,
                    dob = :dob,
                    is_foreigner = :is_foreigner,
                    student_phone = :student_phone,
                    province = :province,
                    district = :district,
                    commune = :commune,
                    village = :village,
                    previousSchool = :previousSchool,
                    student_noted = :student_noted,
                    branch = :branch,
                    previous_values = :previous_values,
                    updated_at = NOW()
                WHERE id = :existing_id
            """)
        else:
            upsert_query = text("""
                INSERT INTO student_profile_edit_requests (
                    student_id, requested_by, requested_by_type,
                    kName, eName, gender, dob, is_foreigner, student_phone,
                    province, district, commune, village, previousSchool, student_noted, branch,
                    previous_values, status, created_at, updated_at
                ) VALUES (
                    :student_id, :requested_by, :requested_by_type,
                    :kName, :eName, :gender, :dob, :is_foreigner, :student_phone,
                    :province, :district, :commune, :village, :previousSchool, :student_noted, :branch,
                    :previous_values, 'pending', NOW(), NOW()
                )
            """)

        req_params = {
            "student_id": student_id,
            "requested_by": requester_id,
            "requested_by_type": requester_type,
            "kName": body.kName,
            "eName": effective_eName if body.eName else None,
            "gender": body.gender,
            "dob": body.dob,
            "is_foreigner": body.is_foreigner,
            "student_phone": body.student_phone,
            "province": body.province,
            "district": body.district,
            "commune": body.commune,
            "village": body.village,
            "previousSchool": body.previousSchool,
            "student_noted": body.student_noted,
            "branch": body.branch,
            "previous_values": previous_values_json,
            "existing_id": existing_request[0] if existing_request else None
        }
        
        try:
            write_result = db.execute(upsert_query, req_params)
            request_id = (
                int(existing_request[0])
                if existing_request
                else int(getattr(write_result, "lastrowid", 0) or 0)
            )
            db.commit()

            # Updating an existing pending request must not alert admins again.
            # They already have the pending item; repeated mobile retries or a
            # second save should update it silently instead of creating the
            # same push twice.
            if not existing_request and request_id > 0:
                requester_name = current_user.kName or current_user.eName or "User"
                background_tasks.add_task(
                    _send_profile_edit_request_bg,
                    request_id=request_id,
                    student_id=student_id,
                    requester_name=requester_name,
                    effective_eName=effective_eName,
                    current_eName=current_eName,
                )
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating profile edit request for child {student_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to submit update request")
            
        return {"success": True, "message": "Request submitted for admin approval"}


@router.post("/my-children/{student_id}/avatar")
async def upload_child_avatar(
    student_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload/replace avatar image for a specific child.
    Verifies the student is in the parent's myChilds list.
    """
    import os, uuid
    from ...services.storage_service import StorageService
    from ...models.user_resource import UserResource
    from ...models.settings import SystemSettings
    

    # 1. Verify parent-child relationship OR admin permission
    is_admin = getattr(current_user, "role", 0) == 1
    if not is_admin:
        perm_check = text("""
            SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
        """)
        perm_count = db.execute(perm_check, {"role_id": getattr(current_user, "role", 0)}).scalar()
        is_admin = bool(perm_count and perm_count > 0)

    if not is_admin:
        parent_id = cast(int, getattr(current_user, "id", 0))
        parent_row = db.execute(
            text("SELECT myChilds FROM parents WHERE id = :pid"),
            {"pid": parent_id}
        ).fetchone()
        if not parent_row or not parent_row[0]:
            raise HTTPException(status_code=404, detail="Parent or children not found")
        my_childs_str = str(parent_row[0]).strip()
        child_ids = [int(x.strip()) for x in my_childs_str.split(",") if x.strip()]
        if student_id not in child_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only update your own children"
            )

    # 2. Validate file type and size
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

    # Determine effective content type — fall back to extension if header is missing/generic
    effective_content_type = file.content_type or ""
    if not effective_content_type or effective_content_type in ("application/octet-stream", ""):
        ext = os.path.splitext(file.filename or "")[1].lower() if file.filename else ""
        ext_to_mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
        }
        effective_content_type = ext_to_mime.get(ext, "")

    if effective_content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, WEBP, GIF are allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 5 MB.",
        )

    # 3. Generate unique filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    if not ext:
        ext = ".jpg"
    unique_filename = f"avatar_{uuid.uuid4().hex[:10]}{ext}"

    # 4. Upload to StorageService
    avatar_url = StorageService.upload_file(
        file_data=contents, 
        folder="avatars", 
        filename=unique_filename,
        content_type=file.content_type
    )

    if not avatar_url:
        raise HTTPException(status_code=500, detail="Failed to upload avatar")

    # 5. Admins apply the avatar immediately; parents/non-admins stage it on a
    #    pending profile-edit request so an App Admin reviews it first. Nothing on
    #    the live student changes (and no old file is deleted) until approval.
    if is_admin:
        resource = db.query(UserResource).filter(
            UserResource.user_id == student_id,
            UserResource.user_type == 'student'
        ).first()
        if resource is None:
            resource = UserResource(user_id=student_id, user_type='student', status=1)
            db.add(resource)
            db.commit()
            db.refresh(resource)

        # Delete old avatar, then point the resource at the new one.
        if resource.avatar:
            StorageService.delete_file(resource.avatar, db.query(SystemSettings).first())
        resource.avatar = avatar_url
        db.commit()
        db.refresh(resource)

        return {
            "success": True,
            "message": "Avatar uploaded successfully",
            "avatar": avatar_url,
            "pending": False,
        }

    # Non-admin → stage on the (create-or-find) pending request.
    from ...models.student_profile_edit_request import StudentProfileEditRequest
    requester_id = getattr(current_user, "id", 0)
    requester_type = getattr(current_user, "role_name", "") or "parent"
    existing = db.query(StudentProfileEditRequest).filter(
        StudentProfileEditRequest.student_id == student_id,
        StudentProfileEditRequest.status == 'pending'
    ).first()

    if existing is not None:
        # Replacing a previously-staged photo before approval — drop the orphan.
        if existing.avatar and existing.avatar != avatar_url:
            StorageService.delete_file(existing.avatar, db.query(SystemSettings).first())
        existing.avatar = avatar_url
        existing.requested_by = requester_id
        existing.requested_by_type = requester_type
        db.commit()
    else:
        db.add(StudentProfileEditRequest(
            student_id=student_id,
            requested_by=requester_id,
            requested_by_type=requester_type,
            avatar=avatar_url,
            status='pending',
        ))
        db.commit()

    return {
        "success": True,
        "message": "Avatar submitted for admin approval",
        "avatar": avatar_url,
        "pending": True,
    }

@router.get("/children/{student_id}/schedule")
def get_child_schedule(
    student_id: int,
    academic_id: int = Query(..., description="Academic year ID"),
    program_id: Optional[int] = Query(None, description="Filter by program (required for correct class schedule)"),
    grade_id: Optional[int] = Query(None, description="Filter by grade"),
    shift_id: Optional[int] = Query(None, description="Filter by shift"),
    grade_type_id: Optional[int] = Query(None, description="Filter by grade type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get weekly schedule for a parent's child.
    Verifies parent-child relationship.
    Filter by program_id, grade_id, shift_id, grade_type_id to get schedule for a specific class.
    """
    parent_id = cast(int, getattr(current_user, "id", 0))
    parent_row = db.execute(
        text("SELECT myChilds FROM parents WHERE id = :pid"),
        {"pid": parent_id}
    ).fetchone()
    if not parent_row or not parent_row[0]:
        raise HTTPException(status_code=404, detail="Parent or children not found")
    my_childs_str = str(parent_row[0]).strip()
    child_ids = [int(x.strip()) for x in my_childs_str.split(",") if x.strip()]
    if student_id not in child_ids:
        raise HTTPException(
            status_code=403,
            detail="You can only view schedule for your own children"
        )

    where_parts = [
        "l.studentid = :student_id",
        "l.academicid = :academic_id",
        "lcs.is_active = TRUE",
        "lts.is_active = TRUE",
    ]
    params = {"student_id": student_id, "academic_id": academic_id}
    if program_id is not None:
        where_parts.append("l.programid = :program_id")
        params["program_id"] = program_id
    if grade_id is not None:
        where_parts.append("l.gradeid = :grade_id")
        params["grade_id"] = grade_id
    if shift_id is not None:
        where_parts.append("l.shiftid = :shift_id")
        params["shift_id"] = shift_id
    if grade_type_id is not None:
        where_parts.append("(l.grade_type_id <=> :grade_type_id)")
        params["grade_type_id"] = grade_type_id

    where_sql = " AND ".join(where_parts)
    query = text(f"""
        SELECT 
            lcs.id as schedule_id,
            lcs.time_slot_id,
            lts.sort_order,
            lcs.day_of_week,
            lts.slot_name,
            lts.start_time,
            lts.end_time,
            lcs.subject_id,
            s.subject_name,
            s.subject_name_us,
            lcs.room_number,
            COALESCE(lcs.teacher_id, ct.teacher_id) as teacher_id,
            CASE 
                WHEN COALESCE(lcs.teacher_id, ct.teacher_id) IS NULL THEN NULL
                WHEN COALESCE(u.isForeigner, u2.isForeigner) = 2
                    THEN COALESCE(NULLIF(u.eName, ''), NULLIF(u2.eName, ''), NULLIF(u.kName, ''), NULLIF(u2.kName, ''))
                ELSE COALESCE(NULLIF(u.kName, ''), NULLIF(u2.kName, ''), NULLIF(u.eName, ''), NULLIF(u2.eName, ''))
            END as teacher_name,
            lcs.notes,
            COALESCE(g.grade_name, gg.group_name) as grade_name,
            gt.type_name as grade_type_name,
            COALESCE(ur_t.avatar, ur_e.avatar) as teacher_image
        FROM learning l
        INNER JOIN grade g ON l.gradeid = g.id
        INNER JOIN grade_group gg ON g.group_id = gg.id
        INNER JOIN learning_class_schedules lcs ON lcs.grade_group_id = g.group_id
          AND lcs.academic_id = l.academicid
          AND lcs.program_id = l.programid
          AND (lcs.shift_id IS NULL OR lcs.shift_id = l.shiftid)
          AND (lcs.grade_id IS NULL OR lcs.grade_id = l.gradeid)
          AND (lcs.grade_type_id <=> l.grade_type_id)
        INNER JOIN learning_time_slots lts ON lcs.time_slot_id = lts.id
        INNER JOIN subjects s ON lcs.subject_id = s.id
        LEFT JOIN users u ON lcs.teacher_id = u.id
        LEFT JOIN users_resource ur_t ON ur_t.user_id = lcs.teacher_id AND ur_t.user_type = 'teacher'
        LEFT JOIN users_resource ur_e ON ur_e.user_id = lcs.teacher_id AND ur_e.user_type = 'employee'
        LEFT JOIN grade_type gt ON lcs.grade_type_id = gt.id
        -- Fallback: resolve teacher from class_teachers when lcs.teacher_id is NULL
        LEFT JOIN class_teachers ct ON ct.academic_id = l.academicid
          AND ct.program_id = l.programid
          AND ct.grade_id = l.gradeid
          AND ct.shift_id = l.shiftid
          AND (ct.grade_type_id <=> l.grade_type_id)
          AND lcs.teacher_id IS NULL
        LEFT JOIN users u2 ON u2.id = ct.teacher_id AND lcs.teacher_id IS NULL
        WHERE {where_sql}
        ORDER BY lcs.day_of_week, lts.sort_order
    """)
    result = db.execute(query, params)

    def _time_to_str(v: Any) -> str:
        """Convert MySQL TIME (timedelta) or string to HH:mm:ss."""
        if v is None:
            return "08:00:00"
        if isinstance(v, timedelta):
            t = (datetime.min + v).time()
            return t.strftime("%H:%M:%S")
        s = str(v).strip()
        if not s:
            return "08:00:00"
        # Already HH:mm:ss or HH:mm
        if ":" in s:
            parts = s.split(":")
            h = parts[0].zfill(2)
            m = parts[1].zfill(2) if len(parts) > 1 else "00"
            sec = parts[2].zfill(2) if len(parts) > 2 else "00"
            return f"{h}:{m}:{sec}"
        # Seconds since midnight
        try:
            secs = int(float(s))
            if 0 <= secs < 86400:
                h, r = divmod(secs, 3600)
                m, s_sec = divmod(r, 60)
                return f"{h:02d}:{m:02d}:{s_sec:02d}"
        except (ValueError, TypeError):
            pass
        return s if len(s) >= 8 else f"{s[:2] if len(s) >= 2 else '08'}:{s[2:4] if len(s) >= 4 else '00'}:00"

    schedules = []
    for row in result:
        d = dict(row._mapping)
        d["start_time"] = _time_to_str(d.get("start_time"))
        d["end_time"] = _time_to_str(d.get("end_time"))
        schedules.append(d)

    return {
        "student_id": student_id,
        "academic_id": academic_id,
        "schedule": schedules
    }


@router.post("/student-attendance-summary", response_model=AttendanceSummaryResponse)
async def get_student_attendance_summary(
    request: StudentAttendanceSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed attendance statistics for a student.
    Supports filtering by specific date, month, or year.
    Defaults to current month if no filters provided.
    Excludes weekends (Sat/Sun) and Holidays from total count.
    """
    try:
        # 1. Determine Date Range
        start_date = None
        end_date = None
        
        if request.date:
            start_date = request.date
            end_date = request.date
        elif request.start_date is not None and request.end_date is not None:
            start_date = request.start_date
            end_date = request.end_date
        elif request.month and request.year:
            import calendar
            last_day = calendar.monthrange(request.year, request.month)[1]
            start_date = date(request.year, request.month, 1)
            end_date = date(request.year, request.month, last_day)
        elif request.month:
            current_year = date.today().year
            import calendar
            last_day = calendar.monthrange(current_year, request.month)[1]
            start_date = date(current_year, request.month, 1)
            end_date = date(current_year, request.month, last_day)
        elif request.year:
            start_date = date(request.year, 1, 1)
            end_date = date(request.year, 12, 31)
        else:
            today = date.today()
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]
            start_date = date(today.year, today.month, 1)
            end_date = date(today.year, today.month, last_day)
            
        # Cap end_date at today to avoid counting future days as "Not Marked" or affecting percentage
        today = date.today()
        if end_date > today:
            end_date = today
            
        logger.info(f"Fetching stats for student {request.student_id} from {start_date} to {end_date} (Program: {request.program_id})")

        # 2. Fetch Holidays in Range
        holidays = db.query(Holiday).filter(Holiday.date.between(start_date, end_date)).all()
        holiday_dates = {h.date for h in holidays}

        # 3. Calculate Total Working Days (Excluding Weekends & Holidays)
        total_working_days = 0
        current_iter_date = start_date
        while current_iter_date <= end_date:
            # 0=Monday, 6=Sunday. Weekends are 5 (Sat) and 6 (Sun).
            if current_iter_date.weekday() < 5 and current_iter_date not in holiday_dates:
                 total_working_days += 1
            current_iter_date += timedelta(days=1)

        # 4. Query Daily Attendance
        # Only count records on working days (weekdays, non-holidays) to align with total_working_days
        # MySQL WEEKDAY: 0=Mon, 6=Sun. Weekdays = 0,1,2,3,4
        base_query = """
            SELECT status, COUNT(*) as count
            FROM daily_attendance
            WHERE student_id = :student_id
            AND DATE(attendance_date) BETWEEN :start_date AND :end_date
            AND WEEKDAY(attendance_date) < 5
            AND attendance_date NOT IN (
                SELECT date FROM holidays
                WHERE date BETWEEN :start_date AND :end_date
            )
        """
        
        params = {
            "student_id": request.student_id,
            "start_date": start_date,
            "end_date": end_date
        }

        if request.program_id is not None:
            base_query += " AND program_id = :program_id"
            params["program_id"] = request.program_id
        if request.grade_id is not None:
            base_query += " AND grade_id = :grade_id"
            params["grade_id"] = request.grade_id
        if request.grade_type_id_is_null is True:
            base_query += " AND grade_type_id IS NULL"
        elif request.grade_type_id is not None:
            base_query += " AND grade_type_id = :grade_type_id"
            params["grade_type_id"] = request.grade_type_id
        if request.shift_id is not None:
            base_query += " AND shift_id = :shift_id"
            params["shift_id"] = request.shift_id
        if request.academic_id is not None:
            base_query += " AND academic_id = :academic_id"
            params["academic_id"] = request.academic_id

        base_query += " GROUP BY status"
        
        try:
            results = db.execute(text(base_query), params).fetchall()
        except Exception as qe:
            # Fallback if holidays table missing or different schema
            logger.warning(f"Attendance query with holidays filter failed, using fallback: {qe}")
            base_query_fallback = """
                SELECT status, COUNT(*) as count
                FROM daily_attendance
                WHERE student_id = :student_id
                AND DATE(attendance_date) BETWEEN :start_date AND :end_date
                AND WEEKDAY(attendance_date) < 5
            """
            if request.program_id is not None:
                base_query_fallback += " AND program_id = :program_id"
            if request.grade_id is not None:
                base_query_fallback += " AND grade_id = :grade_id"
            if request.grade_type_id_is_null is True:
                base_query_fallback += " AND grade_type_id IS NULL"
            elif request.grade_type_id is not None:
                base_query_fallback += " AND grade_type_id = :grade_type_id"
            if request.shift_id is not None:
                base_query_fallback += " AND shift_id = :shift_id"
            if request.academic_id is not None:
                base_query_fallback += " AND academic_id = :academic_id"
            base_query_fallback += " GROUP BY status"
            results = db.execute(text(base_query_fallback), params).fetchall()
        
        stats = {
            "IsPresent": 0,
            "IsAbsent": 0,
            "IsPermission": 0,
            "IsLate": 0
        }
        
        total_marked_records = 0
        for row in results:
            status_val = (row[0] or "").strip() if row[0] else ""
            count = row[1] or 0
            status_lower = status_val.lower()
            
            if status_val in stats:
                stats[status_val] += count
                total_marked_records += count
            elif status_lower in ("ispresent", "present"):
                stats["IsPresent"] += count
                total_marked_records += count
            elif status_lower in ("isabsent", "absent"):
                stats["IsAbsent"] += count
                total_marked_records += count
            elif status_lower in ("ispermission", "permission"):
                stats["IsPermission"] += count
                total_marked_records += count
            elif status_lower in ("islate", "late"):
                stats["IsLate"] += count
                total_marked_records += count
                
        # 5. Calculate "Not Marked" and Percentage based on Working Days
        # Not Marked = Total Working Days - Total Marked Records (that happened on working days)
        # However, attendance ALREADY recorded on a holiday/weekend implies a special session?
        # Typically we just compare count. 
        # Ideally we should also filter the QUERY to exclude weekends/holidays if we are strict, 
        # but simpler to assume extra attendance is valid and counts towards total.
        
        # If total_working_days < total_marked_records, it means there was attendance on weekends/holidays.
        # In that case, we can't have negative "Not Marked".
        
        not_marked = 0
        if total_working_days > total_marked_records:
            not_marked = total_working_days - total_marked_records
            
        # Total records for display context is usually working days
        display_total_records = total_working_days if total_working_days > total_marked_records else total_marked_records
        
        attendance_percentage = 0.0
        if display_total_records > 0:
            present_sum = stats['IsPresent'] + stats['IsLate'] # Late counts as present-ish? or just partial? Usually Present+Late / Total
            # User request: "count % correct". Typically (Present + Late) / Total
            attendance_percentage = (present_sum / display_total_records) * 100
            
        return AttendanceSummaryResponse(
            present=stats['IsPresent'],
            absent=stats['IsAbsent'],
            permission=stats['IsPermission'],
            late=stats['IsLate'],
            not_marked=not_marked,
            total_records=display_total_records,
            attendance_percentage=attendance_percentage
        )

    except Exception as e:
        logger.error(f"Error fetching student stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/student-attendance-daily", response_model=StudentAttendanceDailyResponse)
async def get_student_attendance_daily(
    request: StudentAttendanceSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get daily attendance records for a student in a date range (for calendar + details).
    Returns list of records with date, status, who marked, created_at, updated_at.
    """
    parent_id = cast(int, getattr(current_user, "id", 0))
    parent_row = db.execute(
        text("SELECT myChilds FROM parents WHERE id = :pid"),
        {"pid": parent_id}
    ).fetchone()
    if not parent_row or not parent_row[0]:
        raise HTTPException(status_code=404, detail="Parent or children not found")
    my_childs_str = str(parent_row[0]).strip()
    child_ids = [int(x.strip()) for x in my_childs_str.split(",") if x.strip()]
    if request.student_id not in child_ids:
        raise HTTPException(status_code=403, detail="You can only view your own children's attendance")

    import calendar as cal_mod
    start_date = None
    end_date = None
    if request.date:
        start_date = request.date
        end_date = request.date
    elif request.start_date is not None and request.end_date is not None:
        start_date = request.start_date
        end_date = request.end_date
    elif request.month and request.year:
        last_day = cal_mod.monthrange(request.year, request.month)[1]
        start_date = date(request.year, request.month, 1)
        end_date = date(request.year, request.month, last_day)
    elif request.month:
        current_year = date.today().year
        last_day = cal_mod.monthrange(current_year, request.month)[1]
        start_date = date(current_year, request.month, 1)
        end_date = date(current_year, request.month, last_day)
    elif request.year:
        start_date = date(request.year, 1, 1)
        end_date = date(request.year, 12, 31)
    else:
        today = date.today()
        last_day = cal_mod.monthrange(today.year, today.month)[1]
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, last_day)

    base_sql = """
        SELECT
            da.id,
            DATE(da.attendance_date) AS attendance_date,
            da.status,
            da.note,
            da.created_at,
            da.updated_at,
            da.created_by_type,
            CASE
                WHEN u.id IS NULL THEN da.created_by_type
                WHEN u.isForeigner = 1 THEN COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
                ELSE COALESCE(NULLIF(u.eName, ''), NULLIF(u.kName, ''), 'Unknown')
            END AS marked_by
        FROM daily_attendance da
        LEFT JOIN users u ON u.id = da.teacher_id
        WHERE da.student_id = :student_id
        AND DATE(da.attendance_date) BETWEEN :start_date AND :end_date
    """
    params: Dict[str, Any] = {
        "student_id": request.student_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    if request.program_id is not None:
        base_sql += " AND da.program_id = :program_id"
        params["program_id"] = request.program_id
    if request.grade_id is not None:
        base_sql += " AND da.grade_id = :grade_id"
        params["grade_id"] = request.grade_id
    if request.grade_type_id_is_null is True:
        base_sql += " AND da.grade_type_id IS NULL"
    elif request.grade_type_id is not None:
        base_sql += " AND da.grade_type_id = :grade_type_id"
        params["grade_type_id"] = request.grade_type_id
    if request.shift_id is not None:
        base_sql += " AND da.shift_id = :shift_id"
        params["shift_id"] = request.shift_id
    if request.academic_id is not None:
        base_sql += " AND da.academic_id = :academic_id"
        params["academic_id"] = request.academic_id
    base_sql += " ORDER BY da.attendance_date ASC, da.created_at ASC"

    logger.info(
        f"Daily attendance query: student={request.student_id} "
        f"{start_date}→{end_date} "
        f"program={request.program_id} grade={request.grade_id} "
        f"grade_type={request.grade_type_id} "
        f"grade_type_is_null={request.grade_type_id_is_null} "
        f"shift={request.shift_id} academic={request.academic_id}"
    )
    try:
        rows = db.execute(text(base_sql), params).fetchall()
    except Exception as qe:
        logger.warning(f"student-attendance-daily query failed: {qe}")
        return StudentAttendanceDailyResponse(records=[])

    records = []
    for row in rows:
        r = row._mapping
        att_date = r.get("attendance_date")
        date_str = att_date.strftime("%Y-%m-%d") if hasattr(att_date, "strftime") else str(att_date)
        created = r.get("created_at")
        updated = r.get("updated_at")
        records.append(DailyAttendanceRecord(
            id=int(r.get("id", 0)),
            attendance_date=date_str,
            status=(r.get("status") or "").strip() or "Unknown",
            note=r.get("note") or None,
            created_at=created.isoformat() if created and hasattr(created, "isoformat") else (str(created) if created else None),
            updated_at=updated.isoformat() if updated and hasattr(updated, "isoformat") else (str(updated) if updated else None),
            marked_by=r.get("marked_by") or None,
            created_by_type=r.get("created_by_type") or None,
        ))
    logger.info(f"Daily attendance: returned {len(records)} record(s)")
    return StudentAttendanceDailyResponse(records=records)


@router.post("/link-request", response_model=LinkChildResponse)
async def request_link_child(
    request: LinkChildRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Parent requests to link an existing child (student) to their account.
    Creates a pending record in parent_student_link_requests for admin approval.
    """
    # Verify the user is a parent
    parent_id = cast(int, getattr(current_user, "id", 0))
    if not parent_id:
        raise HTTPException(status_code=401, detail="Invalid parent user")

    # Student cards have existed in both external-ID and internal-ID QR forms.
    # Prefer the external student code, then accept a numeric internal ID for
    # backward compatibility with older printed cards.
    student_identifier = request.student_id.strip()
    internal_id = int(student_identifier) if student_identifier.isdigit() else None
    student_check = db.execute(
        text("""
            SELECT id, studentid
            FROM students
            WHERE studentid = :student_identifier
               OR (:internal_id IS NOT NULL AND id = :internal_id)
            ORDER BY CASE WHEN studentid = :student_identifier THEN 0 ELSE 1 END
            LIMIT 1
        """),
        {
            "student_identifier": student_identifier,
            "internal_id": internal_id,
        },
    ).fetchone()
    if not student_check:
        raise HTTPException(
            status_code=404,
            detail=f"Student record not found for ID: {student_identifier}",
        )

    internal_student_id = student_check[0]
    external_student_id = str(student_check[1] or student_identifier)

    # Check if a pending or approved request already exists
    existing_request = db.execute(
        text("""
            SELECT id, status FROM parent_student_link_requests
            WHERE parent_id = :parent_id AND student_id = :internal_student_id
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE
        """),
        {"parent_id": parent_id, "internal_student_id": internal_student_id}
    ).fetchone()

    if existing_request:
        existing_status = existing_request[1]
        if existing_status == 'pending':
            return LinkChildResponse(success=False, message="You already have a pending request for this student.")
        elif existing_status == 'approved':
            return LinkChildResponse(success=False, message="This student is already linked to your account.")

    # Check if student is already in myChilds
    parent_record = db.execute(
        text("SELECT myChilds FROM parents WHERE id = :parent_id"),
        {"parent_id": parent_id}
    ).fetchone()
    
    if parent_record and parent_record[0]:
        current_childs = [int(x.strip()) for x in str(parent_record[0]).split(',') if x.strip()]
        if internal_student_id in current_childs:
            return LinkChildResponse(success=False, message="This student is already linked to your account.")

    try:
        if existing_request and existing_request[1] == 'rejected':
            link_request_id = int(existing_request[0])
            db.execute(
                text("""
                    UPDATE parent_student_link_requests
                    SET status = 'pending', updated_at = CURRENT_TIMESTAMP
                    WHERE id = :request_id
                """),
                {"request_id": link_request_id},
            )
        else:
            insert_result = db.execute(
                text("""
                    INSERT INTO parent_student_link_requests
                        (parent_id, student_id, status)
                    VALUES (:parent_id, :internal_student_id, 'pending')
                """),
                {
                    "parent_id": parent_id,
                    "internal_student_id": internal_student_id,
                },
            )
            link_request_id = int(getattr(insert_result, "lastrowid", 0) or 0)
        db.commit()
    except Exception:
        db.rollback()
        raise

    from ...services.link_request_notification_service import (
        notify_admins_new_link_request,
    )

    background_tasks.add_task(notify_admins_new_link_request, link_request_id)

    return LinkChildResponse(
        success=True,
        message=f"Request to link student {external_student_id} submitted successfully. Please wait for admin approval.",
    )

@router.get("/admin/link-requests/pending", response_model=List[AdminPendingLinkRequestItem])
def get_admin_pending_link_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all pending link requests for all parents (admin only).
    """
    # Check if user has admin permissions (AdminViewApp, AdminUpdateApp, or AdminDeleteApp)
    if getattr(current_user, "role", 0) != 1:
        perm_query = text("""
            SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id 
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
        """)
        perm_count = db.execute(perm_query, {"role_id": getattr(current_user, "role", 0)}).scalar()
        
        if not perm_count or perm_count == 0:
            raise HTTPException(status_code=403, detail="Not authorized. Admins only.")
    
    query = text("""
        SELECT 
            plr.id,
            MAX(plr.student_id) as student_id,
            MAX(s.studentid) as student_string_id,
            MAX(s.kName) as kName,
            MAX(s.eName) as eName,
            GROUP_CONCAT(DISTINCT p.program_name SEPARATOR ', ') as program_name,
            MAX(plr.status) as status,
            MAX(plr.created_at) as created_at,
            MAX(plr.parent_id) as parent_id,
            MAX(COALESCE(NULLIF(pt.fatherName, ''), NULLIF(pt.motherName, ''), pt.gName)) as parent_name,
            MAX(COALESCE(NULLIF(pt.fatherPhone, ''), NULLIF(pt.motherPhone, ''), pt.gPhone)) as parent_phone
        FROM parent_student_link_requests plr
        JOIN students s ON plr.student_id = s.id
        JOIN parents pt ON plr.parent_id = pt.id
        LEFT JOIN learning l ON l.studentid = s.id
        LEFT JOIN program p ON l.programid = p.id
        WHERE plr.status = 'pending'
        GROUP BY plr.id
        ORDER BY MAX(plr.created_at) DESC
    """)
    
    records = db.execute(query).fetchall()
    result = []
    for r in records:
        result.append(AdminPendingLinkRequestItem(
            id=r[0],
            student_id=r[1],
            student_string_id=r[2],
            kName=r[3],
            eName=r[4],
            program_name=r[5],
            status=r[6],
            created_at=str(r[7]) if r[7] else None,
            parent_id=r[8],
            parent_name=r[9] or "Unknown Parent",
            parent_phone=r[10] or ""
        ))
    
    return result

@router.delete("/link-requests/{request_id}")
def delete_link_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Allow a parent to remove a pending or rejected link request.
    """
    parent_id = cast(int, getattr(current_user, "id", 0))
    if not parent_id:
        raise HTTPException(status_code=401, detail="Invalid parent user")
        
    req = db.execute(
        text("SELECT status FROM parent_student_link_requests WHERE id = :req_id AND parent_id = :parent_id"),
        {"req_id": request_id, "parent_id": parent_id}
    ).fetchone()
    
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    db.execute(
        text("DELETE FROM parent_student_link_requests WHERE id = :req_id"),
        {"req_id": request_id}
    )
    db.commit()
    
    return {"success": True, "message": "Request removed successfully"}
@router.post("/admin/link-requests/{request_id}/action")
async def process_link_request(
    request_id: int,
    action_data: AdminProcessLinkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Approve or reject a pending link request (admin only).
    """
    # Check if user has admin permissions (AdminViewApp, AdminUpdateApp, or AdminDeleteApp)
    if getattr(current_user, "role", 0) != 1:
        perm_query = text("""
            SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = :role_id 
            AND p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
        """)
        perm_count = db.execute(perm_query, {"role_id": getattr(current_user, "role", 0)}).scalar()
        
        if not perm_count or perm_count == 0:
            raise HTTPException(status_code=403, detail="Not authorized. Admins only.")
        
    action = action_data.action.lower()
    if action not in ['approve', 'reject']:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")
        
    # Get request
    req_record = db.execute(
        text("""
            SELECT parent_id, student_id, status
            FROM parent_student_link_requests
            WHERE id = :req_id
            FOR UPDATE
        """),
        {"req_id": request_id}
    ).fetchone()
    
    if not req_record:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req_record[2] != 'pending':
        raise HTTPException(status_code=400, detail=f"Request is already {req_record[2]}")
        
    parent_id = req_record[0]
    student_id = req_record[1]
    
    try:
        db.execute(
            text("""
                UPDATE parent_student_link_requests
                SET status = :status, updated_at = CURRENT_TIMESTAMP
                WHERE id = :req_id
            """),
            {
                "status": 'approved' if action == 'approve' else 'rejected',
                "req_id": request_id,
            },
        )

        if action == 'approve':
            # Lock the parent row in the same transaction so concurrent child
            # approvals cannot overwrite one another's myChilds update.
            p_record = db.execute(
                text("""
                    SELECT myChilds FROM parents
                    WHERE id = :parent_id
                    FOR UPDATE
                """),
                {"parent_id": parent_id},
            ).fetchone()

            current_childs = []
            if p_record and p_record[0]:
                current_childs = [
                    x.strip()
                    for x in str(p_record[0]).split(',')
                    if x.strip()
                ]

            if str(student_id) not in current_childs:
                current_childs.append(str(student_id))
                db.execute(
                    text("""
                        UPDATE parents SET myChilds = :myChilds
                        WHERE id = :parent_id
                    """),
                    {
                        "myChilds": ",".join(current_childs),
                        "parent_id": parent_id,
                    },
                )

        db.commit()
    except Exception:
        db.rollback()
        raise

    from ...services.link_request_notification_service import (
        notify_parent_link_request_decision,
    )

    background_tasks.add_task(notify_parent_link_request_decision, request_id)

    decision = "approved" if action == "approve" else "rejected"
    return {"success": True, "message": f"Request {decision} successfully"}


@router.get("/link-requests/pending", response_model=List[PendingLinkRequestItem])
def get_pending_link_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all pending link requests for the current parent.
    """
    parent_id = cast(int, getattr(current_user, "id", 0))
    if not parent_id:
        raise HTTPException(status_code=401, detail="Invalid parent user")
        
    query = text("""
        SELECT 
            plr.id,
            MAX(plr.student_id) as student_id,
            MAX(s.studentid) as student_string_id,
            MAX(s.kName) as kName,
            MAX(s.eName) as eName,
            GROUP_CONCAT(DISTINCT p.program_name SEPARATOR ', ') as program_name,
            MAX(plr.status) as status,
            MAX(plr.created_at) as created_at
        FROM parent_student_link_requests plr
        JOIN students s ON plr.student_id = s.id
        LEFT JOIN learning l ON l.studentid = s.id
        LEFT JOIN program p ON l.programid = p.id
        WHERE plr.parent_id = :parent_id AND plr.status IN ('pending', 'rejected')
        GROUP BY plr.id
        ORDER BY MAX(plr.created_at) DESC
    """)
    
    records = db.execute(query, {"parent_id": parent_id}).fetchall()
    
    result = []
    for r in records:
        result.append(PendingLinkRequestItem(
            id=r[0],
            student_id=r[1],
            student_string_id=r[2],
            kName=r[3],
            eName=r[4],
            program_name=r[5],
            status=r[6],
            created_at=str(r[7]) if r[7] else None
        ))
        
    return result


def _require_app_admin(db: Session, current_user: User) -> AppAdmin:
    admin = (
        db.query(AppAdmin)
        .filter(AppAdmin.user_id == current_user.id, AppAdmin.is_locked == False)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=403, detail="Only active App Admins can perform this action")
    return admin


def _student_ids_for_parent(db: Session, parent_id: int, my_childs: Optional[str]) -> List[int]:
    ids: set[int] = set()
    if my_childs:
        for part in str(my_childs).split(","):
            p = part.strip()
            if p.isdigit():
                ids.add(int(p))
    rows = db.execute(
        text(
            """
            SELECT id FROM students
            WHERE CAST(NULLIF(TRIM(myparents), '') AS UNSIGNED) = :pid
            """
        ),
        {"pid": parent_id},
    ).fetchall()
    for row in rows:
        ids.add(int(row[0]))
    return list(ids)


def _iso_datetime(val: Any) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _fetch_linked_students(
    db: Session, parent_id: int, my_childs: Optional[str]
) -> List[LinkedStudentSummary]:
    student_ids = _student_ids_for_parent(db, parent_id, my_childs)
    if not student_ids:
        return []
    sid_list = ",".join(str(i) for i in student_ids)
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, kName, eName, gender, dob, status, student_phone
                FROM students
                WHERE id IN ({sid_list})
                ORDER BY id ASC
                """
            )
        ).fetchall()
    except Exception as e:
        logger.warning("Could not load linked students for parent %s: %s", parent_id, e)
        return []
    students: List[LinkedStudentSummary] = []
    for row in rows:
        students.append(
            LinkedStudentSummary(
                id=int(row[0]),
                kName=row[1],
                eName=row[2],
                gender=row[3],
                dob=_iso_datetime(row[4]),
                status=int(row[5]) if row[5] is not None else None,
                studentPhone=row[6],
            )
        )
    return students


def _parent_display_name_from_row(row: Any) -> str:
    for idx in (2, 3, 4, 1):
        val = (row[idx] or "").strip() if row[idx] else ""
        if val:
            return val
    return f"Parent #{row[0]}"


def _parent_registration_snapshot(
    parent: Parent, students: List[LinkedStudentSummary]
) -> Dict[str, Any]:
    return {
        "username": parent.username,
        "fatherName": parent.fatherName,
        "motherName": parent.motherName,
        "gName": parent.gName,
        "fatherPhone": parent.fatherPhone,
        "motherPhone": parent.motherPhone,
        "gPhone": parent.gPhone,
        "fatherJob": parent.fatherJob,
        "motherJob": parent.motherJob,
        "pEmail": parent.pEmail,
        "pTelegramId": parent.pTelegramId,
        "pProvince": parent.pProvince,
        "pDistrict": parent.pDistrict,
        "pCommune": parent.pCommune,
        "pVillage": parent.pVillage,
        "students": [s.model_dump() for s in students],
    }


def _admin_display_name(user: User) -> str:
    username = getattr(user, "username", None)
    if username and str(username).strip():
        return str(username).strip()
    return f"Admin #{user.id}"


def _safe_delete(db: Session, sql: str, params: dict) -> None:
    try:
        db.execute(text(sql), params)
    except Exception as e:
        logger.warning("Delete skipped (%s): %s", e, sql[:120])


def _avatar_urls_for_parent_and_students(
    db: Session, parent_id: int, student_ids: List[int]
) -> List[str]:
    """Collect stored avatar paths/URLs before users_resource rows are deleted."""
    urls: List[str] = []
    try:
        parent_row = db.execute(
            text(
                """
                SELECT avatar FROM users_resource
                WHERE user_type = 'parent' AND user_id = :pid AND avatar IS NOT NULL
                """
            ),
            {"pid": parent_id},
        ).fetchone()
        if parent_row and parent_row[0]:
            urls.append(str(parent_row[0]).strip())
    except Exception as e:
        logger.warning("Could not load parent avatar for cleanup %s: %s", parent_id, e)

    if not student_ids:
        return [u for u in urls if u]

    placeholders = ",".join(str(i) for i in student_ids)
    try:
        rows = db.execute(
            text(
                f"""
                SELECT avatar FROM users_resource
                WHERE user_type = 'student'
                  AND user_id IN ({placeholders})
                  AND avatar IS NOT NULL
                """
            ),
        ).fetchall()
        for row in rows:
            if row[0]:
                urls.append(str(row[0]).strip())
    except Exception as e:
        logger.warning(
            "Could not load student avatars for cleanup parent %s: %s",
            parent_id,
            e,
        )
    return [u for u in urls if u]


def _delete_stored_avatar_files(db: Session, avatar_urls: List[str]) -> None:
    """Remove avatar files from disk/cloud when a registration is rejected."""
    if not avatar_urls:
        return
    from ...models.settings import SystemSettings
    from ...services.storage_service import StorageService

    settings = db.query(SystemSettings).first()
    for url in avatar_urls:
        try:
            if StorageService.delete_file(url, settings):
                logger.info("Deleted avatar file: %s", url)
            else:
                logger.warning("Avatar file not deleted (missing or remote): %s", url)
        except Exception as e:
            logger.warning("Failed to delete avatar file %s: %s", url, e)


def _delete_parent_and_linked_students(db: Session, parent_id: int) -> List[str]:
    """Delete a pending parent and linked students. Returns file URLs to remove after commit."""
    from ...core.pending_student_cleanup import delete_students_by_ids

    parent = db.query(Parent).filter(Parent.id == parent_id).first()
    if not parent:
        return []

    student_ids = _student_ids_for_parent(db, parent_id, parent.myChilds)
    parent_avatar_urls = _avatar_urls_for_parent_and_students(db, parent_id, [])
    pending_files: List[str] = list(parent_avatar_urls)
    params = {"pid": parent_id}

    if student_ids:
        _, student_files = delete_students_by_ids(
            db, student_ids, commit=False, update_parent_my_childs=False
        )
        pending_files.extend(student_files)

        remaining = _student_ids_for_parent(db, parent_id, parent.myChilds)
        if remaining:
            logger.warning(
                "Parent #%s reject: %s linked student(s) remain after delete — retrying",
                parent_id,
                len(remaining),
            )
            _, more_files = delete_students_by_ids(
                db, remaining, commit=False, update_parent_my_childs=False
            )
            pending_files.extend(more_files)

    _safe_delete(
        db,
        "DELETE FROM parent_student_link_requests WHERE parent_id = :pid",
        params,
    )
    _safe_delete(
        db,
        "DELETE FROM parent_permission_interactions WHERE parent_id = :pid",
        params,
    )
    _safe_delete(
        db,
        "DELETE FROM pickup_requests WHERE parent_id = :pid",
        params,
    )
    _safe_delete(
        db,
        "DELETE FROM users_resource WHERE user_type = 'parent' AND user_id = :pid",
        params,
    )
    _safe_delete(
        db,
        "DELETE FROM device_tokens WHERE user_type = 'parent' AND user_id = :pid",
        params,
    )
    db.execute(text("DELETE FROM parents WHERE id = :pid"), params)
    return pending_files


@router.get(
    "/admin/registrations/pending",
    response_model=List[AdminPendingParentRegistrationItem],
)
def get_admin_pending_parent_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List parent accounts awaiting approval (App Admin only)."""
    _require_app_admin(db, current_user)

    try:
        ensure_parent_status_column(db)
    except Exception as e:
        logger.error(f"Parent status column ensure failed: {e}")
        raise HTTPException(status_code=500, detail="Database setup error for parent status")

    try:
        rows = db.execute(
            text(
                """
                SELECT
                    p.id,
                    p.username,
                    p.fatherName,
                    p.motherName,
                    p.gName,
                    p.fatherPhone,
                    p.motherPhone,
                    p.gPhone,
                    p.fatherJob,
                    p.motherJob,
                    p.pEmail,
                    p.pTelegramId,
                    p.pProvince,
                    p.pDistrict,
                    p.pCommune,
                    p.pVillage,
                    p.myChilds,
                    p.status,
                    p.created_at,
                    p.updated_at,
                    ur.avatar
                FROM parents p
                LEFT JOIN users_resource ur
                    ON ur.user_id = p.id AND ur.user_type = 'parent'
                WHERE COALESCE(p.status, 1) != 1
                ORDER BY p.created_at DESC, p.id DESC
                """
            )
        ).fetchall()
    except Exception as e:
        logger.exception("get_admin_pending_parent_registrations query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load pending parent registrations")

    result: List[AdminPendingParentRegistrationItem] = []
    for r in rows:
        try:
            my_childs = r[16]
            students = _fetch_linked_students(db, r[0], my_childs)
            result.append(
                AdminPendingParentRegistrationItem(
                    id=r[0],
                    username=r[1],
                    fatherName=r[2],
                    motherName=r[3],
                    gName=r[4],
                    fatherPhone=r[5],
                    motherPhone=r[6],
                    gPhone=r[7],
                    fatherJob=r[8],
                    motherJob=r[9],
                    pEmail=r[10],
                    pTelegramId=r[11],
                    pProvince=r[12],
                    pDistrict=r[13],
                    pCommune=r[14],
                    pVillage=r[15],
                    myChilds=my_childs,
                    children_count=len(students),
                    students=students,
                    status=r[17] or 0,
                    created_at=_iso_datetime(r[18]),
                    updated_at=_iso_datetime(r[19]),
                    avatar=r[20],
                )
            )
        except Exception as row_err:
            logger.warning("Skipping pending parent row %s: %s", r[0], row_err)
    return result


def _parent_registration_history_window(
    *,
    period: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    day: Optional[int] = None,
) -> tuple[datetime, datetime]:
    """Inclusive start, exclusive end for audit created_at filtering."""
    now = datetime.utcnow()
    p = (period or "month").lower().strip()
    y = year if year is not None else now.year

    if p == "year":
        start = datetime(y, 1, 1)
        end = datetime(y + 1, 1, 1)
        return start, end

    m = month if month is not None else now.month
    if p == "month":
        if m == 12:
            end = datetime(y + 1, 1, 1)
        else:
            end = datetime(y, m + 1, 1)
        return datetime(y, m, 1), end

    if p == "day":
        d = day if day is not None else now.day
        start = datetime(y, m, d)
        return start, start + timedelta(days=1)

    # Fallback: current month
    y = now.year
    m = now.month
    if m == 12:
        return datetime(y, m, 1), datetime(y + 1, 1, 1)
    return datetime(y, m, 1), datetime(y, m + 1, 1)


@router.get(
    "/admin/registrations/history",
    response_model=List[AdminParentRegistrationHistoryItem],
)
def get_admin_parent_registration_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    period: str = Query(
        "month",
        description="Filter period: day, month, or year",
    ),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    day: Optional[int] = Query(None, ge=1, le=31),
    limit: int = Query(200, ge=1, le=500),
):
    """Approve/reject audit log for parent registrations (App Admin only)."""
    _require_app_admin(db, current_user)

    period_norm = (period or "month").lower().strip()
    if period_norm not in ("day", "month", "year"):
        raise HTTPException(
            status_code=400,
            detail="Invalid period. Use day, month, or year.",
        )

    try:
        ensure_parent_registration_audit_table(db)
    except Exception as e:
        logger.error("Parent registration audit table ensure failed: %s", e)
        raise HTTPException(status_code=500, detail="Database setup error")

    range_start, range_end = _parent_registration_history_window(
        period=period_norm,
        year=year,
        month=month,
        day=day,
    )

    try:
        rows = db.execute(
            text(
                """
                SELECT
                    id, parent_id, action, admin_user_id, admin_display,
                    parent_snapshot, students_count, created_at
                FROM parent_registration_audit
                WHERE created_at >= :range_start AND created_at < :range_end
                ORDER BY created_at DESC, id DESC
                LIMIT :lim
                """
            ),
            {
                "range_start": range_start,
                "range_end": range_end,
                "lim": limit,
            },
        ).fetchall()
    except Exception as e:
        logger.exception("get_admin_parent_registration_history failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load registration history")

    history: List[AdminParentRegistrationHistoryItem] = []
    for row in rows:
        snapshot: Dict[str, Any] = {}
        raw_snap = row[5]
        if raw_snap:
            try:
                snapshot = json.loads(raw_snap) if isinstance(raw_snap, str) else {}
            except Exception:
                snapshot = {}
        students_raw = snapshot.get("students") or []
        students: List[LinkedStudentSummary] = []
        for s in students_raw:
            if isinstance(s, dict) and s.get("id") is not None:
                try:
                    students.append(LinkedStudentSummary(**s))
                except Exception:
                    pass
        display = (
            (snapshot.get("fatherName") or "").strip()
            or (snapshot.get("motherName") or "").strip()
            or (snapshot.get("gName") or "").strip()
            or (snapshot.get("username") or "").strip()
            or f"Parent #{row[1]}"
        )
        history.append(
            AdminParentRegistrationHistoryItem(
                id=int(row[0]),
                parent_id=int(row[1]),
                action=str(row[2]),
                admin_user_id=row[3],
                admin_display=row[4],
                display_name=display,
                username=snapshot.get("username"),
                students_count=int(row[6] or 0),
                students=students,
                fatherPhone=snapshot.get("fatherPhone"),
                motherPhone=snapshot.get("motherPhone"),
                gPhone=snapshot.get("gPhone"),
                created_at=_iso_datetime(row[7]) or "",
            )
        )
    return history


@router.post("/admin/registrations/{parent_id}/action")
async def process_parent_registration(
    parent_id: int,
    action_data: AdminParentRegistrationAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Approve (activate parent + children) or reject (delete parent + children)."""
    _require_app_admin(db, current_user)

    action = action_data.action.lower().strip()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")

    parent = db.query(Parent).filter(Parent.id == parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent registration not found")
    if getattr(parent, "status", 0) == 1:
        raise HTTPException(status_code=400, detail="Parent is already active")

    display_name = (
        parent.fatherName
        or parent.motherName
        or parent.gName
        or parent.username
        or f"Parent #{parent_id}"
    )

    students = _fetch_linked_students(db, parent_id, parent.myChilds)
    snapshot = _parent_registration_snapshot(parent, students)
    admin_label = _admin_display_name(current_user)

    if action == "reject":
        try:
            log_parent_registration_audit(
                db,
                action="reject",
                parent_id=parent_id,
                admin_user_id=current_user.id,
                admin_display=admin_label,
                parent_snapshot=snapshot,
                students_count=len(students),
            )
        except Exception as audit_err:
            logger.warning("Audit log before reject failed: %s", audit_err)

        reject_tokens = notification_service.get_parent_user_device_tokens(
            db, parent_id
        )
        background_tasks.add_task(
            notify_parent_registration_rejected,
            parent_id,
            display_name,
            reject_tokens,
        )
        try:
            files_to_delete = _delete_parent_and_linked_students(db, parent_id)
            db.commit()
            _delete_stored_avatar_files(db, files_to_delete)
            try:
                from ...services.query_cache import invalidate_cache
                invalidate_cache("students_list")
            except Exception:
                pass
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to reject parent registration {parent_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to reject registration")
        return {
            "success": True,
            "action": "reject",
            "message": "Registration rejected and removed",
            "processed_by": admin_label,
        }

    try:
        ensure_parent_status_column(db)
    except Exception as e:
        logger.error(f"Parent status column ensure failed: {e}")
        raise HTTPException(status_code=500, detail="Database setup error for parent status")

    student_ids = [s.id for s in students]
    try:
        db.execute(
            text("UPDATE parents SET status = 1 WHERE id = :pid"),
            {"pid": parent_id},
        ),
        try:
            db.execute(
                text("UPDATE parents SET updated_at = CURDATE() WHERE id = :pid"),
                {"pid": parent_id},
            )
        except Exception:
            pass
        if student_ids:
            sid_list = ",".join(str(s) for s in student_ids)
            db.execute(
                text(
                    f"UPDATE students SET status = 1 WHERE id IN ({sid_list})"
                )
            )
            try:
                db.execute(
                    text(
                        f"UPDATE students SET updated_at = NOW() WHERE id IN ({sid_list})"
                    )
                )
            except Exception:
                pass
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Failed to approve parent registration %s: %s", parent_id, e)
        raise HTTPException(status_code=500, detail="Failed to approve registration")

    try:
        log_parent_registration_audit(
            db,
            action="approve",
            parent_id=parent_id,
            admin_user_id=current_user.id,
            admin_display=admin_label,
            parent_snapshot=snapshot,
            students_count=len(students),
        )
        db.commit()
    except Exception as audit_err:
        db.rollback()
        logger.warning("Audit log after approve failed: %s", audit_err)

    background_tasks.add_task(
        notify_parent_registration_approved,
        parent_id,
        display_name,
    )

    return {
        "success": True,
        "action": "approve",
        "message": "Parent and linked students activated",
        "students_activated": len(student_ids),
        "processed_by": admin_label,
    }
