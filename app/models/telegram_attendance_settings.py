"""
Telegram Attendance Settings Model.
Stores Telegram bot configuration for attendance notifications.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from .base import Base


class TelegramAttendanceSettings(Base):
    """
    Telegram Notification Settings for Attendance.
    Stores bot token and chat ID for sending attendance notifications.
    """
    __tablename__ = "telegram_attendance_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Telegram Bot Configuration
    bot_token = Column(String(500), nullable=True)  # Bot token from BotFather
    chat_id = Column(String(100), nullable=True)    # Chat ID (group or private)

    # Leave notifications use the attendance destination by default. When the
    # mode is ``separate``, leave_chat_id is the only valid leave destination.
    # Nullable columns keep startup schema synchronization safe for old DBs.
    leave_routing_mode = Column(String(20), nullable=True, default="combined")
    leave_chat_id = Column(String(100), nullable=True)

    # ``all`` keeps the legacy single-destination behavior. ``by_branch``
    # applies optional workplace-specific overrides and falls back to the
    # destinations above whenever a branch has not been configured.
    branch_routing_mode = Column(String(20), nullable=True, default="all")
    
    # Enable/Disable notifications
    enabled = Column(Boolean, default=False)

    # Leave (ask-permission) notifications — nullable so auto-migrate can add
    # the columns to the existing table; NULL is treated as disabled.
    notify_leave_requests = Column(Boolean, nullable=True, default=False)
    notify_leave_decisions = Column(Boolean, nullable=True, default=False)

    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    branch_routes = relationship(
        "TelegramBranchNotificationRoute",
        back_populates="settings",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return (
            "<TelegramAttendanceSettings("
            f"enabled={self.enabled}, chat_id={self.chat_id}, "
            f"leave_routing_mode={self.leave_routing_mode}, "
            f"leave_chat_id={self.leave_chat_id})>"
        )


class TelegramBranchNotificationRoute(Base):
    """Optional Attendance and Leave destinations for one workplace branch."""

    __tablename__ = "telegram_branch_notification_routes"
    __table_args__ = (
        UniqueConstraint(
            "settings_id",
            "branch_id",
            name="uq_telegram_branch_notification_route",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    settings_id = Column(
        Integer,
        ForeignKey("telegram_attendance_settings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = Column(Integer, nullable=False, index=True)
    attendance_chat_id = Column(String(100), nullable=True)
    # NULL means Leave shares this branch's Attendance destination. When both
    # are NULL, the existing global Leave rules are used as the fallback.
    leave_chat_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    settings = relationship(
        "TelegramAttendanceSettings",
        back_populates="branch_routes",
    )
