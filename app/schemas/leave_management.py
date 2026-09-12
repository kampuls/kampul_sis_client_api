"""
Leave Management Schemas — employee ask-leave/permission feature.

Requests support per-day scope: a full day or specific work sessions
(1-based indexes matching the user's effective schedule for that date).
Balances are per academic year via leave_type_allocations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveDayScope(str, Enum):
    FULL_DAY = "full_day"
    SESSIONS = "sessions"


class DecisionAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


# ── Monthly cap policy ──────────────────────────────────────────────────────

class LeaveMonthlyPolicyRecomputeOut(BaseModel):
    """Result of re-splitting stored leave after a monthly cap change.

    Returned by the recompute endpoint and attached to a leave-type update so
    the administrator immediately sees how much allowance moved.
    """

    leave_type_id: int
    leave_type_name: str
    academic_id: int
    academic_name: str
    cap_days: Optional[float] = None
    affected_users: int = 0
    changed_days: int = 0
    # Allowance handed back because over-cap days became paid again.
    restored_days: float = 0
    newly_unpaid_days: float = 0
    paid_days: float = 0
    unpaid_days: float = 0


# ── Leave types ──────────────────────────────────────────────────────────────

class LeaveTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    max_days_per_year: float = Field(0, ge=0)  # fallback when no allocation exists
    # Monthly cap. Leave beyond it in one calendar month is still granted but
    # costs no annual allowance and is reported as unpaid. None or 0 disables.
    max_days_per_month: Optional[float] = Field(None, ge=0, le=31)
    is_paid: bool = True
    requires_approval: bool = True
    requires_proof: bool = False
    display_order: Optional[int] = Field(None, ge=0)
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class LeaveTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    max_days_per_year: Optional[float] = Field(None, ge=0)
    # Send 0 to disable the monthly cap; omit the field to leave it unchanged.
    max_days_per_month: Optional[float] = Field(None, ge=0, le=31)
    is_paid: Optional[bool] = None
    requires_approval: Optional[bool] = None
    requires_proof: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = Field(None, ge=0)
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class LeaveTypeOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    max_days_per_year: float = 0
    # None means the monthly cap policy is off for this type.
    max_days_per_month: Optional[float] = None
    is_paid: bool = True
    requires_approval: bool = True
    requires_proof: bool = False
    is_active: bool = True
    display_order: int = 0
    color_hex: Optional[str] = None
    created_at: Optional[datetime] = None
    # Referenced by at least one leave request — cannot be deleted (only
    # deactivated or re-allocated).
    in_use: bool = False
    # Populated only when an update changed the monthly cap and therefore
    # re-split stored leave for the active academic year.
    monthly_policy_recompute: Optional[LeaveMonthlyPolicyRecomputeOut] = None

    class Config:
        from_attributes = True


# ── Per-academic-year allocations ────────────────────────────────────────────

class AllocationItem(BaseModel):
    leave_type_id: int
    allocated_days: float = Field(..., ge=0)


class AllocationsUpsert(BaseModel):
    academic_id: int
    items: List[AllocationItem]


class AllocationOut(BaseModel):
    leave_type_id: int
    leave_type_name: str
    academic_id: int
    # None = no allocation row yet for this academic year (falls back to
    # leave_type.max_days_per_year when balances are computed).
    allocated_days: Optional[float] = None
    is_type_active: bool = True


class AllocationsCloneRequest(BaseModel):
    source_academic_id: int
    target_academic_id: int
    overwrite: bool = False


class AcademicYearOut(BaseModel):
    id: int
    name: str
    is_active: bool = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None


# ── Approvers ────────────────────────────────────────────────────────────────

class ApproverCreate(BaseModel):
    user_id: int
    department_id: Optional[int] = None
    branch_id: Optional[int] = None
    can_approve_all: bool = False
    can_view_all_requests: bool = False
    max_days_can_approve: Optional[float] = Field(None, ge=0)
    can_create_for_staff: bool = False
    can_adjust_leave_balance: bool = False
    can_cancel_approved_leave: bool = False


class ApproverUpdate(BaseModel):
    department_id: Optional[int] = None
    branch_id: Optional[int] = None
    can_approve_all: Optional[bool] = None
    can_view_all_requests: Optional[bool] = None
    max_days_can_approve: Optional[float] = Field(None, ge=0)
    can_create_for_staff: Optional[bool] = None
    can_adjust_leave_balance: Optional[bool] = None
    can_cancel_approved_leave: Optional[bool] = None
    is_active: Optional[bool] = None


class ApproverOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    avatar: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    can_approve_all: bool = False
    can_view_all_requests: bool = False
    max_days_can_approve: Optional[float] = None
    can_create_for_staff: bool = False
    can_adjust_leave_balance: bool = False
    can_cancel_approved_leave: bool = False
    is_active: bool = True


# ── Balances ─────────────────────────────────────────────────────────────────

class LeaveBalanceOut(BaseModel):
    leave_type_id: int
    leave_type_name: str
    is_paid: bool = True
    requires_approval: bool = True
    display_order: int = 0
    color_hex: Optional[str] = None
    academic_id: int
    # Monthly cap configured on the leave type; None when the policy is off.
    monthly_cap_days: Optional[float] = None
    allocated_days: float
    # Allowance-charged part of approved leave. Days over the monthly cap are
    # excluded here and reported in unpaid_days instead.
    taken_days: float          # approved, paid portion only
    pending_days: float        # awaiting decision, paid portion only
    # Approved/pending days that exceeded the monthly cap. They were granted
    # but cost no allowance, so they never reduce remaining_days.
    unpaid_days: float = 0
    pending_unpaid_days: float = 0
    # Every approved day actually taken, paid or not (taken + unpaid).
    total_taken_days: float = 0
    policy_deduction_days: float = 0
    # Paid balance: allocated - paid taken - deductions. Salary-deducted days
    # never reduce it, so it stops at zero rather than going negative.
    remaining_days: float
    # Paid days a new request may still reserve (remaining - pending). Once
    # this reaches zero a leave type with a monthly cap keeps accepting
    # requests and marks every further day salary-deducted instead, so it is
    # not a hard limit on how much leave may be asked for.
    available_to_request_days: float


class AdminLeaveBalanceReportRequest(BaseModel):
    """Employees whose current academic-year balances should be exported."""

    user_ids: List[int] = Field(..., min_length=1, max_length=5000)
    academic_id: Optional[int] = None
    as_of_date: Optional[date] = None
    # When supplied, the report also returns approved leave and policy
    # deductions from this date through ``as_of_date``. Detailed attendance
    # exports use those changes to show the balance that applied on each row.
    history_start_date: Optional[date] = None


class LeaveBalanceTypeColumnOut(BaseModel):
    leave_type_id: int
    leave_type_name: str
    allocated_days: float
    monthly_cap_days: Optional[float] = None


class UserLeaveBalanceValueOut(BaseModel):
    leave_type_id: int
    taken_days: float          # paid portion only
    pending_days: float
    # Over-monthly-cap days. Granted, but charged to no allowance — reports
    # surface them as the unpaid column beside the balance columns.
    unpaid_days: float = 0
    pending_unpaid_days: float = 0
    policy_deduction_days: float = 0
    remaining_days: float


class LeaveBalanceDailyChangeOut(BaseModel):
    balance_date: date
    leave_type_id: int
    taken_days: float = 0
    # Unpaid days on this date. Reported separately so a client walking the
    # history backwards does not restore them to the remaining balance.
    unpaid_days: float = 0
    policy_deduction_days: float = 0


class AdminUserLeaveBalancesOut(BaseModel):
    user_id: int
    balances: List[UserLeaveBalanceValueOut]
    daily_changes: List[LeaveBalanceDailyChangeOut] = Field(default_factory=list)


class AdminLeaveBalanceReportOut(BaseModel):
    academic_id: int
    leave_types: List[LeaveBalanceTypeColumnOut]
    users: List[AdminUserLeaveBalancesOut]


class ManualLeaveBalanceRequest(BaseModel):
    """Balance context for employees selected in the manual-leave form."""

    user_ids: List[int] = Field(..., min_length=1, max_length=500)
    start_date: date
    end_date: date
    # Explicit allowance bucket selected by the approver. When omitted, older
    # clients retain the date-range/active-year behavior below.
    academic_id: Optional[int] = Field(None, gt=0)
    # Explicit administrator override: keep the selected leave dates, but
    # charge only the currently-active academic year's allowance.
    use_active_academic_year: bool = False


class ManualLeaveBalanceContextOut(AdminLeaveBalanceReportOut):
    academic_name: str
    academic_start: date
    academic_end: date
    uses_active_academic_override: bool = False


# ── Request preview (per-day working sessions for the form) ─────────────────

class LeavePreviewRequest(BaseModel):
    start_date: date
    end_date: date


class ManualLeavePreviewRequest(LeavePreviewRequest):
    """Preview one target employee's effective sessions for an approver."""

    user_id: int = Field(..., gt=0)


class PreviewSessionOut(BaseModel):
    index: int                 # 1-based, matches AttendanceRecord.session_index
    start: str                 # "HH:MM"
    end: str


class PreviewDayOut(BaseModel):
    leave_date: date
    is_working_day: bool
    holiday_name: Optional[str] = None
    day_type: Optional[str] = None
    sessions: List[PreviewSessionOut] = []
    # True when any part of the date already belongs to a pending/approved
    # request. Employee self-service does not allow a second request that day.
    already_requested: bool = False
    # 1-based sessions covered by pending/approved leave, retained so the UI
    # can explain which part of the blocked date was previously requested.
    requested_session_indexes: List[int] = []


class LeavePreviewResponse(BaseModel):
    days: List[PreviewDayOut]


# ── Create / list requests ───────────────────────────────────────────────────

class LeaveRequestDayIn(BaseModel):
    leave_date: date
    scope: LeaveDayScope = LeaveDayScope.FULL_DAY
    # Required when scope == sessions; 1-based indexes into that day's sessions.
    session_indexes: Optional[List[int]] = None


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    reason: str = Field(..., min_length=1)
    days: List[LeaveRequestDayIn] = Field(..., min_length=1)
    # Colleague proposed to cover the requester's work (optional).
    replacement_user_id: Optional[int] = None
    # Optional storage path returned by POST /requests/proof. Every leave type
    # accepts proof; it is required when the type has requires_proof enabled.
    proof_image_path: Optional[str] = None


class ManualLeaveCreate(BaseModel):
    """Approved leave entered by an authorized approver for staff."""

    user_ids: List[int] = Field(..., min_length=1, max_length=50)
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str = Field(..., min_length=1, max_length=1000)
    # Academic allowance bucket selected by the approver. The leave dates are
    # kept exactly as entered; only the balance/request academic_id changes.
    academic_id: Optional[int] = Field(None, gt=0)
    # Optional explicit per-day configuration. Older clients can omit this and
    # retain full-working-day range behavior.
    days: Optional[List[LeaveRequestDayIn]] = None
    # Optional storage path from POST /requests/proof. Every leave type accepts
    # proof; the API requires it when the type has requires_proof enabled.
    proof_image_path: Optional[str] = None
    # When true, selected dates remain unchanged while balance usage is stored
    # against the currently-active academic year only.
    use_active_academic_year: bool = False


class LeaveRequestDayOut(BaseModel):
    leave_date: date
    scope: LeaveDayScope
    session_indexes: Optional[List[int]] = None
    sessions_total: Optional[int] = None
    day_cost: float
    # Monthly-cap split of day_cost. paid_cost + unpaid_cost == day_cost, and a
    # day is fully paid whenever the leave type has no monthly cap.
    paid_cost: Optional[float] = None
    unpaid_cost: Optional[float] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None


class LeaveDecisionContactOut(BaseModel):
    """An active approver who can make the decision for this request."""

    user_id: int
    user_name: str
    phone: Optional[str] = None
    avatar: Optional[str] = None


class LeaveRequestOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_name_en: Optional[str] = None
    user_name_kh: Optional[str] = None
    user_phone: Optional[str] = None
    avatar: Optional[str] = None
    department_name: Optional[str] = None
    branch_name: Optional[str] = None
    user_branch_id: Optional[int] = None
    leave_type_id: int
    leave_type_name: str
    is_paid: bool = True
    academic_id: Optional[int] = None
    start_date: date
    end_date: date
    total_days: float
    # Monthly-cap split of total_days. unpaid_days > 0 means part of this
    # request exceeded the leave type's monthly limit.
    paid_days: float = 0
    unpaid_days: float = 0
    reason: Optional[str] = None
    status: LeaveStatus
    approver_id: Optional[int] = None
    approver_name: Optional[str] = None
    approval_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    cancelled_by: Optional[int] = None
    cancelled_by_name: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    creation_source: str = "employee"
    is_manual: bool = False
    replacement_user_id: Optional[int] = None
    replacement_user_name: Optional[str] = None
    replacement_avatar: Optional[str] = None
    replacement_note: Optional[str] = None
    # Uploaded proof image (leave types with requires_proof).
    proof_image_url: Optional[str] = None
    # Present in the approver inbox. False means details are view-only even
    # when the request is still pending.
    can_decide: Optional[bool] = None
    # Present when user is authorized to cancel or close this request.
    can_cancel: Optional[bool] = None
    can_cancel_reason: Optional[str] = None
    # Populated for pending, view-only reviewer rows so the viewer can contact
    # an active approver whose scope and day limit cover this request.
    decision_contacts: List[LeaveDecisionContactOut] = []
    # Reminder permission is independent of cooldown. Clients compare the
    # absolute availability timestamp with their current time.
    can_send_review_reminder: bool = False
    review_reminder_count: int = 0
    review_reminder_available_at: Optional[datetime] = None
    days: List[LeaveRequestDayOut] = []


class LeaveDecisionRequest(BaseModel):
    action: DecisionAction
    note: Optional[str] = None
    # Approver may change (or set) the covering colleague when deciding.
    # Pass 0 to clear the replacement; omit/null to keep the proposed one.
    replacement_user_id: Optional[int] = None
    replacement_note: Optional[str] = None


class ColleagueOut(BaseModel):
    """Lightweight user entry for the replacement picker."""
    id: int
    name: str
    avatar: Optional[str] = None
    department_name: Optional[str] = None
    branch_name: Optional[str] = None


class LeaveCancelRequest(BaseModel):
    reason: Optional[str] = None


class ApproverStatusOut(BaseModel):
    is_approver: bool = False
    can_approve_all: bool = False
    can_view_all_requests: bool = False
    can_create_for_staff: bool = False
    can_adjust_leave_balance: bool = False
    # All pending rows in the user's review scope, including read-only rows.
    pending_count: int = 0
    # Subset the current user can personally approve or reject.
    actionable_pending_count: int = 0


class LeaveReviewReminderOut(BaseModel):
    success: bool = True
    recipient_count: int
    reminder_count: int
    next_allowed_at: datetime


# ── Policy balance deductions ───────────────────────────────────────────────

class LeaveBalanceAdjustmentCreate(BaseModel):
    user_ids: List[int] = Field(..., min_length=1, max_length=50)
    leave_type_id: int = Field(..., gt=0)
    amount_days: float = Field(..., gt=0, le=365)
    reason: str = Field(..., min_length=3, max_length=1000)


class LeaveBalanceAdjustmentContextRequest(BaseModel):
    user_ids: List[int] = Field(..., min_length=1, max_length=50)


class LeaveBalanceAdjustmentVoid(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)


class LeaveBalanceAdjustmentOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    leave_type_id: int
    leave_type_name: str
    academic_id: int
    academic_name: str
    amount_days: float
    effective_date: date
    reason: str
    status: str
    created_by: int
    created_by_name: str
    created_at: datetime
    voided_by: Optional[int] = None
    voided_by_name: Optional[str] = None
    void_reason: Optional[str] = None
    voided_at: Optional[datetime] = None


class LeaveBalanceMonthUsageOut(BaseModel):
    """One calendar month of a balance, split by the monthly cap."""

    month: str                 # "YYYY-MM"
    cap_days: Optional[float] = None
    taken_days: float = 0      # paid portion charged to the allowance
    unpaid_days: float = 0     # granted but over the cap


class LeaveBalanceDetailOut(BaseModel):
    balance: LeaveBalanceOut
    requests: List[LeaveRequestOut] = Field(default_factory=list)
    adjustments: List[LeaveBalanceAdjustmentOut] = Field(default_factory=list)
    # Per-month breakdown so an employee can see why a day became unpaid.
    monthly_usage: List[LeaveBalanceMonthUsageOut] = Field(default_factory=list)


# ── Monthly cap policy ──────────────────────────────────────────────────────

class LeavePolicyPreviewRequest(BaseModel):
    """Ask the server to split a not-yet-submitted request by the cap."""

    leave_type_id: int
    days: List[LeaveRequestDayIn] = Field(..., min_length=1)
    # Set when re-checking an existing request so its own days are not counted
    # twice against the cap.
    exclude_request_id: Optional[int] = Field(None, gt=0)


class LeavePolicyMonthOut(BaseModel):
    month: str                 # "YYYY-MM"
    cap_days: Optional[float] = None
    # Pending/approved days this employee already holds in the month.
    already_used_days: float = 0
    requested_days: float = 0
    paid_days: float = 0
    unpaid_days: float = 0


class LeavePolicyPreviewOut(BaseModel):
    leave_type_id: int
    leave_type_name: str
    cap_days: Optional[float] = None
    total_days: float = 0
    paid_days: float = 0
    unpaid_days: float = 0
    # Allowance the paid portion is checked against at submit time.
    available_to_request_days: float = 0
    months: List[LeavePolicyMonthOut] = Field(default_factory=list)


