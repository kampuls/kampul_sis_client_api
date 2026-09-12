"""
Monthly leave cap — the single authority for the paid/unpaid day split.

``LeaveType.max_days_per_month`` limits how much of an employee's annual
allowance one calendar month may consume. Leave beyond the cap is still
granted; it simply costs no allowance and is recorded as unpaid so payroll and
reports can act on it.

The split lives on ``LeaveRequestDay`` as ``paid_cost`` + ``unpaid_cost``,
which always sum to the untouched ``day_cost``. Because it is derived, it can
be recomputed at any time — clearing a cap restores every day to fully paid, so
no leave is ever lost by changing the policy.

Allocation rule: inside one (user, leave type, academic year, calendar month)
bucket, pending and approved days fill the cap chronologically by leave date,
ties broken by request creation order. A day that straddles the cap boundary is
split fractionally, which keeps session (half-day) leave exact.
"""

from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.leave_management import (
    LeaveBalanceAdjustment,
    LeaveRequest,
    LeaveRequestDay,
    LeaveType,
    LeaveTypeAllocation,
)

# Statuses that consume the monthly cap. Rejected and cancelled leave releases
# its slot so a later day can be promoted back to paid.
COUNTED_STATUSES = ("pending", "approved")

# Costs are stored as floats; compare with the same tolerance the balance
# checks already use so a 3-session day never leaks a rounding remainder.
_EPSILON = 1e-9

MonthKey = Tuple[int, int]


def month_key(value: date) -> MonthKey:
    """Calendar month bucket a leave date belongs to."""
    return (value.year, value.month)


def month_label(key: MonthKey) -> str:
    """Stable ``YYYY-MM`` identifier for API responses."""
    return f"{key[0]:04d}-{key[1]:02d}"


def effective_cap(leave_type: LeaveType) -> Optional[float]:
    """Configured monthly cap, or None when the policy is disabled.

    NULL and 0 both mean "no monthly limit", so an administrator can turn the
    policy off by clearing the field or typing 0.
    """
    raw = getattr(leave_type, "max_days_per_month", None)
    if raw is None:
        return None
    cap = float(raw)
    return cap if cap > 0 else None


def paid_cost_of(day: LeaveRequestDay) -> float:
    """Allowance-charged part of a day, treating an unsplit row as fully paid."""
    if day.paid_cost is None:
        return float(day.day_cost or 0)
    return float(day.paid_cost)


def unpaid_cost_of(day: LeaveRequestDay) -> float:
    """Over-cap part of a day, treating an unsplit row as fully paid."""
    if day.unpaid_cost is None:
        return 0.0
    return float(day.unpaid_cost)


def paid_allowance(
    db: Session, user_id: int, leave_type: LeaveType, academic_id: int
) -> float:
    """Paid days available for the year: allocation minus policy deductions.

    Mirrors the allocation fallback used by the balance endpoints — a
    per-year allocation row when one is configured and active, otherwise the
    leave type's own default.
    """
    allocation = (
        db.query(LeaveTypeAllocation)
        .filter(
            LeaveTypeAllocation.leave_type_id == int(leave_type.id),
            LeaveTypeAllocation.academic_id == academic_id,
        )
        .first()
    )
    if allocation is not None and allocation.is_active is not False:
        allocated = float(allocation.allocated_days or 0)
    else:
        allocated = float(leave_type.max_days_per_year or 0)

    deductions = float(
        db.query(func.coalesce(func.sum(LeaveBalanceAdjustment.amount_days), 0.0))
        .filter(
            LeaveBalanceAdjustment.user_id == user_id,
            LeaveBalanceAdjustment.leave_type_id == int(leave_type.id),
            LeaveBalanceAdjustment.academic_id == academic_id,
            LeaveBalanceAdjustment.status == "active",
        )
        .scalar()
        or 0
    )
    return max(0.0, allocated - deductions)


def _split_day(cost: float, room: float) -> Tuple[float, float]:
    """Split one day's cost against the paid room left, guarding float noise."""
    paid = min(cost, max(0.0, room))
    unpaid = cost - paid
    if unpaid <= _EPSILON:
        return round(cost, 4), 0.0
    if paid <= _EPSILON:
        return 0.0, round(cost, 4)
    return round(paid, 4), round(unpaid, 4)


def _ordered_days(
    db: Session,
    user_id: int,
    leave_type_id: int,
    academic_id: int,
) -> List[LeaveRequestDay]:
    """Every cap-consuming day of one employee for the year, in date order.

    The whole year is loaded because the yearly allowance is consumed
    chronologically across months: changing one month can move a later
    month's day between paid and unpaid. Ordering is applied in Python so the
    caller gets exactly the sequence the split uses, without depending on
    database collation of the join.
    """
    rows = (
        db.query(LeaveRequestDay, LeaveRequest)
        .join(LeaveRequest, LeaveRequestDay.leave_request_id == LeaveRequest.id)
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type_id == leave_type_id,
            LeaveRequest.academic_id == academic_id,
            LeaveRequest.status.in_(COUNTED_STATUSES),
        )
        .all()
    )
    entries = [
        (day.leave_date, int(request.id), day) for day, request in rows
    ]
    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry[2] for entry in entries]


def _paid_room(
    cost: float,
    cap: Optional[float],
    month_consumed: float,
    paid_so_far: float,
    allowance: Optional[float],
) -> float:
    """Paid days still available for this day, under both limits."""
    if cap is None:
        # No monthly policy: the balance check governs instead, so leave the
        # day fully paid rather than inventing unpaid days.
        return cost
    room = max(0.0, cap - month_consumed)
    if allowance is not None:
        room = min(room, max(0.0, allowance - paid_so_far))
    return room


def recompute_user_type(
    db: Session,
    user_id: int,
    leave_type: LeaveType,
    academic_id: int,
) -> Dict[str, float]:
    """Rewrite the paid/unpaid split for one employee and leave type.

    Two limits apply, both filled chronologically. A day is paid only while
    its calendar month is still under the monthly cap *and* the yearly paid
    allowance has not run out; anything else is granted salary-deducted. That
    second limit is what lets an employee keep requesting leave after their
    allowance is spent, with every further day correctly marked unpaid.

    The caller owns the transaction — this only flushes. Returns the totals
    after the recompute plus how much moved, so callers can report "N days
    returned to the balance".
    """
    cap = effective_cap(leave_type)
    allowance = (
        paid_allowance(db, user_id, leave_type, academic_id)
        if cap is not None
        else None
    )
    days = _ordered_days(db, user_id, int(leave_type.id), academic_id)

    month_consumed: Dict[MonthKey, float] = {}
    paid_total = 0.0
    unpaid_total = 0.0
    unpaid_before = 0.0
    changed_days = 0
    for day in days:
        cost = float(day.day_cost or 0)
        key = month_key(day.leave_date)
        paid, unpaid = _split_day(
            cost,
            _paid_room(
                cost, cap, month_consumed.get(key, 0.0), paid_total, allowance
            ),
        )
        unpaid_before += unpaid_cost_of(day)
        if (
            day.paid_cost is None
            or abs(paid_cost_of(day) - paid) > _EPSILON
            or abs(unpaid_cost_of(day) - unpaid) > _EPSILON
        ):
            day.paid_cost = paid
            day.unpaid_cost = unpaid
            changed_days += 1
        month_consumed[key] = month_consumed.get(key, 0.0) + cost
        paid_total += paid
        unpaid_total += unpaid

    if changed_days:
        db.flush()
    return {
        "paid_days": round(paid_total, 4),
        "unpaid_days": round(unpaid_total, 4),
        # Positive when the recompute gave allowance back to the employee.
        "restored_days": round(max(0.0, unpaid_before - unpaid_total), 4),
        "newly_unpaid_days": round(max(0.0, unpaid_total - unpaid_before), 4),
        "changed_days": float(changed_days),
    }


def recompute_for_request(db: Session, request: LeaveRequest) -> Dict[str, float]:
    """Re-split the employee's year after a request's status or days change.

    Call this from each mutation path (submit, manual entry, decision,
    cancellation). The whole year is redone rather than just the request's own
    rows because both limits are consumed chronologically: cancelling an early
    paid day promotes a later over-cap day, and freeing yearly allowance can
    promote a day in an entirely different month.
    """
    leave_type = (
        db.query(LeaveType).filter(LeaveType.id == request.leave_type_id).first()
    )
    if leave_type is None or request.academic_id is None:
        return {}
    return recompute_user_type(
        db,
        int(request.user_id),
        leave_type,
        int(request.academic_id),
    )


def recompute_leave_type(
    db: Session,
    leave_type: LeaveType,
    academic_id: int,
) -> Dict[str, float]:
    """Re-split a whole academic year for every employee holding this leave.

    Used when a cap is introduced, changed, or cleared. Clearing a cap restores
    every day to paid, returning the previously unpaid days to the balances.
    """
    user_ids = [
        int(row[0])
        for row in db.query(LeaveRequest.user_id)
        .filter(
            LeaveRequest.leave_type_id == int(leave_type.id),
            LeaveRequest.academic_id == academic_id,
            LeaveRequest.status.in_(COUNTED_STATUSES),
        )
        .distinct()
        .all()
    ]

    totals = {
        "paid_days": 0.0,
        "unpaid_days": 0.0,
        "restored_days": 0.0,
        "newly_unpaid_days": 0.0,
        "changed_days": 0.0,
        "affected_users": 0.0,
    }
    for user_id in user_ids:
        result = recompute_user_type(db, user_id, leave_type, academic_id)
        for key in ("paid_days", "unpaid_days", "restored_days", "newly_unpaid_days", "changed_days"):
            totals[key] += result.get(key, 0.0)
        if result.get("changed_days"):
            totals["affected_users"] += 1
    for key in totals:
        totals[key] = round(totals[key], 4)
    return totals


def simulate(
    db: Session,
    user_id: int,
    leave_type: LeaveType,
    academic_id: int,
    new_day_costs: Dict[date, float],
    exclude_request_id: Optional[int] = None,
) -> Dict[str, object]:
    """Split a *hypothetical* request without writing anything.

    Powers the pre-submit warning and the paid-portion balance check, so the
    client never has to reimplement the allocation rule. ``new_day_costs`` maps
    each proposed leave date to its day cost.

    Runs the same chronological walk over the whole year as the stored
    recompute, with the proposed days merged in, so the preview cannot
    disagree with what submission will store.
    """
    cap = effective_cap(leave_type)
    allowance = (
        paid_allowance(db, user_id, leave_type, academic_id)
        if cap is not None
        else None
    )
    existing = [
        day
        for day in _ordered_days(db, user_id, int(leave_type.id), academic_id)
        if exclude_request_id is None
        or int(day.leave_request_id) != int(exclude_request_id)
    ]

    # A brand-new request sorts after same-date existing leave, matching the
    # (leave_date, request_id) order the stored recompute will apply.
    merged: List[Tuple[date, float, bool]] = [
        (day.leave_date, float(day.day_cost or 0), False) for day in existing
    ]
    merged.extend(
        (leave_date, float(cost), True)
        for leave_date, cost in new_day_costs.items()
    )
    merged.sort(key=lambda item: (item[0], item[2]))

    proposed_months = {month_key(value) for value in new_day_costs}
    month_consumed: Dict[MonthKey, float] = {}
    month_stats: Dict[MonthKey, Dict[str, float]] = {}
    paid_so_far = 0.0
    total_paid = 0.0
    total_unpaid = 0.0

    for leave_date, cost, is_new in merged:
        key = month_key(leave_date)
        paid, unpaid = _split_day(
            cost,
            _paid_room(
                cost, cap, month_consumed.get(key, 0.0), paid_so_far, allowance
            ),
        )
        if key in proposed_months:
            stats = month_stats.setdefault(
                key, {"already_used": 0.0, "requested": 0.0, "paid": 0.0, "unpaid": 0.0}
            )
            if is_new:
                stats["requested"] += cost
                stats["paid"] += paid
                stats["unpaid"] += unpaid
            else:
                stats["already_used"] += cost
        if is_new:
            total_paid += paid
            total_unpaid += unpaid
        month_consumed[key] = month_consumed.get(key, 0.0) + cost
        paid_so_far += paid

    return {
        "cap_days": cap,
        "paid_days": round(total_paid, 4),
        "unpaid_days": round(total_unpaid, 4),
        "months": [
            {
                "month": month_label(key),
                "cap_days": cap,
                "already_used_days": round(month_stats[key]["already_used"], 4),
                "requested_days": round(month_stats[key]["requested"], 4),
                "paid_days": round(month_stats[key]["paid"], 4),
                "unpaid_days": round(month_stats[key]["unpaid"], 4),
            }
            for key in sorted(month_stats)
        ],
    }
