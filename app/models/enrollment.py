"""
Enrollment model for student enrollment management.
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from .base import Base


class Enrollment(Base):
    """Enrollment model for student enrollment management."""
    
    __tablename__ = "enrollments"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False)
    class_id = Column(Integer, nullable=False)
    enrollment_date = Column(DateTime(timezone=True), server_default=func.now())
    grade = Column(String(5), nullable=True)  # A, B, C, D, F
    status = Column(String(20), default="enrolled")  # enrolled, completed, dropped
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Enrollment(id={self.id}, student_id={self.student_id}, class_id={self.class_id}, status='{self.status}')>"
