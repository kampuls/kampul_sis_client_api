"""
Student Profile Edit Request model.
"""

from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func
from .base import Base


class StudentProfileEditRequest(Base):
    """Stores requests from parents/teachers to edit a student's profile."""
    
    __tablename__ = "student_profile_edit_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, index=True, nullable=False)
    requested_by = Column(Integer, index=True, nullable=False) # user_id of requester
    requested_by_type = Column(String(50), nullable=False) # 'parent', 'teacher', etc.
    
    # Proposed Changes
    kName = Column(String(100), nullable=True)
    eName = Column(String(100), nullable=True)
    gender = Column(String(100), nullable=True)
    dob = Column(Date, nullable=True)
    is_foreigner = Column(Integer, nullable=True)
    student_phone = Column(String(50), nullable=True)
    province = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    commune = Column(String(100), nullable=True)
    village = Column(String(100), nullable=True)
    previousSchool = Column(String(100), nullable=True)
    student_noted = Column(String(100), nullable=True)
    branch = Column(String(100), nullable=True)
    # Staged avatar URL awaiting approval (parents/non-admins). Applied to the
    # student on approve, deleted from storage on reject.
    avatar = Column(String(255), nullable=True)
    # JSON snapshot of the student's values at request time, so the history view
    # can show a real before -> after diff.
    previous_values = Column(Text, nullable=True)
    
    # Request Status
    status = Column(String(50), nullable=False, default='pending') # pending, approved, rejected
    reason = Column(Text, nullable=True) # Optional note from admin when rejecting
    
    created_at = Column(DateTime, nullable=True, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=True, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self):
        return f"<StudentProfileEditRequest(id={self.id}, student_id={self.student_id}, status='{self.status}')>"
