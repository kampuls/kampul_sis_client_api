"""
Attendance Audit Log & Statistics API Endpoints
All datetime returned in Cambodia timezone (UTC+7)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json

from ...core import get_db
from ...auth import get_current_active_user
from ...models import AttendanceAuditLog, AttendanceStatistic, User, Student
from ...models.user import User as UserModel

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_role: str
    action_type: str
    entity_type: str
    entity_id: int
    class_id: Optional[int] = None  # grade_id when entity is attendance_record
    student_id: Optional[int]
    student_name: Optional[str]
    class_description: Optional[str]
    change_description: Optional[str]
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: datetime
    created_at_khmer: Optional[str]  # Cambodia time string
    branch_id: Optional[int]


class AttendanceStatisticResponse(BaseModel):
    id: int
    statistic_date: date
    statistic_date_khmer: Optional[str]
    day_of_week: int
    day_name_khmer: Optional[str]
    first_attendance_time: Optional[datetime]
    last_attendance_time: Optional[datetime]
    average_attendance_minutes: Optional[float]
    first_attendance_time_display: Optional[str]  # e.g., "07:30 AM"
    last_attendance_time_display: Optional[str]   # e.g., "10:00 AM"
    average_attendance_time_display: Optional[str] # e.g., "08:15 AM"
    total_students: int
    marked_present: int
    marked_absent: int
    marked_late: int
    marked_permission: int
    attendance_rate: float
    primary_teacher_name: Optional[str]
    peak_hour: Optional[int]
    peak_hour_display: Optional[str]  # e.g., "8:00 AM"


class TeacherActivityResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    total_actions: int
    actions_by_type: Dict[str, int]
    most_active_day: Optional[str]
    average_attendance_time: Optional[str]
    attendance_rate: float


class AttendanceStatisticsSummary(BaseModel):
    total_days: int
    average_start_time: str
    average_end_time: str
    peak_day: Optional[str]
    peak_hour: Optional[int]
    total_students: int
    average_attendance_rate: float
    most_consistent_teacher: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

KHMER_DAYS = {
    0: "ច័ន្ទ",  # Monday
    1: "អង្គារ",  # Tuesday
    2: "ពុធ",  # Wednesday
    3: "ព្រហស្បតិ៍",  # Thursday
    4: "សុក្រ",  # Friday
    5: "សៅរ៍",  # Saturday
    6: "អាទិត្យ",  # Sunday
}


def _mark_volume(stat: AttendanceStatistic) -> int:
    return (
        (stat.marked_present or 0)
        + (stat.marked_absent or 0)
        + (stat.marked_late or 0)
        + (stat.marked_permission or 0)
    )


def _dedupe_statistics_rows(
    stats: List[AttendanceStatistic],
) -> List[AttendanceStatistic]:
    """
    The table has no UNIQUE(statistic_date, grade_id, ...), so duplicate rows per calendar
    day are possible (e.g. concurrent upserts). API consumers expect one row per day.
    Prefer the row with the most attendance marks; tie-break by higher id (newer row).
    """
    best_by_date: Dict[date, AttendanceStatistic] = {}
    for stat in stats:
        d = stat.statistic_date
        prev = best_by_date.get(d)
        if prev is None:
            best_by_date[d] = stat
            continue
        a, b = _mark_volume(stat), _mark_volume(prev)
        if a > b or (a == b and stat.id > prev.id):
            best_by_date[d] = stat
    return sorted(
        best_by_date.values(),
        key=lambda s: s.statistic_date,
        reverse=True,
    )

KHMER_MONTHS = {
    1: "មករា",
    2: "កុម្ភៈ",
    3: "មីនា",
    4: "មេសា",
    5: "ឧសភា",
    6: "មិថុនា",
    7: "កក្កដា",
    8: "សីហា",
    9: "កញ្ញា",
    10: "តុលា",
    11: "វិច្ឆិកា",
    12: "ធ្នូ",
}


def format_cambodia_datetime(dt: datetime) -> str:
    """
    Convert UTC datetime to Cambodia timezone (UTC+7) and format.
    Database stores UTC, we display in Cambodia time.
    """
    if not dt:
        return ""
    
    # Add 7 hours for Cambodia timezone
    cambodia_dt = dt + timedelta(hours=7)
    
    # Format: "08 មេសា 2024 ម៉ោង 07:30"
    day = cambodia_dt.strftime("%d")
    month = KHMER_MONTHS.get(cambodia_dt.month, "")
    year = cambodia_dt.strftime("%Y")
    hour = cambodia_dt.strftime("%H")
    minute = cambodia_dt.strftime("%M")
    
    return f"{day} {month} {year} ម៉ោង {hour}:{minute}"


def format_time_only(dt: datetime) -> str:
    """
    Convert UTC datetime to Cambodia time and format as time only.
    """
    if not dt:
        return ""
    
    # Add 7 hours for Cambodia timezone
    cambodia_dt = dt + timedelta(hours=7)
    return cambodia_dt.strftime("%H:%M")


def format_time_ampm(dt: datetime) -> str:
    """
    Convert UTC datetime to Cambodia time with AM/PM.
    """
    if not dt:
        return ""
    
    cambodia_dt = dt + timedelta(hours=7)
    hour = int(cambodia_dt.strftime("%H"))
    minute = cambodia_dt.strftime("%M")
    
    ampm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    
    return f"{display_hour}:{minute} {ampm}"


def minutes_to_time(minutes: float) -> str:
    """Convert minutes from midnight to time string."""
    if not minutes:
        return ""
    
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    ampm = "AM" if hours < 12 else "PM"
    display_hour = hours if hours <= 12 else hours - 12
    if display_hour == 0:
        display_hour = 12
    
    return f"{display_hour}:{mins:02d} {ampm}"


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=List[AuditLogResponse])
async def get_attendance_audit_log(
    student_id: Optional[int] = Query(None, description="Filter by student ID"),
    teacher_id: Optional[int] = Query(None, description="Filter by teacher ID"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    grade_id: Optional[int] = Query(
        None,
        description="Filter by grade (stored as class_id on attendance_record rows)",
    ),
    attendance_date: Optional[date] = Query(
        None,
        description="Calendar day of the attendance record (not created_at); "
        "narrows rows for one school day. Use with grade_id for best performance.",
    ),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    # Cap raised for grade-scoped queries; clients should paginate with offset.
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """
    Get attendance audit log with Cambodia timezone.
    All timestamps returned in UTC+7 (Cambodia time).
    """
    try:
        # Build query
        query = db.query(AttendanceAuditLog).filter(
            AttendanceAuditLog.entity_type == "attendance_record"
        )
        
        # Apply filters
        if student_id:
            query = query.filter(AttendanceAuditLog.student_id == student_id)
        
        if teacher_id:
            query = query.filter(AttendanceAuditLog.user_id == teacher_id)
        
        if branch_id:
            query = query.filter(AttendanceAuditLog.branch_id == branch_id)

        if grade_id is not None:
            query = query.filter(AttendanceAuditLog.class_id == grade_id)

        if attendance_date is not None:
            # change_description always includes YYYY-MM-DD for attendance_record rows
            # (e.g. "... for 2026-04-22"); avoids scanning by created_at across long ranges.
            ds = attendance_date.strftime("%Y-%m-%d")
            query = query.filter(AttendanceAuditLog.change_description.like(f"%{ds}%"))
        
        if action_type:
            query = query.filter(AttendanceAuditLog.action_type == action_type)
        
        if start_date:
            query = query.filter(
                func.date(AttendanceAuditLog.created_at) >= start_date
            )
        
        if end_date:
            query = query.filter(
                func.date(AttendanceAuditLog.created_at) <= end_date + timedelta(days=1)
            )
        
        # Order by most recent first
        query = query.order_by(AttendanceAuditLog.created_at.desc())
        
        # Pagination
        total = query.count()
        logs = query.offset(offset).limit(limit).all()
        
        # Format response with Cambodia timezone
        result = []
        for log in logs:
            result.append({
                "id": log.id,
                "user_id": log.user_id,
                "user_name": log.user_name,
                "user_role": log.user_role,
                "action_type": log.action_type,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "class_id": getattr(log, "class_id", None),
                "student_id": log.student_id,
                "student_name": log.student_name,
                "class_description": log.class_description,
                "change_description": log.change_description,
                "old_value": getattr(log, "old_value", None),
                "new_value": getattr(log, "new_value", None),
                "created_at": log.created_at,  # UTC from database
                "created_at_khmer": format_cambodia_datetime(log.created_at),
                "branch_id": log.branch_id,
            })
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving audit log: {str(e)}"
        )


@router.get("/statistics", response_model=List[AttendanceStatisticResponse])
async def get_attendance_statistics(
    grade_id: int = Query(..., description="Grade ID"),
    shift_id: int = Query(..., description="Shift ID"),
    program_id: Optional[int] = Query(None, description="Program ID"),
    branch_id: Optional[int] = Query(None, description="Branch ID"),
    academic_id: Optional[int] = Query(None, description="Academic year ID"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month filter"),
    year: Optional[int] = Query(None, description="Year filter"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """
    Get attendance statistics with Cambodia timezone.
    All times displayed in UTC+7 (Cambodia time).
    """
    try:
        # Build query
        query = db.query(AttendanceStatistic).filter(
            AttendanceStatistic.grade_id == grade_id,
            AttendanceStatistic.shift_id == shift_id,
        )
        
        if program_id:
            query = query.filter(AttendanceStatistic.program_id == program_id)
        
        if branch_id:
            query = query.filter(AttendanceStatistic.branch_id == branch_id)
        
        if academic_id:
            query = query.filter(AttendanceStatistic.academic_id == academic_id)
        
        if start_date:
            query = query.filter(AttendanceStatistic.statistic_date >= start_date)
        
        if end_date:
            query = query.filter(AttendanceStatistic.statistic_date <= end_date)
        
        if month:
            query = query.filter(AttendanceStatistic.month == month)
        
        if year:
            query = query.filter(AttendanceStatistic.year == year)
        
        # Order by date
        query = query.order_by(AttendanceStatistic.statistic_date.desc())
        
        stats = query.all()
        stats = _dedupe_statistics_rows(stats)

        # Format response with Cambodia timezone
        result = []
        for stat in stats:
            # Calculate attendance rate
            total = stat.total_students or 0
            present = stat.marked_present or 0
            rate = (present / total * 100) if total > 0 else 0.0
            
            result.append({
                "id": stat.id,
                "statistic_date": stat.statistic_date,
                "statistic_date_khmer": stat.statistic_date_khmer,
                "day_of_week": stat.day_of_week,
                "day_name_khmer": KHMER_DAYS.get(stat.day_of_week, ""),
                "first_attendance_time": stat.first_attendance_time,
                "last_attendance_time": stat.last_attendance_time,
                "average_attendance_minutes": stat.average_attendance_minutes,
                "first_attendance_time_display": minutes_to_time(stat.first_attendance_minutes),
                "last_attendance_time_display": minutes_to_time(stat.last_attendance_minutes),
                "average_attendance_time_display": minutes_to_time(stat.average_attendance_minutes),
                "total_students": total,
                "marked_present": present,
                "marked_absent": stat.marked_absent or 0,
                "marked_late": stat.marked_late or 0,
                "marked_permission": stat.marked_permission or 0,
                "attendance_rate": round(rate, 2),
                "primary_teacher_name": stat.primary_teacher_name,
                "peak_hour": stat.peak_hour,
                "peak_hour_display": f"{stat.peak_hour}:00 AM" if stat.peak_hour and stat.peak_hour < 12 else f"{stat.peak_hour - 12}:00 PM" if stat.peak_hour else "",
            })
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving statistics: {str(e)}"
        )


@router.get("/statistics/summary", response_model=AttendanceStatisticsSummary)
async def get_attendance_statistics_summary(
    grade_id: int = Query(..., description="Grade ID"),
    shift_id: int = Query(..., description="Shift ID"),
    program_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    academic_id: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """
    Get summary statistics for attendance.
    All times in Cambodia timezone (UTC+7).
    """
    try:
        # Build base query
        query = db.query(
            AttendanceStatistic,
        ).filter(
            AttendanceStatistic.grade_id == grade_id,
            AttendanceStatistic.shift_id == shift_id,
        )
        
        if program_id:
            query = query.filter(AttendanceStatistic.program_id == program_id)
        
        if branch_id:
            query = query.filter(AttendanceStatistic.branch_id == branch_id)
        
        if academic_id:
            query = query.filter(AttendanceStatistic.academic_id == academic_id)
        
        if month:
            query = query.filter(AttendanceStatistic.month == month)
        
        if year:
            query = query.filter(AttendanceStatistic.year == year)
        
        stats = query.all()
        stats = _dedupe_statistics_rows(stats)

        if not stats:
            return AttendanceStatisticsSummary(
                total_days=0,
                average_start_time="",
                average_end_time="",
                peak_day=None,
                peak_hour=None,
                total_students=0,
                average_attendance_rate=0.0,
                most_consistent_teacher=None,
            )
        
        # Calculate summary
        total_days = len(stats)
        avg_start_minutes = sum(s.first_attendance_minutes or 0 for s in stats) / total_days
        avg_end_minutes = sum(s.last_attendance_minutes or 0 for s in stats) / total_days
        
        # Find peak day
        day_counts = {}
        for stat in stats:
            dow = stat.day_of_week
            day_counts[dow] = day_counts.get(dow, 0) + 1
        
        peak_day_code = max(day_counts, key=day_counts.get) if day_counts else None
        peak_day_name = KHMER_DAYS.get(peak_day_code, "") if peak_day_code is not None else None
        
        # Find peak hour
        peak_hour = max((s.peak_hour for s in stats if s.peak_hour), default=None)
        
        # Calculate average attendance rate
        total_students = sum(s.total_students or 0 for s in stats)
        total_present = sum(s.marked_present or 0 for s in stats)
        avg_rate = (total_present / total_students * 100) if total_students > 0 else 0.0
        
        # Find most consistent teacher
        teacher_counts = {}
        for stat in stats:
            if stat.primary_teacher_id:
                teacher_counts[stat.primary_teacher_id] = {
                    "name": stat.primary_teacher_name,
                    "count": teacher_counts.get(stat.primary_teacher_id, {}).get("count", 0) + 1
                }
        
        most_consistent_teacher_id = max(teacher_counts, key=lambda x: teacher_counts[x]["count"]) if teacher_counts else None
        most_consistent_teacher = teacher_counts.get(most_consistent_teacher_id, {}).get("name") if most_consistent_teacher_id else None
        
        return AttendanceStatisticsSummary(
            total_days=total_days,
            average_start_time=minutes_to_time(avg_start_minutes),
            average_end_time=minutes_to_time(avg_end_minutes),
            peak_day=peak_day_name,
            peak_hour=peak_hour,
            total_students=total_students,
            average_attendance_rate=round(avg_rate, 2),
            most_consistent_teacher=most_consistent_teacher,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving summary: {str(e)}"
        )


@router.get("/teacher/{teacher_id}/activity", response_model=TeacherActivityResponse)
async def get_teacher_attendance_activity(
    teacher_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """
    Get teacher's attendance activity with Cambodia timezone.
    Shows all actions performed by teacher.
    """
    try:
        # Build query
        query = db.query(AttendanceAuditLog).filter(
            AttendanceAuditLog.user_id == teacher_id,
            AttendanceAuditLog.entity_type == "attendance_record",
        )
        
        if start_date:
            query = query.filter(
                func.date(AttendanceAuditLog.created_at) >= start_date
            )
        
        if end_date:
            query = query.filter(
                func.date(AttendanceAuditLog.created_at) <= end_date + timedelta(days=1)
            )
        
        if month:
            query = query.filter(
                func.extract('month', AttendanceAuditLog.created_at) == month
            )
        
        if year:
            query = query.filter(
                func.extract('year', AttendanceAuditLog.created_at) == year
            )
        
        logs = query.all()
        
        if not logs:
            return TeacherActivityResponse(
                teacher_id=teacher_id,
                teacher_name=logs[0].user_name if logs else "",
                total_actions=0,
                actions_by_type={},
                most_active_day=None,
                average_attendance_time=None,
                attendance_rate=0.0,
            )
        
        # Count actions by type
        actions_by_type = {}
        for log in logs:
            action = log.action_type
            actions_by_type[action] = actions_by_type.get(action, 0) + 1
        
        # Find most active day
        day_counts = {}
        time_sum = 0
        time_count = 0
        
        for log in logs:
            # Cambodia time
            cambodia_time = log.created_at + timedelta(hours=7)
            dow = cambodia_time.weekday()
            day_counts[dow] = day_counts.get(dow, 0) + 1
            
            # Sum times for average
            minutes = cambodia_time.hour * 60 + cambodia_time.minute
            time_sum += minutes
            time_count += 1
        
        most_active_day_code = max(day_counts, key=day_counts.get) if day_counts else None
        most_active_day = KHMER_DAYS.get(most_active_day_code, "") if most_active_day_code is not None else None
        
        avg_time = time_sum / time_count if time_count > 0 else 0
        
        # Calculate attendance rate (present + late / total)
        present_count = actions_by_type.get("MARK_PRESENT", 0) + actions_by_type.get("MARK_LATE", 0)
        total_actions = len(logs)
        attendance_rate = (present_count / total_actions * 100) if total_actions > 0 else 0.0
        
        return TeacherActivityResponse(
            teacher_id=teacher_id,
            teacher_name=logs[0].user_name,
            total_actions=total_actions,
            actions_by_type=actions_by_type,
            most_active_day=most_active_day,
            average_attendance_time=minutes_to_time(avg_time),
            attendance_rate=round(attendance_rate, 2),
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving teacher activity: {str(e)}"
        )
