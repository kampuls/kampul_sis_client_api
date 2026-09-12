"""
Featured top students snapshots for PAMA home.

Keeps history by storing every featured publish action while marking only the
latest snapshot per class context as active.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Numeric,
)
from sqlalchemy.sql import func

from .base import Base


class ResultTopStudent(Base):
    __tablename__ = "results_top_students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Group identifier for one "feature top 3" action
    featured_batch_id = Column(String(36), nullable=False, index=True)

    # Class context (used for replacement)
    academic_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False, index=True)
    grade_id = Column(Integer, nullable=False, index=True)
    shift_id = Column(Integer, nullable=False, index=True)
    grade_type_id = Column(Integer, nullable=True, index=True)

    # Student result snapshot
    student_id = Column(Integer, nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    average = Column(Numeric(10, 2), nullable=True)
    grade = Column(String(20), nullable=True)

    # Result context
    marks_system_id = Column(Integer, nullable=True, index=True)
    result_name = Column(String(255), nullable=True)
    exam_name = Column(String(255), nullable=True)
    exam_type = Column(String(50), nullable=True)
    period = Column(String(50), nullable=True)

    # Active snapshot marker (1 = currently shown on home)
    is_active = Column(Integer, nullable=False, default=1, index=True)

    # Audit
    featured_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

