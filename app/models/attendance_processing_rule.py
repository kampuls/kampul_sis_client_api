"""Opt-out rules for employee attendance participation.

Rules are intentionally stored outside ``users`` and ``department`` so the
feature can be deployed without changing either legacy table.  Missing rules
mean enabled, which keeps every existing employee participating by default.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class AttendanceProcessingRule(Base):
    __tablename__ = "attendance_processing_rules"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", name="uq_attendance_processing_scope"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_type = Column(String(20), nullable=False, index=True)
    scope_id = Column(Integer, nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

