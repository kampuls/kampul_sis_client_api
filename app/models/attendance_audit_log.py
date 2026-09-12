"""
Attendance Audit Log - Track all attendance actions
Records WHO did WHAT and WHEN for attendance operations
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base


class AttendanceAuditLog(Base):
    __tablename__ = "attendance_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    
    # Who performed the action
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_name = Column(String(200), nullable=False)  # Cache user name for quick access
    user_role = Column(String(50), nullable=False)  # teacher, admin, etc.
    
    # What action was performed
    action_type = Column(String(50), nullable=False)  # CREATE, UPDATE, DELETE, MARK_PRESENT, MARK_ABSENT, etc.
    entity_type = Column(String(50), nullable=False)  # attendance_record, attendance_setting, etc.
    entity_id = Column(Integer, nullable=False)  # ID of the affected record
    
    # Details of the change
    old_value = Column(Text)  # JSON of old values (for UPDATE/DELETE)
    new_value = Column(Text)  # JSON of new values (for CREATE/UPDATE)
    change_description = Column(Text)  # Human-readable description
    
    # Context (which class/student)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True, index=True)
    student_name = Column(String(200), nullable=True)
    class_id = Column(Integer, nullable=True)  # grade_id + shift_id + program_id combination
    class_description = Column(String(300), nullable=True)  # e.g., "Grade 1A - Morning Shift"
    
    # Timestamps (Cambodia timezone UTC+7)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at_khmer = Column(String(50), nullable=True)  # Khmer datetime string
    
    # Device/Location info
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    branch_id = Column(Integer, nullable=True, index=True)
    
    # Relationships
    user = relationship("User", back_populates="attendance_audit_logs")
    student = relationship("Student", back_populates="attendance_audit_logs")
