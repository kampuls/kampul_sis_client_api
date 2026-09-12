"""
Pydantic schemas for Telegram Attendance Notifications.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime


class TelegramBranchNotificationRoute(BaseModel):
    """Per-workplace Telegram destination overrides."""

    branch_id: int = Field(..., gt=0)
    attendance_chat_id: Optional[str] = Field(None, max_length=100)
    leave_chat_id: Optional[str] = Field(None, max_length=100)

    class Config:
        from_attributes = True


class TelegramAttendanceSettingsBase(BaseModel):
    """Base schema for Telegram attendance settings."""
    bot_token: Optional[str] = Field(None, max_length=500)
    chat_id: Optional[str] = Field(None, max_length=100)
    leave_routing_mode: Optional[str] = Field("combined", max_length=20)
    leave_chat_id: Optional[str] = Field(None, max_length=100)
    branch_routing_mode: Optional[str] = Field("all", max_length=20)
    branch_routes: List[TelegramBranchNotificationRoute] = Field(
        default_factory=list
    )
    enabled: bool = False
    # Leave (ask-permission) notifications; Optional so legacy NULL rows validate.
    notify_leave_requests: Optional[bool] = False
    notify_leave_decisions: Optional[bool] = False

    @field_validator("leave_routing_mode", mode="before")
    @classmethod
    def validate_leave_routing_mode(cls, value):
        normalized = str(value or "combined").strip().lower()
        if normalized not in {"combined", "separate"}:
            raise ValueError("leave_routing_mode must be combined or separate")
        return normalized

    @field_validator("branch_routing_mode", mode="before")
    @classmethod
    def validate_branch_routing_mode(cls, value):
        normalized = str(value or "all").strip().lower()
        if normalized not in {"all", "by_branch"}:
            raise ValueError("branch_routing_mode must be all or by_branch")
        return normalized


class TelegramAttendanceSettingsCreate(TelegramAttendanceSettingsBase):
    """Schema for creating Telegram settings."""
    pass


class TelegramAttendanceSettingsUpdate(TelegramAttendanceSettingsBase):
    """Schema for updating Telegram settings."""
    pass


class TelegramAttendanceSettingsResponse(TelegramAttendanceSettingsBase):
    """Schema for Telegram settings response."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TelegramTestMessageRequest(BaseModel):
    """Request schema for testing Telegram notification."""
    employee_name: str = Field(..., min_length=1)
    type: str = Field(..., pattern="^(check_in|check_out)$")
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
