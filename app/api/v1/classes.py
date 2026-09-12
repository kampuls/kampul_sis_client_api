from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from ...core import get_db
from ...schemas import ClassCreate, ClassUpdate, ClassResponse, ClassWithTeacher, EnrollmentResponse
from ...services import (
    create_class, get_class, get_classes, update_class, 
    delete_class, get_class_by_code, get_class_enrollments
)
from ...auth import get_current_active_user
from ...models import User, Class

router = APIRouter()

@router.post("/", response_model=ClassResponse)
async def create_new_class(
    class_data: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new class."""
    return create_class(db=db, class_data=class_data)

@router.get("/", response_model=List[ClassResponse])
async def read_classes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get list of classes with optional filtering."""
    return get_classes(db=db, skip=skip, limit=limit, is_active=is_active)

@router.get("/{class_id}", response_model=ClassResponse)
async def read_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific class by ID."""
    db_class = get_class(db=db, class_id=class_id)
    if db_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    return db_class

@router.get("/by-code/{class_code}", response_model=ClassResponse)
async def read_class_by_code(
    class_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific class by class code."""
    db_class = get_class_by_code(db=db, class_code=class_code)
    if db_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    return db_class

@router.get("/{class_id}/with-teacher", response_model=ClassWithTeacher)
async def read_class_with_teacher(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a class with teacher information."""
    db_class = get_class(db=db, class_id=class_id)
    if db_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    return db_class

@router.get("/{class_id}/enrollments", response_model=List[EnrollmentResponse])
async def read_class_enrollments(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all enrollments for a specific class."""
    # Check if class exists
    db_class = get_class(db=db, class_id=class_id)
    if db_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    
    return get_class_enrollments(db=db, class_id=class_id)

@router.put("/{class_id}", response_model=ClassResponse)
async def update_class_info(
    class_id: int,
    class_update: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update class information."""
    db_class = update_class(db=db, class_id=class_id, class_update=class_update)
    if db_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    return db_class

@router.delete("/{class_id}")
async def delete_class_info(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a class (soft delete)."""
    success = delete_class(db=db, class_id=class_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    return {"message": "Class deleted successfully"}

@router.get("/search/{search_term}", response_model=List[ClassResponse])
async def search_classes(
    search_term: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Search classes by name, code, or subject."""
    classes = db.query(Class).filter(
        or_(
            Class.class_name.ilike(f"%{search_term}%"),
            Class.class_code.ilike(f"%{search_term}%"),
            Class.subject.ilike(f"%{search_term}%")
        )
    ).all()
    
    return classes

@router.get("/by-subject/{subject}", response_model=List[ClassResponse])
async def get_classes_by_subject(
    subject: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get classes by subject."""
    classes = db.query(Class).filter(Class.subject.ilike(f"%{subject}%")).all()
    return classes

@router.get("/by-semester/{semester}", response_model=List[ClassResponse])
async def get_classes_by_semester(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get classes by semester."""
    classes = db.query(Class).filter(Class.semester == semester).all()
    return classes

@router.get("/by-academic-year/{academic_year}", response_model=List[ClassResponse])
async def get_classes_by_academic_year(
    academic_year: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get classes by academic year."""
    classes = db.query(Class).filter(Class.academic_year == academic_year).all()
    return classes

@router.get("/by-teacher/{teacher_id}", response_model=List[ClassResponse])
async def get_classes_by_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get classes taught by a specific teacher."""
    classes = db.query(Class).filter(Class.teacher_id == teacher_id).all()
    return classes
