from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from ..database import get_db
from ..schemas import StudentCreate, StudentUpdate, StudentResponse, StudentWithEnrollments
from ..crud import (
    create_student, get_student, get_students, update_student, 
    delete_student, get_student_by_student_id
)
from ..utils import get_current_active_user
from ..models import User, Student

router = APIRouter()

@router.post("/", response_model=StudentResponse)
async def create_new_student(
    student: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new student."""
    return create_student(db=db, student=student)

@router.get("/", response_model=List[StudentResponse])
async def read_students(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of students with optional filtering."""
    return get_students(db=db, skip=skip, limit=limit, is_active=is_active)

@router.get("/{student_id}", response_model=StudentResponse)
async def read_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific student by ID."""
    db_student = get_student(db=db, student_id=student_id)
    if db_student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    return db_student

@router.get("/by-student-id/{student_id}", response_model=StudentResponse)
async def read_student_by_student_id(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific student by student ID."""
    db_student = get_student_by_student_id(db=db, student_id=student_id)
    if db_student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    return db_student

@router.get("/{student_id}/enrollments", response_model=StudentWithEnrollments)
async def read_student_with_enrollments(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a student with all their enrollments."""
    from ..crud import get_student_enrollments
    
    db_student = get_student(db=db, student_id=student_id)
    if db_student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    enrollments = get_student_enrollments(db=db, student_id=student_id)
    db_student.enrollments = enrollments
    return db_student

@router.put("/{student_id}", response_model=StudentResponse)
async def update_student_info(
    student_id: int,
    student_update: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update student information."""
    db_student = update_student(db=db, student_id=student_id, student_update=student_update)
    if db_student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    return db_student

@router.delete("/{student_id}")
async def delete_student_info(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a student (soft delete)."""
    success = delete_student(db=db, student_id=student_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    return {"message": "Student deleted successfully"}

@router.get("/search/{search_term}", response_model=List[StudentResponse])
async def search_students(
    search_term: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Search students by name or email."""
    students = db.query(Student).filter(
        or_(
            Student.first_name.ilike(f"%{search_term}%"),
            Student.last_name.ilike(f"%{search_term}%"),
            Student.email.ilike(f"%{search_term}%"),
            Student.student_id.ilike(f"%{search_term}%")
        )
    ).all()
    
    return students
