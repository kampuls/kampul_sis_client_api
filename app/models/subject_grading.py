"""Per-subject grading composition and attendance models."""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .base import Base


class SubjectGradePlan(Base):
    """A 100% grading plan for one subject/exam/class context."""

    __tablename__ = "subject_grade_plans"
    __table_args__ = (
        UniqueConstraint(
            "academic_id",
            "program_id",
            "grade_id",
            "grade_type_id",
            "shift_id",
            "subject_id",
            "marks_system_id",
            name="uq_subject_grade_plan_context",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    # New tables normalize a missing grade type to zero so MySQL uniqueness is
    # reliable (multiple NULL values are otherwise allowed in a unique index).
    grade_type_id = Column(Integer, nullable=False, default=0)
    shift_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, nullable=False, index=True)
    marks_system_id = Column(Integer, nullable=False, index=True)
    attendance_start_date = Column(Date, nullable=True)
    attendance_end_date = Column(Date, nullable=True)
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SubjectGradeComponent(Base):
    """One weighted component in a subject grade plan."""

    __tablename__ = "subject_grade_components"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(
        Integer,
        ForeignKey("subject_grade_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    weight_percent = Column(Numeric(7, 2), nullable=False)
    source_type = Column(String(30), nullable=False, default="manual")
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SubjectGradeScore(Base):
    """Manual earned points for one student and plan component."""

    __tablename__ = "subject_grade_scores"
    __table_args__ = (
        UniqueConstraint(
            "component_id", "student_id", name="uq_subject_grade_score_student"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(
        Integer,
        ForeignKey("subject_grade_components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(Integer, nullable=False, index=True)
    earned_points = Column(Numeric(7, 2), nullable=False)
    updated_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SubjectAttendance(Base):
    """Attendance for an individual subject study session."""

    __tablename__ = "subject_attendance"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "academic_id",
            "program_id",
            "grade_id",
            "grade_type_id",
            "shift_id",
            "subject_id",
            "attendance_date",
            name="uq_subject_attendance_context",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    grade_type_id = Column(Integer, nullable=False, default=0)
    shift_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False)
    note = Column(String(255), nullable=True)
    teacher_id = Column(Integer, nullable=False)
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
