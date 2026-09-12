"""
Student model for student authentication and management.
"""

from sqlalchemy import Column, Integer, String, Date, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class Student(Base):
    """Student model for student authentication and management."""
    
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(25), unique=True, index=True, nullable=True)
    password = Column(String(100), nullable=True)
    studentid = Column(String(255), nullable=True)
    optional_id = Column(String(100), nullable=True)
    kName = Column(String(100), nullable=False)
    eName = Column(String(100), nullable=False)
    gender = Column(String(100), nullable=False)
    dob = Column(Date, nullable=False)
    # Student image path or URL (VARCHAR for modern file-based storage)
    image = Column(String(255), nullable=True)
    student_phone = Column(String(50), nullable=True)
    is_foreigner = Column(Integer, nullable=False, default=1)
    province = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    commune = Column(String(100), nullable=False)
    village = Column(String(100), nullable=False)
    previousSchool = Column(String(100), nullable=True)
    leaveDate = Column(DateTime, nullable=True)
    myparents = Column(String(100), nullable=False)
    child_order = Column(Integer, nullable=False, default=1)
    academic = Column(String(100), nullable=False)
    branch = Column(String(100), nullable=False)
    status = Column(Integer, nullable=False)
    student_noted = Column(String(100), nullable=True)
    # 1 only when a PARENT self-registered this child via the app (status=2
    # pending). Distinguishes parent submissions from admin/other status=2 rows,
    # so only these appear in the pending screen and the 7-day auto-cleanup.
    submitted_by_parent = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=True, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=True, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    attendance_audit_logs = relationship("AttendanceAuditLog", back_populates="student", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Student(id={self.id}, username='{self.username}', kName='{self.kName}', eName='{self.eName}')>"
