from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from .base import Base

class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    user_type = Column(String(50), nullable=False)
    device_token = Column(String(500), nullable=False)
    device_type = Column(String(50), nullable=True)
    device_name = Column(String(255), nullable=True)
    app_version = Column(String(50), nullable=True)
    
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)

    # Per-installation push preferences. Security/account events intentionally
    # bypass these optional categories so remote logout and access changes are
    # always delivered.
    notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    attendance_notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    leave_notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    message_notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    announcement_notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    market_notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    other_notifications_enabled = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'user_type', 'device_token', name='unique_user_device'),
    )

    def __repr__(self):
        return f"<DeviceToken(user={self.user_id}, type={self.user_type})>"
