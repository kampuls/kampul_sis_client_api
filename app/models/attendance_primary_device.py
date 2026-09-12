"""Primary-device binding used for employee attendance mutations."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from .base import Base


class AttendancePrimaryDevice(Base):
    __tablename__ = "attendance_primary_devices"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    device_id_hash = Column(String(64), nullable=False, index=True)
    device_name = Column(String(255), nullable=False)
    platform = Column(String(20), nullable=False)
    registered_at = Column(DateTime, nullable=False)
    last_changed_at = Column(DateTime, nullable=False)
    change_available_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AttendancePrimaryDeviceEvent(Base):
    """Immutable audit history for registration, change, and reset actions."""

    __tablename__ = "attendance_primary_device_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(40), nullable=False, index=True)
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    previous_device_name = Column(String(255), nullable=True)
    new_device_name = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    detail_json = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
    )
