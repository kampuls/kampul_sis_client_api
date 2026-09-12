from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from ..database import get_db
from ..schemas import TeacherCreate, TeacherUpdate, TeacherResponse, TeacherWithClasses
from ..crud import (
    create_teacher, get_teacher, get_teachers, update_teacher, 
    delete_teacher, get_teacher_by_teacher_id
)
from ..utils import get_current_active_user
from ..models import User, Teacher

router = APIRouter()

@router.post("/", response_model=TeacherResponse)
async def create_new_teacher(
    teacher: TeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new teacher."""
    return create_teacher(db=db, teacher=teacher)

@router.get("/", response_model=List[TeacherResponse])
async def read_teachers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of teachers with optional filtering."""
    return get_teachers(db=db, skip=skip, limit=limit, is_active=is_active)

@router.get("/{teacher_id}", response_model=TeacherResponse)
async def read_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific teacher by ID."""
    db_teacher = get_teacher(db=db, teacher_id=teacher_id)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return db_teacher

@router.get("/by-teacher-id/{teacher_id}", response_model=TeacherResponse)
async def read_teacher_by_teacher_id(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific teacher by teacher ID."""
    db_teacher = get_teacher_by_teacher_id(db=db, teacher_id=teacher_id)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return db_teacher

@router.get("/{teacher_id}/classes", response_model=TeacherWithClasses)
async def read_teacher_with_classes(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a teacher with all their classes."""
    db_teacher = get_teacher(db=db, teacher_id=teacher_id)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    
    return db_teacher

@router.put("/{teacher_id}", response_model=TeacherResponse)
async def update_teacher_info(
    teacher_id: int,
    teacher_update: TeacherUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update teacher information."""
    db_teacher = update_teacher(db=db, teacher_id=teacher_id, teacher_update=teacher_update)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return db_teacher

@router.delete("/{teacher_id}")
async def delete_teacher_info(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a teacher (soft delete)."""
    success = delete_teacher(db=db, teacher_id=teacher_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return {"message": "Teacher deleted successfully"}

@router.get("/search/{search_term}", response_model=List[TeacherResponse])
async def search_teachers(
    search_term: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Search teachers by name, email, or subject."""
    teachers = db.query(Teacher).filter(
        or_(
            Teacher.first_name.ilike(f"%{search_term}%"),
            Teacher.last_name.ilike(f"%{search_term}%"),
            Teacher.email.ilike(f"%{search_term}%"),
            Teacher.subject.ilike(f"%{search_term}%"),
            Teacher.teacher_id.ilike(f"%{search_term}%")
        )
    ).all()
    
    return teachers

@router.get("/by-subject/{subject}", response_model=List[TeacherResponse])
async def get_teachers_by_subject(
    subject: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get teachers by subject."""
    teachers = db.query(Teacher).filter(Teacher.subject.ilike(f"%{subject}%")).all()
    return teachers

@router.get("/by-department/{department}", response_model=List[TeacherResponse])
async def get_teachers_by_department(
    department: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get teachers by department."""
    teachers = db.query(Teacher).filter(Teacher.department.ilike(f"%{department}%")).all()
    return teachers
