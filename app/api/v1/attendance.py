"""
Attendance API endpoints for teachers to mark student attendance.
Matches the structure used in the Telegram bot.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from starlette import status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Any, Dict
from datetime import date, datetime, timedelta
import json
import logging

from ...core import get_db
from ...auth import get_current_active_user
from ...models import User
from ...models.app_admin import AppAdmin
from ...schemas.attendance import (
    BranchResponse,
    ProgramResponse,
    GradeResponse,
    GradeTypeResponse,
    ShiftResponse,
    StudentAttendanceResponse,
    ClassInfoResponse,
    RecordAttendanceRequest,
    RecordAttendanceResponse,
    MonthlyAttendanceResponse,
    MonthlyAttendanceCounts,
)
from ...schemas.parents import (
    StudentAttendanceSummaryRequest,
    StudentAttendanceDailyResponse,
    DailyAttendanceRecord,
)
from ...utils.academic_year import is_historical_academic_year

logger = logging.getLogger(__name__)
router = APIRouter()


# Canonical implementation lives in app/utils/academic_year.py; alias kept
# so the many call sites in this file stay unchanged.
_is_historical_academic_year = is_historical_academic_year


def _current_user_is_super_admin(db: Session, user_id: int) -> bool:
    """Unlocked app super admins may mark attendance for any date."""
    admin = (
        db.query(AppAdmin)
        .filter(AppAdmin.user_id == user_id)
        .first()
    )
    if admin is None:
        return False
    if admin.is_locked:
        return False
    return bool(admin.is_super_admin)


@router.get("/branches", response_model=List[BranchResponse])
async def get_all_branches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all branches - CACHED for 10 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    cache_key = generate_cache_key("attendance_branches")
    
    # Try cache
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached
    
    query = text("""
        SELECT DISTINCT b.id, b.branch_name
        FROM branch b
        JOIN grade g ON g.branch_id = b.id
        JOIN learning l ON l.gradeid = g.id
        JOIN students s ON l.studentid = s.id
        WHERE s.status = 1
        ORDER BY b.branch_name ASC
    """)

    result = db.execute(query)
    branches = []
    for row in result:
        branches.append({
            "id": row[0],
            "branch_name": row[1]
        })
    
    # Cache for 10 minutes
    query_cache.set(cache_key, branches, ttl=600)

    return branches


@router.get("/teacher/branches", response_model=List[BranchResponse])
async def get_teacher_branches(
    teacher_id: int = Query(..., description="Teacher database ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get branches assigned to a teacher.
    Used for "My Class" flow.
    """
    query = text("""
        SELECT DISTINCT b.id, b.branch_name
        FROM class_teachers ct 
        JOIN grade g ON ct.grade_id = g.id
        JOIN branch b ON g.branch_id = b.id
        JOIN learning l ON l.gradeid = g.id
        JOIN students s ON l.studentid = s.id
        WHERE (ct.teacher_id = :teacher_id OR ct.teacher_assistant_id = :teacher_id)
        AND ct.academic_id = :academic_id AND (s.status = 1 OR :historical = 1)
        ORDER BY b.branch_name
    """)

    result = db.execute(query, {
        "teacher_id": teacher_id,
        "academic_id": academic_id,
        "historical": 1 if _is_historical_academic_year(db, academic_id) else 0,
    })
    branches = []
    for row in result:
        branches.append({
            "id": row[0],
            "branch_name": row[1]
        })
    
    return branches


@router.get("/programs", response_model=List[ProgramResponse])
async def get_programs_for_branch(
    branch_id: int = Query(..., description="Branch ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get programs - CACHED for 10 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    cache_key = generate_cache_key("attendance_programs", branch_id, academic_id)
    
    # Try cache
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached
    
    query = text("""
        SELECT DISTINCT p.id, p.program_name
        FROM program p
        JOIN grade g ON p.id = g.program_id
        JOIN learning l ON l.programid = p.id
        JOIN students s ON l.studentid = s.id
        WHERE g.branch_id = :branch_id AND g.academic_id = :academic_id AND (s.status = 1 OR :historical = 1)
        ORDER BY p.program_name ASC
    """)

    result = db.execute(query, {
        "branch_id": branch_id,
        "academic_id": academic_id,
        "historical": 1 if _is_historical_academic_year(db, academic_id) else 0,
    })
    programs = []
    for row in result:
        programs.append({
            "id": row[0],
            "program_name": row[1]
        })
    
    # Cache for 10 minutes
    query_cache.set(cache_key, programs, ttl=600)

    return programs


@router.get("/teacher/programs", response_model=List[ProgramResponse])
async def get_teacher_programs_for_branch(
    teacher_id: int = Query(..., description="Teacher database ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: int = Query(..., description="Branch ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get programs assigned to a teacher in a specific branch with active students.
    """
    query = text("""
        SELECT DISTINCT p.id, p.program_name
        FROM class_teachers ct 
        JOIN grade g ON ct.grade_id = g.id
        JOIN program p ON ct.program_id = p.id
        JOIN learning l ON l.gradeid = g.id
        JOIN students s ON l.studentid = s.id
        WHERE (ct.teacher_id = :teacher_id OR ct.teacher_assistant_id = :teacher_id)
        AND ct.academic_id = :academic_id AND g.branch_id = :branch_id AND (s.status = 1 OR :historical = 1)
        ORDER BY p.program_name
    """)

    result = db.execute(query, {
        "teacher_id": teacher_id,
        "academic_id": academic_id,
        "branch_id": branch_id,
        "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
    })
    programs = []
    for row in result:
        programs.append({
            "id": row[0],
            "program_name": row[1]
        })
    
    return programs


@router.get("/grades", response_model=List[GradeResponse])
async def get_grades_for_program(
    branch_id: int = Query(..., description="Branch ID"),
    program_id: int = Query(..., description="Program ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get grades - CACHED for 10 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    cache_key = generate_cache_key("attendance_grades", branch_id, program_id, academic_id)
    
    # Try cache
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached
    
    query = text("""
        SELECT g.id, g.grade_name, g.grade_type_id, g.group_Id as grade_group_id
        FROM grade g
        JOIN learning l ON l.gradeid = g.id
        JOIN students s ON l.studentid = s.id
        WHERE g.branch_id = :branch_id AND g.program_id = :program_id
        AND g.academic_id = :academic_id AND (s.status = 1 OR :historical = 1)
        GROUP BY g.id, g.grade_name, g.grade_type_id, g.group_Id
        ORDER BY g.id ASC
    """)

    result = db.execute(query, {
        "branch_id": branch_id,
        "program_id": program_id,
        "academic_id": academic_id,
        "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
    })
    grades = []
    logger.info(f"DEBUG: get_grades_for_program params: branch={branch_id}, program={program_id}, academic={academic_id}")
    for row in result:
        # Debug the row structure
        try:
            logger.info(f"DEBUG: Row type: {type(row)}")
            logger.info(f"DEBUG: Row content: {row}")
            # Try to access by index
            logger.info(f"DEBUG: row[3] value: {row[3]}")
        except Exception as e:
            logger.info(f"DEBUG: Error logging row: {e}")

        grades.append({
            "id": row[0],
            "grade_name": row[1],
            "grade_type_id": row[2] if row[2] is not None else None,
            "grade_group_id": row[3] if len(row) > 3 and row[3] is not None else None
        })
    
    # Cache for 10 minutes
    query_cache.set(cache_key, grades, ttl=600)

    return grades


@router.get("/teacher/grades", response_model=List[GradeResponse])
async def get_teacher_grades_for_branch_program(
    teacher_id: int = Query(..., description="Teacher database ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: int = Query(..., description="Branch ID"),
    program_id: int = Query(..., description="Program ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get grades assigned to a teacher within a specific branch and program with active students.
    """
    query = text("""
        SELECT DISTINCT g.id, g.grade_name, g.grade_type_id
        FROM class_teachers ct 
        JOIN grade g ON ct.grade_id = g.id
        JOIN learning l ON l.gradeid = g.id
        JOIN students s ON l.studentid = s.id
        WHERE (ct.teacher_id = :teacher_id OR ct.teacher_assistant_id = :teacher_id)
        AND ct.academic_id = :academic_id AND g.branch_id = :branch_id
        AND ct.program_id = :program_id AND (s.status = 1 OR :historical = 1)
        ORDER BY g.id
    """)

    result = db.execute(query, {
        "teacher_id": teacher_id,
        "academic_id": academic_id,
        "branch_id": branch_id,
        "program_id": program_id,
        "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
    })
    grades = []
    for row in result:
        grades.append({
            "id": row[0],
            "grade_name": row[1],
            "grade_type_id": row[2] if row[2] is not None else None
        })
    
    return grades


@router.get("/grade-types", response_model=List[GradeTypeResponse])
async def get_grade_types(
    academic_id: int = Query(..., description="Academic year ID"),
    program_id: int = Query(..., description="Program ID"),
    grade_id: int = Query(..., description="Grade ID"),
    type_ids: str = Query(..., description="Comma-separated list of grade type IDs"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get grade types that are actually associated with students in learning table.
    """
    type_id_list = [int(tid.strip()) for tid in type_ids.split(',') if tid.strip().isdigit()]
    if not type_id_list:
        return []
    
    # Build parameterized IN clause
    placeholders = ','.join([f':type_id_{i}' for i in range(len(type_id_list))])
    params = {f'type_id_{i}': tid for i, tid in enumerate(type_id_list)}
    params['academic_id'] = academic_id
    params['program_id'] = program_id
    params['grade_id'] = grade_id
    
    query = text(f"""
        SELECT DISTINCT gt.id, gt.type_name 
        FROM grade_type gt 
        JOIN learning l ON l.grade_type_id = gt.id 
        JOIN students s ON l.studentid = s.id
        WHERE gt.id IN ({placeholders})
        AND l.academicid = :academic_id AND l.programid = :program_id AND l.gradeid = :grade_id
        AND (s.status = 1 OR :historical = 1)
        ORDER BY gt.type_name
    """)
    params['historical'] = 1 if _is_historical_academic_year(db, academic_id) else 0
    
    result = db.execute(query, params)
    grade_types = []
    for row in result:
        grade_types.append({
            "id": row[0],
            "type_name": row[1]
        })
    
    return grade_types


@router.get("/teacher/grade-types", response_model=List[GradeTypeResponse])
async def get_teacher_grade_types_for_branch_program_grade(
    teacher_id: int = Query(..., description="Teacher database ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: int = Query(..., description="Branch ID"),
    program_id: int = Query(..., description="Program ID"),
    grade_id: int = Query(..., description="Grade ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get grade types assigned to a teacher within a specific branch, program, and grade with active students.
    """
    query = text("""
        SELECT DISTINCT gt.id, gt.type_name
        FROM class_teachers ct 
        JOIN grade g ON ct.grade_id = g.id
        JOIN grade_type gt ON ct.grade_type_id = gt.id
        JOIN learning l ON l.gradeid = g.id AND l.grade_type_id = gt.id
        JOIN students s ON l.studentid = s.id
        WHERE (ct.teacher_id = :teacher_id OR ct.teacher_assistant_id = :teacher_id)
        AND ct.academic_id = :academic_id AND g.branch_id = :branch_id
        AND ct.program_id = :program_id AND ct.grade_id = :grade_id AND (s.status = 1 OR :historical = 1)
        ORDER BY gt.type_name
    """)

    result = db.execute(query, {
        "teacher_id": teacher_id,
        "academic_id": academic_id,
        "branch_id": branch_id,
        "program_id": program_id,
        "grade_id": grade_id,
        "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
    })
    grade_types = []
    for row in result:
        grade_types.append({
            "id": int(str(row[0]).split(',')[0].strip()) if row[0] is not None and str(row[0]).strip().replace(',', '').isdigit() else (int(str(row[0]).split(',')[0].strip()) if row[0] is not None else row[0]),
            "type_name": row[1]
        })
    
    return grade_types


@router.get("/all-shifts", response_model=List[ShiftResponse])
async def get_all_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all shifts - CACHED for 10 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    cache_key = generate_cache_key("attendance_all_shifts")
    
    # Try cache
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached
    
    query = text("""
        SELECT id, shift_name, shift_name_en, start_at, end_at
        FROM shift
        ORDER BY start_at ASC
    """)

    result = db.execute(query)
    shifts = []
    for row in result:
        shifts.append({
            "id": row[0],
            "shift_name": row[1] or "",
            "shift_name_en": row[2] if row[2] else None,
            "start_at": str(row[3]) if row[3] else None,
            "end_at": str(row[4]) if row[4] else None,
        })
    
    # Cache for 10 minutes
    query_cache.set(cache_key, shifts, ttl=600)

    return shifts


@router.get("/shifts", response_model=List[ShiftResponse])
async def get_shifts_for_class(
    academic_id: int = Query(..., description="Academic year ID"),
    program_id: int = Query(..., description="Program ID"),
    grade_id: int = Query(..., description="Grade ID"),
    grade_type_id: Optional[int] = Query(None, description="Grade Type ID (optional)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get shifts - CACHED for 10 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    cache_key = generate_cache_key("attendance_shifts", academic_id, program_id, grade_id, grade_type_id)
    
    # Try cache
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached
    
    if grade_type_id:
        query = text("""
            SELECT DISTINCT s.id, s.shift_name, s.shift_name_en, s.start_at, s.end_at
            FROM learning l
            JOIN shift s ON l.shiftid = s.id
            JOIN students st ON l.studentid = st.id
            WHERE l.academicid = :academic_id AND l.programid = :program_id
            AND l.gradeid = :grade_id AND l.grade_type_id = :grade_type_id AND (st.status = 1 OR :historical = 1)
            ORDER BY s.shift_name
        """)
        params = {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id
        }
    else:
        query = text("""
            SELECT DISTINCT s.id, s.shift_name, s.shift_name_en, s.start_at, s.end_at
            FROM learning l
            JOIN shift s ON l.shiftid = s.id
            JOIN students st ON l.studentid = st.id
            WHERE l.academicid = :academic_id AND l.programid = :program_id
            AND l.gradeid = :grade_id AND l.grade_type_id IS NULL AND (st.status = 1 OR :historical = 1)
            ORDER BY s.shift_name
        """)
        params = {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id
        }
    params["historical"] = 1 if _is_historical_academic_year(db, academic_id) else 0

    result = db.execute(query, params)
    shifts = []
    for row in result:
        shifts.append({
            "id": row[0],
            "shift_name": row[1] or "",
            "shift_name_en": row[2] if row[2] else None,
            "start_at": str(row[3]) if row[3] else None,
            "end_at": str(row[4]) if row[4] else None,
        })
    
    # Cache for 10 minutes
    query_cache.set(cache_key, shifts, ttl=600)

    return shifts


@router.get("/teacher/shifts", response_model=List[ShiftResponse])
async def get_teacher_shifts_for_branch_program_grade_type(
    teacher_id: int = Query(..., description="Teacher database ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: int = Query(..., description="Branch ID"),
    program_id: int = Query(..., description="Program ID"),
    grade_id: int = Query(..., description="Grade ID"),
    grade_type_id: Optional[int] = Query(None, description="Grade Type ID (optional)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get shifts assigned to a teacher for a specific branch, program, grade, and grade type with active students.
    """
    if grade_type_id:
        query = text("""
            SELECT DISTINCT s.id, s.shift_name, s.shift_name_en, s.start_at, s.end_at
            FROM class_teachers ct 
            JOIN grade g ON ct.grade_id = g.id
            JOIN shift s ON ct.shift_id = s.id
            JOIN learning l ON l.gradeid = g.id AND l.shiftid = s.id
            JOIN students st ON l.studentid = st.id
            WHERE (ct.teacher_id = :teacher_id OR ct.teacher_assistant_id = :teacher_id) 
            AND ct.academic_id = :academic_id AND g.branch_id = :branch_id
            AND ct.program_id = :program_id AND ct.grade_id = :grade_id
            AND ct.grade_type_id = :grade_type_id AND (st.status = 1 OR :historical = 1)
            ORDER BY s.shift_name
        """)
        params = {
            "teacher_id": teacher_id,
            "academic_id": academic_id,
            "branch_id": branch_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id
        }
    else:
        query = text("""
            SELECT DISTINCT s.id, s.shift_name, s.shift_name_en, s.start_at, s.end_at
            FROM class_teachers ct 
            JOIN grade g ON ct.grade_id = g.id
            JOIN shift s ON ct.shift_id = s.id
            JOIN learning l ON l.gradeid = g.id AND l.shiftid = s.id
            JOIN students st ON l.studentid = st.id
            WHERE (ct.teacher_id = :teacher_id OR ct.teacher_assistant_id = :teacher_id) 
            AND ct.academic_id = :academic_id AND g.branch_id = :branch_id
            AND ct.program_id = :program_id AND ct.grade_id = :grade_id
            AND ct.grade_type_id IS NULL AND (st.status = 1 OR :historical = 1)
            ORDER BY s.shift_name
        """)
        params = {
            "teacher_id": teacher_id,
            "academic_id": academic_id,
            "branch_id": branch_id,
            "program_id": program_id,
            "grade_id": grade_id
        }
    params["historical"] = 1 if _is_historical_academic_year(db, academic_id) else 0

    result = db.execute(query, params)
    shifts = []
    for row in result:
        shifts.append({
            "id": row[0],
            "shift_name": row[1],
            "shift_name_en": row[2] if len(row) > 2 else None,
            "start_at": str(row[3]) if len(row) > 3 and row[3] is not None else None,
            "end_at": str(row[4]) if len(row) > 4 and row[4] is not None else None,
        })
    
    return shifts


@router.get("/students", response_model=List[StudentAttendanceResponse])
async def get_students_for_class(
    attendance_date: date = Query(..., description="Attendance date"),
    academic_id: int = Query(..., description="Academic year ID"),
    program_id: int = Query(..., description="Program ID"),
    grade_id: int = Query(..., description="Grade ID"),
    grade_type_id: Optional[int] = Query(None, description="Grade Type ID (optional)"),
    shift_id: int = Query(..., description="Shift ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get students for a specific class with their attendance status and parent information.
    """
    result_rows = None
    if grade_type_id:
        student_query = text("""
            SELECT s.id, s.kName, s.eName, s.gender, s.dob, l.academicid, COALESCE(ur.avatar, '') as avatar, da.status as attendance_status, da.note as attendance_note, da.created_by_type
            FROM learning l
            JOIN students s ON l.studentid = s.id
            LEFT JOIN (
                SELECT user_id, MIN(avatar) AS avatar
                FROM users_resource
                WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                GROUP BY user_id
            ) ur ON ur.user_id = s.id
            LEFT JOIN daily_attendance da ON s.id = da.student_id
                AND DATE(da.attendance_date) = :attendance_date
                AND da.shift_id = :shift_id AND da.academic_id = :academic_id
                AND da.program_id = :program_id AND da.grade_id = :grade_id
                AND (
                    da.grade_type_id = :grade_type_id
                    OR (da.grade_type_id IS NULL AND l.grade_type_id = :grade_type_id)
                )
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND l.grade_type_id = :grade_type_id AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """)
        params = {
            "attendance_date": attendance_date.strftime("%Y-%m-%d"),
            "shift_id": shift_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
        }
        result = db.execute(student_query, params)
        result_rows = result.fetchall()
    else:
        # When grade_type_id is NULL, first try to find students with NULL grade_type_id
        # But if no students found, try without grade_type_id filter (in case students have a grade_type_id)
        student_query = text("""
            SELECT s.id, s.kName, s.eName, s.gender, s.dob, l.academicid, COALESCE(ur.avatar, '') as avatar, da.status as attendance_status, da.note as attendance_note, da.created_by_type
            FROM learning l
            JOIN students s ON l.studentid = s.id
            LEFT JOIN (
                SELECT user_id, MIN(avatar) AS avatar
                FROM users_resource
                WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                GROUP BY user_id
            ) ur ON ur.user_id = s.id
            LEFT JOIN daily_attendance da ON s.id = da.student_id
                AND DATE(da.attendance_date) = :attendance_date
                AND da.shift_id = :shift_id AND da.academic_id = :academic_id
                AND da.program_id = :program_id AND da.grade_id = :grade_id
                AND da.grade_type_id IS NULL
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND l.grade_type_id IS NULL AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """)
        params = {
            "attendance_date": attendance_date.strftime("%Y-%m-%d"),
            "shift_id": shift_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
        }
        result = db.execute(student_query, params)
        result_rows = result.fetchall()
    
    # If no students found with NULL grade_type_id, try without grade_type_id filter
    # (This handles the case where class_teachers has NULL but learning table has a grade_type_id)
    if not result_rows and not grade_type_id:
        student_query = text("""
            SELECT s.id, s.kName, s.eName, s.gender, s.dob, l.academicid, COALESCE(ur.avatar, '') as avatar, da.status as attendance_status, da.note as attendance_note, da.created_by_type
            FROM learning l
            JOIN students s ON l.studentid = s.id
            LEFT JOIN (
                SELECT user_id, MIN(avatar) AS avatar
                FROM users_resource
                WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                GROUP BY user_id
            ) ur ON ur.user_id = s.id
            LEFT JOIN daily_attendance da ON s.id = da.student_id
                AND DATE(da.attendance_date) = :attendance_date
                AND da.shift_id = :shift_id AND da.academic_id = :academic_id
                AND da.program_id = :program_id AND da.grade_id = :grade_id
                AND (
                    (l.grade_type_id IS NULL AND da.grade_type_id IS NULL)
                    OR (da.grade_type_id = l.grade_type_id)
                )
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """)
        result = db.execute(student_query, params)
        result_rows = result.fetchall()
    students = []
    student_ids = []
    
    for row in result_rows:
        student_ids.append(row[0])
        students.append({
            "id": row[0],
            "kName": row[1] or "",
            "eName": row[2] or "",
            "gender": row[3] or "",
            "dob": row[4] if row[4] else None,
            "academicid": row[5],
            "avatar": row[6] if len(row) > 6 and row[6] else None,
            "attendance_status": row[7] if len(row) > 7 and row[7] else None,
            "attendance_note": row[8] if len(row) > 8 and row[8] else None,
            "created_by_type": row[9] if len(row) > 9 and row[9] else None,
            "parent_info": None  # Will be filled below
        })
    
    if not student_ids:
        return []
    
    # Get parent information
    # Build FIND_IN_SET conditions for each student ID
    find_in_set_parts = []
    parent_params = {}
    for i, sid in enumerate(student_ids):
        param_name = f'student_id_{i}'
        find_in_set_parts.append(f"FIND_IN_SET(:{param_name}, myChilds)")
        parent_params[param_name] = sid
    
    find_in_set_conditions = " OR ".join(find_in_set_parts)
    
    parents_query = text(f"""
        SELECT id, pTelegramId, myChilds, fatherName, motherName, fatherPhone, motherPhone 
        FROM parents 
        WHERE {find_in_set_conditions}
    """)
    
    parent_result = db.execute(parents_query, parent_params)
    parent_map = {}
    
    for row in parent_result:
        parent_id = row[0]
        my_childs = row[2] or ""
        child_ids = [int(cid.strip()) for cid in my_childs.split(',') if cid.strip().isdigit()]
        
        for child_id in child_ids:
            if child_id in student_ids:
                if child_id not in parent_map:
                    parent_map[child_id] = {
                        "id": parent_id,
                        "pTelegramId": row[1],
                        "myChilds": my_childs,
                        "fatherName": row[3],
                        "motherName": row[4],
                        "fatherPhone": row[5],
                        "motherPhone": row[6] if len(row) > 6 else None
                    }
    
    # Attach parent info to students
    for student in students:
        if student["id"] in parent_map:
            student["parent_info"] = parent_map[student["id"]]
    
    return students


@router.get("/classes", response_model=List[ClassInfoResponse])
async def get_all_classes_with_students(
    academic_id: int = Query(..., description="Academic year ID"),
    branch_id: Optional[int] = Query(None, description="Optional branch ID to filter by user's workplace"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all classes that have active students, grouped by branch/program/grade/gradeType/shift.
    Used for the attendance dashboard.
    Matches the logic from Telegram bot's database.py - only shows classes with active students.
    
    If branch_id is provided, filters by that branch. Otherwise, returns all classes from all branches.
    """
    # Only filter by branch_id if explicitly provided
    filter_branch_id = branch_id
    
    # Build query with optional branch filtering
    if filter_branch_id and filter_branch_id > 0:
        query = text("""
            SELECT 
                b.id AS branch_id, 
                b.branch_name,
                p.id AS program_id, 
                p.program_name,
                p.program_name_us,
                p.short_code AS program_short_code,
                g.id AS grade_id, 
                g.grade_name,
                g.grade_name_us,
                g.group_id AS grade_group_id,
                gt.id AS grade_type_id, 
                gt.type_name AS grade_type_name,
                s.id AS shift_id, 
                s.shift_name,
                s.shift_name_en,
                COUNT(DISTINCT st.id) AS student_count,
                COUNT(DISTINCT CASE WHEN st.gender = 'ប្រុស' THEN st.id END) AS male_count,
                COUNT(DISTINCT CASE WHEN st.gender = 'ស្រី' THEN st.id END) AS female_count,
                ct.teacher_id,
                COALESCE(NULLIF(u.kName, ''), u.eName) AS teacher_name,
                COALESCE(NULLIF(u.kName, ''), u.eName) AS teacher_kname,
                COALESCE(NULLIF(u.eName, ''), u.kName) AS teacher_ename,
                COALESCE(ur_t.avatar, ur_e.avatar) AS teacher_avatar,
                l.academicid,
                ac.academic_name,
                ac.academic_us_name
            FROM learning l
            JOIN students st ON l.studentid = st.id
            JOIN grade g ON l.gradeid = g.id
            JOIN program p ON l.programid = p.id
            JOIN branch b ON g.branch_id = b.id
            JOIN shift s ON l.shiftid = s.id
            LEFT JOIN academic ac ON l.academicid = ac.id
            LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
            LEFT JOIN class_teachers ct ON (
                l.programid = ct.program_id AND 
                l.gradeid = ct.grade_id AND 
                COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1) AND
                l.shiftid = ct.shift_id AND 
                g.branch_id = ct.branch_id AND 
                l.academicid = ct.academic_id
            )
            LEFT JOIN users u ON ct.teacher_id = u.id
            LEFT JOIN users_resource ur_t ON u.id = ur_t.user_id AND ur_t.user_type = 'teacher'
            LEFT JOIN users_resource ur_e ON u.id = ur_e.user_id AND ur_e.user_type = 'employee'
            WHERE l.academicid = :academic_id AND (st.status = 1 OR :historical = 1) AND b.id = :branch_id
            GROUP BY
                b.id, b.branch_name,
                p.id, p.program_name, p.program_name_us, p.short_code,
                g.id, g.grade_name, g.grade_name_us, g.group_id,
                gt.id, gt.type_name,
                s.id, s.shift_name, s.shift_name_en,
                ct.teacher_id, u.kName, u.eName, l.academicid, ac.academic_name, ac.academic_us_name
            ORDER BY b.branch_name, p.program_name, g.grade_name, gt.type_name, s.shift_name
        """)
        params = {
            "academic_id": academic_id,
            "branch_id": filter_branch_id,
            "historical": 1 if _is_historical_academic_year(db, academic_id) else 0,
        }
    else:
        query = text("""
            SELECT 
                b.id AS branch_id, 
                b.branch_name,
                p.id AS program_id, 
                p.program_name,
                p.program_name_us,
                p.short_code AS program_short_code,
                g.id AS grade_id, 
                g.grade_name,
                g.grade_name_us,
                g.group_id AS grade_group_id,
                gt.id AS grade_type_id, 
                gt.type_name AS grade_type_name,
                s.id AS shift_id, 
                s.shift_name,
                s.shift_name_en,
                COUNT(DISTINCT st.id) AS student_count,
                COUNT(DISTINCT CASE WHEN st.gender = 'ប្រុស' THEN st.id END) AS male_count,
                COUNT(DISTINCT CASE WHEN st.gender = 'ស្រី' THEN st.id END) AS female_count,
                ct.teacher_id,
                COALESCE(NULLIF(u.kName, ''), u.eName) AS teacher_name,
                COALESCE(NULLIF(u.kName, ''), u.eName) AS teacher_kname,
                COALESCE(NULLIF(u.eName, ''), u.kName) AS teacher_ename,
                COALESCE(ur_t.avatar, ur_e.avatar) AS teacher_avatar,
                l.academicid,
                ac.academic_name,
                ac.academic_us_name
            FROM learning l
            JOIN students st ON l.studentid = st.id
            JOIN grade g ON l.gradeid = g.id
            JOIN program p ON l.programid = p.id
            JOIN branch b ON g.branch_id = b.id
            JOIN shift s ON l.shiftid = s.id
            LEFT JOIN academic ac ON l.academicid = ac.id
            LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
            LEFT JOIN class_teachers ct ON (
                l.programid = ct.program_id AND 
                l.gradeid = ct.grade_id AND 
                COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1) AND
                l.shiftid = ct.shift_id AND 
                g.branch_id = ct.branch_id AND 
                l.academicid = ct.academic_id
            )
            LEFT JOIN users u ON ct.teacher_id = u.id
            LEFT JOIN users_resource ur_t ON u.id = ur_t.user_id AND ur_t.user_type = 'teacher'
            LEFT JOIN users_resource ur_e ON u.id = ur_e.user_id AND ur_e.user_type = 'employee'
            WHERE l.academicid = :academic_id AND (st.status = 1 OR :historical = 1)
            GROUP BY
                b.id, b.branch_name,
                p.id, p.program_name, p.program_name_us, p.short_code,
                g.id, g.grade_name, g.grade_name_us, g.group_id,
                gt.id, gt.type_name,
                s.id, s.shift_name, s.shift_name_en,
                ct.teacher_id, u.kName, u.eName, l.academicid, ac.academic_name, ac.academic_us_name
            ORDER BY b.branch_name, p.program_name, g.grade_name, gt.type_name, s.shift_name
        """)
        params = {
            "academic_id": academic_id,
            "historical": 1 if _is_historical_academic_year(db, academic_id) else 0,
        }
    
    result = db.execute(query, params)
    classes = []
    
    for row in result:
        classes.append({
            "branch_id": row[0],
            "branch_name": row[1] or "",
            "program_id": row[2],
            "program_name": row[3] or "",
            "program_name_us": row[4] if row[4] else None,
            "program_short_code": row[5] if row[5] else None,
            "grade_id": row[6],
            "grade_name": row[7] or "",
            "grade_name_us": row[8] if row[8] else None,
            "grade_group_id": row[9] if row[9] is not None else None,
            "grade_type_id": int(str(row[10]).split(',')[0].strip()) if row[10] is not None and str(row[10]).strip() else None,
            "grade_type_name": row[11] if row[11] else None,
            "shift_id": row[12],
            "shift_name": row[13] or "",
            "shift_name_en": row[14] if row[14] else None,
            "student_count": int(row[15]) if row[15] else 0,
            "male_count": int(row[16]) if row[16] else 0,
            "female_count": int(row[17]) if row[17] else 0,
            "teacher_id": row[18] if row[18] is not None else None,
            "teacher_name": row[19] if row[19] else None,
            "teacher_kname": row[20] if row[20] else None,
            "teacher_ename": row[21] if row[21] else None,
            "teacher_avatar": row[22] if row[22] else None,
            "academic_id": row[23],
            "academic_name": row[24] if row[24] else None,
            "academic_us_name": row[25] if row[25] else None,
        })
    
    return classes


@router.get("/settings")
async def get_attendance_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get attendance settings - CACHED for 5 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    cache_key = generate_cache_key("attendance_settings")
    
    # Try cache
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached
    
    academic_id = None

    enterprise_name = None
    e_province = None
    
    # Method 1: Try to get from settings table (PRIMARY METHOD - matches Telegram bot)
    # Telegram bot uses: SELECT academicid FROM settings LIMIT 1
    # academicid is stored as an integer like 2, 1, 3, 4, or 6
    try:
        query = text("SELECT academicid, enterpriseName, eProvince FROM settings LIMIT 1")
        result = db.execute(query)
        row = result.fetchone()
        if row and row[0] is not None:
            academicid_value = row[0]
            enterprise_name = row[1] if len(row) > 1 else None
            e_province = row[2] if len(row) > 2 else None
            
            # Handle both integer and string types from database
            if isinstance(academicid_value, int):
                academic_id = academicid_value
            elif isinstance(academicid_value, (str, bytes)):
                # If it's a string, try to parse it
                try:
                    academicid_str = str(academicid_value).strip()
                    # Handle space-separated values like "2 1" - take the first one
                    if ' ' in academicid_str:
                        parts = academicid_str.split()
                        academic_id = int(parts[0]) if parts else None
                    else:
                        academic_id = int(academicid_str)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse academicid '{academicid_value}' as integer: {e}")
                    academic_id = None
            else:
                # Try to convert to int directly
                try:
                    academic_id = int(academicid_value)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not convert academicid '{academicid_value}' to integer: {e}")
                    academic_id = None
        else:
            logger.warning("No academicid found in settings table (row is None or value is None)")
            academic_id = None
    except Exception as e:
        # Table might not exist or error occurred
        # Check if it's a table not found error (1146)
        error_str = str(e)
        if "1146" in error_str and "settings" in error_str:
             logger.warning("Settings table not found. Using fallback method to determine academic year.")
        else:
             logger.error(f"Error getting academicid from settings: {e}", exc_info=True)
        academic_id = None
    
    # Method 2: Try to get from learning table (most recent academic_id with active students)
    # This matches the pattern used in Telegram bot when settings are not available
    if academic_id is None:
        try:
            query = text("""
                SELECT DISTINCT l.academicid 
                FROM learning l
                JOIN students s ON l.studentid = s.id
                WHERE s.status = 1
                ORDER BY l.academicid DESC 
                LIMIT 1
            """)
            result = db.execute(query)
            row = result.fetchone()
            if row and row[0] is not None:
                academic_id = int(row[0]) if row[0] is not None else None
        except Exception as e:
            logger.warning(f"Error getting academic_id from learning table: {e}")
    
    # Method 3: Try alternative column names from learning table (fallback)
    if academic_id is None:
        try:
            query = text("SELECT DISTINCT academic_id FROM learning ORDER BY academic_id DESC LIMIT 1")
            result = db.execute(query)
            row = result.fetchone()
            if row and row[0] is not None:
                academic_id = int(row[0]) if row[0] is not None else None
        except Exception as e:
            logger.warning(f"Error getting academic_id from learning.academic_id: {e}")
    
    # Method 4: Try to get the most recent academic_id from academic table
    if academic_id is None:
        try:
            query = text("SELECT id FROM academic ORDER BY id DESC LIMIT 1")
            result = db.execute(query)
            row = result.fetchone()
            if row and row[0] is not None:
                academic_id = int(row[0]) if row[0] is not None else None
        except Exception as e:
            logger.warning(f"Error getting academic_id from academic table: {e}")
    
    # Default fallback - use 1 if nothing found (but log a warning)
    if academic_id is None:
        logger.warning("All methods failed to get academic_id, using default value of 1")
        academic_id = 1  # Default academic year ID
    
    # Ensure academic_id is always an integer, never None
    academic_id = int(academic_id) if academic_id is not None else 1
    
    result = {
        "academic_id": academic_id,
        "enterpriseName": enterprise_name,
        "eProvince": e_province,
        "message": "Settings retrieved successfully",
    }
    
    # Cache for 5 minutes (300 seconds)
    query_cache.set(cache_key, result, ttl=300)
    
    return result


@router.get("/monthly", response_model=MonthlyAttendanceResponse)
async def get_monthly_attendance(
    academic_id: int = Query(..., description="Academic year ID"),
    program_id: int = Query(..., description="Program ID"),
    grade_id: int = Query(..., description="Grade ID"),
    grade_type_id: Optional[int] = Query(None, description="Grade Type ID (optional)"),
    shift_id: int = Query(..., description="Shift ID"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD). If not provided, uses month/year"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). If not provided, uses month/year"),
    month: Optional[int] = Query(None, description="Month (1-12). Used if start_date/end_date not provided"),
    year: Optional[int] = Query(None, description="Year (e.g., 2024). Used if start_date/end_date not provided"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get attendance counts for all students in a class for a date range or month.
    Returns counts for Present (P), Absent (A), Late (L), and Permission (Permission) statuses.
    """
    # Use date range if provided, otherwise use month/year
    if start_date and end_date:
        first_day = date.fromisoformat(start_date)
        last_day = date.fromisoformat(end_date)
        # Add 1 day to end_date to make it inclusive
        last_day = last_day + timedelta(days=1)
        # For response, use first day's month/year
        response_month = first_day.month
        response_year = first_day.year
    elif month and year:
        # Calculate first and last day of the month
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1)
        else:
            last_day = date(year, month + 1, 1)
        response_month = month
        response_year = year
    else:
        # Default to current month if nothing provided
        today = date.today()
        first_day = date(today.year, today.month, 1)
        if today.month == 12:
            last_day = date(today.year + 1, 1, 1)
        else:
            last_day = date(today.year, today.month + 1, 1)
        response_month = today.month
        response_year = today.year
    
    # Get all students in the class
    historical = 1 if _is_historical_academic_year(db, academic_id) else 0
    if grade_type_id:
        student_query = text("""
            SELECT DISTINCT s.studentid, s.kName, s.eName, COALESCE(s.gender, '') as gender, s.id
            FROM learning l
            JOIN students s ON l.studentid = s.id
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND l.grade_type_id = :grade_type_id AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """)
        params = {
            "shift_id": shift_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "historical": historical
        }
    else:
        student_query = text("""
            SELECT DISTINCT s.studentid, s.kName, s.eName, COALESCE(s.gender, '') as gender, s.id
            FROM learning l
            JOIN students s ON l.studentid = s.id
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND l.grade_type_id IS NULL AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """)
        params = {
            "shift_id": shift_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "historical": historical
        }

    result = db.execute(student_query, params)
    student_list = []
    student_ids = []

    for row in result:
        student_id_for_display = str(row[0] or "")  # s.studentid for display (convert to string)
        student_id_for_query = row[4]    # s.id for querying attendance (integer)
        student_ids.append(student_id_for_query)
        student_list.append({
            "student_id": student_id_for_display,  # Display s.studentid as string
            "student_internal_id": student_id_for_query,  # Internal id for mapping attendance
            "kName": row[1] or "",
            "eName": row[2] or "",
            "gender": row[3] or "",
            "present_count": 0,
            "absent_count": 0,
            "late_count": 0,
            "permission_count": 0
        })
    
    # Fallback: If no students found and grade_type_id was not provided, try without the strict IS NULL filter
    # This matches the behavior in get_students_for_class
    if not student_ids and not grade_type_id:
        fallback_query = text("""
            SELECT DISTINCT s.studentid, s.kName, s.eName, COALESCE(s.gender, '') as gender, s.id
            FROM learning l
            JOIN students s ON l.studentid = s.id
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """)
        fallback_params = {
            "shift_id": shift_id,
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_id": grade_id,
            "historical": historical
        }
        
        fallback_result = db.execute(fallback_query, fallback_params)
        for row in fallback_result:
            student_id_for_display = str(row[0] or "")
            student_id_for_query = row[4]
            student_ids.append(student_id_for_query)
            student_list.append({
                "student_id": student_id_for_display,
                "student_internal_id": student_id_for_query,
                "kName": row[1] or "",
                "eName": row[2] or "",
                "gender": row[3] or "",
                "present_count": 0,
                "absent_count": 0,
                "late_count": 0,
                "permission_count": 0
            })
    
    if not student_ids:

        # Determine response month/year based on input
        if start_date and end_date:
            first_day = date.fromisoformat(start_date)
            response_month = first_day.month
            response_year = first_day.year
        elif month and year:
            response_month = month
            response_year = year
        else:
            today = date.today()
            response_month = today.month
            response_year = today.year
            
        return MonthlyAttendanceResponse(
            month=response_month,
            year=response_year,
            total_students=0,
            total_present=0,
            total_absent=0,
            total_late=0,
            total_permission=0,
            students=[]
        )
    
    # Get attendance counts for the month
    # Build IN clause with proper parameter substitution
    student_ids_str = ','.join(str(sid) for sid in student_ids)
    attendance_query = text(f"""
        SELECT 
            da.student_id,
            da.status,
            COUNT(*) as count
        FROM daily_attendance da
        WHERE da.student_id IN ({student_ids_str})
        AND da.attendance_date >= :first_day
        AND da.attendance_date < :last_day
        AND da.shift_id = :shift_id
        AND da.academic_id = :academic_id
        AND da.status IS NOT NULL
        GROUP BY da.student_id, da.status
    """)
    
    attendance_params = {
        "first_day": first_day.strftime("%Y-%m-%d"),
        "last_day": last_day.strftime("%Y-%m-%d"),
        "shift_id": shift_id,
        "academic_id": academic_id
    }
    
    attendance_result = db.execute(attendance_query, attendance_params)
    
    # Map attendance counts to students using internal id (integer)
    student_map = {s["student_internal_id"]: s for s in student_list}
    
    total_present = 0
    total_absent = 0
    total_late = 0
    total_permission = 0
    
    for row in attendance_result:
        student_internal_id = row[0]  # This is the integer id from students table
        status = row[1]
        count = row[2]
        
        if student_internal_id in student_map:
            if status == 'IsPresent':
                student_map[student_internal_id]["present_count"] = count
                total_present += count
            elif status == 'IsAbsent':
                student_map[student_internal_id]["absent_count"] = count
                total_absent += count
            elif status == 'IsLate':
                student_map[student_internal_id]["late_count"] = count
                total_late += count
            elif status == 'IsPermission':
                student_map[student_internal_id]["permission_count"] = count
                total_permission += count
    
    # Convert to response format
    students = [
        MonthlyAttendanceCounts(
            student_id=s["student_id"],
            kName=s["kName"],
            eName=s["eName"],
            gender=s["gender"],
            present_count=s["present_count"],
            absent_count=s["absent_count"],
            late_count=s["late_count"],
            permission_count=s["permission_count"]
        )
        for s in student_list
    ]
    
    return MonthlyAttendanceResponse(
        month=month if month is not None else 1,
        year=year if year is not None else datetime.now().year,
        total_students=len(students),
        total_present=total_present,
        total_absent=total_absent,
        total_late=total_late,
        total_permission=total_permission,
        students=students
    )


@router.get("/daily-activity")
async def get_daily_activity(
    grade_id: int = Query(..., description="Grade ID"),
    shift_id: int = Query(..., description="Shift ID"),
    program_id: int = Query(..., description="Program ID"),
    academic_id: int = Query(..., description="Academic year ID"),
    attendance_date: str = Query(..., description="Date YYYY-MM-DD"),
    grade_type_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Returns daily attendance records with teacher info for a specific class/date.
    Used to show who marked attendance in the audit log sheet.
    """
    query = text("""
        SELECT 
            da.student_id,
            COALESCE(s.kName, s.eName, '') as student_name,
            da.status,
            da.created_at,
            da.updated_at,
            COALESCE(
                NULLIF(uu.kName, ''),
                NULLIF(uu.eName, ''),
                NULLIF(uu.username, ''),
                NULLIF(ut.kName, ''),
                NULLIF(ut.eName, ''),
                NULLIF(ut.username, ''),
                NULLIF(uc.kName, ''),
                NULLIF(uc.eName, ''),
                NULLIF(uc.username, ''),
                NULLIF(da.created_by_type, ''),
                'Unknown'
            ) as teacher_name,
            COALESCE(da.updated_by, da.teacher_id, da.created_by) as teacher_id,
            da.created_by_type
        FROM daily_attendance da
        JOIN students s ON da.student_id = s.id
        LEFT JOIN users uu ON da.updated_by = uu.id
        LEFT JOIN users ut ON da.teacher_id = ut.id
        LEFT JOIN users uc ON da.created_by = uc.id
        WHERE da.grade_id = :grade_id
        AND da.shift_id = :shift_id
        AND (da.program_id = :program_id OR :program_id = 0)
        AND (da.academic_id = :academic_id OR :academic_id = 0)
        AND DATE(da.attendance_date) = :attendance_date
        AND (:grade_type_id IS NULL OR da.grade_type_id = :grade_type_id)
        ORDER BY da.created_at DESC
    """)

    rows = db.execute(query, {
        "grade_id": grade_id,
        "shift_id": shift_id,
        "program_id": program_id,
        "academic_id": academic_id,
        "attendance_date": attendance_date,
        "grade_type_id": grade_type_id,
    }).fetchall()

    result = []
    for row in rows:
        result.append({
            "student_id": row[0],
            "student_name": row[1],
            "status": row[2],
            "created_at": str(row[3]) if row[3] else None,
            "updated_at": str(row[4]) if row[4] else None,
            "teacher_name": row[5] or "Unknown",
            "teacher_id": row[6],
            "created_by_type": row[7],
        })

    return result


def _build_daily_attendance_snapshot(
    db: Session,
    *,
    daily_attendance_id: Optional[int],
    student_id: int,
    attendance_date: str,
    academic_id: int,
    program_id: int,
    grade_id: int,
    grade_type_id: Optional[int],
    shift_id: int,
    status: Optional[str],
    note: Optional[str],
    teacher_id: int,
    created_by: Optional[int],
    updated_by: Optional[int],
    created_by_type: str,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolved context for audit / logs (matches daily_attendance columns + names)."""
    snap: Dict[str, Any] = {
        "id": daily_attendance_id,
        "student_id": student_id,
        "program_id": program_id,
        "grade_id": grade_id,
        "grade_type_id": grade_type_id,
        "shift_id": shift_id,
        "status": status,
        "attendance_date": attendance_date,
        "academic_id": academic_id,
        "note": note,
        "created_at": created_at,
        "updated_at": updated_at,
        "created_by": created_by,
        "updated_by": updated_by,
        "teacher_id": teacher_id,
        "created_by_type": created_by_type,
    }
    try:
        gr = db.execute(
            text("SELECT branch_id, grade_name FROM grade WHERE id = :gid"),
            {"gid": grade_id},
        ).fetchone()
        if gr:
            bid, gname = gr[0], gr[1] or ""
            snap["branch_id"] = bid
            snap["grade_name"] = gname
            br = db.execute(
                text("SELECT branch_name FROM branch WHERE id = :id"),
                {"id": bid},
            ).fetchone()
            snap["branch_name"] = (br[0] if br else "") or ""
        pr = db.execute(
            text("SELECT program_name FROM program WHERE id = :id"),
            {"id": program_id},
        ).fetchone()
        snap["program_name"] = (pr[0] if pr else "") or ""
        ar = db.execute(
            text("SELECT academic_name FROM academic WHERE id = :id"),
            {"id": academic_id},
        ).fetchone()
        snap["academic_name"] = (ar[0] if ar else "") or ""
        sr = db.execute(
            text("SELECT shift_name FROM shift WHERE id = :id"),
            {"id": shift_id},
        ).fetchone()
        snap["shift_name"] = (sr[0] if sr else "") or ""
        if grade_type_id is not None:
            gt = db.execute(
                text("SELECT type_name FROM grade_type WHERE id = :id"),
                {"id": grade_type_id},
            ).fetchone()
            snap["grade_type_name"] = (gt[0] if gt else "") or ""
        else:
            snap["grade_type_name"] = None
    except Exception as ex:
        snap["_enrich_error"] = str(ex)
    return snap


def _log_attendance_audit(
    db: Session,
    user_id: int,
    user_name: str,
    user_role: str,
    action_type: str,
    entity_id: int,
    student_id: int,
    grade_id: int,
    grade_type_id: Optional[int],
    change_description: str,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
):
    """Internal helper to insert into attendance_audit_log"""
    try:
        from .attendance_audit import format_cambodia_datetime
        from datetime import datetime
        
        khmer_time = format_cambodia_datetime(datetime.utcnow())
        
        # Get student name
        student_query = text("SELECT kName, eName FROM students WHERE id = :student_id")
        student_row = db.execute(student_query, {"student_id": student_id}).fetchone()
        student_name = ""
        if student_row:
            kname = student_row[0] or ""
            ename = student_row[1] or ""
            student_name = kname if kname else ename
            
        # Get branch/class metadata
        branch_query = text("SELECT branch_id, grade_name FROM grade WHERE id = :grade_id")
        branch_row = db.execute(branch_query, {"grade_id": grade_id}).fetchone()
        branch_id = branch_row[0] if branch_row else 0
        grade_name = branch_row[1] if branch_row else ""
        class_description = grade_name
        if grade_type_id is not None:
            grade_type_query = text("SELECT type_name FROM grade_type WHERE id = :grade_type_id")
            grade_type_row = db.execute(grade_type_query, {"grade_type_id": grade_type_id}).fetchone()
            grade_type_name = (grade_type_row[0] if grade_type_row else "") or ""
            if grade_type_name.strip():
                class_description = f"{grade_name} - {grade_type_name}"
        
        query = text("""
            INSERT INTO attendance_audit_log (
                user_id, user_name, user_role, action_type, entity_type, entity_id,
                student_id, student_name, class_id, class_description,
                created_at_khmer, change_description, branch_id,
                old_value, new_value
            ) VALUES (
                :user_id, :user_name, :user_role, :action_type, 'attendance_record', :entity_id,
                :student_id, :student_name, :class_id, :class_description,
                :created_at_khmer, :change_description, :branch_id,
                :old_value, :new_value
            )
        """)
        
        db.execute(query, {
            "user_id": user_id,
            "user_name": user_name,
            "user_role": user_role,
            "action_type": action_type,
            "entity_id": entity_id,
            "student_id": student_id,
            "student_name": student_name,
            "class_id": grade_id,
            "class_description": class_description,
            "created_at_khmer": khmer_time,
            "change_description": change_description,
            "branch_id": branch_id,
            "old_value": old_value,
            "new_value": new_value,
        })
        # db.commit() is intentionally left out to be committed along with the main transaction or explicitly called after
    except Exception as e:
        logger.error(f"Error logging attendance audit: {e}", exc_info=True)


def _update_attendance_statistics(
    db: Session,
    grade_id: int,
    shift_id: int,
    program_id: int,
    academic_id: int,
    attendance_date: str,
    teacher_id: int,
    teacher_name: str
):
    """Internal helper to calculate and upsert attendance statistics for a class on a given date"""
    try:
        from datetime import datetime, date
        from .attendance_audit import format_cambodia_datetime
        
        # Get branch_id
        branch_query = text("SELECT branch_id FROM grade WHERE id = :grade_id")
        branch_row = db.execute(branch_query, {"grade_id": grade_id}).fetchone()
        branch_id = branch_row[0] if branch_row else 0
        
        # Parse attendance date
        try:
            stat_date = date.fromisoformat(attendance_date)
        except ValueError:
            stat_date = datetime.strptime(attendance_date, "%Y-%m-%d").date()
            
        day_of_week = stat_date.weekday()
        month = stat_date.month
        year = stat_date.year
        
        khmer_date_str = str(stat_date)  # Will be overridden below
        try:
            khmer_date_str = format_cambodia_datetime(datetime.combine(stat_date, datetime.min.time())).split(" ម៉ោង")[0]
        except:
            pass
            
        # Total students in class (historical years count past enrollees so
        # re-marked old-year attendance keeps a correct denominator)
        student_query = text("""
            SELECT COUNT(DISTINCT s.id)
            FROM learning l
            JOIN students s ON l.studentid = s.id
            WHERE l.programid = :program_id AND l.gradeid = :grade_id
            AND l.shiftid = :shift_id AND l.academicid = :academic_id
            AND (s.status = 1 OR :historical = 1)
        """)
        student_count = db.execute(student_query, {
            "program_id": program_id,
            "grade_id": grade_id,
            "shift_id": shift_id,
            "academic_id": academic_id,
            "historical": 1 if _is_historical_academic_year(db, academic_id) else 0
        }).scalar() or 0
        
        # Attendance counts and times for today
        stats_query = text("""
            SELECT 
                status, 
                COUNT(*) as count,
                MIN(created_at) as min_time,
                MAX(created_at) as max_time
            FROM daily_attendance
            WHERE attendance_date = :attendance_date
            AND grade_id = :grade_id
            AND shift_id = :shift_id
            AND program_id = :program_id
            AND academic_id = :academic_id
            GROUP BY status
        """)
        stats_rows = db.execute(stats_query, {
            "attendance_date": attendance_date,
            "grade_id": grade_id,
            "shift_id": shift_id,
            "program_id": program_id,
            "academic_id": academic_id
        }).fetchall()
        
        present = 0
        absent = 0
        late = 0
        permission = 0
        min_times = []
        max_times = []
        
        for row in stats_rows:
            st = row[0]
            cnt = row[1]
            if st == "IsPresent": present = cnt
            elif st == "IsAbsent": absent = cnt
            elif st == "IsLate": late = cnt
            elif st == "IsPermission": permission = cnt
            
            if row[2]: min_times.append(row[2])
            if row[3]: max_times.append(row[3])
            
        first_time = min(min_times) if min_times else None
        last_time = max(max_times) if max_times else None
        
        first_min = None
        last_min = None
        avg_min = None
        peak_hour = None
        
        if first_time:
            first_min = first_time.hour * 60 + first_time.minute
            peak_hour = first_time.hour # Simplified peak hour
        if last_time:
            last_min = last_time.hour * 60 + last_time.minute
            
        if first_min is not None and last_min is not None:
            avg_min = (first_min + last_min) / 2.0
            
        # Check if row exists
        check_query = text("""
            SELECT id FROM attendance_statistics
            WHERE statistic_date = :stat_date
            AND grade_id = :grade_id
            AND shift_id = :shift_id
            AND program_id = :program_id
            AND academic_id = :academic_id
            AND branch_id = :branch_id
        """)
        
        existing = db.execute(check_query, {
            "stat_date": stat_date,
            "grade_id": grade_id,
            "shift_id": shift_id,
            "program_id": program_id,
            "academic_id": academic_id,
            "branch_id": branch_id,
        }).fetchone()
        
        if existing:
            # Update
            upd_query = text("""
                UPDATE attendance_statistics SET
                    total_students = :total,
                    marked_present = :present,
                    marked_absent = :absent,
                    marked_late = :late,
                    marked_permission = :permission,
                    first_attendance_time = :first_time,
                    last_attendance_time = :last_time,
                    first_attendance_minutes = :first_min,
                    last_attendance_minutes = :last_min,
                    average_attendance_minutes = :avg_min,
                    peak_hour = :peak_hour,
                    primary_teacher_id = :teacher_id,
                    primary_teacher_name = :teacher_name
                WHERE id = :id
            """)
            db.execute(upd_query, {
                "total": student_count, "present": present, "absent": absent, 
                "late": late, "permission": permission,
                "first_time": first_time, "last_time": last_time,
                "first_min": first_min, "last_min": last_min, "avg_min": avg_min,
                "peak_hour": peak_hour, "teacher_id": teacher_id, "teacher_name": teacher_name,
                "id": existing[0]
            })
        else:
            # Insert
            ins_query = text("""
                INSERT INTO attendance_statistics (
                    branch_id, program_id, grade_id, shift_id, academic_id,
                    statistic_date, day_of_week, month, year, statistic_date_khmer,
                    total_students, marked_present, marked_absent, marked_late, marked_permission,
                    first_attendance_time, last_attendance_time, first_attendance_minutes,
                    last_attendance_minutes, average_attendance_minutes, peak_hour,
                    primary_teacher_id, primary_teacher_name
                ) VALUES (
                    :branch, :program, :grade, :shift, :academic,
                    :stat_date, :dow, :month, :year, :khmer_date,
                    :total, :present, :absent, :late, :permission,
                    :first_time, :last_time, :first_min,
                    :last_min, :avg_min, :peak_hour,
                    :teacher_id, :teacher_name
                )
            """)
            db.execute(ins_query, {
                "branch": branch_id, "program": program_id, "grade": grade_id, 
                "shift": shift_id, "academic": academic_id,
                "stat_date": stat_date, "dow": day_of_week, "month": month, "year": year, 
                "khmer_date": khmer_date_str,
                "total": student_count, "present": present, "absent": absent, 
                "late": late, "permission": permission,
                "first_time": first_time, "last_time": last_time,
                "first_min": first_min, "last_min": last_min, "avg_min": avg_min,
                "peak_hour": peak_hour, "teacher_id": teacher_id, "teacher_name": teacher_name
            })
            
        # We don't commit here either, we let the parent transaction commit
    except Exception as e:
        logger.error(f"Error updating attendance statistics: {e}", exc_info=True)


def _send_attendance_notif_bg(
    student_id: int,
    attendance_status: str,
    attendance_date: str,
    action_type: str,
    teacher_id_value: Optional[int]
):
    """Background task to send attendance notification without holding the API connection."""
    from ...core.database import SessionLocal
    from ...services.notification_service import send_attendance_notification
    db = SessionLocal()
    try:
        student_query = text("SELECT kName, eName FROM students WHERE id = :student_id")
        student_result = db.execute(student_query, {"student_id": student_id})
        student_row = student_result.fetchone()
        
        if student_row:
            student_kname = student_row[0] or ""
            student_ename = student_row[1] or ""
            student_name = student_kname if student_kname else student_ename
            
            logger.info(f"Sending background attendance notification for student {student_id} ({student_name})")
            result = send_attendance_notification(
                db=db,
                student_id=student_id,
                student_name=student_name,
                attendance_status=attendance_status,
                attendance_date=attendance_date,
                class_info=None,
                teacher_id=teacher_id_value,
                action_type=action_type
            )
            if result:
                logger.info(f"Background notification sent successfully for student {student_id}")
            else:
                logger.warning(f"Failed to send background notification for student {student_id}")
        else:
            logger.warning(f"Student {student_id} not found, skipping background notification")
    except ImportError:
        logger.warning("Notification service not available for background task (ImportError)")
    except Exception as e:
        logger.error(f"Error in background notification task: {e}", exc_info=True)
    finally:
        db.close()


@router.post("/record", response_model=RecordAttendanceResponse)
async def record_attendance(
    request: RecordAttendanceRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Record or remove attendance for a student.
    If status is None, the attendance record will be deleted.
    Uses INSERT ... ON DUPLICATE KEY UPDATE to handle existing records.
    """
    try:
        # Get current time in Cambodia timezone
        from datetime import datetime, timedelta
        import pytz
        cambodia_tz = pytz.timezone("Asia/Phnom_Penh")
        current_time_obj = datetime.now(cambodia_tz)
        current_time = current_time_obj.strftime("%Y-%m-%d %H:%M:%S")
        
        # Security check: 7-day window for teachers; super admins have no date restriction
        server_today = current_time_obj.date()
        is_super_admin = _current_user_is_super_admin(db, current_user.id)
        if not is_super_admin:
            earliest_allowed = server_today - timedelta(days=6)  # 7-day window including today
            if request.attendance_date > server_today:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot mark attendance for future dates",
                )
            if request.attendance_date < earliest_allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot mark attendance older than 7 days",
                )
        
        teacher_id = current_user.id
        
        # If status is None, delete the attendance record
        if request.status is None:
            delete_params = {
                "student_id": request.student_id,
                "attendance_date": request.attendance_date.strftime("%Y-%m-%d"),
                "academic_id": request.academic_id,
                "program_id": request.program_id,
                "grade_id": request.grade_id,
                "grade_type_id": request.grade_type_id,
                "shift_id": request.shift_id,
            }

            prior_row_query = text("""
                SELECT id, status, note, created_by, updated_by, teacher_id, created_by_type,
                       created_at, updated_at
                FROM daily_attendance
                WHERE student_id = :student_id
                AND attendance_date = :attendance_date
                AND academic_id = :academic_id
                AND program_id = :program_id
                AND grade_id = :grade_id
                AND shift_id = :shift_id
                AND (grade_type_id = :grade_type_id OR (:grade_type_id IS NULL AND grade_type_id IS NULL))
                LIMIT 1
            """)
            prior_row = db.execute(prior_row_query, delete_params).fetchone()
            if prior_row and prior_row[6] == 'parent' and not is_super_admin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Locked: Attendance has a parent permission request",
                )
            prior_status = prior_row[1] if prior_row else None

            delete_query = text("""
                DELETE FROM daily_attendance
                WHERE student_id = :student_id
                AND attendance_date = :attendance_date
                AND academic_id = :academic_id
                AND program_id = :program_id
                AND grade_id = :grade_id
                AND shift_id = :shift_id
                AND (grade_type_id = :grade_type_id OR (:grade_type_id IS NULL AND grade_type_id IS NULL))
            """)

            db.execute(delete_query, delete_params)
            db.commit()
            
            # Record audit and upate stats
            try:
                emp_name = getattr(current_user, 'kName', None) or getattr(current_user, 'eName', None) or str(current_user.username)
                emp_role = str(getattr(current_user, 'role', 'teacher'))
                date_str = request.attendance_date.strftime("%Y-%m-%d")
                if prior_status:
                    # Same pattern as status updates so clients can show "Absent → Removed"
                    change_desc = f"Changed from {prior_status} to Removed for {date_str}"
                else:
                    change_desc = f"Removed attendance for {date_str}"
                old_json = None
                if prior_row:
                    ca = prior_row[7]
                    ua = prior_row[8]
                    old_snap = _build_daily_attendance_snapshot(
                        db,
                        daily_attendance_id=prior_row[0],
                        student_id=request.student_id,
                        attendance_date=date_str,
                        academic_id=request.academic_id,
                        program_id=request.program_id,
                        grade_id=request.grade_id,
                        grade_type_id=request.grade_type_id,
                        shift_id=request.shift_id,
                        status=prior_row[1],
                        note=prior_row[2],
                        teacher_id=int(prior_row[5] or teacher_id),
                        created_by=int(prior_row[3]) if prior_row[3] is not None else teacher_id,
                        updated_by=int(prior_row[4]) if prior_row[4] is not None else teacher_id,
                        created_by_type=(prior_row[6] or "teacher"),
                        created_at=ca.isoformat() if hasattr(ca, "isoformat") else str(ca) if ca else None,
                        updated_at=ua.isoformat() if hasattr(ua, "isoformat") else str(ua) if ua else None,
                    )
                    old_json = json.dumps(old_snap, ensure_ascii=False)
                else:
                    old_snap = _build_daily_attendance_snapshot(
                        db,
                        daily_attendance_id=None,
                        student_id=request.student_id,
                        attendance_date=date_str,
                        academic_id=request.academic_id,
                        program_id=request.program_id,
                        grade_id=request.grade_id,
                        grade_type_id=request.grade_type_id,
                        shift_id=request.shift_id,
                        status=None,
                        note=None,
                        teacher_id=teacher_id,
                        created_by=teacher_id,
                        updated_by=teacher_id,
                        created_by_type="teacher",
                    )
                    old_json = json.dumps(old_snap, ensure_ascii=False)
                new_json = json.dumps({"removed": True, "by_user_id": current_user.id}, ensure_ascii=False)
                _log_attendance_audit(
                    db,
                    current_user.id,
                    emp_name,
                    emp_role,
                    "DELETE",
                    0,
                    request.student_id,
                    request.grade_id,
                    request.grade_type_id,
                    change_desc,
                    old_value=old_json,
                    new_value=new_json,
                )
                _update_attendance_statistics(db, request.grade_id, request.shift_id, request.program_id, request.academic_id, request.attendance_date.strftime("%Y-%m-%d"), current_user.id, emp_name)
                db.commit()
            except Exception as e:
                logger.error(f"Error logging delete: {e}", exc_info=True)
            
            # Broadcast real-time update via WebSocket
            try:
                from .websocket import broadcast_attendance_update
                await broadcast_attendance_update(
                    academic_id=request.academic_id,
                    attendance_date=request.attendance_date.strftime("%Y-%m-%d"),
                    student_id=request.student_id,
                    program_id=request.program_id,
                    grade_id=request.grade_id,
                    grade_type_id=request.grade_type_id,  # type: ignore
                    shift_id=request.shift_id,
                    status=None  # type: ignore # None indicates deletion
                )
            except Exception as e:
                logger.error(f"Error broadcasting attendance deletion: {e}")
                # Don't fail the request if broadcast fails
            
            # Send cancellation push notification to parents in background
            try:
                from .attendance_audit import format_cambodia_datetime
                # Fetch khmer date specifically for the notification display
                khmer_notif_date = format_cambodia_datetime(datetime.combine(request.attendance_date, datetime.min.time())).split(" ម៉ោង")[0]
                
                teacher_id_value: Optional[int] = getattr(current_user, 'id', None)
                background_tasks.add_task(
                    _send_attendance_notif_bg,
                    student_id=request.student_id,
                    attendance_status="cancelled",
                    attendance_date=khmer_notif_date,
                    action_type="cancelled",
                    teacher_id_value=teacher_id_value
                )
            except Exception as cancel_notify_err:
                logger.error(f"Error queuing cancellation notification: {cancel_notify_err}")
            
            return RecordAttendanceResponse(
                success=True,
                message="Attendance removed successfully"
            )
        
        # Otherwise, insert or update the attendance record
        # Note: Only save note for Permission (IsPermission) and Absent (IsAbsent) statuses
        note_value = None
        if request.status in ['IsPermission', 'IsAbsent'] and request.note:
            note_value = request.note.strip() if request.note.strip() else None
        
        # Check if a record already exists to determine if this is a new mark or an update
        existing_check = text("""
            SELECT id, status, created_by_type FROM daily_attendance
            WHERE student_id = :student_id
            AND attendance_date = :attendance_date
            AND academic_id = :academic_id
            AND program_id = :program_id
            AND grade_id = :grade_id
            AND shift_id = :shift_id
            AND (grade_type_id = :grade_type_id OR (:grade_type_id IS NULL AND grade_type_id IS NULL))
            LIMIT 1
        """)
        existing_row = db.execute(existing_check, {
            "student_id": request.student_id,
            "attendance_date": request.attendance_date.strftime("%Y-%m-%d"),
            "academic_id": request.academic_id,
            "program_id": request.program_id,
            "grade_id": request.grade_id,
            "shift_id": request.shift_id,
            "grade_type_id": request.grade_type_id if request.grade_type_id else None,
        }).fetchone()
        
        if existing_row and existing_row[2] == 'parent' and not is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Locked: Attendance has a parent permission request",
            )
            
        action_type = "updated" if existing_row else "marked"
        prior_status = existing_row[1] if existing_row else None
        status_changed = prior_status != request.status
        should_notify_parents = not existing_row or status_changed

        query = text("""
            INSERT INTO daily_attendance (
                student_id, attendance_date, status, academic_id,
                program_id, grade_id, grade_type_id, shift_id,
                note, created_by, updated_by, teacher_id, created_at, updated_at, created_by_type
            ) VALUES (
                :student_id, :attendance_date, :status, :academic_id,
                :program_id, :grade_id, :grade_type_id, :shift_id,
                :note, :created_by, :updated_by, :teacher_id, :created_at, :updated_at, 'teacher'
            )
            ON DUPLICATE KEY UPDATE
                program_id = VALUES(program_id),
                grade_id = VALUES(grade_id),
                grade_type_id = VALUES(grade_type_id),
                shift_id = VALUES(shift_id),
                academic_id = VALUES(academic_id),
                attendance_date = VALUES(attendance_date),
                status = VALUES(status),
                note = VALUES(note),
                updated_by = VALUES(updated_by),
                teacher_id = VALUES(teacher_id),
                updated_at = VALUES(updated_at),
                created_by_type = VALUES(created_by_type)
        """)
        
        params = {
            "student_id": request.student_id,
            "attendance_date": request.attendance_date.strftime("%Y-%m-%d"),
            "status": request.status,
            "academic_id": request.academic_id,
            "program_id": request.program_id,
            "grade_id": request.grade_id,
            "grade_type_id": request.grade_type_id if request.grade_type_id else None,
            "shift_id": request.shift_id,
            "note": note_value,
            "created_by": teacher_id,
            "updated_by": teacher_id,
            "teacher_id": teacher_id,
            "created_at": current_time,
            "updated_at": current_time
        }
        
        db.execute(query, params)
        db.commit()

        da_id_row = db.execute(
            text("""
                SELECT id FROM daily_attendance
                WHERE student_id = :student_id AND attendance_date = :attendance_date
                AND academic_id = :academic_id AND program_id = :program_id
                AND grade_id = :grade_id AND shift_id = :shift_id
                AND (grade_type_id = :grade_type_id OR (:grade_type_id IS NULL AND grade_type_id IS NULL))
                ORDER BY id DESC LIMIT 1
            """),
            {
                "student_id": request.student_id,
                "attendance_date": request.attendance_date.strftime("%Y-%m-%d"),
                "academic_id": request.academic_id,
                "program_id": request.program_id,
                "grade_id": request.grade_id,
                "shift_id": request.shift_id,
                "grade_type_id": request.grade_type_id if request.grade_type_id else None,
            },
        ).fetchone()
        da_id = int(da_id_row[0]) if da_id_row else None

        # Record audit and update stats
        try:
            emp_name = getattr(current_user, 'kName', None) or getattr(current_user, 'eName', None) or str(current_user.username)
            emp_role = str(getattr(current_user, 'role', 'teacher'))
            audit_action = "UPDATE" if existing_row else "CREATE"

            date_str = request.attendance_date.strftime("%Y-%m-%d")
            base_snap = _build_daily_attendance_snapshot(
                db,
                daily_attendance_id=da_id,
                student_id=request.student_id,
                attendance_date=date_str,
                academic_id=request.academic_id,
                program_id=request.program_id,
                grade_id=request.grade_id,
                grade_type_id=request.grade_type_id,
                shift_id=request.shift_id,
                status=request.status,
                note=note_value,
                teacher_id=teacher_id,
                created_by=teacher_id,
                updated_by=teacher_id,
                created_by_type="teacher",
                created_at=current_time,
                updated_at=current_time,
            )
            old_json: Optional[str] = None
            if existing_row:
                old_status = existing_row[1]
                audit_desc = f"Changed from {old_status} to {request.status} for {date_str}"
                old_snap = dict(base_snap)
                old_snap["id"] = existing_row[0]
                old_snap["status"] = old_status
                old_json = json.dumps(old_snap, ensure_ascii=False)
            else:
                audit_desc = f"Marked as {request.status} for {date_str}"
            new_json = json.dumps(base_snap, ensure_ascii=False)

            _log_attendance_audit(
                db,
                current_user.id,
                emp_name,
                emp_role,
                audit_action,
                0,
                request.student_id,
                request.grade_id,
                request.grade_type_id,
                audit_desc,
                old_value=old_json,
                new_value=new_json,
            )
            _update_attendance_statistics(db, request.grade_id, request.shift_id, request.program_id, request.academic_id, request.attendance_date.strftime("%Y-%m-%d"), current_user.id, emp_name)
            db.commit()
        except Exception as e:
            logger.error(f"Error updating audit/stats: {e}", exc_info=True)
        
        # Broadcast real-time update via WebSocket
        try:
            from .websocket import broadcast_attendance_update
            await broadcast_attendance_update(
                academic_id=request.academic_id,
                attendance_date=request.attendance_date.strftime("%Y-%m-%d"),
                student_id=request.student_id,
                program_id=request.program_id,
                grade_id=request.grade_id,
                grade_type_id=request.grade_type_id,  # type: ignore
                shift_id=request.shift_id,
                status=request.status
            )
        except Exception as e:
            logger.error(f"Error broadcasting attendance update: {e}")
            # Don't fail the request if broadcast fails
        
        # Send push notification to parents in background (skip note-only updates).
        if should_notify_parents:
            try:
                from .attendance_audit import format_cambodia_datetime
                # Fetch khmer date specifically for the notification display
                khmer_notif_date = format_cambodia_datetime(datetime.combine(request.attendance_date, datetime.min.time())).split(" ម៉ោង")[0]
                
                teacher_id_value: Optional[int] = getattr(current_user, 'id', None)
                background_tasks.add_task(
                    _send_attendance_notif_bg,
                    student_id=request.student_id,
                    attendance_status=request.status,
                    attendance_date=khmer_notif_date,
                    action_type=action_type,
                    teacher_id_value=teacher_id_value
                )
            except Exception as notify_err:
                logger.error(f"Error queuing attendance notification: {notify_err}")
        else:
            logger.info(
                "Skipping parent attendance notification for student %s on %s "
                "(status unchanged: %s)",
                request.student_id,
                request.attendance_date,
                prior_status,
            )
        
        return RecordAttendanceResponse(
            success=True,
            message="Attendance recorded successfully"
        )
    except Exception as e:
        import traceback
        print(f"ERROR RECORDING ATTENDANCE: {str(e)}")
        print(traceback.format_exc())
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record attendance: {str(e)}"
        )


@router.post("/student-attendance-daily", response_model=StudentAttendanceDailyResponse)
async def get_student_attendance_daily_for_staff(
    request: StudentAttendanceSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Daily attendance records for a student (calendar + detail sheet).
    Same shape as the parent endpoint; available to authenticated staff.
    """
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

    try:
        rows = db.execute(text(base_sql), params).fetchall()
    except Exception as qe:
        logger.warning("staff student-attendance-daily query failed: %s", qe)
        return StudentAttendanceDailyResponse(records=[])

    records = []
    for row in rows:
        r = row._mapping
        att_date = r.get("attendance_date")
        date_str = (
            att_date.strftime("%Y-%m-%d")
            if hasattr(att_date, "strftime")
            else str(att_date)
        )
        created = r.get("created_at")
        updated = r.get("updated_at")
        records.append(
            DailyAttendanceRecord(
                id=int(r.get("id", 0)),
                attendance_date=date_str,
                status=(r.get("status") or "").strip() or "Unknown",
                note=r.get("note") or None,
                created_at=(
                    created.isoformat()
                    if created and hasattr(created, "isoformat")
                    else (str(created) if created else None)
                ),
                updated_at=(
                    updated.isoformat()
                    if updated and hasattr(updated, "isoformat")
                    else (str(updated) if updated else None)
                ),
                marked_by=r.get("marked_by") or None,
                created_by_type=r.get("created_by_type") or None,
            )
        )
    return StudentAttendanceDailyResponse(records=records)

