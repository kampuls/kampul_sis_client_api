"""
Subjects API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from ...core import get_db
from ...auth import get_current_active_user
from ...models import User
from ...models.learning import Subject
from ...models.marks import SubjectsGroup
from pydantic import BaseModel

router = APIRouter(prefix="/subjects", tags=["Subjects"])


class SubjectResponse(BaseModel):
    id: int
    subject_name: str
    subject_name_us: Optional[str]
    short_code: Optional[str] = None
    program_id: int
    academic_id: int
    
    class Config:
        from_attributes = True


@router.get("", response_model=List[SubjectResponse])
def get_subjects(
    grade_id: Optional[int] = None,
    grade_group_id: Optional[int] = None, # Support direct grade_group_id
    academic_id: Optional[int] = None,
    program_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all subjects, filtered by grade (converting to grade group), academic year, and program.
    """
    from sqlalchemy import text
    import logging
    logger = logging.getLogger("uvicorn")
    
    query = db.query(Subject)
    
    # 1. Resolve Grade Group ID
    # If grade_id provided, look up grade_group_id
    if grade_id:
        grade_query = text("SELECT group_id FROM grade WHERE id = :grade_id")
        grade_result = db.execute(grade_query, {"grade_id": grade_id}).fetchone()
        if grade_result and grade_result[0]:
            grade_group_id = grade_result[0] # Override/Set grade_group_id
    
    # 2. Filter logic
    if grade_group_id or academic_id or program_id:
        # Join with SubjectsGroup to filter by class context
        query = query.join(SubjectsGroup, SubjectsGroup.subject_id == Subject.id)
        
        if grade_group_id:
            query = query.filter(SubjectsGroup.grade_group_id == grade_group_id)
        
        if academic_id:
            query = query.filter(SubjectsGroup.academic_id == academic_id)
            
        if program_id:
            query = query.filter(SubjectsGroup.program_id == program_id)
            
    return query.order_by(Subject.subject_name).distinct().all()
