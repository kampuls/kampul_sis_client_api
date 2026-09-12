"""
Learning schedule API endpoints.
Handles time slots, class schedules, sessions, and exceptions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional
from datetime import date, time
import logging

logger = logging.getLogger(__name__)

from ...core import get_db
from ...auth import get_current_active_user
from ...models import User
from ...models.learning import (
    LearningTimeSlot, LearningClassSchedule,
    LearningSessionLog, LearningScheduleException,
    LearningTimeSlotScope, Subject
)
from ...utils.academic_year import get_current_academic_id
from .websocket import broadcast_schedule_update
from pydantic import BaseModel, Field

router = APIRouter(prefix="/learning", tags=["Learning Schedule"])


# ==================== PERMISSION HELPER ====================

def check_user_permission(user: User, permission_name: str, db: Session) -> bool:
    """Check if user has a specific permission."""
    from ...models.rbac import Permission, RolePermission
    
    # Admins (role_id = 1) have all permissions
    if user.role == 1:
        return True
    
    # Check if user's role has the required permission
    has_permission = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(
            RolePermission.role_id == user.role,
            Permission.permission_name == permission_name
        )
        .first()
    )
    
    return has_permission is not None


def require_permission(permission_name: str):
    """Dependency to require a specific permission."""
    def permission_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        if not check_user_permission(current_user, permission_name, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_name}"
            )
        return current_user
    return permission_checker


def _require_current_schedule_academic_year(
    db: Session,
    academic_id: int,
) -> int:
    """Reject schedule mutations outside the school's current year."""
    current_academic_id = get_current_academic_id(db)
    if int(academic_id) != current_academic_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Teaching schedules can only be changed for the active "
                f"academic year ({current_academic_id})"
            ),
        )
    return current_academic_id


# ==================== PYDANTIC SCHEMAS ====================

class TimeSlotCreate(BaseModel):
    slot_name: str = Field(..., max_length=100, description="e.g., 'Period 1', 'Morning Session'")
    start_time: time
    end_time: time
    duration_minutes: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True
    is_global: bool = True
    grade_group_ids: List[int] = []
    grade_ids: List[int] = []

class TimeSlotResponse(BaseModel):
    id: int
    slot_name: str
    start_time: time
    end_time: time
    duration_minutes: Optional[int]
    sort_order: int
    is_active: bool
    is_global: Optional[bool] = True
    grade_group_ids: List[int] = []
    grade_ids: List[int] = []
    usage_count: int = 0
    section_count: int = 0  # Number of distinct classes (grade/group) using this slot

    class Config:
        from_attributes = True



class ClassScheduleCreate(BaseModel):
    academic_id: int
    branch_id: int
    program_id: int
    grade_group_id: int
    grade_id: Optional[int] = None  # Auto-populated if not provided
    grade_type_id: Optional[int] = None  # Should be provided by frontend (single ID, not comma-separated)
    shift_id: Optional[int] = None  # Exact class shift; required for homework publishing
    subject_id: int
    teacher_id: int
    time_slot_id: int
    day_of_week: int = Field(..., ge=1, le=7, description="1=Monday, 7=Sunday")
    room_number: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: bool = True
    notes: Optional[str] = None

class ClassScheduleResponse(BaseModel):
    id: int
    academic_id: int
    branch_id: int
    program_id: int
    grade_group_id: int
    shift_id: Optional[int] = None
    subject_id: int
    teacher_id: int
    time_slot_id: int
    day_of_week: int
    room_number: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    is_active: bool
    notes: Optional[str]
    
    # New fields
    grade_id: Optional[int] = None
    grade_type_id: Optional[int] = None
    grade_name: Optional[str] = None
    grade_type_name: Optional[str] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    class_name: Optional[str] = None
    class_branch_id: Optional[int] = None

    class Config:
        from_attributes = True


class SessionLogCreate(BaseModel):
    class_schedule_id: int
    session_date: date
    teacher_id: int
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    topic_covered: Optional[str] = None
    homework_assigned: Optional[str] = None
    attendance_count: int = 0
    status: str = "scheduled"
    cancellation_reason: Optional[str] = None
    notes: Optional[str] = None


class SubjectResponse(BaseModel):
    id: int
    subject_name: str
    subject_name_us: Optional[str] = None
    program_id: int
    academic_id: int

    class Config:
        from_attributes = True


class TeacherReferenceResponse(BaseModel):
    id: int
    name: str # Combined or preferred name
    kName: Optional[str] = None
    eName: Optional[str] = None
    phone: Optional[str] = None
    branch_id: Optional[int] = None  # workplace (branch the teacher belongs to)
    isForeigner: Optional[int] = None

    class Config:
        from_attributes = True


# ==================== ACADEMIC YEAR ENDPOINTS ====================

@router.get("/active-academic")
def get_active_academic_year(db: Session = Depends(get_db)):
    """Get the current academic year (status=1 -> settings.academicid -> newest)."""
    return {"academic_id": get_current_academic_id(db)}


class AcademicYearResponse(BaseModel):
    id: int
    academic_us_name: Optional[str] = None
    academic_name: Optional[str] = None
    academic_year: Optional[str] = None
    academic_start: Optional[date] = None
    academic_end: Optional[date] = None
    status: Optional[int] = None


@router.get("/academics", response_model=List[AcademicYearResponse])
def list_academic_years(
    db: Session = Depends(get_db),
    only_active: bool = False,
):
    """
    List academic years from the legacy academic table.
    This is used by admin UIs (e.g. events) to let users pick a year.
    """
    from sqlalchemy import text

    base_query = """
        SELECT id,
               academic_us_name,
               academic_name,
               academic_start,
               academic_end,
               status
        FROM academic
    """
    params: dict = {}
    if only_active:
        base_query += " WHERE status = 1"
    base_query += " ORDER BY academic_start DESC, id DESC"

    result = db.execute(text(base_query), params).fetchall()
    years: List[AcademicYearResponse] = []
    for row in result:
        m = row._mapping
        years.append(
            AcademicYearResponse(
                id=m["id"],
                academic_us_name=m.get("academic_us_name"),
                academic_name=m.get("academic_name"),
                academic_start=m.get("academic_start"),
                academic_end=m.get("academic_end"),
                status=m.get("status"),
            )
        )
    return years


# ==================== TIME SLOTS ENDPOINTS ====================

@router.post("/time-slots", response_model=TimeSlotResponse, status_code=status.HTTP_201_CREATED)
def create_time_slot(
    slot: TimeSlotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminUpdateApp"))
):
    """Create a new time slot."""
    # Check for duplicate slot name (globally)
    existing = db.query(LearningTimeSlot).filter(
        LearningTimeSlot.slot_name == slot.slot_name
    ).first()
    
    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Time slot '{slot.slot_name}' already exists"
            )
        else:
            # Reactivate the existing inactive slot and update its properties
            for key, value in slot.dict(exclude={'grade_group_ids', 'grade_ids'}).items():
                if key == 'is_global':
                    continue # Don't update is_global on reactivation for now, or handle specifically
                setattr(existing, key, value)
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            
            # Update scopes for reactivated slot
            # Remove old scopes
            db.query(LearningTimeSlotScope).filter(LearningTimeSlotScope.time_slot_id == existing.id).delete()
            
            # Add new scopes
            for gg_id in slot.grade_group_ids:
                db.add(LearningTimeSlotScope(time_slot_id=existing.id, scope_type='grade_group', scope_id=gg_id))
            for g_id in slot.grade_ids:
                db.add(LearningTimeSlotScope(time_slot_id=existing.id, scope_type='grade', scope_id=g_id))
                
            db.commit()
            
            # Prepare response
            existing_response = TimeSlotResponse.from_orm(existing)
            existing_response.grade_group_ids = slot.grade_group_ids
            existing_response.grade_ids = slot.grade_ids
            return existing_response
    
    # Default new slot to global if not specified (though schema defaults to True)
    slot_dict = slot.dict(exclude={'grade_group_ids', 'grade_ids'})
    if 'is_global' not in slot_dict:
        slot_dict['is_global'] = True
    
    new_slot = LearningTimeSlot(**slot_dict)
    db.add(new_slot)
    db.commit()
    db.refresh(new_slot)
    
    # Add scopes
    for gg_id in slot.grade_group_ids:
        db.add(LearningTimeSlotScope(time_slot_id=new_slot.id, scope_type='grade_group', scope_id=gg_id))
    for g_id in slot.grade_ids:
        db.add(LearningTimeSlotScope(time_slot_id=new_slot.id, scope_type='grade', scope_id=g_id))
        
    db.commit()
    
    response = TimeSlotResponse.from_orm(new_slot)
    response.grade_group_ids = slot.grade_group_ids
    response.grade_ids = slot.grade_ids
    return response



@router.get("/time-slots", response_model=List[TimeSlotResponse])
def get_time_slots(
    is_active: Optional[bool] = None,
    grade_group_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    assigned_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get time slots filtered by scope.
    - is_active: Filter by active status
    - grade_group_id / grade_id: Context for "assigned" check
    - shift_id: Optional context to filter scopes by shift (if scope has shift_id set)
    - assigned_only=True: Returns ONLY slots assigned to the provided grade/group (excludes others)
    - assigned_only=False: Returns ALL slots (allows picking any slot to add)
    """
    query = db.query(LearningTimeSlot)
    
    if is_active is not None:
        query = query.filter(LearningTimeSlot.is_active == is_active)
    
    # Always order by sort_order
    all_slots = query.order_by(LearningTimeSlot.sort_order).all()
    
    if assigned_only and (grade_group_id or grade_id):
        # Filter to return ONLY slots that have a matching scope
        filtered_slots = []
        for slot in all_slots:
            if slot.scopes:
                # Check for match in either grade_group or grade
                matches_group = False
                matches_grade = False
                
                if grade_group_id:
                    # Check for group matches
                    # A match occurs if:
                    # 1. Scope ID matches AND
                    # 2. (Scope Shift ID is NULL OR Scope Shift ID matches provided shift_id)
                    matches_group = any(
                        s.scope_type == 'grade_group' and 
                        s.scope_id == grade_group_id and
                        (s.shift_id is None or (shift_id and s.shift_id == shift_id))
                        for s in slot.scopes
                    )
                
                if grade_id:
                    # Check for grade matches
                    matches_grade = any(
                        s.scope_type == 'grade' and 
                        s.scope_id == grade_id and
                         (s.shift_id is None or (shift_id and s.shift_id == shift_id))
                        for s in slot.scopes
                    )
                
                if matches_group or matches_grade:
                    filtered_slots.append(slot)
                    
        slots = filtered_slots
    else:
        # If not assigned_only, or no context provided, return ALL slots
        # This allows users to see and "Add" (assign) any existing slot
        slots = all_slots
    
    # Enrich with scopes and usage count
    response = []
    
    # Get usage counts efficiently
    usage_counts = {}
    if slots:
        slot_ids = [s.id for s in slots]
        usage_query = db.query(
            LearningClassSchedule.time_slot_id,
            func.count(func.distinct(LearningClassSchedule.grade_group_id))
        ).filter(
            LearningClassSchedule.time_slot_id.in_(slot_ids),
            LearningClassSchedule.is_active == True
        ).group_by(LearningClassSchedule.time_slot_id).all()
        

    # Get distinct section usage counts (grades/groups using this slot in schedules)
    section_usage_counts = {}
    if slots:
        slot_ids = [s.id for s in slots]
        # Count distinct grade_group_id + branch_id + academic_id combinations? 
        # User wants "how many Group assigned".
        # Better: Count distinct grade_group_id usage in schedules
        section_query = db.query(
            LearningClassSchedule.time_slot_id,
            func.count(func.distinct(LearningClassSchedule.grade_group_id))
        ).filter(
            LearningClassSchedule.time_slot_id.in_(slot_ids),
            LearningClassSchedule.is_active == True
        ).group_by(LearningClassSchedule.time_slot_id).all()
        
        section_usage_counts = {time_slot_id: count for time_slot_id, count in section_query}

    for slot in slots:
        slot_resp = TimeSlotResponse.from_orm(slot)
        slot_resp.grade_group_ids = [s.scope_id for s in slot.scopes if s.scope_type == 'grade_group']
        slot_resp.grade_ids = [s.scope_id for s in slot.scopes if s.scope_type == 'grade']
        slot_resp.usage_count = usage_counts.get(slot.id, 0)
        slot_resp.section_count = section_usage_counts.get(slot.id, 0)
        response.append(slot_resp)
        
    return response




@router.get("/time-slots/{slot_id}", response_model=TimeSlotResponse)
def get_time_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminViewApp"))
):
    """Get a specific time slot by ID."""
    slot = db.query(LearningTimeSlot).filter(LearningTimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
        
    response = TimeSlotResponse.from_orm(slot)
    response.grade_group_ids = [s.scope_id for s in slot.scopes if s.scope_type == 'grade_group']
    response.grade_ids = [s.scope_id for s in slot.scopes if s.scope_type == 'grade']
    return response


@router.put("/time-slots/{slot_id}", response_model=TimeSlotResponse)
def update_time_slot(
    slot_id: int,
    slot_update: TimeSlotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminUpdateApp"))
):
    """Update an existing time slot."""
    slot = db.query(LearningTimeSlot).filter(LearningTimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    
    # Check if slot is in use (for logging/awareness, but allow updates)
    is_in_use = db.query(LearningClassSchedule).filter(
        LearningClassSchedule.time_slot_id == slot_id,
        LearningClassSchedule.is_active == True
    ).count() > 0

    # Update all fields - admins can update time slots even when in use
    for key, value in slot_update.dict(exclude={'grade_group_ids', 'grade_ids'}).items():
        setattr(slot, key, value)
    
    # Update scopes
    # Remove old scopes
    db.query(LearningTimeSlotScope).filter(LearningTimeSlotScope.time_slot_id == slot.id).delete()
    
    # Add new scopes
    for gg_id in slot_update.grade_group_ids:
        db.add(LearningTimeSlotScope(time_slot_id=slot.id, scope_type='grade_group', scope_id=gg_id))
    for g_id in slot_update.grade_ids:
        db.add(LearningTimeSlotScope(time_slot_id=slot.id, scope_type='grade', scope_id=g_id))
    
    db.commit()
    db.refresh(slot)
    
    response = TimeSlotResponse.from_orm(slot)
    response.grade_group_ids = slot_update.grade_group_ids
    response.grade_ids = slot_update.grade_ids
    return response


@router.delete("/time-slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminDeleteApp"))
):
    """Delete a time slot (soft delete by setting is_active=False)."""
    slot = db.query(LearningTimeSlot).filter(LearningTimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    
    # Cascade delete associated class schedules (permanent deletion)
    # Find all schedules using this time slot
    schedules = db.query(LearningClassSchedule).filter(
        LearningClassSchedule.time_slot_id == slot_id
    ).all()
    
    # Delete them permanently
    for schedule in schedules:
        db.delete(schedule)
    
    # Delete the time slot
    db.delete(slot)
    db.commit()
    return None


class TimeSlotScopeCreate(BaseModel):
    scope_type: str  # 'grade' or 'grade_group'
    scope_id: int
    shift_id: Optional[int] = None


@router.post("/time-slots/{time_slot_id}/scopes", status_code=201)
def create_time_slot_scope(
    time_slot_id: int,
    scope_data: TimeSlotScopeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminViewApp"))
):
    """Assign a time slot to a specific grade or grade group, optionally restricted by shift."""
    # Verify time slot exists
    slot = db.query(LearningTimeSlot).filter(LearningTimeSlot.id == time_slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    
    # Check if scope already exists
    # If shift_id is provided, check for exact match including shift_id
    # If shift_id is None, check for match where shift_id is NULL
    query = db.query(LearningTimeSlotScope).filter(
        LearningTimeSlotScope.time_slot_id == time_slot_id,
        LearningTimeSlotScope.scope_type == scope_data.scope_type,
        LearningTimeSlotScope.scope_id == scope_data.scope_id
    )
    
    if scope_data.shift_id is not None:
        query = query.filter(LearningTimeSlotScope.shift_id == scope_data.shift_id)
    else:
        query = query.filter(LearningTimeSlotScope.shift_id.is_(None))
        
    existing_scope = query.first()
    
    if existing_scope:
        # If it already exists, we can perhaps just return success or error
        # Returning success (idempotent) might be safer for bulk operations
        return {"message": "Scope already exists", "id": existing_scope.id}
    
    # Create new scope
    new_scope = LearningTimeSlotScope(
        time_slot_id=time_slot_id,
        scope_type=scope_data.scope_type,
        scope_id=scope_data.scope_id,
        shift_id=scope_data.shift_id
    )
    
    db.add(new_scope)
    db.commit()
    db.refresh(new_scope)
    
    return {"message": "Time slot scope created successfully", "id": new_scope.id}


@router.delete("/time-slots/{time_slot_id}/scopes", status_code=204)
def delete_time_slot_scope(
    time_slot_id: int,
    scope_type: str = Query(...),
    scope_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminViewApp"))
):
    """Remove a time slot from a specific grade or grade group"""
    # Find and delete the scope
    scope = db.query(LearningTimeSlotScope).filter(
        LearningTimeSlotScope.time_slot_id == time_slot_id,
        LearningTimeSlotScope.scope_type == scope_type,
        LearningTimeSlotScope.scope_id == scope_id
    ).first()
    
    if not scope:
        raise HTTPException(status_code=404, detail="Time slot scope not found")
    
    
    # Cascade soft-delete associated class schedules if scope is grade_group
    if scope_type == 'grade_group':
        schedules = db.query(LearningClassSchedule).filter(
            LearningClassSchedule.time_slot_id == time_slot_id,
            LearningClassSchedule.grade_group_id == scope_id,
            LearningClassSchedule.is_active == True
        ).all()
        
        for schedule in schedules:
            schedule.is_active = False
            schedule.updated_by = current_user.id
            
            # Note: We should ideally broadcast updates for each schedule, 
            # but usually the client refreshes after scope change.
            
    db.delete(scope)
    db.commit()
    
    return None


# ==================== CLASS SCHEDULES ENDPOINTS ====================

@router.post("/schedules", response_model=ClassScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_class_schedule(
    schedule: ClassScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminUpdateApp"))
):
    """Create a new class schedule."""
    from sqlalchemy import text as sql_text

    _require_current_schedule_academic_year(db, schedule.academic_id)

    # Resolve grade_group_id BEFORE conflict checks. If the client sends 0/null but grade_id is set,
    # using raw schedule.grade_group_id makes teacher_conflict use `!= 0`, which matches almost every
    # other row and causes false "Teacher conflict" errors.
    effective_grade_group_id = schedule.grade_group_id
    if (effective_grade_group_id is None or effective_grade_group_id == 0) and schedule.grade_id:
        grade_row = db.execute(
            sql_text("SELECT group_id FROM grade WHERE id = :grade_id LIMIT 1"),
            {"grade_id": schedule.grade_id}
        ).fetchone()
        if grade_row and grade_row[0] is not None:
            effective_grade_group_id = grade_row[0]
            logger.debug("Derived grade_group_id=%s from grade_id=%s", effective_grade_group_id, schedule.grade_id)
    if effective_grade_group_id is None or effective_grade_group_id == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="grade_group_id is required (or provide grade_id to derive it)"
        )

    # Check for duplicate subject: same subject already scheduled at this time for THIS specific class.
    # A schedule applies to our class if (grade_id is null or matches) AND (grade_type_id is null or matches).
    duplicate_filters = [
        LearningClassSchedule.branch_id == schedule.branch_id,
        LearningClassSchedule.grade_group_id == effective_grade_group_id,
        LearningClassSchedule.day_of_week == schedule.day_of_week,
        LearningClassSchedule.time_slot_id == schedule.time_slot_id,
        LearningClassSchedule.academic_id == schedule.academic_id,
        LearningClassSchedule.subject_id == schedule.subject_id,
        LearningClassSchedule.is_active == True
    ]
    # Existing applies to our class if its grade_id/grade_type_id are null (whole group) or match
    duplicate_filters.append(
        or_(
            LearningClassSchedule.grade_id.is_(None),
            LearningClassSchedule.grade_id == schedule.grade_id
        )
    )
    duplicate_filters.append(
        or_(
            LearningClassSchedule.grade_type_id.is_(None),
            LearningClassSchedule.grade_type_id == schedule.grade_type_id
        )
    )
    if schedule.shift_id is not None:
        duplicate_filters.append(
            or_(
                LearningClassSchedule.shift_id.is_(None),
                LearningClassSchedule.shift_id == schedule.shift_id,
            )
        )
    duplicate_subject = db.query(LearningClassSchedule).filter(and_(*duplicate_filters)).first()

    if duplicate_subject:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Schedule conflict: This subject is already scheduled at this time for this grade"
        )
    
    # Check for teacher conflict (teacher teaching different grade at same time)
    teacher_conflict = db.query(LearningClassSchedule).filter(
        and_(
            LearningClassSchedule.branch_id == schedule.branch_id,
            LearningClassSchedule.day_of_week == schedule.day_of_week,
            LearningClassSchedule.time_slot_id == schedule.time_slot_id,
            LearningClassSchedule.academic_id == schedule.academic_id,
            LearningClassSchedule.teacher_id == schedule.teacher_id,
            LearningClassSchedule.grade_group_id != effective_grade_group_id,  # Different class group
            LearningClassSchedule.is_active == True
        )
    ).first()
    
    if teacher_conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Teacher conflict: This teacher is already scheduled to teach another class at this time"
        )
    
    # Auto-populate grade_id if not provided (use first grade in group)
    if not schedule.grade_id:
        grade_query = sql_text("""
            SELECT id
            FROM grade
            WHERE group_id = :group_id AND academic_id = :academic_id
            LIMIT 1
        """)
        grade_result = db.execute(grade_query, {
            "group_id": effective_grade_group_id,
            "academic_id": schedule.academic_id
        }).first()
        if grade_result:
            schedule.grade_id = grade_result.id

    schedule_dict = schedule.dict()
    schedule_dict["grade_group_id"] = effective_grade_group_id
    new_schedule = LearningClassSchedule(
        **schedule_dict,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    
    # Broadcast update
    await broadcast_schedule_update(
        academic_id=new_schedule.academic_id,
        branch_id=new_schedule.branch_id,
        grade_group_id=new_schedule.grade_group_id,
        action="created"
    )
    
    return new_schedule


@router.get("/classes")
def get_classes(
    academic_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminViewApp"))
):
    """
    Get all unique class combinations (grade, program, shift, branch) from learning table.
    Returns aggregated data with student count and teacher info.
    """
    from sqlalchemy import text
    
    # Build query to get unique class combinations with counts
    query = """
        SELECT 
            MIN(l.id) as id,
            l.academicid as academic_id,
            l.gradeid as grade_id,
            g.group_id as grade_group_id,
            l.programid as program_id,
            l.shiftid as shift_id,
            g.branch_id,
            g.grade_name,
            g.grade_type_id,
            gt.type_name as grade_type_name,
            p.program_name,
            p.short_code as program_short_code,
            s.shift_name,
            b.branch_name,
            COUNT(DISTINCT l.studentid) as student_count,
            COUNT(DISTINCT CASE WHEN st.gender IN ('M', 'Male', 'ប្រុស') THEN l.studentid END) as male_count,
            COUNT(DISTINCT CASE WHEN st.gender IN ('F', 'Female', 'ស្រី') THEN l.studentid END) as female_count
        FROM learning l
        JOIN grade g ON l.gradeid = g.id
        JOIN program p ON l.programid = p.id
        JOIN shift s ON l.shiftid = s.id
        JOIN branch b ON g.branch_id = b.id
        LEFT JOIN grade_type gt ON g.grade_type_id = gt.id
        LEFT JOIN students st ON l.studentid = st.id
        WHERE 1=1
    """
    
    params = {}
    
    # Filter by academic year if provided
    if academic_id:
        query += " AND l.academicid = :academic_id"
        params['academic_id'] = academic_id
    
    query += """
        GROUP BY 
            l.academicid,
            l.gradeid,
            g.group_id,
            l.programid,
            l.shiftid,
            g.branch_id,
            g.grade_name,
            g.grade_type_id,
            gt.type_name,
            p.program_name,
            p.short_code,
            s.shift_name,
            b.branch_name
        ORDER BY g.grade_name, p.program_name, s.shift_name
    """
    
    result = db.execute(text(query), params)
    classes = result.fetchall()
    
    # Format response
    result_list = []
    for cls in classes:
        # Try to find class teacher from class_teachers table
        teacher_query = text("""
            SELECT CASE 
                WHEN u.isForeigner = 1 THEN COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
                WHEN u.isForeigner = 2 THEN COALESCE(NULLIF(u.eName, ''), NULLIF(u.kName, ''), 'Unknown')
                ELSE COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
            END as teacher_name,
            ct.teacher_id
            FROM class_teachers ct
            JOIN users u ON ct.teacher_id = u.id
            WHERE ct.academic_id = :academic_id
              AND ct.grade_id = :grade_id
              AND ct.program_id = :program_id
              AND ct.shift_id = :shift_id
            LIMIT 1
        """)
        
        teacher_result = db.execute(teacher_query, {
            'academic_id': cls.academic_id,
            'grade_id': cls.grade_id,
            'program_id': cls.program_id,
            'shift_id': cls.shift_id,
        })
        teacher_row = teacher_result.fetchone()
        teacher_name = teacher_row[0] if teacher_row else None
        teacher_id = teacher_row[1] if teacher_row else None
        
        result_list.append({
            'id': cls.id,
            'academic_id': cls.academic_id,
            'grade_id': cls.grade_id,
            'grade_group_id': getattr(cls, 'grade_group_id', None),
            'program_id': cls.program_id,
            'shift_id': cls.shift_id,
            'branch_id': cls.branch_id,
            'grade_name': cls.grade_name,
            'grade_type_id': cls.grade_type_id,
            'grade_type_name': cls.grade_type_name,
            'program_name': cls.program_name,
            'program_short_code': cls.program_short_code,
            'shift_name': cls.shift_name,
            'branch_name': cls.branch_name,
            'student_count': cls.student_count,
            'male_count': cls.male_count,
            'female_count': cls.female_count,
            'teacher_name': teacher_name
        })
    
    return {'classes': result_list, 'message': 'Classes retrieved successfully'}


@router.get("/schedules", response_model=List[ClassScheduleResponse])
def get_class_schedules(
    academic_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    grade_group_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    program_id: Optional[int] = None,
    grade_type_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
    day_of_week: Optional[int] = Query(None, ge=1, le=7),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get class schedules with optional filters, including grade type name.
    When grade_group_id is null but grade_id is provided, derives grade_group_id from grade.group_id.
    """
    from sqlalchemy import text

    # Ordinary teacher users always receive only their own current-year
    # schedules. Admin schedule management may explicitly browse other years.
    if not check_user_permission(current_user, "AdminViewApp", db):
        academic_id = get_current_academic_id(db)
        teacher_id = current_user.id

    # If grade_group_id is missing but grade_id provided, derive it from grade table
    effective_grade_group_id = grade_group_id
    if effective_grade_group_id is None and grade_id is not None:
        grade_row = db.execute(
            text("SELECT group_id FROM grade WHERE id = :grade_id LIMIT 1"),
            {"grade_id": grade_id}
        ).fetchone()
        if grade_row and grade_row[0] is not None:
            effective_grade_group_id = grade_row[0]
            logger.debug(f"Derived grade_group_id={effective_grade_group_id} from grade_id={grade_id}")

    # Build WHERE conditions
    where_conditions = []
    params = {}

    if academic_id:
        where_conditions.append("lcs.academic_id = :academic_id")
        params["academic_id"] = academic_id
    if branch_id:
        where_conditions.append("lcs.branch_id = :branch_id")
        params["branch_id"] = branch_id
    if effective_grade_group_id:
        where_conditions.append("lcs.grade_group_id = :grade_group_id")
        params["grade_group_id"] = effective_grade_group_id
    if grade_id is not None:
        # Schedule applies if grade_id is NULL (whole group) or matches this grade
        where_conditions.append("(lcs.grade_id IS NULL OR lcs.grade_id = :grade_id)")
        params["grade_id"] = grade_id
    if program_id is not None:
        where_conditions.append("lcs.program_id = :program_id")
        params["program_id"] = program_id
    if grade_type_id is not None:
        # Use <=> for null-safe comparison (matches both NULL and value)
        where_conditions.append("(lcs.grade_type_id <=> :grade_type_id)")
        params["grade_type_id"] = grade_type_id
    if shift_id is not None:
        where_conditions.append("(lcs.shift_id IS NULL OR lcs.shift_id = :shift_id)")
        params["shift_id"] = shift_id
    if teacher_id:
        where_conditions.append("lcs.teacher_id = :teacher_id")
        params["teacher_id"] = teacher_id
    if day_of_week:
        where_conditions.append("lcs.day_of_week = :day_of_week")
        params["day_of_week"] = day_of_week
    if is_active is not None:
        where_conditions.append("lcs.is_active = :is_active")
        params["is_active"] = is_active

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
    
    query = text(f"""
        SELECT 
            lcs.id,
            lcs.academic_id,
            lcs.branch_id,
            lcs.program_id,
            lcs.grade_group_id,
            lcs.grade_id,
            lcs.grade_type_id,
            lcs.shift_id,
            lcs.subject_id,
            lcs.teacher_id,
            lcs.time_slot_id,
            lcs.day_of_week,
            lcs.room_number,
            lcs.start_date,
            lcs.end_date,
            lcs.is_active,
            lcs.notes,
            COALESCE(g.grade_name, gg.group_name) as grade_name,
            COALESCE(sub.subject_name, sub.subject_name_us) as subject_name,
            gt.type_name as grade_type_name,
            g.branch_id as class_branch_id,
            -- Resolve teacher_name: prefer lcs.teacher_id, else fallback to class_teachers.
            -- class_teachers has no grade_group_id; join on grade_id.
            -- When lcs.grade_id IS NULL (group-wide schedule), derive grade_id from grade table.
            -- This correlated subquery avoids duplicate rows and handles NULL grade_id safely.
            CASE
                WHEN lcs.teacher_id IS NOT NULL THEN (
                    SELECT CASE
                        WHEN u.isForeigner = 2
                            THEN COALESCE(NULLIF(u.eName,''), NULLIF(u.kName,''))
                        ELSE COALESCE(NULLIF(u.kName,''), NULLIF(u.eName,''))
                    END
                    FROM users u WHERE u.id = lcs.teacher_id LIMIT 1
                )
                ELSE (
                    SELECT CASE
                        WHEN u.isForeigner = 2
                            THEN COALESCE(NULLIF(u.eName,''), NULLIF(u.kName,''))
                        ELSE COALESCE(NULLIF(u.kName,''), NULLIF(u.eName,''))
                    END
                    FROM class_teachers ct
                    JOIN users u ON u.id = ct.teacher_id
                    WHERE ct.academic_id = lcs.academic_id
                      AND ct.program_id  = lcs.program_id
                      AND (ct.grade_type_id <=> lcs.grade_type_id)
                      AND ct.grade_id IN (
                            SELECT id FROM grade
                            WHERE group_id = lcs.grade_group_id
                          )
                    LIMIT 1
                )
            END as teacher_name
        FROM learning_class_schedules lcs
        JOIN grade_group gg ON lcs.grade_group_id = gg.id
        LEFT JOIN grade g ON g.id = lcs.grade_id
        LEFT JOIN grade_type gt ON gt.id = lcs.grade_type_id
        LEFT JOIN subjects sub ON sub.id = lcs.subject_id
        WHERE {where_clause}
        ORDER BY lcs.day_of_week, lcs.time_slot_id
    """)
    
    result = db.execute(query, params)
    schedules = []
    
    for row in result:
        grade_type_display = (row.grade_type_name or "").strip().strip('"').strip("'")
        class_name = row.grade_name or ""
        if grade_type_display:
            class_name = f"{class_name} - {grade_type_display}"
        
        d = dict(row._mapping)
        schedules.append({
            "id": d["id"],
            "academic_id": d["academic_id"],
            "branch_id": d["branch_id"],
            "program_id": d["program_id"],
            "grade_group_id": d["grade_group_id"],
            "grade_id": d["grade_id"],
            "grade_type_id": d["grade_type_id"],
            "shift_id": d["shift_id"],
            "subject_id": d["subject_id"],
            "subject_name": d.get("subject_name"),
            "teacher_id": d["teacher_id"],
            "time_slot_id": d["time_slot_id"],
            "day_of_week": d["day_of_week"],
            "room_number": d["room_number"],
            "start_date": d["start_date"],
            "end_date": d["end_date"],
            "is_active": d["is_active"],
            "notes": d["notes"],
            "class_name": class_name,
            "grade_name": d["grade_name"],
            "grade_type_name": grade_type_display or d["grade_type_name"],
            "class_branch_id": d["class_branch_id"],
            "teacher_name": d.get("teacher_name"),
        })
    
    return schedules


@router.get("/schedules/student/{student_id}")
def get_student_schedule(
    student_id: int,
    academic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get weekly schedule for a specific student.
    Joins through: student → learning → grade → grade_group → schedules
    """
    from sqlalchemy import text
    
    # Raw SQL query to get student's schedule
    query = text("""
        SELECT 
            lcs.id as schedule_id,
            lcs.day_of_week,
            lts.slot_name,
            lts.start_time,
            lts.end_time,
            s.subject_name,
            s.subject_name_us,
            lcs.room_number,
            lcs.teacher_id,
            lcs.notes
        FROM learning_class_schedules lcs
        INNER JOIN learning l ON l.academicid = lcs.academic_id
          AND l.programid = lcs.program_id
          AND (lcs.shift_id IS NULL OR l.shiftid = lcs.shift_id)
          AND (lcs.grade_id IS NULL OR l.gradeid = lcs.grade_id)
          AND (lcs.grade_type_id <=> l.grade_type_id)
        INNER JOIN grade g ON g.id = l.gradeid
          AND g.group_id = lcs.grade_group_id
        INNER JOIN grade_group gg ON gg.id = lcs.grade_group_id
        INNER JOIN learning_time_slots lts ON lcs.time_slot_id = lts.id
        INNER JOIN subjects s ON lcs.subject_id = s.id
        WHERE l.studentid = :student_id
          AND lcs.academic_id = :academic_id
          AND lcs.is_active = TRUE
          AND lts.is_active = TRUE
        ORDER BY lcs.day_of_week, lts.sort_order
    """)
    
    result = db.execute(query, {"student_id": student_id, "academic_id": academic_id})
    schedules = [dict(row._mapping) for row in result]
    
    return {
        "student_id": student_id,
        "academic_id": academic_id,
        "schedule": schedules
    }


@router.put("/schedules/{schedule_id}", response_model=ClassScheduleResponse)
async def update_class_schedule(
    schedule_id: int,
    schedule_update: ClassScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminUpdateApp"))
):
    """Update an existing class schedule."""
    schedule = db.query(LearningClassSchedule).filter(
        LearningClassSchedule.id == schedule_id
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    _require_current_schedule_academic_year(db, schedule.academic_id)
    _require_current_schedule_academic_year(db, schedule_update.academic_id)
    
    # Update fields
    for key, value in schedule_update.dict().items():
        # Older clients predate class shift ownership. Do not let an omitted
        # field erase a safely backfilled shift on an existing schedule.
        if key == "shift_id" and value is None and schedule.shift_id is not None:
            continue
        setattr(schedule, key, value)
    
    schedule.updated_by = current_user.id
    db.commit()
    db.refresh(schedule)
    
    # Broadcast update
    await broadcast_schedule_update(
        academic_id=schedule.academic_id,
        branch_id=schedule.branch_id,
        grade_group_id=schedule.grade_group_id,
        action="updated"
    )
    
    return schedule


@router.get("/subjects", response_model=List[SubjectResponse])
def get_subjects(
    academic_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all subjects."""
    query = db.query(Subject)
    if academic_id:
        query = query.filter(Subject.academic_id == academic_id)
    
    return query.all()


@router.get("/teachers", response_model=List[TeacherReferenceResponse])
def get_teachers(
    academic_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all active users who can be assigned as teachers.
    Returns ALL active users (not just those already in schedules) with
    their workplace (branch_id) for branch-based filtering in the UI."""

    def resolve_name(t: User) -> str:
        kn = (t.kName or "").strip()
        en = (t.eName or "").strip()
        return kn or en or t.username or f"User #{t.id}"

    # Return all active users — any user can be assigned as a teacher
    teachers = db.query(User).filter(User.status == 1).order_by(User.id).all()

    return [
        TeacherReferenceResponse(
            id=t.id,
            name=resolve_name(t),
            kName=t.kName,
            eName=t.eName,
            phone=t.phone,
            branch_id=t.workplace,   # workplace stores the branch the user belongs to
            isForeigner=t.isForeigner,
        )
        for t in teachers
    ]


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("AdminDeleteApp"))
):
    """Delete a class schedule (hard delete)."""
    schedule = db.query(LearningClassSchedule).filter(
        LearningClassSchedule.id == schedule_id
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    _require_current_schedule_academic_year(db, schedule.academic_id)
    
    # Capture context before delete
    academic_id = schedule.academic_id
    branch_id = schedule.branch_id
    grade_group_id = schedule.grade_group_id
    
    # Hard delete from database
    db.delete(schedule)
    db.commit()
    
    # Broadcast update
    await broadcast_schedule_update(
        academic_id=academic_id,
        branch_id=branch_id,
        grade_group_id=grade_group_id,
        action="deleted"
    )
    
    return None


# ==================== SESSION LOGS ENDPOINTS ====================

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session_log(
    session: SessionLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Log a class session."""
    # Check if session already exists
    existing = db.query(LearningSessionLog).filter(
        and_(
            LearningSessionLog.class_schedule_id == session.class_schedule_id,
            LearningSessionLog.session_date == session.session_date
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already logged for this date"
        )
    
    new_session = LearningSessionLog(**session.dict())
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


@router.get("/sessions/{schedule_id}")
def get_session_logs(
    schedule_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get session logs for a specific class schedule."""
    query = db.query(LearningSessionLog).filter(
        LearningSessionLog.class_schedule_id == schedule_id
    )
    
    if start_date:
        query = query.filter(LearningSessionLog.session_date >= start_date)
    if end_date:
        query = query.filter(LearningSessionLog.session_date <= end_date)
    
    return query.order_by(LearningSessionLog.session_date.desc()).all()
