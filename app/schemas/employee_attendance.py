"""
Pydantic schemas for Employee Attendance System
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from datetime import date, datetime
from enum import Enum


class AttendanceType(str, Enum):
    STANDARD = "standard"
    FLEXIBLE = "flexible"
    INDIVIDUAL = "individual"


class WorkType(str, Enum):
    FULL_DAY = "full_day"
    HALF_DAY = "half_day"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    LATE = "late"


class DeductionType(str, Enum):
    FIXED_AMOUNT = "fixed_amount"
    HOURLY_RATE = "hourly_rate"
    PERCENTAGE = "percentage"


class BonusType(str, Enum):
    FIXED_AMOUNT = "fixed_amount"
    HOURLY_RATE = "hourly_rate"
    PERCENTAGE = "percentage"


# Response Models



class WorkLocationResponse(BaseModel):
    id: int
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_meters: float = 100.0
    branch_id: Optional[int] = None
    is_active: bool = True


class WorkLocationUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_meters: float = Field(default=100.0, ge=5, le=10000)
    branch_id: Optional[int] = Field(None, ge=1)
    is_active: bool = True


class AttendanceRecordResponse(BaseModel):
    id: Optional[int] = None
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    session_index: Optional[int] = None
    schedule_id: Optional[int] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    snapshot_late_grace_minutes: Optional[int] = None
    snapshot_allow_early_leave_mins: Optional[int] = None
    work_hours: Optional[float] = None
    status: str = "not_checked_in"
    notes: Optional[str] = None
    late_reason: Optional[str] = None
    leave_early_reason: Optional[str] = None


class CheckInOutRequest(BaseModel):
    action: str = Field(
        ...,
        pattern=r"^(auto|check_in|check_out)$",
        description="Must be 'auto', 'check_in', or 'check_out'",
    )
    session_index: Optional[int] = Field(
        None,
        ge=1,
        le=20,
        description=(
            "The 1-based session selected by the attendance client. Required "
            "for deterministic explicit check-in/check-out requests."
        ),
    )
    schedule_exception_id: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "Optional self-enrollment schedule exception selected during the "
            "employee's first attendance action of the date."
        ),
    )
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    gps_accuracy_meters: Optional[float] = Field(None, ge=0, le=10000)
    gps_timestamp: Optional[datetime] = None
    # Diagnostic only: lets the server distinguish a stale GPS fix from a
    # manually changed phone clock. It is never trusted to approve attendance.
    device_timestamp: Optional[datetime] = None
    is_mock_location: Optional[bool] = None
    device_info: Optional[str] = Field(None, max_length=1000)
    attendance_device_id: Optional[str] = Field(None, min_length=32, max_length=128)
    # A modern app may send its previously persisted installation ID while
    # moving to the stable OS-derived ID. The API accepts the migration only
    # when this value hashes to the account's existing primary binding.
    attendance_device_previous_id: Optional[str] = Field(
        None,
        min_length=32,
        max_length=128,
    )
    attendance_device_name: Optional[str] = Field(None, max_length=255)
    attendance_device_platform: Optional[str] = Field(
        None,
        pattern=r"^(android|ios)$",
    )
    branch_id: Optional[int] = Field(None, ge=1)
    reason: Optional[str] = Field(None, max_length=1000)
    qr_type: Optional[str] = Field(
        None,
        pattern=r"^(branch|t_attendance|r_attendance)$",
    )
    qr_id: Optional[int] = Field(None, ge=1)


class AttendanceDeviceIdentityRequest(BaseModel):
    attendance_device_id: str = Field(..., min_length=32, max_length=128)
    attendance_device_previous_id: Optional[str] = Field(
        None,
        min_length=32,
        max_length=128,
    )
    attendance_device_name: Optional[str] = Field(None, max_length=255)
    attendance_device_platform: str = Field(..., pattern=r"^(android|ios)$")


class AttendanceDeviceAdminResetRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class CheckInOutResponse(BaseModel):
    success: bool
    message: str
    timestamp: datetime
    action: str
    work_hours: Optional[float] = None
    primary_device_registered: bool = False
    primary_device_name: Optional[str] = None


class UpdateUserAllowedBranchesRequest(BaseModel):
    branch_ids: List[int] = Field(..., description="List of branch IDs the user is allowed to check in at")

class AttendanceScheduleBase(BaseModel):
    total_work_hours: float
    present_days: float
    absent_days: float
    total_days: float


class AttendanceSummary(BaseModel):
    total_work_hours: float
    present_days: float
    absent_days: float
    # Approved leave days in range — excluded from absent_days.
    leave_days: float = 0.0
    total_days: float


class AttendanceReportResponse(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    records: List[dict]  # List of attendance records
    # Per-date approved leave ({'YYYY-MM-DD': {fraction, full_day, session_indexes, leave_type}})
    leave_by_date: Optional[Dict[str, dict]] = None
    # Per-date effective sessions with schedule exceptions applied
    # ({'YYYY-MM-DD': {sessions, is_active_day, source, exception_reason}})
    day_sessions: Optional[Dict[str, dict]] = None
    summary: AttendanceSummary


class AdminUserReportSummary(BaseModel):
    user_id: int
    user_name: str
    department: str
    branch: str
    total_work_hours: float
    present_days: float
    absent_days: float
    late_days: int
    late_hours: float = 0.0
    early_leave_days: int
    early_leave_hours: float = 0.0
    # Leave already reached in the period — excluded from absence/rate math.
    leave_days: float = 0.0
    # All approved leave in the selected period, including upcoming dates.
    approved_leave_days: float = 0.0
    attendance_rate: float
    total_days: float
    avatar: Optional[str] = None
    gender: Optional[str] = None


class AdminGlobalReportResponse(BaseModel):
    start_date: date
    end_date: date
    total_users: int
    overall_attendance_rate: float
    users: List[AdminUserReportSummary]


class MonthlyTrend(BaseModel):
    month: str  # Format: "YYYY-MM" or "Month"
    attendance_rate: float

class AdminTrendReportResponse(BaseModel):
    start_date: date
    end_date: date
    trends: List[MonthlyTrend]


class DailySessionDetails(BaseModel):
    session_index: int
    expected_start: Optional[str] = None
    expected_end: Optional[str] = None
    schedule_id: Optional[int] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    snapshot_late_grace_minutes: Optional[int] = None
    snapshot_allow_early_leave_mins: Optional[int] = None
    actual_check_in: Optional[datetime] = None
    actual_check_out: Optional[datetime] = None
    status: str  # "on_time", "late", "early_leave", "missing_in", "missing_out", "missing_both", "on_leave"
    # True when the check-out landed after scheduled_end + the configured
    # late-clock-out allowance. Late check-outs are always accepted so a
    # forgotten session can still be closed, so this classifies the row for
    # the report rather than indicating a rejected action. `status` describes
    # the check-in side and cannot carry this at the same time.
    is_late_check_out: bool = False
    work_hours: float = 0.0
    late_reason: Optional[str] = None
    leave_early_reason: Optional[str] = None
    notes: Optional[str] = None

class DailyAttendanceBreakdown(BaseModel):
    date: date
    day_type: str  # e.g., "Full Day", "Half Day", "Non-Working Day"
    expected_sessions_count: int
    sessions: List[DailySessionDetails]
    daily_status: str # "present", "absent", "incomplete", "on_leave"
    total_work_hours: float = 0.0
    # Fraction of the day covered by approved leave (0..1); label of leave type.
    leave_fraction: float = 0.0
    leave_type_name: Optional[str] = None

class AdminUserDetailedReportResponse(BaseModel):
    user_id: int
    user_name: str
    department: str
    branch: str
    start_date: date
    end_date: date
    total_expected_days: float
    total_present_days: float
    total_absent_days: float
    total_leave_days: float = 0.0
    days_breakdown: List[DailyAttendanceBreakdown]


class SalaryHistoryResponse(BaseModel):
    id: int
    base_salary: float
    effective_date: date
    end_date: Optional[date] = None
    is_active: bool
    reason: Optional[str] = None


class SalaryDeductionResponse(BaseModel):
    id: int
    type: DeductionType
    amount: float
    description: str
    is_active: bool
    effective_date: date
    end_date: Optional[date] = None


class SalaryBonusResponse(BaseModel):
    id: int
    type: BonusType
    amount: float
    description: str
    is_active: bool
    effective_date: date
    end_date: Optional[date] = None


# Request Models for Admin/Manager operations



class CreateWorkLocationRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    radius_meters: float = 100.0
    branch_id: Optional[int] = None





class CreateSalaryHistoryRequest(BaseModel):
    user_id: int
    base_salary: float = Field(..., gt=0)
    effective_date: date
    end_date: Optional[date] = None
    reason: Optional[str] = None


class CreateSalaryDeductionRequest(BaseModel):
    user_id: int
    type: DeductionType
    amount: float = Field(..., gt=0)
    description: str
    effective_date: date
    end_date: Optional[date] = None


class CreateSalaryBonusRequest(BaseModel):
    user_id: int
    type: BonusType
    amount: float = Field(..., gt=0)
    description: str
    effective_date: date
    end_date: Optional[date] = None


class SystemSettingsResponse(BaseModel):
    id: int
    require_location: bool
    block_mock_location: bool
    block_developer_options: bool
    allowed_ip_ranges: Optional[str] = None
    allow_early_clock_in_mins: int = 30  # 0..240 minutes (never unlimited)
    # Optional [session1_mins, session2_mins, ...]; null = use allow_early_clock_in_mins for all.
    per_session_early_clock_in_mins: Optional[List[int]] = None
    allow_late_clock_out_mins: Optional[int] = None
    min_minutes_before_checkout: int = 30
    session_transition_wait_mins: int = 10
    allow_early_leave_mins: int = 0
    allow_makeup_missing_sessions: bool = False
    late_grace_minutes: int = 15
    notify_enable_before: bool = True
    notify_minutes_before: Optional[List[int]] = None
    notify_enable_after: bool = True
    notify_minutes_after: Optional[List[int]] = None
    notify_enable_before_checkout: bool = True
    notify_minutes_before_checkout: Optional[List[int]] = None
    notify_enable_after_checkout: bool = True
    notify_minutes_after_checkout: Optional[List[int]] = None
    updated_at: Optional[date] = None

class UpdateSystemSettingsRequest(BaseModel):
    require_location: Optional[bool] = None
    block_mock_location: Optional[bool] = None
    block_developer_options: Optional[bool] = None
    allowed_ip_ranges: Optional[str] = Field(None, max_length=500)
    allow_early_clock_in_mins: Optional[int] = Field(None, ge=0, le=240)
    per_session_early_clock_in_mins: Optional[List[int]] = None
    allow_late_clock_out_mins: Optional[int] = Field(None, ge=0, le=1440)
    min_minutes_before_checkout: Optional[int] = Field(None, ge=0, le=1440)
    session_transition_wait_mins: Optional[int] = Field(None, ge=0, le=60)
    allow_early_leave_mins: Optional[int] = Field(None, ge=0, le=1440)
    allow_makeup_missing_sessions: Optional[bool] = None
    late_grace_minutes: Optional[int] = Field(None, ge=0, le=240)
    notify_enable_before: Optional[bool] = None
    notify_minutes_before: Optional[List[int]] = None
    notify_enable_after: Optional[bool] = None
    notify_minutes_after: Optional[List[int]] = None
    notify_enable_before_checkout: Optional[bool] = None
    notify_minutes_before_checkout: Optional[List[int]] = None
    notify_enable_after_checkout: Optional[bool] = None
    notify_minutes_after_checkout: Optional[List[int]] = None

class UserScheduleInfo(BaseModel):
    user_id: int
    user_name: str
    avatar: Optional[str] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    is_active: bool
    has_schedule: bool
    schedule_name: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_source: Optional[str] = None # user, department, branch, global
    schedule_id: Optional[int] = None
    schedule_is_default: Optional[bool] = None
    schedule_effective_date: Optional[date] = None
    allowed_branches: Optional[List[int]] = []

class UserScheduleListResponse(BaseModel):
    users: List[UserScheduleInfo]
    total: int
    page: int
    limit: int
    total_pages: int


class CheckInSecurityEventItem(BaseModel):
    id: int
    created_at: datetime
    user_id: Optional[int] = None
    username: Optional[str] = None
    client_ip: Optional[str] = None
    event_type: str
    severity: str
    message: str
    detail_json: Optional[str] = None
    user_agent: Optional[str] = None


class CheckInSecurityEventListResponse(BaseModel):
    events: List[CheckInSecurityEventItem]
    can_delete: bool = False


class ClientSecurityEventReportItem(BaseModel):
    """Allow-listed device-side attendance block reported by the official app."""

    event_type: Literal[
        "mock_location",
        "poor_gps_accuracy",
        "location_required",
        "developer_options",
        "compromised_device",
        "debugger_attached",
        "vpn_active",
        "device_verification_unavailable",
        "invalid_ip",
    ]
    gps_accuracy_meters: Optional[float] = Field(None, ge=0, le=10000)


class ClientSecurityEventReportRequest(BaseModel):
    events: List[ClientSecurityEventReportItem] = Field(
        ...,
        min_length=1,
        max_length=10,
    )


class AttendanceProblemReportRequest(BaseModel):
    """Sanitized attendance problem submitted explicitly by an employee."""

    issue_code: Literal[
        "stale_gps",
        "device_time_incorrect",
        "poor_gps_accuracy",
        "missing_gps_evidence",
        "location_required",
        "mock_location",
        "outside_workplace",
        "unauthorized_branch",
        "unauthorized_network",
        "location_anomaly",
        "device_security",
        "developer_options",
        "compromised_device",
        "debugger_attached",
        "vpn_active",
        "schedule",
        "server_time",
        "server_error",
        "unknown",
    ]
    surface: Literal[
        "quick_attendance",
        "qr_scanner",
        "employee_attendance",
        "gps_recovery",
    ]
    technical_message: Optional[str] = Field(None, max_length=500)

class ManualAttendanceSession(BaseModel):
    session_index: Optional[int] = Field(None, ge=1, le=20)
    scheduled_start: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    scheduled_end: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    check_in_latitude: Optional[float] = Field(None, ge=-90, le=90)
    check_in_longitude: Optional[float] = Field(None, ge=-180, le=180)
    check_out_latitude: Optional[float] = Field(None, ge=-90, le=90)
    check_out_longitude: Optional[float] = Field(None, ge=-180, le=180)

class ManualAttendanceBulkRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    branch_id: int = Field(..., ge=1)
    attendance_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: Optional[str] = Field(None, max_length=1000)
    sessions: List[ManualAttendanceSession] = Field(..., min_length=1, max_length=20)


class ScheduleExceptionSession(BaseModel):
    start: str
    end: str


class ScheduleExceptionCreate(BaseModel):
    exception_date: date
    end_date: Optional[date] = None
    recurrence_type: str = Field(
        default="once",
        description="once, date_range, or monthly",
    )
    user_id: Optional[int] = None
    branch_id: Optional[int] = None
    department_id: Optional[int] = None
    is_foreigner: Optional[int] = Field(
        default=None,
        description="1 = Khmer staff only, 2 = Foreigner staff only, null = all",
    )
    exception_type: str = Field(
        default="sessions_override",
        description="sessions_override or day_off",
    )
    preset: Optional[str] = Field(
        default=None,
        description="morning_only, afternoon_only, full_day (optional shortcut)",
    )
    sessions: Optional[List[ScheduleExceptionSession]] = None
    reason: Optional[str] = None
    title_en: Optional[str] = Field(None, max_length=150)
    title_km: Optional[str] = Field(None, max_length=150)
    reason_en: Optional[str] = Field(None, max_length=500)
    reason_km: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    self_enrollment_enabled: bool = False
    allow_outside_workplace: bool = False


class ScheduleExceptionUpdate(BaseModel):
    exception_date: Optional[date] = None
    end_date: Optional[date] = None
    recurrence_type: Optional[str] = None
    user_id: Optional[int] = None
    branch_id: Optional[int] = None
    department_id: Optional[int] = None
    is_foreigner: Optional[int] = None
    exception_type: Optional[str] = None
    preset: Optional[str] = None
    sessions: Optional[List[ScheduleExceptionSession]] = None
    reason: Optional[str] = None
    title_en: Optional[str] = Field(None, max_length=150)
    title_km: Optional[str] = Field(None, max_length=150)
    reason_en: Optional[str] = Field(None, max_length=500)
    reason_km: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    self_enrollment_enabled: Optional[bool] = None
    allow_outside_workplace: Optional[bool] = None


class ScheduleExceptionItem(BaseModel):
    id: int
    exception_date: date
    end_date: Optional[date] = None
    recurrence_type: str = "once"
    user_id: Optional[int] = None
    branch_id: Optional[int] = None
    department_id: Optional[int] = None
    is_foreigner: Optional[int] = None
    exception_type: str
    sessions: Optional[List[Dict[str, str]]] = None
    reason: Optional[str] = None
    title_en: Optional[str] = None
    title_km: Optional[str] = None
    reason_en: Optional[str] = None
    reason_km: Optional[str] = None
    created_by: Optional[int] = None
    is_active: bool = True
    self_enrollment_enabled: bool = False
    allow_outside_workplace: bool = False
    enrollment_count: int = 0
    scope_label: Optional[str] = None
    user_name: Optional[str] = None
    branch_name: Optional[str] = None
    department_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScheduleExceptionListResponse(BaseModel):
    exceptions: List[ScheduleExceptionItem]
    total: int
