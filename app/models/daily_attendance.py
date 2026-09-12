from sqlalchemy import Column, Integer, String, Date, Float, Enum, Boolean, ForeignKey, func, DateTime
from .base import Base

class DailyAttendance(Base):
    __tablename__ = "daily_attendance"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False, index=True)
    grade_id = Column(Integer, nullable=False, index=True)
    grade_type_id = Column(Integer, nullable=False, index=True)
    shift_id = Column(Integer, nullable=False, index=True)
    
    status = Column(String(20), nullable=False)
    attendance_date = Column(Date, nullable=False, index=True)
    
    academic_id = Column(Integer, nullable=True)
    note = Column(String(50), nullable=True)
    
    teacher_id = Column(Integer, nullable=False)
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer, nullable=False)
    created_by_type = Column(String(20), nullable=False, default='teacher', index=True) # ENUM handled as String to avoid issues
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<DailyAttendance(student_id={self.student_id}, date={self.attendance_date}, status={self.status})>"
