"""
Marks models for the marking system.
Based on the Python Telegram bot implementation.
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey, Date
from sqlalchemy.sql import func
from .base import Base


class MarksSystem(Base):
    """Marks system (exam) definition."""
    __tablename__ = "marks_system"
    
    id = Column(Integer, primary_key=True, index=True)
    marks_name = Column(String(255), nullable=False)
    program_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=True)
    academic_id = Column(Integer, nullable=False)
    for_month = Column(Date, nullable=True)  # Exam date - marks entry is allowed from this date
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SubjectsGroup(Base):
    """Subject configuration for grade groups."""
    __tablename__ = "subjects_group"
    
    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, nullable=False)
    academic_id = Column(Integer, nullable=False)
    program_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    full_marks = Column(Numeric(10, 2), nullable=False, default=100.00)
    calculate_marks = Column(Numeric(10, 2), nullable=False, default=100.00)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MarksInput(Base):
    """Raw marks entered by teachers."""
    __tablename__ = "marks_input"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    academic_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, nullable=False, index=True)
    marks_system_id = Column(Integer, nullable=False, index=True)
    marks = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MarksMonthly(Base):
    """Calculated monthly exam results. Links to marks_input via marks_monthly_items junction table."""
    __tablename__ = "marks_monthly"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_name = Column(String(255), nullable=False)
    student_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    academic_id = Column(Integer, nullable=False)
    marks_system_id = Column(Integer, nullable=False, index=True)
    total = Column(Numeric(10, 2), nullable=False)
    average = Column(Numeric(10, 2), nullable=False)
    grade_scale_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MarksSemester(Base):
    """Calculated semester exam results."""
    __tablename__ = "marks_semester"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_name = Column(String(255), nullable=False)
    student_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    academic_id = Column(Integer, nullable=False)
    marks_imonthly_ids = Column(Text, nullable=True)  # Comma-separated IDs (matches Telegram bot)
    marks_system_id = Column(Integer, nullable=False, index=True)
    total = Column(Numeric(10, 2), nullable=False)
    average = Column(Numeric(10, 2), nullable=False)
    grade_scale_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MarksYearly(Base):
    """Calculated yearly exam results. Links to marks_semester via marks_yearly_semesters junction table."""
    __tablename__ = "marks_yearly"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_name = Column(String(255), nullable=False)
    student_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    academic_id = Column(Integer, nullable=False)
    marks_system_id = Column(Integer, nullable=False, index=True)
    total = Column(Numeric(10, 2), nullable=False)
    average = Column(Numeric(10, 2), nullable=False)
    grade_scale_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class GradeScale(Base):
    """Grade scale definitions."""
    __tablename__ = "grade_scale"
    
    id = Column(Integer, primary_key=True, index=True)
    academic_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    us_grade = Column(String(10), nullable=False)  # A, B, C, D, E, F
    kh_grade = Column(String(50), nullable=True)  # Khmer grade
    min_marks = Column(Numeric(10, 2), nullable=False)
    max_marks = Column(Numeric(10, 2), nullable=False)
    is_overall = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ExamCalculateSign(Base):
    """Exam calculation configuration."""
    __tablename__ = "exam_calculate_sign"
    
    id = Column(Integer, primary_key=True, index=True)
    result_name = Column(String(255), nullable=False)
    exam_type = Column(String(50), nullable=False)  # 'input', 'semester', 'yearly'
    formula_expression = Column(Text, nullable=True)
    marks_system_id = Column(Integer, nullable=False)
    academic_id = Column(Integer, nullable=False)
    program_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    divide_by_multiplier = Column(Numeric(10, 2), nullable=True, default=1.0)  # Matches Telegram bot
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DecimalMarksAllow(Base):
    """Configuration for allowed decimal values in marks."""
    __tablename__ = "decimal_marks_allow"
    
    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, nullable=False, index=True)
    allow = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

