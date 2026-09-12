"""
Pickup models for the child pickup request system.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SAEnum, Index
from sqlalchemy.sql import func
from .base import Base
import enum


class PickupStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    cancelled = "cancelled"


class PickupRequest(Base):
    """A parent's request to pick up a specific child."""

    __tablename__ = "pickup_requests"
    __table_args__ = (
        Index(
            "idx_pickup_academic_status_requested",
            "academic_id",
            "status",
            "requested_at",
            "id",
        ),
        Index(
            "idx_pickup_branch_queue",
            "academic_id",
            "pickup_branch_id",
            "status",
            "requested_at",
            "id",
        ),
        Index(
            "idx_pickup_parent_student_latest",
            "parent_id",
            "student_id",
            "id",
        ),
        Index("idx_pickup_student_active", "student_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    pickup_branch_id = Column(Integer, nullable=True, index=True)
    status = Column(
        SAEnum("pending", "processing", "completed", "cancelled", name="pickup_status_enum"),
        nullable=False,
        default="pending"
    )
    repeat_count = Column(Integer, nullable=False, default=3)    # configured at request time
    current_repeat = Column(Integer, nullable=False, default=0)  # how many plays done
    requested_at = Column(DateTime, server_default=func.now())
    processing_started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)             # parent can't call again until this


class PickupSettings(Base):
    """Admin-configurable settings for pickup per academic year."""

    __tablename__ = "pickup_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    academic_id = Column(Integer, nullable=False, unique=True, index=True)
    repeat_count = Column(Integer, nullable=False, default=3)          # times to play per student
    cooldown_seconds = Column(Integer, nullable=False, default=300)    # 5 minutes default
    calling_enabled = Column(Boolean, nullable=False, default=False)   # staff session: announce in hall
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
