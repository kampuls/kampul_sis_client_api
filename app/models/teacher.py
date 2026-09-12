"""
Teacher model for teacher management.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float
from sqlalchemy.sql import func
from .base import Base


class Teacher(Base):
    """Teacher model for teacher management."""
    
    __tablename__ = "teachers"
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(String(50), unique=True, index=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), nullable=True)
    subject = Column(String(100), nullable=False)
    department = Column(String(100), nullable=True)
    hire_date = Column(DateTime(timezone=True), server_default=func.now())
    salary = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Teacher(id={self.id}, teacher_id='{self.teacher_id}', name='{self.first_name} {self.last_name}')>"
