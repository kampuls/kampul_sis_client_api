"""
Class model for class management.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from .base import Base


class Class(Base):
    """Class model for class management."""
    
    __tablename__ = "classes"
    
    id = Column(Integer, primary_key=True, index=True)
    class_code = Column(String(20), unique=True, index=True, nullable=False)
    class_name = Column(String(200), nullable=False)
    subject = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    credits = Column(Integer, default=3)
    max_students = Column(Integer, default=30)
    teacher_id = Column(Integer, nullable=False)
    semester = Column(String(20), nullable=False)
    academic_year = Column(String(10), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Class(id={self.id}, class_code='{self.class_code}', class_name='{self.class_name}')>"
