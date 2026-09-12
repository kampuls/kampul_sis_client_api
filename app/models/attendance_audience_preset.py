"""Reusable employee audiences for attendance administration workflows."""

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class AttendanceAudiencePreset(Base):
    __tablename__ = "attendance_audience_presets"
    __table_args__ = (
        UniqueConstraint(
            "created_by",
            "name",
            name="uq_attendance_audience_preset_owner_name",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    preset_type = Column(String(20), nullable=False, index=True)
    branch_id = Column(Integer, nullable=True, index=True)
    department_id = Column(Integer, nullable=True, index=True)
    is_foreigner = Column(Integer, nullable=True, index=True)
    employee_ids_json = Column(Text, nullable=True)
    created_by = Column(Integer, nullable=False, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
