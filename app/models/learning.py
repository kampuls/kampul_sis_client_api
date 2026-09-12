"""
Learning schedule models for timetable and session management.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Time, Boolean, Enum as SQLEnum, SMALLINT, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class LearningTimeSlot(Base):
    """Time slots for scheduling (e.g., Period 1: 8:00-9:00 AM)."""
    __tablename__ = "learning_time_slots"
    
    id = Column(Integer, primary_key=True, index=True)
    slot_name = Column(String(100), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_global = Column(Boolean, default=True, server_default='1', doc="If true, visible to everyone. If false, only visible to assigned scopes.")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    
    # Relationship to scopes
    scopes = relationship("LearningTimeSlotScope", back_populates="time_slot", cascade="all, delete-orphan")


class LearningTimeSlotScope(Base):
    """
    Links a time slot to specific scopes (Grade Groups or Grades).
    Allows a single time slot to be used by multiple groups.
    """
    __tablename__ = "learning_time_slot_scopes"
    
    id = Column(Integer, primary_key=True, index=True)
    time_slot_id = Column(Integer, ForeignKey("learning_time_slots.id"), index=True, nullable=False)
    scope_type = Column(String(20), nullable=False)  # 'grade_group', 'grade'
    scope_id = Column(Integer, nullable=False)
    shift_id = Column(Integer, nullable=True, comment='Optional shift restriction')
    created_at = Column(DateTime, server_default=func.now())
    
    
    # Relationship
    time_slot = relationship("LearningTimeSlot", back_populates="scopes")



class Subject(Base):
    """Subject definition (e.g., Math, Physics)."""
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    subject_name = Column(String(100), nullable=False)
    subject_name_us = Column(String(255), nullable=True)
    short_code = Column(String(50), nullable=True)
    program_id = Column(Integer, nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    noted = Column(String(100), nullable=True)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(Date, server_default=func.now())
    updated_at = Column(Date, server_default=func.now(), onupdate=func.now())


class LearningClassSchedule(Base):
    """Main schedule table linking grade groups, subjects, teachers, and time slots."""
    __tablename__ = "learning_class_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True, comment='Links to branch table')
    program_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False, index=True, comment='Links to grade_group table')
    grade_id = Column(Integer, nullable=True, index=True, comment='Links to grade table')
    grade_type_id = Column(Integer, nullable=True, comment='Specific single grade type ID for this schedule')
    shift_id = Column(Integer, nullable=True, index=True, comment='Exact class shift for schedule recipients')
    subject_id = Column(Integer, nullable=False, index=True, comment='Links to subjects table')
    teacher_id = Column(Integer, nullable=False, index=True, comment='Links to teachers/users table')
    time_slot_id = Column(Integer, nullable=False)
    day_of_week = Column(SMALLINT, nullable=False, comment='1=Monday, 7=Sunday')
    room_number = Column(String(50), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LearningSessionLog(Base):
    """Track actual class sessions (attendance, topics covered)."""
    __tablename__ = "learning_session_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    class_schedule_id = Column(Integer, nullable=False, index=True)
    session_date = Column(Date, nullable=False, index=True)
    teacher_id = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    topic_covered = Column(String(500), nullable=True)
    homework_assigned = Column(Text, nullable=True)
    attendance_count = Column(Integer, default=0)
    status = Column(
        SQLEnum('scheduled', 'completed', 'cancelled', name='session_status'),
        default='scheduled',
        nullable=False
    )
    cancellation_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LearningScheduleException(Base):
    """Handle holidays, teacher absences, room changes, etc."""
    __tablename__ = "learning_schedule_exceptions"
    
    id = Column(Integer, primary_key=True, index=True)
    class_schedule_id = Column(Integer, nullable=False, index=True)
    exception_date = Column(Date, nullable=False, index=True)
    exception_type = Column(
        SQLEnum('cancelled', 'rescheduled', 'room_change', 'teacher_change', name='exception_type'),
        nullable=False
    )
    new_time_slot_id = Column(Integer, nullable=True)
    new_room_number = Column(String(50), nullable=True)
    substitute_teacher_id = Column(Integer, nullable=True)
    reason = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
