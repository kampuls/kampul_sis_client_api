"""
Attendance Statistics - Aggregated stats for attendance patterns
Tracks when attendance is usually taken, peak times, etc.
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, func, Date
from sqlalchemy.orm import relationship
from .base import Base


class AttendanceStatistic(Base):
    __tablename__ = "attendance_statistics"

    id = Column(Integer, primary_key=True, index=True)
    
    # Class/Group identification
    branch_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False, index=True)
    grade_id = Column(Integer, nullable=False, index=True)
    shift_id = Column(Integer, nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    
    # Time period (daily aggregation)
    statistic_date = Column(Date, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    month = Column(Integer, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    
    # Timing statistics
    first_attendance_time = Column(DateTime(timezone=True), nullable=True)  # Earliest attendance mark
    last_attendance_time = Column(DateTime(timezone=True), nullable=True)  # Latest attendance mark
    average_attendance_time = Column(DateTime(timezone=True), nullable=True)  # Average time
    
    # Time in minutes from midnight for easier calculation
    first_attendance_minutes = Column(Integer, nullable=True)  # e.g., 420 = 7:00 AM
    last_attendance_minutes = Column(Integer, nullable=True)  # e.g., 600 = 10:00 AM
    average_attendance_minutes = Column(Float, nullable=True)  # e.g., 480.5 = 8:00:30 AM
    
    # Attendance counts
    total_students = Column(Integer, default=0)
    marked_present = Column(Integer, default=0)
    marked_absent = Column(Integer, default=0)
    marked_late = Column(Integer, default=0)
    marked_permission = Column(Integer, default=0)
    
    # Teacher who took attendance (most common for the day)
    primary_teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    primary_teacher_name = Column(String(200), nullable=True)
    
    # Peak time analysis (which hour has most attendance marks)
    peak_hour = Column(Integer, nullable=True)  # 0-23
    peak_hour_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Khmer datetime for display
    statistic_date_khmer = Column(String(100), nullable=True)
