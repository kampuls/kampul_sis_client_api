"""
Leave Management API — employee ask-leave/permission feature.

Employees request leave per date, either full day or specific work sessions
(1-based indexes matching their effective attendance schedule). Allowed days
come from leave_type_allocations for the active academic year; balances are
computed dynamically from approved request days, so cancelling restores
balance automatically. First approver to act wins.
"""

import logging
import math
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import bindparam, case, func, or_, text
from sqlalchemy.orm import Session
from PIL import Image, UnidentifiedImageError

from ...auth.dependencies import get_current_active_employee
from ...core.database import get_db
from ...core.feature_lock_guard import require_feature_unlocked
from ...models import (
    Branch,
    Holiday,
    LeaveApprover,
    LeaveBalanceAdjustment,
    LeaveHistory,
    LeaveRequest,
    LeaveRequestDay,
    LeaveType,
    LeaveTypeAllocation,
    SystemSettings,
    User,
)
from ...schemas.leave_management import (
    AcademicYearOut,
    AdminLeaveBalanceReportOut,
    AdminLeaveBalanceReportRequest,
    AdminUserLeaveBalancesOut,
    AllocationOut,
    AllocationsCloneRequest,
    AllocationsUpsert,
    ApproverCreate,
    ApproverOut,
    ApproverStatusOut,
    ApproverUpdate,
    ColleagueOut,
    DecisionAction,
    LeaveBalanceOut,
    LeaveBalanceAdjustmentCreate,
    LeaveBalanceAdjustmentContextRequest,
    LeaveBalanceAdjustmentOut,
    LeaveBalanceAdjustmentVoid,
    LeaveBalanceDetailOut,
    LeaveBalanceDailyChangeOut,
    LeaveBalanceMonthUsageOut,
    LeaveBalanceTypeColumnOut,
    LeaveCancelRequest,
    LeaveDayScope,
    LeaveDecisionRequest,
    LeaveMonthlyPolicyRecomputeOut,
    LeavePolicyMonthOut,
    LeavePolicyPreviewOut,
    LeavePolicyPreviewRequest,
    LeavePreviewRequest,
    LeavePreviewResponse,
    LeaveReviewReminderOut,
    LeaveRequestCreate,
    LeaveRequestDayOut,
    LeaveRequestOut,
    LeaveTypeCreate,
    LeaveTypeOut,
    LeaveTypeUpdate,
    ManualLeaveCreate,
    ManualLeaveBalanceContextOut,
    ManualLeaveBalanceRequest,
    ManualLeavePreviewRequest,
    PreviewDayOut,
    PreviewSessionOut,
    UserLeaveBalanceValueOut,
)
from ...services import leave_monthly_policy
from ...services import leave_notification_service as leave_notify
from ...services.leave_approval_policy import (
    APPROVAL_DAY_EPSILON,
    approval_day_limit_allows,
)
from ...services.attendance_schedule_exception_service import (
    ensure_schedule_exceptions_table,
    get_effective_day_attendance,
)
from ...services.cache import RedisCache, redis_client
from ...services.storage_service import StorageService

logger = logging.getLogger(__name__)

router = APIRouter()

user_requests_cache = RedisCache(prefix="user_reqs", ttl_seconds=300)


def _invalidate_user_requests_cache(user_id: int):
    try:
        user_requests_cache.clear()
    except Exception as e:
        logger.warning(f"Cache invalidation failed: {e}")

CAMBODIA_TZ = timezone(timedelta(hours=7))

# Safety cap for preview / request span (up to 10 months).
MAX_RANGE_DAYS = 310


def _today_kh() -> date:
    return datetime.now(CAMBODIA_TZ).date()


def _my_request_date_window(
    start_date: Optional[str],
    end_date: Optional[str],
    all_dates: bool,
) -> Tuple[Optional[str], Optional[str]]:
    if all_dates or start_date or end_date:
        return start_date, end_date

    import calendar

    today = _today_kh()
    _, last_day = calendar.monthrange(today.year, today.month)
    return (
        today.replace(day=1).isoformat(),
        today.replace(day=last_day).isoformat(),
    )


def _cambodia_date_filter_utc_bounds(
    filter_start: Optional[date],
    filter_end: Optional[date],
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Convert inclusive Cambodia dates to UTC-naive timestamp boundaries."""
    start_utc = (
        datetime.combine(filter_start, datetime.min.time()) - timedelta(hours=7)
        if filter_start
        else None
    )
    end_exclusive_utc = (
        datetime.combine(
            filter_end + timedelta(days=1),
            datetime.min.time(),
        )
        - timedelta(hours=7)
        if filter_end
        else None
    )
    return start_utc, end_exclusive_utc


def _review_activity_timestamp(date_basis: str):
    """Timestamp column/expression used by leave activity filters."""
    if date_basis == "submitted":
        return LeaveRequest.created_at
    if date_basis == "decision":
        return case(
            (
                LeaveRequest.status == "cancelled",
                func.coalesce(
                    LeaveRequest.cancelled_at,
                    LeaveRequest.approval_date,
                    LeaveRequest.created_at,
                ),
            ),
            else_=func.coalesce(
                LeaveRequest.approval_date,
                LeaveRequest.created_at,
            ),
        )
    if date_basis == "activity":
        return case(
            (
                LeaveRequest.status == "pending",
                LeaveRequest.created_at,
            ),
            (
                LeaveRequest.status == "cancelled",
                func.coalesce(
                    LeaveRequest.cancelled_at,
                    LeaveRequest.approval_date,
                    LeaveRequest.created_at,
                ),
            ),
            else_=func.coalesce(
                LeaveRequest.approval_date,
                LeaveRequest.created_at,
            ),
        )
    return None


def _now_utc() -> datetime:
    return datetime.utcnow()


def _display_name(user: Optional[User]) -> str:
    if user is None:
        return "Unknown"
    for attr in ("eName", "kName", "username"):
        value = getattr(user, attr, None)
        if value:
            return str(value)
    return f"User #{getattr(user, 'id', '?')}"


def _user_name_variant(user: Optional[User], attribute: str) -> Optional[str]:
    if user is None:
        return None
    value = str(getattr(user, attribute, "") or "").strip()
    return value or None


def _employee_name_fields(user: Optional[User]) -> Dict[str, Optional[str]]:
    """Return each stored name separately so clients never infer or translate it."""
    def stored(attribute: str) -> Optional[str]:
        if user is None:
            return None
        raw = getattr(user, attribute, None)
        if raw is None:
            return None
        value = str(raw)
        return value if value.strip() else None

    return {
        "user_name": _display_name(user),
        "user_name_en": stored("eName"),
        "user_name_kh": stored("kName"),
    }


def _is_admin(user: User) -> bool:
    # role=1 is Admin. role=2 is Teacher (regular staff — see teachers.py /
    # user_resource.py), so it must NOT bypass the LeaveApprover assignment:
    # non-admins may only review/approve leave via an active approvers row.
    return getattr(user, "role_id", None) == 1


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _active_academic_id(db: Session) -> int:
    # Canonical rule: academic.status=1 first, then settings.academicid.
    from ...utils.academic_year import get_current_academic_id

    academic_id = get_current_academic_id(db)
    if academic_id:
        return int(academic_id)
    raise HTTPException(status_code=400, detail="No active academic year configured")


def _academic_id_for_range(db: Session, start: date, end: date) -> int:
    """Resolve the one academic year that owns an entire leave range.

    Manual leave may be entered for a past or future date. Charging every
    request to the currently-active year would make historical corrections
    consume the wrong allowance, so configured academic dates take priority.
    A range crossing two academic years is intentionally rejected because a
    single leave request cannot safely debit two separate allocations.
    """
    row = db.execute(
        text(
            """
            SELECT id, academic_name, academic_us_name,
                   academic_start, academic_end, status
            FROM academic
            WHERE academic_start IS NOT NULL
              AND academic_end IS NOT NULL
              AND academic_start <= :start_date
              AND academic_end >= :end_date
            ORDER BY CASE WHEN status = 1 THEN 0 ELSE 1 END,
                     academic_start DESC,
                     id DESC
            LIMIT 1
            """
        ),
        {"start_date": start, "end_date": end},
    ).first()
    if row is not None:
        return int(row[0])

    configured = db.execute(
        text(
            """
            SELECT id, academic_name, academic_us_name,
                   academic_start, academic_end, status
            FROM academic
            WHERE academic_start IS NOT NULL
              AND academic_end IS NOT NULL
            ORDER BY CASE WHEN status = 1 THEN 0 ELSE 1 END,
                     academic_start DESC,
                     id DESC
            """
        )
    ).all()
    if configured:
        def year_date(value) -> date:
            return value.date() if isinstance(value, datetime) else value

        def owns(year, selected_date: date) -> bool:
            return year_date(year[3]) <= selected_date <= year_date(year[4])

        def label(year) -> str:
            return str(year[2] or year[1] or f"Academic year #{year[0]}").strip()

        def formatted(selected_date) -> str:
            return year_date(selected_date).strftime("%d %b %Y")

        start_owner = next((year for year in configured if owns(year, start)), None)
        end_owner = next((year for year in configured if owns(year, end)), None)
        if (
            start_owner is not None
            and end_owner is not None
            and int(start_owner[0]) != int(end_owner[0])
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Your selected dates ({formatted(start)} to {formatted(end)}) cross "
                    f"two academic years. {label(start_owner)} runs from "
                    f"{formatted(start_owner[3])} to {formatted(start_owner[4])}, while "
                    f"{label(end_owner)} runs from {formatted(end_owner[3])} to "
                    f"{formatted(end_owner[4])}. Split the leave into separate records."
                ),
            )

        reference = (
            start_owner
            or end_owner
            or next((year for year in configured if int(year[5] or 0) == 1), None)
            or configured[0]
        )
        year_kind = (
            "active academic year"
            if int(reference[5] or 0) == 1
            else "closest configured academic year"
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"The {year_kind}, {label(reference)}, runs from "
                f"{formatted(reference[3])} to {formatted(reference[4])}. "
                f"Your selected dates ({formatted(start)} to {formatted(end)}) are outside "
                "that range, so leave cannot be processed. Ask an administrator to "
                "configure the correct academic year."
            ),
        )
    raise HTTPException(
        status_code=400,
        detail=(
            "No academic year has valid start and end dates, so leave cannot be "
            "processed. Ask an administrator to configure the academic year first."
        ),
    )


def _manual_leave_academic_id(
    db: Session,
    start: date,
    end: date,
    use_active_academic_year: bool,
    selected_academic_id: Optional[int] = None,
) -> int:
    """Resolve the allowance bucket for an authorized manual leave.

    An explicit academic year is authoritative and never changes the leave
    dates. The legacy boolean remains supported for older clients, while new
    clients can choose any configured academic allowance bucket directly.
    """
    if selected_academic_id is not None:
        academic_id = int(selected_academic_id)
        _academic_details(db, academic_id)
        return academic_id
    if use_active_academic_year:
        academic_id = _active_academic_id(db)
        # Require a real configured range so the audit/UI can identify exactly
        # which active allowance was intentionally used.
        _academic_details(db, academic_id)
        return academic_id
    return _academic_id_for_range(db, start, end)


def _academic_details(db: Session, academic_id: int):
    row = db.execute(
        text(
            """
            SELECT id, academic_name, academic_us_name,
                   academic_start, academic_end, status
            FROM academic
            WHERE id = :academic_id
            LIMIT 1
            """
        ),
        {"academic_id": academic_id},
    ).first()
    if row is None or row[3] is None or row[4] is None:
        raise HTTPException(
            status_code=400,
            detail="The selected academic year has no valid start and end dates. Ask an administrator to update it.",
        )
    return row


def _user_employment_boundary(user: User, field: str) -> Optional[date]:
    """Parse legacy users.startWork/endWork values used by attendance reports."""
    raw = getattr(user, field, None)
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    value = str(raw or "").strip().split(" ")[0].split("T")[0]
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _approver_row(db: Session, user_id: int) -> Optional[LeaveApprover]:
    return (
        db.query(LeaveApprover)
        .filter(LeaveApprover.user_id == user_id, LeaveApprover.is_active == True)  # noqa: E712
        .first()
    )


def _approver_scope_matches(approver: LeaveApprover, requester: User) -> bool:
    if bool(approver.can_approve_all):
        return True
    # Empty scope must never silently mean school-wide authority. It is a
    # valid read-only configuration when can_view_all_requests is enabled,
    # but it grants no decision/manual-entry/balance-adjustment authority.
    if approver.department_id is None and approver.branch_id is None:
        return False
    if approver.department_id is not None and getattr(requester, "departmentId", None) != approver.department_id:
        return False
    if approver.branch_id is not None and getattr(requester, "workplace", None) != approver.branch_id:
        return False
    return True


def _approver_has_decision_scope(approver: LeaveApprover) -> bool:
    return bool(
        approver.can_approve_all
        or approver.department_id is not None
        or approver.branch_id is not None
    )


def _request_actionability(
    request: LeaveRequest,
    current_user: User,
    requester: Optional[User],
    approver: Optional[LeaveApprover],
) -> Dict[str, object]:
    """Return request-specific view/decision/cancellation rights for app deep links."""
    is_own = int(request.user_id) == int(current_user.id)
    replacement_user_id = getattr(request, "replacement_user_id", None)
    is_replacement = (
        replacement_user_id is not None
        and int(replacement_user_id) == int(current_user.id)
    )
    approver_in_scope = bool(
        approver is not None
        and requester is not None
        and _approver_scope_matches(approver, requester)
    )
    approver_can_view_all = bool(
        approver is not None
        and getattr(approver, "can_view_all_requests", False)
    )
    is_admin = _is_admin(current_user)
    is_manual = str(getattr(request, "creation_source", None) or "employee") == "manual"
    is_approver_who_approved = bool(
        getattr(request, "approver_id", None) is not None
        and int(request.approver_id) == int(current_user.id)
    )

    can_view = bool(
        is_own
        or is_replacement
        or is_admin
        or approver_in_scope
        or approver_can_view_all
        or is_approver_who_approved
    )

    # ── Decision capability ───────────────────────────────────────────────────
    can_decide = False
    decide_reason = None

    if not can_view:
        decide_reason = "You do not have permission to view this leave request"
    elif str(request.status) != "pending":
        decide_reason = f"This leave request is already {request.status}"
    elif is_own:
        decide_reason = "You cannot approve your own leave request"
    elif not approver_in_scope:
        decide_reason = "Only assigned leave approvers can decide this request"
    elif not approval_day_limit_allows(
        getattr(approver, "max_days_can_approve", None)
        if isinstance(getattr(approver, "max_days_can_approve", None), (int, float))
        else None,
        getattr(request, "total_days", 0.0),
    ):
        max_limit = getattr(approver, "max_days_can_approve", 0) if approver else 0
        if not isinstance(max_limit, (int, float)):
            max_limit = 0.0
        decide_reason = (
            f"This request ({float(getattr(request, 'total_days', 0.0) or 0):g} days) exceeds "
            f"your approval limit of "
            f"{float(max_limit):g} days"
        )
    else:
        can_decide = True

    # ── Cancellation capability ───────────────────────────────────────────────
    can_cancel = False
    can_cancel_reason = None
    status_str = str(request.status)

    if status_str == "cancelled":
        can_cancel_reason = "Request is already cancelled"
    elif status_str == "rejected":
        can_cancel_reason = "Rejected requests cannot be cancelled"
    elif status_str == "pending":
        request_start_date = getattr(request, "start_date", None)
        if isinstance(request_start_date, datetime):
            request_start_date = request_start_date.date()

        # Once any part of a pending request belongs to a past Cambodia
        # calendar day, it must be reviewed rather than withdrawn. This keeps
        # historical attendance-related requests in the approval audit trail.
        if (
            isinstance(request_start_date, date)
            and request_start_date < _today_kh()
        ):
            can_cancel_reason = (
                "This pending leave request cannot be cancelled because its "
                "first leave date has already passed"
            )
        # Preserve the submitted-request workflow: the requester (or an
        # administrator) can withdraw it. A reviewer should approve/reject a
        # pending request rather than silently cancelling another user's row.
        elif is_admin or is_own:
            can_cancel = True
        elif is_manual:
            if (
                approver is not None
                and bool(getattr(approver, "can_create_for_staff", False))
                and approver_in_scope
            ):
                can_cancel = True
            else:
                can_cancel_reason = "Only an authorized leave recorder in scope can cancel manual leave"
        else:
            can_cancel_reason = "Not allowed to cancel this request"
    elif status_str == "approved":
        # Closing an approved request is always governed by the dedicated
        # permission. Admin role, original approval, manual-record permission,
        # and request ownership do not bypass this switch.
        if approver is None:
            can_cancel_reason = (
                "Requires an active approver assignment with 'Cancel / Close "
                "Approved Leave' permission"
            )
        elif not bool(getattr(approver, "can_cancel_approved_leave", False)):
            can_cancel_reason = (
                "Requires 'Cancel / Close Approved Leave' permission in your "
                "approver settings"
            )
        elif not approver_in_scope:
            # View-all is visibility only and must never expand cancellation
            # authority beyond the approver's configured branch/department.
            can_cancel_reason = "This approved leave is outside your approver scope"
        elif not approval_day_limit_allows(
            getattr(approver, "max_days_can_approve", None)
            if isinstance(
                getattr(approver, "max_days_can_approve", None), (int, float)
            )
            else None,
            getattr(request, "total_days", 0.0),
        ):
            can_cancel_reason = (
                "This approved leave exceeds your configured approval day limit"
            )
        else:
            can_cancel = True

    return {
        "can_view": can_view,
        "can_decide": can_decide,
        "reason": decide_reason,
        "can_cancel": can_cancel,
        "can_cancel_reason": can_cancel_reason,
    }


def _filter_to_approver_day_limit(query, approver: LeaveApprover):
    """Keep only requests this approver's configured day limit can decide."""
    limit = approver.max_days_can_approve
    if limit is None:
        return query
    return query.filter(
        func.coalesce(LeaveRequest.total_days, 0.0)
        <= float(limit) + APPROVAL_DAY_EPSILON
    )


def _filter_to_approver_visibility_scope(query, approver: LeaveApprover):
    """Apply organizational visibility without applying decision-day limits.

    View-all and school-wide approvers may inspect every request. Other active
    approvers may inspect every request in their configured branch/department,
    including requests above ``max_days_can_approve``. That limit is enforced
    only by actionability and the decision endpoint.
    """
    if bool(getattr(approver, "can_view_all_requests", False)) or bool(
        approver.can_approve_all
    ):
        return query
    if not _approver_has_decision_scope(approver):
        return query.filter(LeaveRequest.id < 0)
    if approver.department_id is not None:
        query = query.filter(User.departmentId == approver.department_id)
    if approver.branch_id is not None:
        query = query.filter(User.workplace == approver.branch_id)
    return query


def _decision_contacts_for_request(
    request: LeaveRequest,
    requester: Optional[User],
    approvers: List[LeaveApprover],
    users: Dict[int, User],
    avatars: Dict[int, str],
) -> List[Dict[str, object]]:
    """Return active people who can actually decide this pending request."""
    if requester is None or str(request.status) != "pending":
        return []

    contacts: List[Dict[str, object]] = []
    for approver in approvers:
        user_id = int(approver.user_id)
        user = users.get(user_id)
        if (
            user is None
            or int(getattr(user, "status", 0) or 0) != 1
            or user_id == int(request.user_id)
            or not _approver_scope_matches(approver, requester)
            or not approval_day_limit_allows(
                approver.max_days_can_approve,
                request.total_days,
            )
        ):
            continue
        contacts.append(
            {
                "user_id": user_id,
                "user_name": _display_name(user),
                "phone": str(getattr(user, "phone", "") or "").strip() or None,
                "avatar": avatars.get(user_id),
            }
        )

    contacts.sort(key=lambda item: str(item["user_name"]).casefold())
    return contacts


FIRST_REVIEW_REMINDER_COOLDOWN = timedelta(minutes=15)
REPEAT_REVIEW_REMINDER_COOLDOWN = timedelta(hours=1)


def _review_reminder_available_at(
    request: LeaveRequest,
) -> Optional[datetime]:
    """Absolute UTC time when another manual reminder may be sent."""
    count = int(getattr(request, "review_reminder_count", 0) or 0)
    last_sent = getattr(request, "last_review_reminder_at", None)
    if count <= 0 or last_sent is None:
        return None
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    else:
        last_sent = last_sent.astimezone(timezone.utc)
    cooldown = (
        FIRST_REVIEW_REMINDER_COOLDOWN
        if count == 1
        else REPEAT_REVIEW_REMINDER_COOLDOWN
    )
    return last_sent + cooldown


def _review_reminder_retry_after_seconds(
    request: LeaveRequest,
    *,
    now: Optional[datetime] = None,
) -> int:
    available_at = _review_reminder_available_at(request)
    if available_at is None:
        return 0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    remaining = (available_at - current.astimezone(timezone.utc)).total_seconds()
    return max(0, math.ceil(remaining))


def _can_send_review_reminder(
    request: LeaveRequest,
    current_user: User,
    approver: Optional[LeaveApprover],
    actionability: Dict[str, object],
) -> bool:
    """Allow the requester or any read-only leave reviewer to follow up."""
    is_requester = int(request.user_id) == int(current_user.id)
    is_read_only_reviewer = bool(
        approver is not None
        and not is_requester
        and actionability.get("can_view")
        and not actionability.get("can_decide")
    )
    return bool(
        str(request.status) == "pending"
        and actionability.get("can_view")
        and not actionability.get("can_decide")
        and (is_requester or is_read_only_reviewer)
    )


def _can_view_decision_contacts(
    request: LeaveRequest,
    current_user: User,
    approver: Optional[LeaveApprover],
    actionability: Dict[str, object],
) -> bool:
    """Approver identities stay private from the employee who requested leave."""
    return bool(
        str(request.status) == "pending"
        and approver is not None
        and int(request.user_id) != int(current_user.id)
        and actionability.get("can_view")
        and not actionability.get("can_decide")
    )


def _review_reminder_metadata(
    request: LeaveRequest,
    current_user: User,
    approver: Optional[LeaveApprover],
    actionability: Dict[str, object],
) -> Dict[str, object]:
    return {
        "can_send_review_reminder": _can_send_review_reminder(
            request,
            current_user,
            approver,
            actionability,
        ),
        "review_reminder_count": int(
            getattr(request, "review_reminder_count", 0) or 0
        ),
        "review_reminder_available_at": _review_reminder_available_at(request),
    }


def _manual_leave_approver(db: Session, user: User) -> LeaveApprover:
    approver = _approver_row(db, int(user.id))
    if approver is None or not bool(getattr(approver, "can_create_for_staff", False)):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to create leave for staff",
        )
    return approver


def _balance_adjustment_approver(db: Session, user: User) -> LeaveApprover:
    approver = _approver_row(db, int(user.id))
    if approver is None or not bool(
        getattr(approver, "can_adjust_leave_balance", False)
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to deduct staff leave balances",
        )
    return approver


def _allocated_days(db: Session, leave_type: LeaveType, academic_id: int) -> float:
    alloc = (
        db.query(LeaveTypeAllocation)
        .filter(
            LeaveTypeAllocation.leave_type_id == leave_type.id,
            LeaveTypeAllocation.academic_id == academic_id,
        )
        .first()
    )
    if alloc is not None and alloc.is_active is not False:
        return float(alloc.allocated_days or 0)
    # No allocation configured for this academic year → fall back to the
    # type-level default so the feature works before allocations are set up.
    return float(leave_type.max_days_per_year or 0)


# Allowance-charged part of a leave day. Rows written before the monthly-cap
# migration have no split yet and are read as fully paid.
_PAID_COST = func.coalesce(LeaveRequestDay.paid_cost, LeaveRequestDay.day_cost)
# Granted-but-over-the-monthly-cap part. It never touches the balance.
_UNPAID_COST = func.coalesce(LeaveRequestDay.unpaid_cost, 0.0)


def _sum_day_costs(
    db: Session,
    user_id: int,
    leave_type_id: int,
    academic_id: int,
    statuses: List[str],
    column=None,
) -> float:
    """Sum leave day costs. Defaults to the balance-charged (paid) portion.

    Pass ``LeaveRequestDay.day_cost`` for the total days actually taken, or
    ``_UNPAID_COST`` for the over-cap portion.
    """
    total = (
        db.query(func.coalesce(func.sum(column if column is not None else _PAID_COST), 0.0))
        .join(LeaveRequest, LeaveRequestDay.leave_request_id == LeaveRequest.id)
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type_id == leave_type_id,
            LeaveRequest.academic_id == academic_id,
            LeaveRequest.status.in_(statuses),
        )
        .scalar()
    )
    return float(total or 0)


def _sum_policy_deductions(
    db: Session,
    user_id: int,
    leave_type_id: int,
    academic_id: int,
    as_of_date: Optional[date] = None,
) -> float:
    query = db.query(
        func.coalesce(func.sum(LeaveBalanceAdjustment.amount_days), 0.0)
    ).filter(
        LeaveBalanceAdjustment.user_id == user_id,
        LeaveBalanceAdjustment.leave_type_id == leave_type_id,
        LeaveBalanceAdjustment.academic_id == academic_id,
        LeaveBalanceAdjustment.status == "active",
    )
    if as_of_date is not None:
        query = query.filter(LeaveBalanceAdjustment.effective_date <= as_of_date)
    return float(query.scalar() or 0)


def _leave_balance_value(
    db: Session,
    user_id: int,
    leave_type: LeaveType,
    academic_id: int,
) -> LeaveBalanceOut:
    """One authoritative balance calculation used by every adjustment flow.

    Only the paid portion of leave reduces the allowance. Days that exceeded
    the leave type's monthly cap were still granted, so they are reported
    separately as unpaid instead of being charged here.
    """
    allocated = _allocated_days(db, leave_type, academic_id)
    taken = _sum_day_costs(
        db, user_id, int(leave_type.id), academic_id, ["approved"]
    )
    pending = _sum_day_costs(
        db, user_id, int(leave_type.id), academic_id, ["pending"]
    )
    unpaid = _sum_day_costs(
        db, user_id, int(leave_type.id), academic_id, ["approved"],
        column=_UNPAID_COST,
    )
    pending_unpaid = _sum_day_costs(
        db, user_id, int(leave_type.id), academic_id, ["pending"],
        column=_UNPAID_COST,
    )
    deductions = _sum_policy_deductions(
        db, user_id, int(leave_type.id), academic_id
    )
    remaining = max(0.0, allocated - taken - deductions)
    # Only paid days are reserved. When the allowance runs out this reaches
    # zero and stays there — a leave type with a monthly cap keeps accepting
    # requests, marking every further day salary-deducted instead.
    available_to_request = max(0.0, remaining - pending)
    return LeaveBalanceOut(
        leave_type_id=int(leave_type.id),
        leave_type_name=str(leave_type.name),
        is_paid=leave_type.is_paid is not False,
        requires_approval=leave_type.requires_approval is not False,
        display_order=int(leave_type.display_order or 0),
        color_hex=(
            str(leave_type.color_hex).upper() if leave_type.color_hex else None
        ),
        academic_id=academic_id,
        monthly_cap_days=leave_monthly_policy.effective_cap(leave_type),
        allocated_days=round(allocated, 2),
        taken_days=round(taken, 2),
        pending_days=round(pending, 2),
        unpaid_days=round(unpaid, 2),
        pending_unpaid_days=round(pending_unpaid, 2),
        total_taken_days=round(taken + unpaid, 2),
        policy_deduction_days=round(deductions, 2),
        remaining_days=round(remaining, 2),
        available_to_request_days=round(available_to_request, 2),
    )


def _serialize_balance_adjustment(
    db: Session,
    adjustment: LeaveBalanceAdjustment,
) -> LeaveBalanceAdjustmentOut:
    target = db.query(User).filter(User.id == adjustment.user_id).first()
    leave_type = (
        db.query(LeaveType).filter(LeaveType.id == adjustment.leave_type_id).first()
    )
    creator = db.query(User).filter(User.id == adjustment.created_by).first()
    voider = (
        db.query(User).filter(User.id == adjustment.voided_by).first()
        if adjustment.voided_by
        else None
    )
    academic = _academic_details(db, int(adjustment.academic_id))
    return LeaveBalanceAdjustmentOut(
        id=int(adjustment.id),
        user_id=int(adjustment.user_id),
        user_name=_display_name(target),
        leave_type_id=int(adjustment.leave_type_id),
        leave_type_name=(str(leave_type.name) if leave_type else "Leave"),
        academic_id=int(adjustment.academic_id),
        academic_name=str(
            academic[2] or academic[1] or f"Academic year #{adjustment.academic_id}"
        ),
        amount_days=round(float(adjustment.amount_days or 0), 2),
        effective_date=adjustment.effective_date,
        reason=str(adjustment.reason or ""),
        status=str(adjustment.status or "active"),
        created_by=int(adjustment.created_by),
        created_by_name=_display_name(creator),
        created_at=adjustment.created_at,
        voided_by=(int(adjustment.voided_by) if adjustment.voided_by else None),
        voided_by_name=(_display_name(voider) if voider else None),
        void_reason=adjustment.void_reason,
        voided_at=adjustment.voided_at,
    )


def _holidays_in_range(db: Session, start: date, end: date) -> Dict[date, str]:
    rows = db.query(Holiday).filter(Holiday.date >= start, Holiday.date <= end).all()
    return {row.date: str(row.name) for row in rows}


def _existing_leave_days(
    db: Session,
    user_id: int,
    start: date,
    end: date,
    exclude_request_id: Optional[int] = None,
) -> Dict[date, List[LeaveRequestDay]]:
    """Pending/approved leave days of the user inside the range, keyed by date."""
    query = (
        db.query(LeaveRequestDay)
        .join(LeaveRequest, LeaveRequestDay.leave_request_id == LeaveRequest.id)
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequestDay.leave_date >= start,
            LeaveRequestDay.leave_date <= end,
        )
    )
    if exclude_request_id is not None:
        query = query.filter(LeaveRequest.id != exclude_request_id)
    result: Dict[date, List[LeaveRequestDay]] = {}
    for row in query.all():
        result.setdefault(row.leave_date, []).append(row)
    return result


def _leave_date_conflict_detail(
    conflict_dates: List[date],
    *,
    employee_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a stable, app-readable error for overlapping leave dates."""
    normalized_dates = sorted(set(conflict_dates))
    formatted_dates = ", ".join(
        value.strftime("%d/%m/%Y") for value in normalized_dates
    )
    subject = f"{employee_name} already has" if employee_name else "Leave already exists for"
    if employee_name:
        message = f"{subject} pending or approved leave on {formatted_dates}"
    else:
        message = f"{subject} {formatted_dates}. Remove the conflicting date and try again."
    return {
        "code": "leave_date_conflict",
        "message": message,
        "conflict_dates": [value.isoformat() for value in normalized_dates],
    }


def _covered_session_indexes(
    existing_days: List[LeaveRequestDay], sessions_total: int
) -> Tuple[Set[int], bool]:
    """Sessions of a date already covered by pending/approved leave.

    Returns (covered 1-based indexes, fully_covered). Coverage is still exposed
    for clear UI details, although any existing coverage now blocks the date.
    """
    covered: Set[int] = set()
    full_day = False
    for row in existing_days:
        if row.scope == "full_day":
            full_day = True
        else:
            covered |= {int(i) for i in (row.session_indexes or [])}
    if full_day:
        all_sessions = set(range(1, sessions_total + 1)) if sessions_total > 0 else covered
        return all_sessions or covered, True
    fully = sessions_total > 0 and all(
        i in covered for i in range(1, sessions_total + 1)
    )
    return covered, fully


# Optional proof attachments for leave requests. Types with requires_proof
# enabled enforce that at least one validated attachment is supplied.
PROOF_FOLDER = "leave_proofs"
PROOF_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
PROOF_ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
PROOF_FORMAT_CONTENT_TYPES = {
    "JPEG": {"image/jpeg", "image/jpg"},
    "PNG": {"image/png"},
    "WEBP": {"image/webp"},
}
PROOF_MAX_PIXELS = 25_000_000


def _validate_proof_path(path: str, user_id: int) -> str:
    """Proof paths must come from POST /requests/proof and belong to the user."""
    paths = [p.strip() for p in (path or "").split(",") if p.strip()]
    validated = []
    for p in paths:
        marker = f"{PROOF_FOLDER}/u{user_id}_"
        if not p or ".." in p or marker not in p:
            raise HTTPException(status_code=400, detail=f"Invalid proof image: {p}")
        validated.append(p)
    return ",".join(validated)


def _validated_proof_path_for_type(
    path: Optional[str],
    user_id: int,
    leave_type: LeaveType,
) -> Optional[str]:
    """Validate optional proof and enforce types that require an attachment."""
    proof_path = _validate_proof_path(path, user_id) if path else None
    if bool(leave_type.requires_proof) and not proof_path:
        raise HTTPException(
            status_code=400,
            detail=f"A proof image is required for {leave_type.name}",
        )
    return proof_path


def _delete_proof_file(path: Optional[str]) -> None:
    """Remove the proof image from storage (local/S3/Cloudinary/Firebase)."""
    if not path:
        return
    paths = [p.strip() for p in path.split(",") if p.strip()]
    for p in paths:
        try:
            if not StorageService.delete_file(p):
                logger.warning(f"Proof image not deleted from storage: {p}")
        except Exception as exc:
            logger.error(f"Failed to delete proof image {p}: {exc}")


def _delete_unreferenced_proof_files(db: Session, path: Optional[str]) -> None:
    """Delete cancelled-request proof only when no other request shares it."""
    candidates = {p.strip() for p in (path or "").split(",") if p.strip()}
    if not candidates:
        return
    try:
        rows = (
            db.query(LeaveRequest.proof_image_path)
            .filter(LeaveRequest.proof_image_path.isnot(None))
            .all()
        )
        referenced: Set[str] = set()
        for row in rows:
            value = row[0] if isinstance(row, (tuple, list)) else getattr(
                row,
                "proof_image_path",
                None,
            )
            referenced.update(
                part.strip() for part in str(value or "").split(",") if part.strip()
            )
    except Exception as exc:
        # A failed reference check must not risk breaking proof still used by
        # another request in a manually-created batch.
        logger.error(f"Failed to verify leave proof references: {exc}")
        return

    unreferenced = sorted(candidates - referenced)
    if unreferenced:
        _delete_proof_file(",".join(unreferenced))


def _validate_replacement(db: Session, replacement_id: int, requester_id: int) -> User:
    """Replacement must be an active user other than the requester."""
    if int(replacement_id) == int(requester_id):
        raise HTTPException(status_code=400, detail="Replacement cannot be the requester")
    user = (
        db.query(User)
        .filter(User.id == replacement_id, User.status == 1)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Replacement user not found or inactive")
    return user


# ── Serialization helpers ────────────────────────────────────────────────────


def _user_maps(db: Session, user_ids: List[int]) -> Tuple[Dict[int, User], Dict[int, str]]:
    """Batch-load users and their avatar URLs (users_resource pattern)."""
    users: Dict[int, User] = {}
    avatars: Dict[int, str] = {}
    ids = sorted({int(u) for u in user_ids if u})
    if not ids:
        return users, avatars
    for user in db.query(User).filter(User.id.in_(ids)).all():
        users[int(user.id)] = user
    try:
        stmt = text(
            """
            SELECT ur.user_id, ur.avatar
            FROM users_resource ur
            WHERE ur.user_id IN :uids
              AND ur.user_type IN ('employee', 'teacher')
              AND ur.avatar IS NOT NULL
              AND ur.avatar != ''
            ORDER BY ur.user_id, ur.id DESC
            """
        ).bindparams(bindparam("uids", expanding=True))
        for row in db.execute(stmt, {"uids": ids}).fetchall():
            uid = int(row[0])
            if uid not in avatars:
                avatars[uid] = str(row[1])
    except Exception:
        pass
    return users, avatars


def _current_workplace_id(user: User) -> Optional[int]:
    value = getattr(user, "workplace", None)
    try:
        branch_id = int(value)
    except (TypeError, ValueError):
        return None
    return branch_id if branch_id > 0 else None


def _name_maps(db: Session, users: Dict[int, User]) -> Tuple[Dict[int, str], Dict[int, str]]:
    dept_ids = {int(u.departmentId) for u in users.values() if getattr(u, "departmentId", None)}
    branch_ids = {int(u.workplace) for u in users.values() if getattr(u, "workplace", None)}
    dept_names = _department_name_map(db, dept_ids)
    branch_names: Dict[int, str] = {}
    if branch_ids:
        for b in db.query(Branch).filter(Branch.id.in_(branch_ids)).all():
            branch_names[int(b.id)] = str(b.branch_name)
    return dept_names, branch_names


def _department_name_map(db: Session, department_ids: Set[int]) -> Dict[int, str]:
    """Read the canonical legacy department table used by users.departmentId."""
    if not department_ids:
        return {}
    statement = text(
        """
        SELECT id, department, translate
        FROM department
        WHERE id IN :department_ids
        """
    ).bindparams(bindparam("department_ids", expanding=True))
    rows = db.execute(
        statement,
        {"department_ids": sorted(department_ids)},
    ).all()
    result: Dict[int, str] = {}
    for row in rows:
        stored_name = row[1] if row[1] is not None and str(row[1]).strip() else row[2]
        if stored_name is not None and str(stored_name).strip():
            result[int(row[0])] = str(stored_name)
    return result


def _serialize_requests(
    db: Session,
    requests: List[LeaveRequest],
    *,
    include_user_phone: bool = False,
    current_user: Optional[User] = None,
) -> List[LeaveRequestOut]:
    if not requests:
        return []
    type_ids = {int(r.leave_type_id) for r in requests}
    types = {
        int(t.id): t
        for t in db.query(LeaveType).filter(LeaveType.id.in_(type_ids)).all()
    }
    related_user_ids: List[int] = []
    for r in requests:
        related_user_ids.append(int(r.user_id))
        if r.approver_id:
            related_user_ids.append(int(r.approver_id))
        if r.cancelled_by:
            related_user_ids.append(int(r.cancelled_by))
        if getattr(r, "replacement_user_id", None):
            related_user_ids.append(int(r.replacement_user_id))
        if getattr(r, "created_by", None):
            related_user_ids.append(int(r.created_by))
    users, avatars = _user_maps(db, related_user_ids)
    dept_names, branch_names = _name_maps(db, users)
    approver = _approver_row(db, int(current_user.id)) if current_user else None

    out: List[LeaveRequestOut] = []
    for r in requests:
        requester = users.get(int(r.user_id))
        leave_type = types.get(int(r.leave_type_id))
        day_rows = sorted(r.days, key=lambda d: d.leave_date)

        can_decide = None
        can_cancel = None
        can_cancel_reason = None
        if current_user is not None:
            act = _request_actionability(r, current_user, requester, approver)
            can_decide = bool(act.get("can_decide"))
            can_cancel = bool(act.get("can_cancel"))
            can_cancel_reason = act.get("can_cancel_reason") if isinstance(act.get("can_cancel_reason"), str) else None

        out.append(
            LeaveRequestOut(
                id=int(r.id),
                user_id=int(r.user_id),
                user_name=_display_name(requester),
                user_name_en=_user_name_variant(requester, "eName"),
                user_name_kh=_user_name_variant(requester, "kName"),
                user_phone=(
                    str(getattr(requester, "phone", "") or "").strip() or None
                    if include_user_phone and requester
                    else None
                ),
                avatar=avatars.get(int(r.user_id)),
                department_name=dept_names.get(int(getattr(requester, "departmentId", 0) or 0)),
                branch_name=branch_names.get(int(getattr(requester, "workplace", 0) or 0)),
                user_branch_id=int(getattr(requester, "workplace", 0) or 0) if requester else None,
                leave_type_id=int(r.leave_type_id),
                leave_type_name=str(leave_type.name) if leave_type else f"Type #{r.leave_type_id}",
                is_paid=bool(leave_type.is_paid) if leave_type else True,
                academic_id=r.academic_id,
                start_date=r.start_date,
                end_date=r.end_date,
                total_days=float(r.total_days or 0),
                paid_days=round(
                    sum(leave_monthly_policy.paid_cost_of(d) for d in day_rows), 4
                ),
                unpaid_days=round(
                    sum(leave_monthly_policy.unpaid_cost_of(d) for d in day_rows), 4
                ),
                reason=r.reason,
                status=r.status,
                approver_id=r.approver_id,
                approver_name=_display_name(users.get(int(r.approver_id))) if r.approver_id else None,
                approval_date=r.approval_date,
                rejection_reason=r.rejection_reason,
                cancelled_by=r.cancelled_by,
                cancelled_by_name=_display_name(users.get(int(r.cancelled_by))) if r.cancelled_by else None,
                cancelled_at=r.cancelled_at,
                cancel_reason=r.cancel_reason,
                created_at=r.created_at,
                created_by=getattr(r, "created_by", None),
                created_by_name=(
                    _display_name(users.get(int(r.created_by)))
                    if getattr(r, "created_by", None)
                    else _display_name(requester)
                ),
                creation_source=str(getattr(r, "creation_source", None) or "employee"),
                is_manual=str(getattr(r, "creation_source", None) or "employee") == "manual",
                replacement_user_id=r.replacement_user_id,
                replacement_user_name=(
                    _display_name(users.get(int(r.replacement_user_id)))
                    if r.replacement_user_id
                    else None
                ),
                replacement_avatar=(
                    avatars.get(int(r.replacement_user_id)) if r.replacement_user_id else None
                ),
                proof_image_url=r.proof_image_path,
                replacement_note=r.replacement_note,
                can_decide=can_decide,
                can_cancel=can_cancel,
                can_cancel_reason=can_cancel_reason,
                days=[
                    LeaveRequestDayOut(
                        leave_date=d.leave_date,
                        scope=d.scope,
                        session_indexes=d.session_indexes,
                        sessions_total=d.sessions_total,
                        day_cost=float(d.day_cost or 0),
                        paid_cost=round(leave_monthly_policy.paid_cost_of(d), 4),
                        unpaid_cost=round(
                            leave_monthly_policy.unpaid_cost_of(d), 4
                        ),
                        time_from=d.time_from,
                        time_to=d.time_to,
                    )
                    for d in day_rows
                ],
            )
        )
    return out


def _add_history(
    db: Session,
    request_id: int,
    action: str,
    old_status: Optional[str],
    new_status: str,
    changed_by: int,
    notes: Optional[str] = None,
) -> None:
    db.add(
        LeaveHistory(
            leave_request_id=request_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            notes=notes,
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# Leave types (admin manages; employees may read active ones)
# ═══════════════════════════════════════════════════════════════════════════


def _leave_type_in_use(db: Session, leave_type_id: int) -> bool:
    """A leave type referenced by any request must never be deleted."""
    return (
        db.query(LeaveRequest.id)
        .filter(LeaveRequest.leave_type_id == leave_type_id)
        .first()
        is not None
    )


_DEFAULT_LEAVE_TYPE_COLORS = (
    "#1877F2",
    "#43A047",
    "#42A5F5",
    "#FFB300",
    "#E91E63",
)


def _leave_type_ordering():
    """Stable setup order, falling back to creation order for legacy rows."""
    return (
        func.coalesce(LeaveType.display_order, 2147483647).asc(),
        LeaveType.created_at.asc(),
        LeaveType.id.asc(),
    )


def _recompute_summary(
    db: Session,
    leave_type: LeaveType,
    academic_id: int,
    totals: Dict[str, float],
) -> LeaveMonthlyPolicyRecomputeOut:
    """Describe a monthly-cap recompute so the admin UI can report the effect."""
    academic = _academic_details(db, academic_id)
    return LeaveMonthlyPolicyRecomputeOut(
        leave_type_id=int(leave_type.id),
        leave_type_name=str(leave_type.name),
        academic_id=academic_id,
        academic_name=str(
            academic[2] or academic[1] or f"Academic year #{academic_id}"
        ),
        cap_days=leave_monthly_policy.effective_cap(leave_type),
        affected_users=int(totals.get("affected_users", 0)),
        changed_days=int(totals.get("changed_days", 0)),
        restored_days=round(float(totals.get("restored_days", 0)), 2),
        newly_unpaid_days=round(float(totals.get("newly_unpaid_days", 0)), 2),
        paid_days=round(float(totals.get("paid_days", 0)), 2),
        unpaid_days=round(float(totals.get("unpaid_days", 0)), 2),
    )


def _leave_type_out(t: LeaveType, in_use: bool = False) -> LeaveTypeOut:
    return LeaveTypeOut(
        id=int(t.id),
        name=str(t.name),
        description=t.description,
        max_days_per_year=float(t.max_days_per_year or 0),
        max_days_per_month=leave_monthly_policy.effective_cap(t),
        is_paid=t.is_paid is not False,
        requires_approval=t.requires_approval is not False,
        requires_proof=bool(t.requires_proof),
        is_active=t.is_active is not False,
        display_order=int(t.display_order or 0),
        color_hex=str(t.color_hex).upper() if t.color_hex else None,
        created_at=t.created_at,
        in_use=in_use,
    )


@router.get("/leave-types", response_model=List[LeaveTypeOut])
async def list_leave_types(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    query = db.query(LeaveType)
    if not (include_inactive and _is_admin(current_user)):
        query = query.filter(LeaveType.is_active.isnot(False))
    types = query.order_by(*_leave_type_ordering()).all()
    # Which types are referenced by requests (→ not deletable), in one query.
    used_ids = {
        int(row[0])
        for row in db.query(LeaveRequest.leave_type_id).distinct().all()
    }
    return [_leave_type_out(t, in_use=int(t.id) in used_ids) for t in types]


@router.post("/leave-types", response_model=LeaveTypeOut)
async def create_leave_type(
    payload: LeaveTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    existing = db.query(LeaveType).filter(LeaveType.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Leave type with this name already exists")
    max_order = db.query(func.max(LeaveType.display_order)).scalar()
    if max_order is None:
        existing_count = db.query(func.count(LeaveType.id)).scalar() or 0
        next_order = int(existing_count) + 1
    else:
        next_order = int(max_order) + 1
    leave_type = LeaveType(
        name=payload.name,
        description=payload.description,
        max_days_per_year=payload.max_days_per_year,
        # 0 and None both mean "no monthly cap"; store None so the disabled
        # state is unambiguous everywhere it is read.
        max_days_per_month=(
            payload.max_days_per_month
            if payload.max_days_per_month
            else None
        ),
        is_paid=payload.is_paid,
        requires_approval=payload.requires_approval,
        requires_proof=payload.requires_proof,
        display_order=payload.display_order
        if payload.display_order is not None
        else next_order,
        color_hex=(
            payload.color_hex.upper()
            if payload.color_hex
            else _DEFAULT_LEAVE_TYPE_COLORS[
                max(0, next_order - 1) % len(_DEFAULT_LEAVE_TYPE_COLORS)
            ]
        ),
        is_active=True,
    )
    db.add(leave_type)
    db.commit()
    db.refresh(leave_type)
    return _leave_type_out(leave_type)


@router.put("/leave-types/{leave_type_id}", response_model=LeaveTypeOut)
async def update_leave_type(
    leave_type_id: int,
    payload: LeaveTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")
    data = payload.dict(exclude_unset=True)
    if data.get("name"):
        duplicate = (
            db.query(LeaveType)
            .filter(LeaveType.name == data["name"], LeaveType.id != leave_type_id)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Leave type with this name already exists")

    previous_cap = leave_monthly_policy.effective_cap(leave_type)
    for key, value in data.items():
        if key == "color_hex" and value:
            value = value.upper()
        if key == "max_days_per_month":
            # 0 disables the policy; store it as NULL so "off" reads the same
            # way everywhere.
            value = value if value else None
        setattr(leave_type, key, value)

    # Changing the cap changes which stored days were over the limit, so the
    # split has to be rebuilt. Clearing the cap restores every day to paid,
    # returning the previously unpaid days to the employees' balances.
    recompute_out: Optional[LeaveMonthlyPolicyRecomputeOut] = None
    if "max_days_per_month" in data:
        new_cap = leave_monthly_policy.effective_cap(leave_type)
        if new_cap != previous_cap:
            academic_id = _active_academic_id(db)
            try:
                totals = leave_monthly_policy.recompute_leave_type(
                    db, leave_type, academic_id
                )
                recompute_out = _recompute_summary(
                    db, leave_type, academic_id, totals
                )
            except Exception:
                db.rollback()
                raise

    db.commit()
    db.refresh(leave_type)
    out = _leave_type_out(leave_type, in_use=_leave_type_in_use(db, int(leave_type.id)))
    out.monthly_policy_recompute = recompute_out
    return out


@router.delete("/leave-types/{leave_type_id}")
async def delete_leave_type(
    leave_type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Delete a leave type that has never been used.

    Types referenced by any leave request cannot be deleted (history must
    stay intact) — deactivate them or change their allocated days instead.
    """
    _require_admin(current_user)
    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")
    if _leave_type_in_use(db, leave_type_id):
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{leave_type.name}" has been used in leave requests and cannot be '
                "deleted. You can deactivate it or change its allocated days instead."
            ),
        )
    # Never used → remove cleanly, including per-year allocations.
    db.query(LeaveTypeAllocation).filter(
        LeaveTypeAllocation.leave_type_id == leave_type_id
    ).delete()
    db.delete(leave_type)
    db.commit()
    return {"success": True}


@router.post(
    "/admin/leave-types/{leave_type_id}/recompute-monthly-policy",
    response_model=LeaveMonthlyPolicyRecomputeOut,
)
async def recompute_monthly_policy(
    leave_type_id: int,
    academic_id: Optional[int] = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Re-apply the monthly cap to stored leave for one academic year.

    Saving a changed cap already recomputes the active year. This endpoint
    covers the other years, which are left alone by default so a cap change
    never silently rewrites a closed year's payroll basis.

    The operation is idempotent and reversible: day_cost is never touched, only
    the paid/unpaid split derived from it.
    """
    _require_admin(current_user)
    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")
    target_academic_id = academic_id or _active_academic_id(db)
    try:
        totals = leave_monthly_policy.recompute_leave_type(
            db, leave_type, target_academic_id
        )
        summary = _recompute_summary(db, leave_type, target_academic_id, totals)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Academic years + per-year allocations (admin)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/admin/academic-years", response_model=List[AcademicYearOut])
async def list_academic_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    active_id: Optional[int] = None
    try:
        active_id = _active_academic_id(db)
    except HTTPException:
        pass
    rows = db.execute(
        text(
            """
            SELECT id, academic_name, academic_us_name,
                   academic_start, academic_end
            FROM academic
            ORDER BY id DESC
            """
        )
    ).fetchall()
    return [
        AcademicYearOut(
            id=int(row[0]),
            name=str(row[2] or row[1] or f"Academic #{row[0]}"),
            is_active=(active_id is not None and int(row[0]) == active_id),
            start_date=row[3],
            end_date=row[4],
        )
        for row in rows
    ]


@router.get(
    "/admin/manual-leave/academic-years",
    response_model=List[AcademicYearOut],
    dependencies=[Depends(require_feature_unlocked("record_staff_leave"))],
)
async def list_manual_leave_academic_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Return selectable allowance years to an authorized leave creator.

    This is intentionally separate from the admin-only leave setup endpoint:
    approvers who can record staff leave need to choose an allowance bucket,
    but should not gain access to academic-year administration.
    """
    _manual_leave_approver(db, current_user)
    try:
        active_id = _active_academic_id(db)
    except HTTPException:
        active_id = None
    rows = db.execute(
        text(
            """
            SELECT id, academic_name, academic_us_name,
                   academic_start, academic_end
            FROM academic
            WHERE academic_start IS NOT NULL
              AND academic_end IS NOT NULL
            ORDER BY CASE WHEN status = 1 THEN 0 ELSE 1 END,
                     academic_start DESC,
                     id DESC
            """
        )
    ).fetchall()
    return [
        AcademicYearOut(
            id=int(row[0]),
            name=str(row[2] or row[1] or f"Academic #{row[0]}"),
            is_active=(active_id is not None and int(row[0]) == active_id),
            start_date=row[3],
            end_date=row[4],
        )
        for row in rows
    ]


@router.get("/admin/allocations", response_model=List[AllocationOut])
async def list_allocations(
    academic_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    academic = academic_id or _active_academic_id(db)
    types = db.query(LeaveType).order_by(*_leave_type_ordering()).all()
    allocations = {
        int(a.leave_type_id): a
        for a in db.query(LeaveTypeAllocation)
        .filter(LeaveTypeAllocation.academic_id == academic)
        .all()
    }
    out: List[AllocationOut] = []
    for t in types:
        alloc = allocations.get(int(t.id))
        out.append(
            AllocationOut(
                leave_type_id=int(t.id),
                leave_type_name=str(t.name),
                academic_id=academic,
                allocated_days=float(alloc.allocated_days) if alloc is not None else None,
                is_type_active=t.is_active is not False,
            )
        )
    return out


@router.put("/admin/allocations", response_model=List[AllocationOut])
async def upsert_allocations(
    payload: AllocationsUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    type_ids = [item.leave_type_id for item in payload.items]
    valid_ids = {
        int(t.id) for t in db.query(LeaveType).filter(LeaveType.id.in_(type_ids or [0])).all()
    }
    for item in payload.items:
        if item.leave_type_id not in valid_ids:
            raise HTTPException(status_code=400, detail=f"Unknown leave type id {item.leave_type_id}")
        alloc = (
            db.query(LeaveTypeAllocation)
            .filter(
                LeaveTypeAllocation.leave_type_id == item.leave_type_id,
                LeaveTypeAllocation.academic_id == payload.academic_id,
            )
            .first()
        )
        if alloc is None:
            db.add(
                LeaveTypeAllocation(
                    leave_type_id=item.leave_type_id,
                    academic_id=payload.academic_id,
                    allocated_days=item.allocated_days,
                    is_active=True,
                    created_by=current_user.id,
                )
            )
        else:
            alloc.allocated_days = item.allocated_days
            alloc.is_active = True
    db.commit()
    return await list_allocations(payload.academic_id, db, current_user)


@router.post("/admin/allocations/clone")
async def clone_allocations(
    payload: AllocationsCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Copy one academic year's allowances to another (e.g. new school year)."""
    _require_admin(current_user)
    if payload.source_academic_id == payload.target_academic_id:
        raise HTTPException(status_code=400, detail="Source and target academic years must differ")
    source_rows = (
        db.query(LeaveTypeAllocation)
        .filter(LeaveTypeAllocation.academic_id == payload.source_academic_id)
        .all()
    )
    if not source_rows:
        raise HTTPException(status_code=404, detail="No allocations found for the source academic year")
    existing = {
        int(a.leave_type_id): a
        for a in db.query(LeaveTypeAllocation)
        .filter(LeaveTypeAllocation.academic_id == payload.target_academic_id)
        .all()
    }
    created = 0
    updated = 0
    skipped = 0
    for row in source_rows:
        target = existing.get(int(row.leave_type_id))
        if target is None:
            db.add(
                LeaveTypeAllocation(
                    leave_type_id=row.leave_type_id,
                    academic_id=payload.target_academic_id,
                    allocated_days=row.allocated_days,
                    is_active=row.is_active,
                    created_by=current_user.id,
                )
            )
            created += 1
        elif payload.overwrite:
            target.allocated_days = row.allocated_days
            target.is_active = row.is_active
            updated += 1
        else:
            skipped += 1
    db.commit()
    return {"success": True, "created": created, "updated": updated, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════════
# Approvers (admin assigns who can approve)
# ═══════════════════════════════════════════════════════════════════════════


def _serialize_approver(db: Session, approver: LeaveApprover) -> ApproverOut:
    users, avatars = _user_maps(db, [int(approver.user_id)])
    user = users.get(int(approver.user_id))
    dept_name = None
    branch_name = None
    if approver.department_id:
        dept_name = _department_name_map(db, {int(approver.department_id)}).get(
            int(approver.department_id)
        )
    if approver.branch_id:
        branch = db.query(Branch).filter(Branch.id == approver.branch_id).first()
        branch_name = str(branch.branch_name) if branch else None
    return ApproverOut(
        id=int(approver.id),
        user_id=int(approver.user_id),
        user_name=_display_name(user),
        avatar=avatars.get(int(approver.user_id)),
        department_id=approver.department_id,
        department_name=dept_name,
        branch_id=approver.branch_id,
        branch_name=branch_name,
        can_approve_all=bool(approver.can_approve_all),
        can_view_all_requests=bool(
            getattr(approver, "can_view_all_requests", False)
        ),
        max_days_can_approve=approver.max_days_can_approve,
        can_create_for_staff=bool(getattr(approver, "can_create_for_staff", False)),
        can_adjust_leave_balance=bool(
            getattr(approver, "can_adjust_leave_balance", False)
        ),
        can_cancel_approved_leave=bool(
            getattr(approver, "can_cancel_approved_leave", False)
        ),
        is_active=approver.is_active is not False,
    )


@router.get("/admin/approvers", response_model=List[ApproverOut])
async def list_approvers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    approvers = db.query(LeaveApprover).order_by(LeaveApprover.id.desc()).all()
    return [_serialize_approver(db, a) for a in approvers]


@router.post("/admin/approvers", response_model=ApproverOut)
async def create_approver(
    payload: ApproverCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.query(LeaveApprover).filter(LeaveApprover.user_id == payload.user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a leave approver")
    approver = LeaveApprover(
        user_id=payload.user_id,
        department_id=payload.department_id,
        branch_id=payload.branch_id,
        can_approve_all=payload.can_approve_all,
        can_view_all_requests=payload.can_view_all_requests,
        max_days_can_approve=payload.max_days_can_approve,
        can_create_for_staff=payload.can_create_for_staff,
        can_adjust_leave_balance=payload.can_adjust_leave_balance,
        can_cancel_approved_leave=payload.can_cancel_approved_leave,
        is_active=True,
    )
    db.add(approver)
    db.commit()
    db.refresh(approver)
    _invalidate_user_requests_cache(int(approver.user_id))
    return _serialize_approver(db, approver)


@router.put("/admin/approvers/{approver_id}", response_model=ApproverOut)
async def update_approver(
    approver_id: int,
    payload: ApproverUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    approver = db.query(LeaveApprover).filter(LeaveApprover.id == approver_id).first()
    if not approver:
        raise HTTPException(status_code=404, detail="Approver not found")
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(approver, key, value)
    db.commit()
    db.refresh(approver)
    _invalidate_user_requests_cache(int(approver.user_id))
    return _serialize_approver(db, approver)


@router.delete("/admin/approvers/{approver_id}")
async def delete_approver(
    approver_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_admin(current_user)
    approver = db.query(LeaveApprover).filter(LeaveApprover.id == approver_id).first()
    if not approver:
        raise HTTPException(status_code=404, detail="Approver not found")
    user_id = int(approver.user_id)
    db.delete(approver)
    db.commit()
    _invalidate_user_requests_cache(user_id)
    return {"success": True}


@router.get("/me/approver-status", response_model=ApproverStatusOut)
async def my_approver_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Whether the current user can approve leave, and their pending inbox size.

    Approval rights come ONLY from an active Leave Approvers assignment —
    role (admin or teacher) is irrelevant. Admins who need to approve must
    be added to the approvers list like anyone else.
    """
    approver = _approver_row(db, int(current_user.id))
    if approver is None:
        return ApproverStatusOut(
            is_approver=False,
            can_approve_all=False,
            can_view_all_requests=False,
            can_create_for_staff=False,
            can_adjust_leave_balance=False,
            pending_count=0,
            actionable_pending_count=0,
        )
    base_query = (
        db.query(func.count(LeaveRequest.id))
        .join(User, LeaveRequest.user_id == User.id)
        .filter(LeaveRequest.status == "pending")
    )

    # Visibility is independent of the approval-day limit. The badge includes
    # read-only pending rows; actionable_pending_count remains the strict
    # subset this approver can personally approve or reject.
    visible_query = _filter_to_approver_visibility_scope(base_query, approver)
    pending = int(visible_query.scalar() or 0)

    # Keep the actionable subset explicit for adaptive UI copy. Own requests
    # remain visible in the inbox but can never be self-approved.
    actionable_query = base_query.filter(LeaveRequest.user_id != current_user.id)
    if not bool(approver.can_approve_all):
        if not _approver_has_decision_scope(approver):
            actionable_query = actionable_query.filter(LeaveRequest.id < 0)
        else:
            if approver.department_id is not None:
                actionable_query = actionable_query.filter(
                    User.departmentId == approver.department_id
                )
            if approver.branch_id is not None:
                actionable_query = actionable_query.filter(
                    User.workplace == approver.branch_id
                )
    actionable_query = _filter_to_approver_day_limit(
        actionable_query,
        approver,
    )
    actionable_pending = int(actionable_query.scalar() or 0)

    return ApproverStatusOut(
        is_approver=True,
        can_approve_all=bool(approver.can_approve_all),
        can_view_all_requests=bool(
            getattr(approver, "can_view_all_requests", False)
        ),
        can_create_for_staff=bool(getattr(approver, "can_create_for_staff", False)),
        can_adjust_leave_balance=bool(
            getattr(approver, "can_adjust_leave_balance", False)
        ),
        pending_count=pending,
        actionable_pending_count=actionable_pending,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Balances + preview (employee)
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/admin/balances/report", response_model=AdminLeaveBalanceReportOut)
async def admin_leave_balance_report(
    payload: AdminLeaveBalanceReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Return export-ready leave balances for many employees in one request.

    Remaining is the academic-year allocation minus approved leave days on or
    before ``as_of_date``. Pending leave and leave after that date do not
    reduce the report balance yet. When ``history_start_date`` is supplied,
    per-day deductions are included so clients can reconstruct the balance on
    every date without issuing one API request per report row.
    """
    _require_admin(current_user)
    academic_id = payload.academic_id or _active_academic_id(db)
    balance_as_of = payload.as_of_date or _today_kh()
    requested_user_ids = list(
        dict.fromkeys(int(user_id) for user_id in payload.user_ids)
    )
    existing_user_ids = {
        int(user_id)
        for (user_id,) in db.query(User.id)
        .filter(User.id.in_(requested_user_ids or [-1]))
        .all()
    }
    user_ids = [
        user_id for user_id in requested_user_ids if user_id in existing_user_ids
    ]

    leave_types = (
        db.query(LeaveType)
        .filter(LeaveType.is_active.isnot(False))
        .order_by(*_leave_type_ordering())
        .all()
    )
    leave_type_ids = [int(leave_type.id) for leave_type in leave_types]
    allocations = {
        int(allocation.leave_type_id): allocation
        for allocation in db.query(LeaveTypeAllocation)
        .filter(
            LeaveTypeAllocation.academic_id == academic_id,
            LeaveTypeAllocation.leave_type_id.in_(leave_type_ids or [0]),
        )
        .all()
    }

    allocated_by_type: Dict[int, float] = {}
    type_columns: List[LeaveBalanceTypeColumnOut] = []
    for leave_type in leave_types:
        leave_type_id = int(leave_type.id)
        allocation = allocations.get(leave_type_id)
        allocated = (
            float(allocation.allocated_days or 0)
            if allocation is not None and allocation.is_active is not False
            else float(leave_type.max_days_per_year or 0)
        )
        allocated = round(allocated, 2)
        allocated_by_type[leave_type_id] = allocated
        type_columns.append(
            LeaveBalanceTypeColumnOut(
                leave_type_id=leave_type_id,
                leave_type_name=str(leave_type.name),
                allocated_days=allocated,
                monthly_cap_days=leave_monthly_policy.effective_cap(leave_type),
            )
        )

    # Paid and unpaid usage are collected separately: only the paid portion
    # reduces the remaining balance, while the unpaid portion feeds the
    # over-policy column beside it.
    usage_by_user_and_type: Dict[Tuple[int, int], Dict[str, float]] = {}
    if user_ids and leave_type_ids:
        usage_rows = (
            db.query(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.status,
                func.coalesce(func.sum(_PAID_COST), 0.0),
                func.coalesce(func.sum(_UNPAID_COST), 0.0),
            )
            .join(LeaveRequestDay, LeaveRequestDay.leave_request_id == LeaveRequest.id)
            .filter(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.leave_type_id.in_(leave_type_ids),
                LeaveRequest.academic_id == academic_id,
                LeaveRequest.status.in_(["approved", "pending"]),
                LeaveRequestDay.leave_date <= balance_as_of,
            )
            .group_by(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.status,
            )
            .all()
        )
        for user_id, leave_type_id, status, paid_total, unpaid_total in usage_rows:
            entry = usage_by_user_and_type.setdefault(
                (int(user_id), int(leave_type_id)),
                {
                    "approved": 0.0,
                    "pending": 0.0,
                    "approved_unpaid": 0.0,
                    "pending_unpaid": 0.0,
                },
            )
            entry[str(status)] = float(paid_total or 0)
            entry[f"{status}_unpaid"] = float(unpaid_total or 0)

    deductions_by_user_and_type: Dict[Tuple[int, int], float] = {}
    if user_ids and leave_type_ids:
        deduction_rows = (
            db.query(
                LeaveBalanceAdjustment.user_id,
                LeaveBalanceAdjustment.leave_type_id,
                func.coalesce(func.sum(LeaveBalanceAdjustment.amount_days), 0.0),
            )
            .filter(
                LeaveBalanceAdjustment.user_id.in_(user_ids),
                LeaveBalanceAdjustment.leave_type_id.in_(leave_type_ids),
                LeaveBalanceAdjustment.academic_id == academic_id,
                LeaveBalanceAdjustment.status == "active",
                LeaveBalanceAdjustment.effective_date <= balance_as_of,
            )
            .group_by(
                LeaveBalanceAdjustment.user_id,
                LeaveBalanceAdjustment.leave_type_id,
            )
            .all()
        )
        deductions_by_user_and_type = {
            (int(user_id), int(leave_type_id)): float(total or 0)
            for user_id, leave_type_id, total in deduction_rows
        }

    daily_changes_by_user: Dict[int, List[LeaveBalanceDailyChangeOut]] = {}
    history_start = payload.history_start_date
    if (
        history_start is not None
        and history_start <= balance_as_of
        and user_ids
        and leave_type_ids
    ):
        daily_change_values: Dict[Tuple[int, int, date], Dict[str, float]] = {}
        leave_change_rows = (
            db.query(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequestDay.leave_date,
                func.coalesce(func.sum(_PAID_COST), 0.0),
                func.coalesce(func.sum(_UNPAID_COST), 0.0),
            )
            .join(LeaveRequestDay, LeaveRequestDay.leave_request_id == LeaveRequest.id)
            .filter(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.leave_type_id.in_(leave_type_ids),
                LeaveRequest.academic_id == academic_id,
                LeaveRequest.status == "approved",
                LeaveRequestDay.leave_date >= history_start,
                LeaveRequestDay.leave_date <= balance_as_of,
            )
            .group_by(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequestDay.leave_date,
            )
            .all()
        )
        for user_id, leave_type_id, balance_date, paid_total, unpaid_total in leave_change_rows:
            entry = daily_change_values.setdefault(
                (int(user_id), int(leave_type_id), balance_date),
                {"taken": 0.0, "unpaid": 0.0, "policy": 0.0},
            )
            entry["taken"] = float(paid_total or 0)
            entry["unpaid"] = float(unpaid_total or 0)

        policy_change_rows = (
            db.query(
                LeaveBalanceAdjustment.user_id,
                LeaveBalanceAdjustment.leave_type_id,
                LeaveBalanceAdjustment.effective_date,
                func.coalesce(func.sum(LeaveBalanceAdjustment.amount_days), 0.0),
            )
            .filter(
                LeaveBalanceAdjustment.user_id.in_(user_ids),
                LeaveBalanceAdjustment.leave_type_id.in_(leave_type_ids),
                LeaveBalanceAdjustment.academic_id == academic_id,
                LeaveBalanceAdjustment.status == "active",
                LeaveBalanceAdjustment.effective_date >= history_start,
                LeaveBalanceAdjustment.effective_date <= balance_as_of,
            )
            .group_by(
                LeaveBalanceAdjustment.user_id,
                LeaveBalanceAdjustment.leave_type_id,
                LeaveBalanceAdjustment.effective_date,
            )
            .all()
        )
        for user_id, leave_type_id, balance_date, total in policy_change_rows:
            daily_change_values.setdefault(
                (int(user_id), int(leave_type_id), balance_date),
                {"taken": 0.0, "unpaid": 0.0, "policy": 0.0},
            )["policy"] = float(total or 0)

        for (user_id, leave_type_id, balance_date), values in sorted(
            daily_change_values.items(), key=lambda item: item[0]
        ):
            daily_changes_by_user.setdefault(user_id, []).append(
                LeaveBalanceDailyChangeOut(
                    balance_date=balance_date,
                    leave_type_id=leave_type_id,
                    taken_days=round(values["taken"], 2),
                    unpaid_days=round(values["unpaid"], 2),
                    policy_deduction_days=round(values["policy"], 2),
                )
            )

    users: List[AdminUserLeaveBalancesOut] = []
    for user_id in user_ids:
        balances: List[UserLeaveBalanceValueOut] = []
        for leave_type_id in leave_type_ids:
            usage = usage_by_user_and_type.get(
                (user_id, leave_type_id),
                {
                    "approved": 0.0,
                    "pending": 0.0,
                    "approved_unpaid": 0.0,
                    "pending_unpaid": 0.0,
                },
            )
            taken = round(float(usage["approved"]), 2)
            pending = round(float(usage["pending"]), 2)
            unpaid = round(float(usage.get("approved_unpaid", 0.0)), 2)
            pending_unpaid = round(float(usage.get("pending_unpaid", 0.0)), 2)
            policy_deductions = round(
                deductions_by_user_and_type.get((user_id, leave_type_id), 0.0),
                2,
            )
            balances.append(
                UserLeaveBalanceValueOut(
                    leave_type_id=leave_type_id,
                    taken_days=taken,
                    pending_days=pending,
                    unpaid_days=unpaid,
                    pending_unpaid_days=pending_unpaid,
                    policy_deduction_days=policy_deductions,
                    remaining_days=round(
                        max(
                            0.0,
                            allocated_by_type[leave_type_id]
                            - taken
                            - policy_deductions,
                        ),
                        2,
                    ),
                )
            )
        users.append(
            AdminUserLeaveBalancesOut(
                user_id=user_id,
                balances=balances,
                daily_changes=daily_changes_by_user.get(user_id, []),
            )
        )

    return AdminLeaveBalanceReportOut(
        academic_id=academic_id,
        leave_types=type_columns,
        users=users,
    )


@router.get("/me/balances", response_model=List[LeaveBalanceOut])
async def my_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    academic_id = _active_academic_id(db)
    types = (
        db.query(LeaveType)
        .filter(LeaveType.is_active.isnot(False))
        .order_by(*_leave_type_ordering())
        .all()
    )
    out: List[LeaveBalanceOut] = []
    for t in types:
        out.append(_leave_balance_value(db, int(current_user.id), t, academic_id))
    return out


@router.get(
    "/me/balances/{leave_type_id}/details",
    response_model=LeaveBalanceDetailOut,
)
async def my_balance_details(
    leave_type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Explain a balance, including every audited policy deduction."""
    academic_id = _active_academic_id(db)
    leave_type = (
        db.query(LeaveType)
        .filter(LeaveType.id == leave_type_id, LeaveType.is_active.isnot(False))
        .first()
    )
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    adjustments = (
        db.query(LeaveBalanceAdjustment)
        .filter(
            LeaveBalanceAdjustment.user_id == int(current_user.id),
            LeaveBalanceAdjustment.leave_type_id == leave_type_id,
            LeaveBalanceAdjustment.academic_id == academic_id,
        )
        .order_by(LeaveBalanceAdjustment.created_at.desc())
        .all()
    )
    requests = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == int(current_user.id),
            LeaveRequest.leave_type_id == leave_type_id,
            LeaveRequest.academic_id == academic_id,
            LeaveRequest.status.in_(["approved", "pending"]),
        )
        .order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
        .all()
    )
    # Per-month usage explains why a specific day became unpaid, which the
    # balance totals alone cannot show.
    cap = leave_monthly_policy.effective_cap(leave_type)
    monthly: Dict[str, Dict[str, float]] = {}
    for request in requests:
        for day in request.days:
            bucket = monthly.setdefault(
                leave_monthly_policy.month_label(
                    leave_monthly_policy.month_key(day.leave_date)
                ),
                {"taken": 0.0, "unpaid": 0.0},
            )
            bucket["taken"] += leave_monthly_policy.paid_cost_of(day)
            bucket["unpaid"] += leave_monthly_policy.unpaid_cost_of(day)

    return LeaveBalanceDetailOut(
        balance=_leave_balance_value(
            db, int(current_user.id), leave_type, academic_id
        ),
        requests=_serialize_requests(db, requests),
        adjustments=[
            _serialize_balance_adjustment(db, adjustment)
            for adjustment in adjustments
        ],
        monthly_usage=[
            LeaveBalanceMonthUsageOut(
                month=month,
                cap_days=cap,
                taken_days=round(values["taken"], 2),
                unpaid_days=round(values["unpaid"], 2),
            )
            for month, values in sorted(monthly.items(), reverse=True)
        ],
    )


@router.post("/requests/preview", response_model=LeavePreviewResponse)
async def preview_request_days(
    payload: LeavePreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Resolve working sessions per day so the form can offer full/session choices."""
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    if (payload.end_date - payload.start_date).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"Date range too large (max {MAX_RANGE_DAYS} days)")

    holidays = _holidays_in_range(db, payload.start_date, payload.end_date)
    existing = _existing_leave_days(db, int(current_user.id), payload.start_date, payload.end_date)

    days: List[PreviewDayOut] = []
    current = payload.start_date
    while current <= payload.end_date:
        holiday_name = holidays.get(current)
        if holiday_name is not None:
            days.append(
                PreviewDayOut(
                    leave_date=current,
                    is_working_day=False,
                    holiday_name=holiday_name,
                    day_type="Holiday",
                    sessions=[],
                    already_requested=current in existing,
                )
            )
        else:
            day_info = get_effective_day_attendance(db, current_user, current)
            sessions = day_info.get("sessions") or []
            covered, _ = _covered_session_indexes(
                existing.get(current, []), len(sessions)
            )
            days.append(
                PreviewDayOut(
                    leave_date=current,
                    is_working_day=bool(day_info.get("is_active_day")),
                    day_type=day_info.get("day_type"),
                    sessions=[
                        PreviewSessionOut(index=i + 1, start=str(s.get("start")), end=str(s.get("end")))
                        for i, s in enumerate(sessions)
                    ],
                    # Any pending/approved leave on the date blocks selecting
                    # that date again, even if the older request used one session.
                    already_requested=bool(existing.get(current)),
                    requested_session_indexes=sorted(covered),
                )
            )
        current += timedelta(days=1)
    return LeavePreviewResponse(days=days)


def _preview_day_cost(db: Session, user: User, item) -> Optional[float]:
    """Balance cost of one proposed day, or None when it is not selectable.

    Mirrors the cost rule in create_leave_request but never raises: the policy
    preview runs while the employee is still editing the form, so an
    unusable date is skipped instead of failing the whole preview.
    """
    day_info = get_effective_day_attendance(db, user, item.leave_date)
    sessions = day_info.get("sessions") or []
    if not day_info.get("is_active_day") or not sessions:
        return None
    sessions_total = len(sessions)
    if item.scope != LeaveDayScope.SESSIONS:
        return 1.0
    indexes = sorted(
        {i for i in (item.session_indexes or []) if 1 <= i <= sessions_total}
    )
    if not indexes:
        return None
    if len(indexes) == sessions_total:
        return 1.0
    return round(len(indexes) / sessions_total, 4)


@router.post("/requests/policy-preview", response_model=LeavePolicyPreviewOut)
async def preview_monthly_policy(
    payload: LeavePolicyPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Split a not-yet-submitted request by the leave type's monthly cap.

    The request form calls this whenever the selection changes so it can warn
    that part of the leave will be unpaid. The same service backs the real
    submission, so the warning and the stored result cannot drift apart.
    """
    leave_type = (
        db.query(LeaveType)
        .filter(LeaveType.id == payload.leave_type_id, LeaveType.is_active.isnot(False))
        .first()
    )
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")

    academic_id = _active_academic_id(db)
    balance = _leave_balance_value(
        db, int(current_user.id), leave_type, academic_id
    )
    day_costs: Dict[date, float] = {}
    for item in payload.days:
        cost = _preview_day_cost(db, current_user, item)
        if cost is not None:
            day_costs[item.leave_date] = cost

    if not day_costs:
        return LeavePolicyPreviewOut(
            leave_type_id=int(leave_type.id),
            leave_type_name=str(leave_type.name),
            cap_days=leave_monthly_policy.effective_cap(leave_type),
            available_to_request_days=balance.available_to_request_days,
        )

    split = leave_monthly_policy.simulate(
        db,
        int(current_user.id),
        leave_type,
        academic_id,
        day_costs,
        exclude_request_id=payload.exclude_request_id,
    )
    return LeavePolicyPreviewOut(
        leave_type_id=int(leave_type.id),
        leave_type_name=str(leave_type.name),
        cap_days=split["cap_days"],
        total_days=round(sum(day_costs.values()), 2),
        paid_days=round(float(split["paid_days"]), 2),
        unpaid_days=round(float(split["unpaid_days"]), 2),
        available_to_request_days=balance.available_to_request_days,
        months=[
            LeavePolicyMonthOut(
                month=str(month["month"]),
                cap_days=month["cap_days"],
                already_used_days=round(float(month["already_used_days"]), 2),
                requested_days=round(float(month["requested_days"]), 2),
                paid_days=round(float(month["paid_days"]), 2),
                unpaid_days=round(float(month["unpaid_days"]), 2),
            )
            for month in split["months"]
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Submit / list / cancel requests (employee)
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/requests/proof")
async def upload_leave_proof(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Stage an optional or required leave proof image (max 5 MB).

    Returns {"path": ...} to send as proof_image_path in POST /requests.
    """
    content_type = (file.content_type or "").lower()
    if content_type not in PROOF_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > PROOF_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Proof image must be 5 MB or smaller")

    # UploadFile.content_type is supplied by the client and can be forged.
    # Decode and verify the actual image before it reaches persistent storage.
    try:
        with Image.open(BytesIO(data)) as image:
            detected_format = str(image.format or "").upper()
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > PROOF_MAX_PIXELS:
                raise HTTPException(
                    status_code=400,
                    detail="Proof image dimensions are invalid or too large",
                )
            if content_type not in PROOF_FORMAT_CONTENT_TYPES.get(detected_format, set()):
                raise HTTPException(
                    status_code=400,
                    detail="Proof file content does not match its image type",
                )
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="Proof file is not a valid image")

    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    import uuid

    filename = f"u{int(current_user.id)}_{uuid.uuid4().hex}{ext}"
    path = StorageService.upload_file(data, PROOF_FOLDER, filename, content_type)
    if not path:
        raise HTTPException(status_code=500, detail="Upload failed")
    return {"path": path, "size": len(data)}


@router.post("/requests", response_model=LeaveRequestOut)
async def create_leave_request(
    payload: LeaveRequestCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    # Serialize balance-affecting employee submissions with authorized manual
    # leave batches, which lock the same user row before checking balances.
    locked_user = (
        db.query(User)
        .filter(User.id == int(current_user.id))
        .with_for_update()
        .first()
    )
    if locked_user is None or getattr(locked_user, "status", None) != 1:
        raise HTTPException(status_code=403, detail="Employee account is inactive")
    current_user = locked_user
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Reason is required")

    leave_type = db.query(LeaveType).filter(LeaveType.id == payload.leave_type_id).first()
    if not leave_type or leave_type.is_active is False:
        raise HTTPException(status_code=404, detail="Leave type not found")

    # Dedupe + sort request days
    seen_dates: Set[date] = set()
    day_inputs = []
    for item in sorted(payload.days, key=lambda d: d.leave_date):
        if item.leave_date in seen_dates:
            raise HTTPException(status_code=400, detail=f"Duplicate date {item.leave_date}")
        seen_dates.add(item.leave_date)
        day_inputs.append(item)

    start = day_inputs[0].leave_date
    end = day_inputs[-1].leave_date
    # Employee self-requests always charge the currently active academic
    # allowance. The leave dates may be outside that academic year's configured
    # calendar (for example, a newly opened future term), but the request must
    # still be processed without requiring an academic-year switch. Manual
    # staff entries retain their explicit date-range/active-year controls.
    academic_id = _active_academic_id(db)
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"Date range too large (max {MAX_RANGE_DAYS} days)")
    if start < _today_kh():
        raise HTTPException(status_code=400, detail="Cannot request leave for past dates")

    holidays = _holidays_in_range(db, start, end)
    existing = _existing_leave_days(db, int(current_user.id), start, end)
    conflicting_dates = [
        item.leave_date for item in day_inputs if existing.get(item.leave_date)
    ]
    if conflicting_dates:
        raise HTTPException(
            status_code=409,
            detail=_leave_date_conflict_detail(conflicting_dates),
        )

    day_rows: List[LeaveRequestDay] = []
    total_cost = 0.0
    for item in day_inputs:
        if item.leave_date in holidays:
            raise HTTPException(
                status_code=400,
                detail=f"{item.leave_date} is a holiday ({holidays[item.leave_date]})",
            )
        day_info = get_effective_day_attendance(db, current_user, item.leave_date)
        sessions = day_info.get("sessions") or []
        if not day_info.get("is_active_day") or not sessions:
            raise HTTPException(
                status_code=400,
                detail=f"{item.leave_date} is not a working day for you",
            )
        sessions_total = len(sessions)

        if item.scope == LeaveDayScope.SESSIONS:
            indexes = sorted(set(item.session_indexes or []))
            if not indexes:
                raise HTTPException(
                    status_code=400,
                    detail=f"Select at least one session for {item.leave_date}",
                )
            if any(i < 1 or i > sessions_total for i in indexes):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid session selection for {item.leave_date}",
                )
            # Selecting every session is just a full day
            if len(indexes) == sessions_total:
                scope = "full_day"
                indexes_value = None
                day_cost = 1.0
                time_from = str(sessions[0].get("start"))
                time_to = str(sessions[-1].get("end"))
            else:
                scope = "sessions"
                indexes_value = indexes
                day_cost = round(len(indexes) / sessions_total, 4)
                time_from = str(sessions[indexes[0] - 1].get("start"))
                time_to = str(sessions[indexes[-1] - 1].get("end"))
        else:
            scope = "full_day"
            indexes_value = None
            day_cost = 1.0
            time_from = str(sessions[0].get("start"))
            time_to = str(sessions[-1].get("end"))

        total_cost += day_cost
        day_rows.append(
            LeaveRequestDay(
                leave_date=item.leave_date,
                scope=scope,
                session_indexes=indexes_value,
                sessions_total=sessions_total,
                day_cost=day_cost,
                time_from=time_from,
                time_to=time_to,
            )
        )

    total_cost = round(total_cost, 4)

    # Split the request first. For a leave type with a monthly cap, days over
    # the cap — and days once the yearly allowance is spent — come back as
    # salary-deducted and cost no balance, so the check below passes and the
    # employee can keep requesting leave with everything correctly unpaid.
    # For a type without a cap nothing is deducted, so this stays the classic
    # "must fit the remaining balance" rule.
    split = leave_monthly_policy.simulate(
        db,
        int(current_user.id),
        leave_type,
        academic_id,
        {row.leave_date: float(row.day_cost) for row in day_rows},
    )
    paid_cost = float(split["paid_days"])

    # Policy deductions reserve allowance just like approved leave, while
    # pending requests reserve it until a decision is made.
    allocated = _allocated_days(db, leave_type, academic_id)
    taken = _sum_day_costs(db, int(current_user.id), int(leave_type.id), academic_id, ["approved"])
    pending = _sum_day_costs(db, int(current_user.id), int(leave_type.id), academic_id, ["pending"])
    policy_deductions = _sum_policy_deductions(
        db, int(current_user.id), int(leave_type.id), academic_id
    )
    available = allocated - taken - pending - policy_deductions
    if paid_cost > available + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough {leave_type.name} balance: requested {paid_cost:g} paid day(s), "
                f"available {max(0.0, round(available, 2)):g} day(s)"
            ),
        )

    # Optional covering colleague proposed by the requester
    replacement_id: Optional[int] = None
    if payload.replacement_user_id:
        replacement = _validate_replacement(db, payload.replacement_user_id, int(current_user.id))
        replacement_id = int(replacement.id)

    # Proof images are supported by every leave type and mandatory when the
    # type requires them. Every path must come from POST /requests/proof and
    # belong to the requester.
    proof_path = _validated_proof_path_for_type(
        payload.proof_image_path,
        int(current_user.id),
        leave_type,
    )

    auto_approved = leave_type.requires_approval is False
    request = LeaveRequest(
        user_id=int(current_user.id),
        leave_type_id=int(leave_type.id),
        start_date=start,
        end_date=end,
        reason=reason,
        status="approved" if auto_approved else "pending",
        approval_date=_now_utc() if auto_approved else None,
        academic_id=academic_id,
        total_days=total_cost,
        replacement_user_id=replacement_id,
        proof_image_path=proof_path,
        created_by=int(current_user.id),
        creation_source="employee",
    )
    request.days = day_rows
    try:
        db.add(request)
        db.flush()
        _add_history(
            db,
            int(request.id),
            "created",
            None,
            str(request.status),
            int(current_user.id),
            notes=reason,
        )
        # Persist the monthly-cap split for the months this request touches.
        # Doing it after the flush lets the recompute see the new rows in the
        # same chronological order the balance will later read them in.
        leave_monthly_policy.recompute_for_request(db, request)
        # Flush history and build the validated response before committing.
        # If either step fails, no partial request survives and the row lock is
        # released by the explicit rollback below.
        db.flush()
        response = _serialize_requests(
            db,
            [request],
            include_user_phone=_is_admin(current_user),
        )[0]
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Cache invalidation and notification delivery are post-commit side
    # effects. Their failure must never make the client think the saved leave
    # failed and submit the same dates a second time.
    try:
        _invalidate_user_requests_cache(int(current_user.id))
    except Exception as exc:
        logger.warning(
            "Leave request %s saved but cache invalidation failed: %s",
            request.id,
            exc,
        )
    try:
        background_tasks.add_task(
            leave_notify.notify_leave_request_created,
            int(request.id),
        )
    except Exception as exc:
        logger.error(
            "Leave request %s saved but notification scheduling failed: %s",
            request.id,
            exc,
        )

    return response


@router.get("/me/requests", response_model=List[LeaveRequestOut])
async def my_requests(
    status: Optional[str] = Query(None),
    academic_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    all_dates: bool = Query(False),
    date_basis: str = Query(
        "leave",
        pattern="^(leave|submitted|decision|activity)$",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    # History calls default to the current month to avoid heavy load. Small
    # status/count consumers may explicitly request all dates so future
    # unresolved leave is not hidden merely because its leave date is outside
    # the current month.
    start_date, end_date = _my_request_date_window(
        start_date,
        end_date,
        all_dates,
    )

    cache_key = f"my:{current_user.id}:v6:{status or ''}:{academic_id or ''}:{int(all_dates)}:{date_basis}:{start_date or ''}:{end_date or ''}:{limit}:{offset}"
    cached = user_requests_cache.get(cache_key)
    if cached is not None:
        return cached

    query = db.query(LeaveRequest).filter(LeaveRequest.user_id == current_user.id)
    if status:
        query = query.filter(LeaveRequest.status == status)
    if academic_id:
        query = query.filter(LeaveRequest.academic_id == academic_id)
    try:
        filter_start = date.fromisoformat(start_date) if start_date else None
        filter_end = date.fromisoformat(end_date) if end_date else None
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Dates must use YYYY-MM-DD format",
        )
    if filter_start and filter_end and filter_end < filter_start:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date",
        )

    if date_basis == "leave":
        if filter_start:
            query = query.filter(LeaveRequest.end_date >= filter_start)
        if filter_end:
            query = query.filter(LeaveRequest.start_date <= filter_end)
        order_column = LeaveRequest.created_at
    else:
        activity_timestamp = _review_activity_timestamp(date_basis)
        start_utc, end_exclusive_utc = _cambodia_date_filter_utc_bounds(
            filter_start,
            filter_end,
        )
        if start_utc:
            query = query.filter(activity_timestamp >= start_utc)
        if end_exclusive_utc:
            query = query.filter(activity_timestamp < end_exclusive_utc)
        order_column = activity_timestamp

    requests = (
        query.order_by(order_column.desc(), LeaveRequest.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = [
        item.model_copy(
            update=_review_reminder_metadata(
                request,
                current_user,
                None,
                {
                    "can_view": True,
                    "can_decide": False,
                },
            )
        )
        for item, request in zip(
            _serialize_requests(db, requests, current_user=current_user),
            requests,
        )
    ]

    # Cache serialized result
    from fastapi.encoders import jsonable_encoder
    user_requests_cache.set(cache_key, jsonable_encoder(result))

    return result


@router.get("/requests/{request_id}", response_model=LeaveRequestOut)
async def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    requester = db.query(User).filter(User.id == request.user_id).first()
    approver = _approver_row(db, int(current_user.id))
    actionability = _request_actionability(
        request,
        current_user,
        requester,
        approver,
    )
    if not actionability["can_view"]:
        raise HTTPException(status_code=403, detail=actionability["reason"])
    item = _serialize_requests(
        db,
        [request],
        include_user_phone=approver is not None or _is_admin(current_user),
        current_user=current_user,
    )[0]
    decision_contacts: List[Dict[str, object]] = []
    can_view_decision_contacts = _can_view_decision_contacts(
        request,
        current_user,
        approver,
        actionability,
    )
    if can_view_decision_contacts:
        active_approvers = (
            db.query(LeaveApprover)
            .filter(LeaveApprover.is_active == True)  # noqa: E712
            .all()
        )
        approver_users, approver_avatars = _user_maps(
            db,
            [int(row.user_id) for row in active_approvers],
        )
        decision_contacts = _decision_contacts_for_request(
            request,
            requester,
            active_approvers,
            approver_users,
            approver_avatars,
        )
    return item.model_copy(
        update={
            "can_decide": bool(actionability["can_decide"]),
            "decision_contacts": decision_contacts,
            **_review_reminder_metadata(
                request,
                current_user,
                approver,
                actionability,
            ),
        }
    )


@router.get("/requests/{request_id}/actionability")
async def get_request_actionability(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Return whether the signed-in user may view or decide one request."""
    request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    requester = db.query(User).filter(User.id == request.user_id).first()
    approver = _approver_row(db, int(current_user.id))
    result = _request_actionability(request, current_user, requester, approver)
    if not result["can_view"]:
        raise HTTPException(status_code=403, detail=result["reason"])
    return {
        "request_id": int(request.id),
        "status": str(request.status),
        **result,
    }


@router.post(
    "/requests/{request_id}/review-reminder",
    response_model=LeaveReviewReminderOut,
)
async def send_review_reminder(
    request_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Let a read-only reviewer remind the people who can decide this request."""
    request = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if str(request.status) != "pending":
        raise HTTPException(
            status_code=409,
            detail="This leave request is no longer pending",
        )

    requester = db.query(User).filter(User.id == request.user_id).first()
    approver = _approver_row(db, int(current_user.id))
    actionability = _request_actionability(
        request,
        current_user,
        requester,
        approver,
    )
    if not actionability["can_view"]:
        raise HTTPException(status_code=403, detail=actionability["reason"])
    if not _can_send_review_reminder(
        request,
        current_user,
        approver,
        actionability,
    ):
        if actionability["can_decide"]:
            raise HTTPException(
                status_code=403,
                detail=(
                    "You can approve or reject this request directly; "
                    "a reminder is not needed"
                ),
            )
        raise HTTPException(
            status_code=403,
            detail=(
                "Only the requester or a read-only leave reviewer "
                "can send this reminder"
            ),
        )

    retry_after = _review_reminder_retry_after_seconds(request)
    if retry_after > 0:
        available_at = _review_reminder_available_at(request)
        wait_minutes = max(1, math.ceil(retry_after / 60))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "leave_review_reminder_cooldown",
                "message": (
                    f"A reminder was already sent. Try again in "
                    f"{wait_minutes} minute(s)."
                ),
                "retry_after_seconds": retry_after,
                "next_allowed_at": (
                    available_at.isoformat() if available_at else None
                ),
            },
        )

    active_approvers = (
        db.query(LeaveApprover)
        .filter(LeaveApprover.is_active == True)  # noqa: E712
        .all()
    )
    approver_users, approver_avatars = _user_maps(
        db,
        [int(row.user_id) for row in active_approvers],
    )
    contacts = _decision_contacts_for_request(
        request,
        requester,
        active_approvers,
        approver_users,
        approver_avatars,
    )
    recipient_ids = sorted(
        {
            int(contact["user_id"])
            for contact in contacts
            if int(contact["user_id"]) != int(current_user.id)
        }
    )
    if not recipient_ids:
        raise HTTPException(
            status_code=409,
            detail="No eligible approver is currently available",
        )

    request.review_reminder_count = int(
        getattr(request, "review_reminder_count", 0) or 0
    ) + 1
    request.last_review_reminder_at = _now_utc()
    _add_history(
        db,
        int(request.id),
        "review_reminder_sent",
        str(request.status),
        str(request.status),
        int(current_user.id),
        notes=f"Push reminder sent to {len(recipient_ids)} eligible approver(s)",
    )
    db.commit()
    db.refresh(request)
    _invalidate_user_requests_cache(int(request.user_id))

    background_tasks.add_task(
        leave_notify.notify_leave_review_reminder,
        int(request.id),
        int(current_user.id),
        recipient_ids,
    )
    next_allowed_at = _review_reminder_available_at(request)
    if next_allowed_at is None:  # Defensive: count and timestamp were just set.
        next_allowed_at = datetime.now(timezone.utc)
    return LeaveReviewReminderOut(
        recipient_count=len(recipient_ids),
        reminder_count=int(request.review_reminder_count or 0),
        next_allowed_at=next_allowed_at,
    )


@router.post("/requests/{request_id}/cancel", response_model=LeaveRequestOut)
async def cancel_request(
    request_id: int,
    payload: LeaveCancelRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    request = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Leave request not found")

    requester = db.query(User).filter(User.id == request.user_id).first()
    approver = _approver_row(db, int(current_user.id))
    actionability = _request_actionability(
        request, current_user, requester, approver
    )

    if not actionability.get("can_cancel"):
        reason = (
            str(actionability.get("can_cancel_reason") or "")
            or "Not allowed to cancel this request"
        )
        if str(request.status) in ("cancelled", "rejected"):
            raise HTTPException(status_code=400, detail=reason)
        raise HTTPException(status_code=403, detail=reason)

    is_manual = str(getattr(request, "creation_source", None) or "employee") == "manual"
    is_closing_someone_elses_approved_leave = (
        str(request.status) == "approved"
        and int(request.user_id) != int(current_user.id)
    )
    if (
        is_manual or is_closing_someone_elses_approved_leave
    ) and not (payload.reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="A reason is required when closing approved staff leave",
        )

    proof_to_delete = request.proof_image_path
    try:
        old_status = str(request.status)
        request.status = "cancelled"
        request.cancelled_by = int(current_user.id)
        request.cancelled_at = _now_utc()
        request.cancel_reason = (payload.reason or "").strip() or None
        # Status, cancellation audit data, proof reference, and history are one
        # database transaction. Any pre-commit failure rolls all of them back.
        request.proof_image_path = None
        _add_history(
            db,
            int(request.id),
            "cancelled",
            old_status,
            "cancelled",
            int(current_user.id),
            notes=request.cancel_reason,
        )
        db.flush()
        # The cancelled days release their monthly-cap slots, so a later day in
        # the same month that was pushed over the cap becomes paid again.
        leave_monthly_policy.recompute_for_request(db, request)
        response = _serialize_requests(
            db, [request], current_user=current_user
        )[0]
        db.commit()
    except Exception:
        db.rollback()
        raise

    _delete_unreferenced_proof_files(db, proof_to_delete)

    _invalidate_user_requests_cache(int(request.user_id))

    try:
        background_tasks.add_task(
            leave_notify.notify_leave_request_cancelled,
            int(request.id),
            int(current_user.id),
        )
    except Exception as exc:
        # The cancellation is already safely committed. Do not return a false
        # failure that invites a duplicate retry; record the delivery problem.
        logger.error(
            "Leave cancellation %s saved but notification scheduling failed: %s",
            request.id,
            exc,
        )
    return response


@router.get("/active-upcoming", response_model=List[LeaveRequestOut])
async def list_active_upcoming_leaves(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Retrieve visible active/upcoming leave without leaking private evidence.

    Administrators and assigned approvers retain their authorized scope.
    Ordinary staff only see approved colleagues in their own branch, and
    private reasons/proofs/decision notes are removed from colleague rows.
    """
    approver = _approver_row(db, int(current_user.id))
    privileged_all = _is_admin(current_user) or bool(
        approver is not None
        and (
            approver.can_approve_all
            or getattr(approver, "can_view_all_requests", False)
        )
    )

    query = db.query(LeaveRequest).join(User, LeaveRequest.user_id == User.id)
    if privileged_all:
        query = query.filter(LeaveRequest.status.in_(["approved", "pending"]))
    elif approver is not None and _approver_has_decision_scope(approver):
        query = query.filter(LeaveRequest.status.in_(["approved", "pending"]))
        if approver.department_id is not None:
            query = query.filter(User.departmentId == approver.department_id)
        if approver.branch_id is not None:
            query = query.filter(User.workplace == approver.branch_id)
    else:
        query = query.filter(LeaveRequest.status == "approved")
        own_branch = getattr(current_user, "workplace", None)
        if own_branch is not None:
            query = query.filter(User.workplace == own_branch)
        else:
            # A missing branch must not accidentally remove the tenant/privacy
            # boundary and expose every employee's upcoming leave.
            query = query.filter(LeaveRequest.user_id == int(current_user.id))
    
    if start_date and end_date:
        query = query.filter(
            LeaveRequest.end_date >= start_date,
            LeaveRequest.start_date <= end_date
        )
    else:
        today = _today_kh()
        query = query.filter(LeaveRequest.end_date >= today)

    requests = query.order_by(LeaveRequest.start_date.asc()).all()
    serialized = _serialize_requests(db, requests, current_user=current_user)
    if privileged_all or approver is not None:
        return serialized

    redacted: List[LeaveRequestOut] = []
    for item in serialized:
        if int(item.user_id) == int(current_user.id):
            redacted.append(item)
            continue
        redacted.append(
            item.model_copy(
                update={
                    "reason": None,
                    "proof_image_url": None,
                    "rejection_reason": None,
                    "cancel_reason": None,
                    "replacement_note": None,
                }
            )
        )
    return redacted


@router.get("/colleagues", response_model=List[ColleagueOut])
async def list_colleagues(
    search: Optional[str] = Query(None),
    branch_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Active users for the replacement picker (any authenticated employee)."""
    query = db.query(User).filter(User.status == 1, User.id != current_user.id)

    # Filter by branch if specified
    if branch_id is not None:
        query = query.filter(User.workplace == branch_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (User.eName.like(term)) | (User.kName.like(term)) | (User.username.like(term))
        ).order_by(User.eName.asc(), User.id.asc())
    else:
        # Default view: colleagues from the requester's own branch first.
        own_branch = getattr(current_user, "workplace", None)
        if own_branch and branch_id is None:
            query = query.order_by(
                (User.workplace != own_branch).asc(), User.eName.asc(), User.id.asc()
            )
        else:
            query = query.order_by(User.eName.asc(), User.id.asc())
    users = query.offset(offset).limit(limit).all()

    user_map = {int(u.id): u for u in users}
    _, avatars = _user_maps(db, list(user_map.keys()))
    dept_names, branch_names = _name_maps(db, user_map)

    return [
        ColleagueOut(
            id=int(u.id),
            name=_display_name(u),
            avatar=avatars.get(int(u.id)),
            department_name=dept_names.get(int(getattr(u, "departmentId", 0) or 0)),
            branch_name=branch_names.get(int(getattr(u, "workplace", 0) or 0)),
        )
        for u in users
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Approver inbox + decision
# ═══════════════════════════════════════════════════════════════════════════


def _manual_leave_employee_scope_query(
    db: Session,
    current_user: User,
    approver: LeaveApprover,
):
    """Base employee query shared by manual-leave filters and results."""
    query = db.query(User).filter(
        User.status == 1,
        User.id != int(current_user.id),
    )
    if not bool(approver.can_approve_all):
        if not _approver_has_decision_scope(approver):
            return query.filter(User.id < 0)
        if approver.department_id is not None:
            query = query.filter(User.departmentId == approver.department_id)
        if approver.branch_id is not None:
            query = query.filter(User.workplace == approver.branch_id)
    return query


@router.get("/admin/manual-leave/filter-options")
async def list_manual_leave_employee_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Branches and departments visible to the current manual-leave approver."""
    approver = _manual_leave_approver(db, current_user)
    scoped_users = _manual_leave_employee_scope_query(db, current_user, approver)
    rows = (
        scoped_users.order_by(None)
        .with_entities(User.departmentId, User.workplace)
        .distinct()
        .all()
    )
    department_ids = {int(row[0]) for row in rows if row[0] is not None}
    branch_ids = {int(row[1]) for row in rows if row[1] is not None}
    current_branch_id = _current_workplace_id(current_user)
    if current_branch_id is not None:
        branch_ids.add(current_branch_id)
    department_names = _department_name_map(db, department_ids)
    branch_names = {
        int(branch.id): str(branch.branch_name)
        for branch in (
            db.query(Branch).filter(Branch.id.in_(sorted(branch_ids))).all()
            if branch_ids
            else []
        )
    }

    departments = [
        {"id": item_id, "name": department_names[item_id]}
        for item_id in department_ids
        if item_id in department_names
    ]
    branches = [
        {"id": item_id, "name": branch_names[item_id]}
        for item_id in branch_ids
        if item_id in branch_names
    ]
    departments.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    branches.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    return {
        "departments": departments,
        "branches": branches,
        "current_branch_id": current_branch_id,
    }


@router.get("/admin/manual-leave/employees")
async def list_manual_leave_employees(
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    is_foreigner: Optional[int] = Query(None, description="1=Khmer, 2=Foreigner"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    include_avatar: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Employees an authorized approver may record manual leave for."""
    approver = _manual_leave_approver(db, current_user)
    query = _manual_leave_employee_scope_query(db, current_user, approver)
    if branch_id is not None:
        query = query.filter(User.workplace == branch_id)
    if department_id is not None:
        query = query.filter(User.departmentId == department_id)
    if is_foreigner is not None:
        query = query.filter(User.isForeigner == is_foreigner)
    if user_ids:
        parsed_ids = sorted(
            {
                int(value.strip())
                for value in user_ids.split(",")
                if value.strip().isdigit() and int(value.strip()) > 0
            }
        )
        if len(parsed_ids) > 500:
            raise HTTPException(status_code=400, detail="At most 500 users can be requested")
        query = query.filter(User.id.in_(parsed_ids or [-1]))
    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions = [
            User.eName.like(term),
            User.kName.like(term),
            User.username.like(term),
            User.email.like(term),
        ]
        if search.strip().isdigit():
            conditions.append(User.id == int(search.strip()))
        query = query.filter(or_(*conditions))

    total = query.order_by(None).count()
    users_page = (
        query.order_by(User.eName.asc(), User.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    user_map = {int(user.id): user for user in users_page}
    avatars: Dict[int, str] = {}
    if include_avatar:
        _, avatars = _user_maps(db, list(user_map.keys()))
    dept_names, branch_names = _name_maps(db, user_map)
    users_out = [
        {
            "user_id": int(user.id),
            **_employee_name_fields(user),
            "avatar": avatars.get(int(user.id)),
            "department_id": getattr(user, "departmentId", None),
            "department_name": dept_names.get(
                int(getattr(user, "departmentId", 0) or 0)
            ),
            "branch_id": getattr(user, "workplace", None),
            "branch_name": branch_names.get(int(getattr(user, "workplace", 0) or 0)),
            "is_foreigner": getattr(user, "isForeigner", None),
        }
        for user in users_page
    ]
    return {
        "users": users_out,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
    }


def _balance_adjustment_employee_scope_query(
    db: Session,
    current_user: User,
    approver: LeaveApprover,
):
    """Base employee query shared by policy-adjustment filters and results."""
    query = db.query(User).filter(
        User.status == 1,
        User.id != int(current_user.id),
    )
    if not bool(approver.can_approve_all):
        if not _approver_has_decision_scope(approver):
            return query.filter(User.id < 0)
        if approver.department_id is not None:
            query = query.filter(User.departmentId == approver.department_id)
        if approver.branch_id is not None:
            query = query.filter(User.workplace == approver.branch_id)
    return query


@router.get(
    "/admin/balance-adjustments/filter-options",
    dependencies=[Depends(require_feature_unlocked("adjust_leave_balance"))],
)
async def list_balance_adjustment_employee_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Branches and departments visible to the current policy-adjuster."""
    approver = _balance_adjustment_approver(db, current_user)
    scoped_users = _balance_adjustment_employee_scope_query(db, current_user, approver)
    rows = (
        scoped_users.order_by(None)
        .with_entities(User.departmentId, User.workplace)
        .distinct()
        .all()
    )
    department_ids = {int(row[0]) for row in rows if row[0] is not None}
    branch_ids = {int(row[1]) for row in rows if row[1] is not None}
    current_branch_id = _current_workplace_id(current_user)
    if current_branch_id is not None:
        branch_ids.add(current_branch_id)
    department_names = _department_name_map(db, department_ids)
    branch_names = {
        int(branch.id): str(branch.branch_name)
        for branch in (
            db.query(Branch).filter(Branch.id.in_(sorted(branch_ids))).all()
            if branch_ids
            else []
        )
    }

    departments = [
        {"id": item_id, "name": department_names[item_id]}
        for item_id in department_ids
        if item_id in department_names
    ]
    branches = [
        {"id": item_id, "name": branch_names[item_id]}
        for item_id in branch_ids
        if item_id in branch_names
    ]
    departments.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    branches.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    return {
        "departments": departments,
        "branches": branches,
        "current_branch_id": current_branch_id,
    }


@router.get(
    "/admin/balance-adjustments/employees",
    dependencies=[Depends(require_feature_unlocked("adjust_leave_balance"))],
)
async def list_balance_adjustment_employees(
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    is_foreigner: Optional[int] = Query(None, description="1=Khmer, 2=Foreigner"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    include_avatar: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Employees inside the policy-adjuster's configured approval scope."""
    approver = _balance_adjustment_approver(db, current_user)
    query = _balance_adjustment_employee_scope_query(db, current_user, approver)
    if branch_id is not None:
        query = query.filter(User.workplace == branch_id)
    if department_id is not None:
        query = query.filter(User.departmentId == department_id)
    if is_foreigner is not None:
        query = query.filter(User.isForeigner == is_foreigner)
    if user_ids:
        parsed_ids = sorted(
            {
                int(value.strip())
                for value in user_ids.split(",")
                if value.strip().isdigit() and int(value.strip()) > 0
            }
        )
        if len(parsed_ids) > 500:
            raise HTTPException(status_code=400, detail="At most 500 users can be requested")
        query = query.filter(User.id.in_(parsed_ids or [-1]))
    if search and search.strip():
        value = search.strip()
        term = f"%{value}%"
        conditions = [
            User.eName.like(term),
            User.kName.like(term),
            User.username.like(term),
            User.email.like(term),
        ]
        if value.isdigit():
            conditions.append(User.id == int(value))
        query = query.filter(or_(*conditions))

    total = query.order_by(None).count()
    users_page = (
        query.order_by(User.eName.asc(), User.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    user_map = {int(user.id): user for user in users_page}
    avatars: Dict[int, str] = {}
    if include_avatar:
        _, avatars = _user_maps(db, list(user_map.keys()))
    dept_names, branch_names = _name_maps(db, user_map)
    return {
        "users": [
            {
                "user_id": int(user.id),
                **_employee_name_fields(user),
                "avatar": avatars.get(int(user.id)),
                "department_id": getattr(user, "departmentId", None),
                "department_name": dept_names.get(
                    int(getattr(user, "departmentId", 0) or 0)
                ),
                "branch_id": getattr(user, "workplace", None),
                "branch_name": branch_names.get(
                    int(getattr(user, "workplace", 0) or 0)
                ),
                "is_foreigner": getattr(user, "isForeigner", None),
            }
            for user in users_page
        ],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
    }


@router.post(
    "/admin/balance-adjustments/context",
    response_model=ManualLeaveBalanceContextOut,
    dependencies=[Depends(require_feature_unlocked("adjust_leave_balance"))],
)
async def balance_adjustment_context(
    payload: LeaveBalanceAdjustmentContextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Active-year balance preview before a policy deduction is submitted."""
    approver = _balance_adjustment_approver(db, current_user)
    user_ids = sorted({int(value) for value in payload.user_ids if int(value) > 0})
    if int(current_user.id) in user_ids:
        raise HTTPException(status_code=403, detail="You cannot adjust your own leave balance")
    targets = db.query(User).filter(User.id.in_(user_ids)).all()
    target_by_id = {int(user.id): user for user in targets}
    missing = [value for value in user_ids if value not in target_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Employee not found: {missing[0]}")
    for user_id in user_ids:
        target = target_by_id[user_id]
        if not _approver_scope_matches(approver, target):
            raise HTTPException(
                status_code=403,
                detail=f"{_display_name(target)} is outside your leave adjustment scope",
            )

    academic_id = _active_academic_id(db)
    academic = _academic_details(db, academic_id)
    leave_types = (
        db.query(LeaveType)
        .filter(LeaveType.is_active.isnot(False))
        .order_by(*_leave_type_ordering())
        .all()
    )
    type_columns = [
        LeaveBalanceTypeColumnOut(
            leave_type_id=int(leave_type.id),
            leave_type_name=str(leave_type.name),
            allocated_days=round(_allocated_days(db, leave_type, academic_id), 2),
        )
        for leave_type in leave_types
    ]
    users_out: List[AdminUserLeaveBalancesOut] = []
    for user_id in user_ids:
        values: List[UserLeaveBalanceValueOut] = []
        for leave_type in leave_types:
            balance = _leave_balance_value(db, user_id, leave_type, academic_id)
            values.append(
                UserLeaveBalanceValueOut(
                    leave_type_id=int(leave_type.id),
                    taken_days=balance.taken_days,
                    pending_days=balance.pending_days,
                    policy_deduction_days=balance.policy_deduction_days,
                    remaining_days=balance.remaining_days,
                )
            )
        users_out.append(AdminUserLeaveBalancesOut(user_id=user_id, balances=values))
    return ManualLeaveBalanceContextOut(
        academic_id=academic_id,
        academic_name=str(academic[2] or academic[1] or f"Academic year #{academic_id}"),
        academic_start=academic[3],
        academic_end=academic[4],
        uses_active_academic_override=False,
        leave_types=type_columns,
        users=users_out,
    )


@router.post(
    "/admin/balance-adjustments",
    response_model=List[LeaveBalanceAdjustmentOut],
    dependencies=[Depends(require_feature_unlocked("adjust_leave_balance"))],
)
async def create_balance_adjustments(
    payload: LeaveBalanceAdjustmentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Deduct allowance under policy without creating leave or attendance rows."""
    approver = _balance_adjustment_approver(db, current_user)
    reason = (payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="A clear policy reason is required")
    amount_days = round(float(payload.amount_days), 2)
    if amount_days <= 0:
        raise HTTPException(status_code=400, detail="Deduction must be greater than zero")

    user_ids = sorted({int(value) for value in payload.user_ids if int(value) > 0})
    if int(current_user.id) in user_ids:
        raise HTTPException(status_code=403, detail="You cannot adjust your own leave balance")
    leave_type = (
        db.query(LeaveType)
        .filter(LeaveType.id == payload.leave_type_id, LeaveType.is_active.isnot(False))
        .first()
    )
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")

    targets = (
        db.query(User)
        .filter(User.id.in_(user_ids))
        .order_by(User.id.asc())
        .with_for_update()
        .all()
    )
    target_by_id = {int(user.id): user for user in targets}
    missing = [value for value in user_ids if value not in target_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Employee not found: {missing[0]}")
    academic_id = _active_academic_id(db)
    _academic_details(db, academic_id)
    allocated = _allocated_days(db, leave_type, academic_id)

    created: List[LeaveBalanceAdjustment] = []
    for user_id in user_ids:
        target = target_by_id[user_id]
        if getattr(target, "status", None) != 1:
            raise HTTPException(status_code=400, detail=f"{_display_name(target)} is inactive")
        if not _approver_scope_matches(approver, target):
            raise HTTPException(
                status_code=403,
                detail=f"{_display_name(target)} is outside your leave adjustment scope",
            )
        taken = _sum_day_costs(
            db, user_id, int(leave_type.id), academic_id, ["approved"]
        )
        pending = _sum_day_costs(
            db, user_id, int(leave_type.id), academic_id, ["pending"]
        )
        deductions = _sum_policy_deductions(
            db, user_id, int(leave_type.id), academic_id
        )
        available = allocated - taken - pending - deductions
        if amount_days > available + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{_display_name(target)} has only "
                    f"{max(0.0, round(available, 2)):g} day(s) available for "
                    f"{leave_type.name}; {round(pending, 2):g} day(s) are pending"
                ),
            )
        adjustment = LeaveBalanceAdjustment(
            user_id=user_id,
            leave_type_id=int(leave_type.id),
            academic_id=academic_id,
            amount_days=amount_days,
            effective_date=_today_kh(),
            reason=reason,
            created_by=int(current_user.id),
            status="active",
        )
        db.add(adjustment)
        db.flush()
        created.append(adjustment)

    db.commit()
    for adjustment in created:
        db.refresh(adjustment)
    background_tasks.add_task(
        leave_notify.notify_leave_balance_adjusted,
        [int(adjustment.id) for adjustment in created],
        int(current_user.id),
    )
    return [
        _serialize_balance_adjustment(db, adjustment)
        for adjustment in created
    ]


@router.get(
    "/admin/balance-adjustments",
    response_model=List[LeaveBalanceAdjustmentOut],
    dependencies=[Depends(require_feature_unlocked("adjust_leave_balance"))],
)
async def list_balance_adjustments(
    user_id: Optional[int] = Query(None),
    academic_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    approver = _balance_adjustment_approver(db, current_user)
    query = db.query(LeaveBalanceAdjustment).join(
        User, LeaveBalanceAdjustment.user_id == User.id
    )
    if not bool(approver.can_approve_all):
        if not _approver_has_decision_scope(approver):
            query = query.filter(LeaveBalanceAdjustment.id < 0)
        else:
            if approver.department_id is not None:
                query = query.filter(User.departmentId == approver.department_id)
            if approver.branch_id is not None:
                query = query.filter(User.workplace == approver.branch_id)
    if user_id is not None:
        query = query.filter(LeaveBalanceAdjustment.user_id == user_id)
    query = query.filter(
        LeaveBalanceAdjustment.academic_id == (academic_id or _active_academic_id(db))
    )
    rows = query.order_by(LeaveBalanceAdjustment.created_at.desc()).limit(limit).all()
    return [_serialize_balance_adjustment(db, row) for row in rows]


@router.post(
    "/admin/balance-adjustments/{adjustment_id}/void",
    response_model=LeaveBalanceAdjustmentOut,
    dependencies=[Depends(require_feature_unlocked("adjust_leave_balance"))],
)
async def void_balance_adjustment(
    adjustment_id: int,
    payload: LeaveBalanceAdjustmentVoid,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    approver = _balance_adjustment_approver(db, current_user)
    adjustment = (
        db.query(LeaveBalanceAdjustment)
        .filter(LeaveBalanceAdjustment.id == adjustment_id)
        .with_for_update()
        .first()
    )
    if adjustment is None:
        raise HTTPException(status_code=404, detail="Leave balance deduction not found")
    target = db.query(User).filter(User.id == adjustment.user_id).first()
    if target is None or not _approver_scope_matches(approver, target):
        raise HTTPException(status_code=403, detail="Deduction is outside your scope")
    if adjustment.status != "active":
        raise HTTPException(status_code=400, detail="This deduction was already reversed")
    reason = (payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="A reversal reason is required")
    adjustment.status = "voided"
    adjustment.voided_by = int(current_user.id)
    adjustment.void_reason = reason
    adjustment.voided_at = _now_utc()
    db.commit()
    db.refresh(adjustment)
    background_tasks.add_task(
        leave_notify.notify_leave_balance_adjustment_voided,
        int(adjustment.id),
        int(current_user.id),
    )
    return _serialize_balance_adjustment(db, adjustment)


@router.post(
    "/admin/manual-leave/balances",
    response_model=ManualLeaveBalanceContextOut,
    dependencies=[Depends(require_feature_unlocked("record_staff_leave"))],
)
async def manual_leave_balance_context(
    payload: ManualLeaveBalanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Return creation-time balances for employees in the approver's scope.

    This subtracts both approved and pending leave across the whole owning
    academic year, matching the final manual-leave mutation's balance check.
    """
    approver = _manual_leave_approver(db, current_user)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    if (payload.end_date - payload.start_date).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range too large (max {MAX_RANGE_DAYS} days)",
        )

    academic_id = _manual_leave_academic_id(
        db,
        payload.start_date,
        payload.end_date,
        payload.use_active_academic_year,
        payload.academic_id,
    )
    academic = _academic_details(db, academic_id)
    user_ids = sorted({int(user_id) for user_id in payload.user_ids if int(user_id) > 0})
    if not user_ids:
        raise HTTPException(status_code=400, detail="Choose at least one employee")
    if int(current_user.id) in user_ids:
        raise HTTPException(
            status_code=403,
            detail="You cannot create manually-approved leave for yourself",
        )

    targets = db.query(User).filter(User.id.in_(user_ids)).all()
    target_by_id = {int(user.id): user for user in targets}
    missing_ids = [user_id for user_id in user_ids if user_id not in target_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Employee not found: {missing_ids[0]}")
    for user_id in user_ids:
        target = target_by_id[user_id]
        if getattr(target, "status", None) != 1:
            raise HTTPException(status_code=400, detail=f"{_display_name(target)} is inactive")
        if not _approver_scope_matches(approver, target):
            raise HTTPException(
                status_code=403,
                detail=f"{_display_name(target)} is outside your leave approval scope",
            )

    leave_types = (
        db.query(LeaveType)
        .filter(LeaveType.is_active.isnot(False))
        .order_by(*_leave_type_ordering())
        .all()
    )
    leave_type_ids = [int(leave_type.id) for leave_type in leave_types]
    allocations = {
        int(allocation.leave_type_id): allocation
        for allocation in db.query(LeaveTypeAllocation)
        .filter(
            LeaveTypeAllocation.academic_id == academic_id,
            LeaveTypeAllocation.leave_type_id.in_(leave_type_ids or [0]),
        )
        .all()
    }
    allocated_by_type: Dict[int, float] = {}
    type_columns: List[LeaveBalanceTypeColumnOut] = []
    for leave_type in leave_types:
        leave_type_id = int(leave_type.id)
        allocation = allocations.get(leave_type_id)
        allocated = (
            float(allocation.allocated_days or 0)
            if allocation is not None and allocation.is_active is not False
            else float(leave_type.max_days_per_year or 0)
        )
        allocated = round(allocated, 2)
        allocated_by_type[leave_type_id] = allocated
        type_columns.append(
            LeaveBalanceTypeColumnOut(
                leave_type_id=leave_type_id,
                leave_type_name=str(leave_type.name),
                allocated_days=allocated,
                monthly_cap_days=leave_monthly_policy.effective_cap(leave_type),
            )
        )

    usage_by_user_and_type: Dict[Tuple[int, int], Dict[str, float]] = {}
    if user_ids and leave_type_ids:
        usage_rows = (
            db.query(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.status,
                func.coalesce(func.sum(_PAID_COST), 0.0),
                func.coalesce(func.sum(_UNPAID_COST), 0.0),
            )
            .join(LeaveRequestDay, LeaveRequestDay.leave_request_id == LeaveRequest.id)
            .filter(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.leave_type_id.in_(leave_type_ids),
                LeaveRequest.academic_id == academic_id,
                LeaveRequest.status.in_(["approved", "pending"]),
            )
            .group_by(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.status,
            )
            .all()
        )
        for user_id, leave_type_id, status, paid_total, unpaid_total in usage_rows:
            entry = usage_by_user_and_type.setdefault(
                (int(user_id), int(leave_type_id)),
                {
                    "approved": 0.0,
                    "pending": 0.0,
                    "approved_unpaid": 0.0,
                    "pending_unpaid": 0.0,
                },
            )
            entry[str(status)] = float(paid_total or 0)
            entry[f"{status}_unpaid"] = float(unpaid_total or 0)

    deductions_by_user_and_type: Dict[Tuple[int, int], float] = {}
    if user_ids and leave_type_ids:
        deduction_rows = (
            db.query(
                LeaveBalanceAdjustment.user_id,
                LeaveBalanceAdjustment.leave_type_id,
                func.coalesce(func.sum(LeaveBalanceAdjustment.amount_days), 0.0),
            )
            .filter(
                LeaveBalanceAdjustment.user_id.in_(user_ids),
                LeaveBalanceAdjustment.leave_type_id.in_(leave_type_ids),
                LeaveBalanceAdjustment.academic_id == academic_id,
                LeaveBalanceAdjustment.status == "active",
            )
            .group_by(
                LeaveBalanceAdjustment.user_id,
                LeaveBalanceAdjustment.leave_type_id,
            )
            .all()
        )
        deductions_by_user_and_type = {
            (int(user_id), int(leave_type_id)): float(total or 0)
            for user_id, leave_type_id, total in deduction_rows
        }

    # Manual creation must also reserve allowance already held by pending
    # employee requests; the UI uses this value as the true available amount.

    users: List[AdminUserLeaveBalancesOut] = []
    for user_id in user_ids:
        balances: List[UserLeaveBalanceValueOut] = []
        for leave_type_id in leave_type_ids:
            usage = usage_by_user_and_type.get(
                (user_id, leave_type_id),
                {
                    "approved": 0.0,
                    "pending": 0.0,
                    "approved_unpaid": 0.0,
                    "pending_unpaid": 0.0,
                },
            )
            taken = round(float(usage["approved"]), 2)
            pending = round(float(usage["pending"]), 2)
            unpaid = round(float(usage.get("approved_unpaid", 0.0)), 2)
            pending_unpaid = round(float(usage.get("pending_unpaid", 0.0)), 2)
            policy_deductions = round(
                deductions_by_user_and_type.get((user_id, leave_type_id), 0.0),
                2,
            )
            balances.append(
                UserLeaveBalanceValueOut(
                    leave_type_id=leave_type_id,
                    taken_days=taken,
                    pending_days=pending,
                    unpaid_days=unpaid,
                    pending_unpaid_days=pending_unpaid,
                    policy_deduction_days=policy_deductions,
                    # Paid days only: the manual-leave form shows this as the
                    # remaining paid balance, and a leave type with a monthly
                    # cap can still record days beyond it as deducted.
                    remaining_days=round(
                        max(
                            0.0,
                            allocated_by_type[leave_type_id]
                            - taken
                            - pending
                            - policy_deductions,
                        ),
                        2,
                    ),
                )
            )
        users.append(AdminUserLeaveBalancesOut(user_id=user_id, balances=balances))

    return ManualLeaveBalanceContextOut(
        academic_id=academic_id,
        academic_name=str(academic[2] or academic[1] or f"Academic year #{academic_id}"),
        academic_start=academic[3],
        academic_end=academic[4],
        uses_active_academic_override=payload.use_active_academic_year,
        leave_types=type_columns,
        users=users,
    )


@router.post(
    "/admin/manual-leave/preview",
    response_model=LeavePreviewResponse,
    dependencies=[Depends(require_feature_unlocked("record_staff_leave"))],
)
async def preview_manual_leave_days(
    payload: ManualLeavePreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Resolve a target employee's sessions for the manual leave form.

    The target must be active and inside the approver's scope. Past dates are
    intentionally supported because an authorized approver may correct
    historical leave.
    """
    approver = _manual_leave_approver(db, current_user)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    if (payload.end_date - payload.start_date).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range too large (max {MAX_RANGE_DAYS} days)",
        )

    target = db.query(User).filter(User.id == payload.user_id).first()
    if target is None or getattr(target, "status", None) != 1:
        raise HTTPException(status_code=404, detail="Employee not found or inactive")
    if int(target.id) == int(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You cannot create manually-approved leave for yourself",
        )
    if not _approver_scope_matches(approver, target):
        raise HTTPException(status_code=403, detail="Employee is outside your approval scope")
    holidays = _holidays_in_range(db, payload.start_date, payload.end_date)
    existing = _existing_leave_days(
        db,
        int(target.id),
        payload.start_date,
        payload.end_date,
    )
    employment_start = _user_employment_boundary(target, "startWork")
    employment_end = _user_employment_boundary(target, "endWork")
    days: List[PreviewDayOut] = []
    current = payload.start_date
    while current <= payload.end_date:
        holiday_name = holidays.get(current)
        inside_employment = (
            (employment_start is None or current >= employment_start)
            and (employment_end is None or current <= employment_end)
        )
        if holiday_name is not None or not inside_employment:
            days.append(
                PreviewDayOut(
                    leave_date=current,
                    is_working_day=False,
                    holiday_name=holiday_name,
                    day_type="Holiday" if holiday_name is not None else "Outside employment",
                    sessions=[],
                    already_requested=current in existing,
                )
            )
        else:
            day_info = get_effective_day_attendance(db, target, current)
            sessions = day_info.get("sessions") or []
            covered, _ = _covered_session_indexes(
                existing.get(current, []), len(sessions)
            )
            days.append(
                PreviewDayOut(
                    leave_date=current,
                    is_working_day=bool(day_info.get("is_active_day")),
                    day_type=day_info.get("day_type"),
                    sessions=[
                        PreviewSessionOut(
                            index=index + 1,
                            start=str(session.get("start")),
                            end=str(session.get("end")),
                        )
                        for index, session in enumerate(sessions)
                    ],
                    already_requested=bool(existing.get(current)),
                    requested_session_indexes=sorted(covered),
                )
            )
        current += timedelta(days=1)
    return LeavePreviewResponse(days=days)


@router.post(
    "/admin/manual-leave",
    response_model=List[LeaveRequestOut],
    dependencies=[Depends(require_feature_unlocked("record_staff_leave"))],
)
async def create_manual_leave(
    payload: ManualLeaveCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Create immediately-approved, audited leave for one or more employees.

    Past and future dates are allowed. Holidays and non-working dates are not
    charged. Every target is validated before the transaction commits, so a
    partial batch can never silently consume only some employees' balances.
    """
    approver = _manual_leave_approver(db, current_user)
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Reason is required")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    if (payload.end_date - payload.start_date).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range too large (max {MAX_RANGE_DAYS} days)",
        )

    explicit_day_inputs = {}
    for item in sorted(payload.days or [], key=lambda value: value.leave_date):
        if item.leave_date in explicit_day_inputs:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate date {item.leave_date}",
            )
        if item.leave_date < payload.start_date or item.leave_date > payload.end_date:
            raise HTTPException(
                status_code=400,
                detail=f"Configured date {item.leave_date} is outside the selected range",
            )
        explicit_day_inputs[item.leave_date] = item

    user_ids = sorted({int(user_id) for user_id in payload.user_ids if int(user_id) > 0})
    if not user_ids:
        raise HTTPException(status_code=400, detail="Choose at least one employee")
    if int(current_user.id) in user_ids:
        raise HTTPException(
            status_code=403,
            detail="You cannot create manually-approved leave for yourself",
        )

    leave_type = (
        db.query(LeaveType)
        .filter(LeaveType.id == payload.leave_type_id)
        .first()
    )
    if leave_type is None or leave_type.is_active is False:
        raise HTTPException(status_code=404, detail="Leave type not found")

    proof_path = _validated_proof_path_for_type(
        payload.proof_image_path,
        int(current_user.id),
        leave_type,
    )

    # Run idempotent schema guards before taking employee row locks; DDL may
    # implicitly commit on MySQL and must never release a balance lock midway.
    ensure_schedule_exceptions_table(db)

    # Lock in stable id order to serialize balance changes and avoid races
    # with another manual batch targeting the same employee.
    targets = (
        db.query(User)
        .filter(User.id.in_(user_ids))
        .order_by(User.id.asc())
        .with_for_update()
        .all()
    )
    target_by_id = {int(user.id): user for user in targets}
    missing_ids = [user_id for user_id in user_ids if user_id not in target_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Employee not found: {missing_ids[0]}")
    academic_id = _manual_leave_academic_id(
        db,
        payload.start_date,
        payload.end_date,
        payload.use_active_academic_year,
        payload.academic_id,
    )
    academic = _academic_details(db, academic_id)
    allocated = _allocated_days(db, leave_type, academic_id)
    holidays = _holidays_in_range(db, payload.start_date, payload.end_date)
    # Preload schedules, assignments, and exceptions once. Without this
    # request-scoped resolver a 50-person monthly batch would issue database
    # queries for every employee/day pair.
    from .employee_attendance import _build_report_schedule_context

    day_info_for = _build_report_schedule_context(
        db,
        targets,
        payload.start_date,
        payload.end_date,
    )
    now = _now_utc()
    created: List[LeaveRequest] = []

    for user_id in user_ids:
        target = target_by_id[user_id]
        if getattr(target, "status", None) != 1:
            raise HTTPException(status_code=400, detail=f"{_display_name(target)} is inactive")
        if not _approver_scope_matches(approver, target):
            raise HTTPException(
                status_code=403,
                detail=f"{_display_name(target)} is outside your leave approval scope",
            )

        existing = _existing_leave_days(
            db,
            user_id,
            payload.start_date,
            payload.end_date,
        )
        employment_start = _user_employment_boundary(target, "startWork")
        employment_end = _user_employment_boundary(target, "endWork")
        day_rows: List[LeaveRequestDay] = []
        if explicit_day_inputs:
            selected_dates = sorted(explicit_day_inputs)
        else:
            selected_dates = [
                payload.start_date + timedelta(days=offset)
                for offset in range((payload.end_date - payload.start_date).days + 1)
            ]
        for current in selected_dates:
            inside_employment = (
                (employment_start is None or current >= employment_start)
                and (employment_end is None or current <= employment_end)
            )
            if current not in holidays and inside_employment:
                day_info = day_info_for(target, current)
                sessions = day_info.get("sessions") or []
                if day_info.get("is_active_day") and sessions:
                    item = explicit_day_inputs.get(current)
                    requested_scope = (
                        item.scope if item is not None else LeaveDayScope.FULL_DAY
                    )
                    indexes = sorted(set(item.session_indexes or [])) if item is not None else []
                    sessions_total = len(sessions)
                    if requested_scope == LeaveDayScope.SESSIONS:
                        if not indexes:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Select at least one session for {current}",
                            )
                        if any(index < 1 or index > sessions_total for index in indexes):
                            raise HTTPException(
                                status_code=400,
                                detail=(
                                    f"Invalid session selection for {_display_name(target)} "
                                    f"on {current}"
                                ),
                            )
                        if len(indexes) == sessions_total:
                            scope = "full_day"
                            indexes_value = None
                            day_cost = 1.0
                            time_from = str(sessions[0].get("start"))
                            time_to = str(sessions[-1].get("end"))
                        else:
                            scope = "sessions"
                            indexes_value = indexes
                            day_cost = round(len(indexes) / sessions_total, 4)
                            time_from = str(sessions[indexes[0] - 1].get("start"))
                            time_to = str(sessions[indexes[-1] - 1].get("end"))
                    else:
                        scope = "full_day"
                        indexes_value = None
                        day_cost = 1.0
                        time_from = str(sessions[0].get("start"))
                        time_to = str(sessions[-1].get("end"))

                    existing_rows = existing.get(current, [])
                    if existing_rows:
                        raise HTTPException(
                            status_code=409,
                            detail=_leave_date_conflict_detail(
                                [current],
                                employee_name=_display_name(target),
                            ),
                        )
                    day_rows.append(
                        LeaveRequestDay(
                            leave_date=current,
                            scope=scope,
                            session_indexes=indexes_value,
                            sessions_total=sessions_total,
                            day_cost=day_cost,
                            time_from=time_from,
                            time_to=time_to,
                        )
                    )

        total_cost = round(sum(float(row.day_cost or 0) for row in day_rows), 4)
        if total_cost <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No scheduled working dates were found for {_display_name(target)} "
                    "inside the selected range"
                ),
            )
        # max_days_can_approve limits decisions on requests submitted by
        # employees. Manual leave is a separate, explicit permission guarded
        # by can_create_for_staff, so an authorized creator is not constrained
        # by that approval-inbox limit.
        # Only the paid portion is charged. With a monthly cap configured, the
        # split already marks over-cap days and days beyond the yearly
        # allowance as salary-deducted, so staff leave can still be recorded
        # once an employee's balance is spent.
        split = leave_monthly_policy.simulate(
            db,
            user_id,
            leave_type,
            academic_id,
            {row.leave_date: float(row.day_cost) for row in day_rows},
        )
        paid_cost = float(split["paid_days"])
        taken = _sum_day_costs(
            db, user_id, int(leave_type.id), academic_id, ["approved"]
        )
        pending = _sum_day_costs(
            db, user_id, int(leave_type.id), academic_id, ["pending"]
        )
        policy_deductions = _sum_policy_deductions(
            db, user_id, int(leave_type.id), academic_id
        )
        available = allocated - taken - pending - policy_deductions
        if paid_cost > available + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Not enough {leave_type.name} balance for {_display_name(target)}: "
                    f"needs {paid_cost:g} paid day(s), available {max(0.0, round(available, 2)):g}"
                ),
            )

        request = LeaveRequest(
            user_id=user_id,
            leave_type_id=int(leave_type.id),
            start_date=day_rows[0].leave_date,
            end_date=day_rows[-1].leave_date,
            reason=reason,
            status="approved",
            approver_id=int(current_user.id),
            approval_date=now,
            academic_id=academic_id,
            total_days=total_cost,
            created_by=int(current_user.id),
            creation_source="manual",
            proof_image_path=proof_path,
        )
        request.days = day_rows
        db.add(request)
        db.flush()
        history_notes = reason
        if payload.use_active_academic_year or payload.academic_id is not None:
            academic_label = str(
                academic[2] or academic[1] or f"Academic year #{academic_id}"
            ).strip()
            selection_note = (
                "Selected academic allowance"
                if payload.academic_id is not None
                else "Active academic allowance override"
            )
            history_notes = (
                f"{reason}\n[{selection_note}: charged to "
                f"{academic_label} (academic_id={academic_id}); selected leave dates "
                f"remain {day_rows[0].leave_date} to {day_rows[-1].leave_date}.]"
            )
        _add_history(
            db,
            int(request.id),
            "manually_created",
            None,
            "approved",
            int(current_user.id),
            notes=history_notes,
        )
        leave_monthly_policy.recompute_for_request(db, request)
        created.append(request)

    db.commit()
    for request in created:
        db.refresh(request)
        _invalidate_user_requests_cache(int(request.user_id))
    background_tasks.add_task(
        leave_notify.notify_manual_leave_created,
        [int(request.id) for request in created],
        int(current_user.id),
    )
    return _serialize_requests(db, created)


@router.get("/admin/requests", response_model=List[LeaveRequestOut])
async def list_requests_for_review(
    status: Optional[str] = Query(None),
    academic_id: Optional[int] = Query(None),
    active_academic_only: bool = Query(False),
    user_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    date_basis: str = Query("leave", pattern="^(leave|submitted|decision)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Inbox for assigned approvers (scoped to their dept/branch).

    Only users with an active Leave Approvers assignment may review —
    role does not grant access.
    """
    approver = _approver_row(db, int(current_user.id))
    if approver is None:
        raise HTTPException(status_code=403, detail="Not an approver")

    # If no dates are specified, default to the current month to avoid heavy load.
    # ``date_basis`` lets the approval inbox behave like an activity inbox:
    # pending → submitted timestamp, processed → decision timestamp. The
    # default remains leave-date overlap for backwards compatibility.
    if not start_date and not end_date:
        today = _today_kh()
        import calendar
        _, last_day = calendar.monthrange(today.year, today.month)
        start_date = today.replace(day=1).isoformat()
        end_date = today.replace(day=last_day).isoformat()

    active_scope_id = _active_academic_id(db) if active_academic_only else None

    can_view_all = bool(getattr(approver, "can_view_all_requests", False))

    # v9 separates visibility from approval-day actionability. The version
    # prevents an older cached response from hiding read-only pending rows.
    cache_key = f"review:v9:{current_user.id}:{int(can_view_all)}:{status or ''}:{academic_id or ''}:{active_scope_id or ''}:{user_id or ''}:{date_basis}:{start_date or ''}:{end_date or ''}:{limit}:{offset}"
    cached = user_requests_cache.get(cache_key)
    if cached is not None:
        return cached

    query = db.query(LeaveRequest).join(User, LeaveRequest.user_id == User.id)
    query = _filter_to_approver_visibility_scope(query, approver)
    if status:
        query = query.filter(LeaveRequest.status == status)
    if active_scope_id is not None:
        query = query.filter(LeaveRequest.academic_id == active_scope_id)
    elif academic_id:
        query = query.filter(LeaveRequest.academic_id == academic_id)
    if user_id:
        query = query.filter(LeaveRequest.user_id == user_id)
    try:
        filter_start = date.fromisoformat(start_date) if start_date else None
        filter_end = date.fromisoformat(end_date) if end_date else None
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Dates must use YYYY-MM-DD format",
        )
    if filter_start and filter_end and filter_end < filter_start:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date",
        )

    if date_basis == "leave":
        if filter_start:
            query = query.filter(LeaveRequest.end_date >= filter_start)
        if filter_end:
            query = query.filter(LeaveRequest.start_date <= filter_end)
        order_column = LeaveRequest.start_date
    else:
        activity_timestamp = _review_activity_timestamp(date_basis)
        start_utc, end_exclusive_utc = _cambodia_date_filter_utc_bounds(
            filter_start,
            filter_end,
        )
        # Stored timestamps are UTC-naive. Convert Cambodia calendar-day
        # boundaries to UTC rather than applying DATE() in SQL, preserving
        # index-friendly comparisons and correct dates around midnight.
        if start_utc:
            query = query.filter(activity_timestamp >= start_utc)
        if end_exclusive_utc:
            query = query.filter(activity_timestamp < end_exclusive_utc)
        order_column = activity_timestamp

    requests = (
        query.order_by(order_column.desc(), LeaveRequest.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = _serialize_requests(
        db, requests, include_user_phone=True, current_user=current_user
    )

    # Every inbox row carries request-specific decision authority. A view-all
    # approver can therefore inspect out-of-scope/over-limit requests without
    # the client ever presenting active Approve or Reject controls.
    requesters, _ = _user_maps(db, [int(request.user_id) for request in requests])
    actionability = [
        _request_actionability(
            request,
            current_user,
            requesters.get(int(request.user_id)),
            approver,
        )
        for request in requests
    ]
    needs_decision_contacts = any(
        _can_view_decision_contacts(
            request,
            current_user,
            approver,
            access,
        )
        for request, access in zip(requests, actionability)
    )
    active_approvers = (
        db.query(LeaveApprover)
        .filter(LeaveApprover.is_active == True)  # noqa: E712
        .all()
        if needs_decision_contacts
        else []
    )
    approver_users, approver_avatars = _user_maps(
        db,
        [int(item.user_id) for item in active_approvers],
    )
    result = [
        item.model_copy(
            update={
                "can_decide": bool(access["can_decide"]),
                "can_cancel": bool(access["can_cancel"]),
                "can_cancel_reason": access.get("can_cancel_reason"),
                "decision_contacts": (
                    _decision_contacts_for_request(
                        request,
                        requesters.get(int(request.user_id)),
                        active_approvers,
                        approver_users,
                        approver_avatars,
                    )
                    if _can_view_decision_contacts(
                        request,
                        current_user,
                        approver,
                        access,
                    )
                    else []
                ),
                **_review_reminder_metadata(
                    request,
                    current_user,
                    approver,
                    access,
                ),
            }
        )
        for item, request, access in zip(result, requests, actionability)
    ]

    # Cache serialized result
    from fastapi.encoders import jsonable_encoder
    user_requests_cache.set(cache_key, jsonable_encoder(result))
    return result


@router.post("/requests/{request_id}/decision", response_model=LeaveRequestOut)
async def decide_request(
    request_id: int,
    payload: LeaveDecisionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Approve or reject. First approver to act wins (row-locked)."""
    request = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Leave request not found")

    if request.status != "pending":
        if request.status in ("approved", "rejected") and request.approver_id:
            decider = db.query(User).filter(User.id == request.approver_id).first()
            raise HTTPException(
                status_code=400,
                detail=f"Already {request.status} by {_display_name(decider)}",
            )
        raise HTTPException(status_code=400, detail=f"Request is already {request.status}")

    requester = db.query(User).filter(User.id == request.user_id).first()
    # Nobody approves their own leave — not even admins. Another approver
    # (or another admin) must make the decision.
    if int(request.user_id) == int(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You cannot approve your own leave request — another approver must decide it",
        )

    # Approval rights come ONLY from an active Leave Approvers assignment.
    # Role (admin or teacher) grants nothing here — admins who need to
    # approve must be added to the approvers list like anyone else.
    approver = _approver_row(db, int(current_user.id))
    if approver is None or requester is None or not _approver_scope_matches(approver, requester):
        raise HTTPException(
            status_code=403,
            detail="Only assigned leave approvers can decide this request",
        )
    if not approval_day_limit_allows(
        approver.max_days_can_approve,
        request.total_days,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                f"This request ({float(request.total_days or 0):g} days) exceeds your "
                f"approval limit of {float(approver.max_days_can_approve):g} days"
            ),
        )

    note = (payload.note or "").strip() or None
    if payload.action == DecisionAction.REJECT and note is None:
        raise HTTPException(
            status_code=400,
            detail="A rejection reason is required",
        )

    # Approver may override the covering colleague: >0 sets, 0 clears,
    # null/omitted keeps whatever the requester proposed.
    replacement_changed = False
    if payload.replacement_user_id is not None:
        if payload.replacement_user_id == 0:
            replacement_changed = request.replacement_user_id is not None
            request.replacement_user_id = None
        else:
            replacement = _validate_replacement(
                db, payload.replacement_user_id, int(request.user_id)
            )
            replacement_changed = request.replacement_user_id != int(replacement.id)
            request.replacement_user_id = int(replacement.id)

    old_status = str(request.status)
    if payload.action == DecisionAction.APPROVE:
        request.status = "approved"
        request.approver_id = int(current_user.id)
        request.approval_date = _now_utc()
        request.rejection_reason = note
        request.replacement_note = (payload.replacement_note or "").strip() or None
        action = "approved"
    else:
        request.status = "rejected"
        request.approver_id = int(current_user.id)
        request.approval_date = _now_utc()
        request.rejection_reason = note
        request.replacement_note = None
        action = "rejected"

    history_note = note
    if replacement_changed:
        changed_label = "Replacement cleared" if request.replacement_user_id is None else (
            f"Replacement changed to user #{request.replacement_user_id}"
        )
        history_note = f"{note} · {changed_label}" if note else changed_label

    _add_history(db, int(request.id), action, old_status, str(request.status), int(current_user.id), notes=history_note)
    # A rejection releases the request's monthly-cap slots; an approval keeps
    # them. Either way the whole month is re-split so the surviving days carry
    # the correct paid/unpaid values.
    try:
        db.flush()
        leave_monthly_policy.recompute_for_request(db, request)
    except Exception:
        db.rollback()
        raise
    db.commit()
    db.refresh(request)

    _invalidate_user_requests_cache(int(request.user_id))

    background_tasks.add_task(
        leave_notify.notify_leave_request_decided, int(request.id), int(current_user.id)
    )
    return _serialize_requests(db, [request])[0]
