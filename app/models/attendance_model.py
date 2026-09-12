from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, JSON, func, DateTime, Float, Text, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base

class AttendanceSchedule(Base):
    """
    Attendance Configuration / Schedule Definition.
    Defines the working hours and logic (e.g. "Standard Office", "Shift A").
    """
    __tablename__ = "attendance_schedules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    
    # Type: 'standard' or 'flexible'
    type = Column(String(50), nullable=False, default='standard') 

    # Scope (Restored for Simplicity)
    # A schedule can be tied directly to a scope.
    branch_id = Column(Integer, nullable=True) 
    department_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)

    # Configuration for the week (Monday-Sunday)
    weekly_config = Column(JSON, nullable=False)

    is_active = Column(Integer, default=1)
    effective_date = Column(Date, nullable=False)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AttendanceSchedule(name={self.name})>"

class AttendanceSystemSettings(Base):
    """
    Global Attendance System Security Settings.
    Stores policies for fraud prevention.
    """
    __tablename__ = "attendance_system_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Security Policies
    require_location = Column(Boolean, default=True)
    block_mock_location = Column(Boolean, default=True)
    block_developer_options = Column(Boolean, default=False)
    
    # Network / IP Restrictions
    allowed_ip_ranges = Column(String(500), nullable=True) # Comma separated CIDRs
    
    # Time Restrictions (Global) - NULL legacy rows coerced to max 240 at runtime
    allow_early_clock_in_mins = Column(Integer, nullable=True, default=None)  # 0..240 minutes when set
    # Optional JSON list [mins_session1, mins_session2, ...] — per-session early clock-in caps.
    # When null/empty, all sessions use allow_early_clock_in_mins. Index i overrides session i only.
    per_session_early_clock_in_mins = Column(JSON, nullable=True)
    allow_late_clock_out_mins = Column(Integer, nullable=True, default=None)  # NULL = unlimited
    min_minutes_before_checkout = Column(Integer, nullable=False, default=30)  # Minimum minutes after session start before checkout
    session_transition_wait_mins = Column(Integer, nullable=False, default=10)  # Wait after checkout before another session check-in
    allow_early_leave_mins = Column(Integer, nullable=False, default=0)  # Minutes before end allowed without early-leave penalty
    allow_makeup_missing_sessions = Column(Boolean, nullable=False, default=False)  # Allow backfilling missed sessions in current day

    # Late Grace Period - How many minutes before marking as "late"
    late_grace_minutes = Column(Integer, nullable=False, default=15)  # Default 15 minutes grace

    # Reminders Configuration
    notify_enable_before = Column(Boolean, default=True, nullable=False)
    notify_minutes_before = Column(JSON, nullable=True) # e.g. [10, 5]
    notify_enable_after = Column(Boolean, default=True, nullable=False)
    notify_minutes_after = Column(JSON, nullable=True) # e.g. [10, 30]
    notify_enable_before_checkout = Column(Boolean, default=True, nullable=False)
    notify_minutes_before_checkout = Column(JSON, nullable=True) # e.g. [1]
    notify_enable_after_checkout = Column(Boolean, default=True, nullable=False)
    notify_minutes_after_checkout = Column(JSON, nullable=True) # e.g. [5]
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AttendanceSettings(mock={self.block_mock_location}, dev={self.block_developer_options})>"

class AttendanceUserAssignment(Base):
    """
    Explicit assignment of an AttendanceSchedule to a User.
    Overrides Department/Branch defaults.
    """
    __tablename__ = "attendance_user_assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True) # Explicit user link
    schedule_id = Column(Integer, ForeignKey("attendance_schedules.id"), nullable=False, index=True)
    
    # History Tracking
    start_date = Column(Date, nullable=False, default=func.current_date())
    end_date = Column(Date, nullable=True) # NULL means currently active
    
    # Audit trail
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    assigned_by = Column(Integer, nullable=True)

    schedule = relationship("AttendanceSchedule")

    def __repr__(self):
        return f"<AttendanceUserAssignment(user={self.user_id}, schedule={self.schedule_id})>"

class AttendanceScheduleException(Base):
    """
    Per-date override of the recurring weekly attendance schedule.
    Supports company-wide, branch, department, or individual scope.
    """
    __tablename__ = "attendance_schedule_exceptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exception_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=True, index=True)

    user_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True, index=True)
    department_id = Column(Integer, nullable=True, index=True)
    # NULL = all staff; 1 = Khmer; 2 = Foreigner
    is_foreigner = Column(Integer, nullable=True, index=True)

    # once | date_range | monthly
    recurrence_type = Column(String(30), nullable=True, default="once")

    # sessions_override | day_off
    exception_type = Column(String(50), nullable=False, default="sessions_override")
    sessions = Column(JSON, nullable=True)
    reason = Column(String(500), nullable=True)
    title_en = Column(String(150), nullable=True)
    title_km = Column(String(150), nullable=True)
    reason_en = Column(String(500), nullable=True)
    reason_km = Column(String(500), nullable=True)

    # When enabled, matching staff may opt into this alternate schedule during
    # their first attendance action. It is never applied automatically.
    self_enrollment_enabled = Column(Integer, nullable=False, default=0)

    # When enabled, staff can take attendance outside the workplace (from home,
    # off-site event/training, or day-off remote attendance without workplace geofence).
    allow_outside_workplace = Column(Integer, nullable=False, default=0)

    created_by = Column(Integer, nullable=True)
    is_active = Column(Integer, default=1)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AttendanceScheduleException(date={self.exception_date}, type={self.exception_type})>"


class AttendanceScheduleExceptionEnrollment(Base):
    """Immutable employee choice of one optional exception for one date."""

    __tablename__ = "attendance_schedule_exception_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "occurrence_date",
            name="uq_attendance_exception_enrollment_user_date",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exception_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    occurrence_date = Column(Date, nullable=False, index=True)
    enrolled_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self):
        return (
            "<AttendanceScheduleExceptionEnrollment("
            f"user={self.user_id}, date={self.occurrence_date}, "
            f"exception={self.exception_id})>"
        )


class AttendanceRecord(Base):
    """
    Advanced Attendance Record.
    Tracks check-in/out, geolocation, device info, and status.
    """
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    
    # Check-in
    check_in_time = Column(DateTime, nullable=True)
    check_in_latitude = Column(Float(10, 8), nullable=True)
    check_in_longitude = Column(Float(11, 8), nullable=True)
    check_in_branch_id = Column(Integer, nullable=True)  # Branch scanned at check-in
    
    # Check-out
    check_out_time = Column(DateTime, nullable=True)
    check_out_latitude = Column(Float(10, 8), nullable=True)
    check_out_longitude = Column(Float(11, 8), nullable=True)
    check_out_branch_id = Column(Integer, nullable=True)  # Branch scanned at check-out
    
    # Verification
    is_mock_location = Column(Boolean, default=False)
    device_info = Column(Text, nullable=True)
    
    # Analysis
    attendance_date = Column(Date, nullable=False, index=True)
    session_index = Column(Integer, nullable=True, index=True)  # 1-based schedule session number
    schedule_id = Column(Integer, nullable=True, index=True)
    scheduled_start = Column(String(8), nullable=True)
    scheduled_end = Column(String(8), nullable=True)
    snapshot_late_grace_minutes = Column(Integer, nullable=True)
    snapshot_allow_early_leave_mins = Column(Integer, nullable=True)
    work_hours = Column(Float, nullable=True)
    status = Column(String(20), default='present') # present, absent, half_day, late
    earned_percentage = Column(Float, default=0.0)
    
    notes = Column(Text, nullable=True)
    late_reason = Column(Text, nullable=True)
    leave_early_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AttendanceRecord(user={self.user_id}, date={self.attendance_date}, status={self.status})>"
