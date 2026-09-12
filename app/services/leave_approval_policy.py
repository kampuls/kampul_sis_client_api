"""Shared leave-approval eligibility rules."""

from typing import Optional


APPROVAL_DAY_EPSILON = 1e-9


def approval_day_limit_allows(
    max_days_can_approve: Optional[float],
    request_days: Optional[float],
) -> bool:
    """Return whether an approver's day limit covers a leave request.

    ``None`` means unlimited. Legacy requests without ``total_days`` retain
    the API's existing zero-day fallback instead of becoming inaccessible.
    """

    if max_days_can_approve is None:
        return True
    days = float(request_days or 0.0)
    return days <= float(max_days_can_approve) + APPROVAL_DAY_EPSILON
