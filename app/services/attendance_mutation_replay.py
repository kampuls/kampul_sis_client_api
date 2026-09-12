"""Safety guard for duplicate automatic attendance submissions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


AUTO_ACTION_REPLAY_GRACE_SECONDS = 90


def is_recent_auto_checkin_replay(
    *,
    requested_action: str,
    open_check_in_time: Optional[datetime],
    now: datetime,
    grace_seconds: int = AUTO_ACTION_REPLAY_GRACE_SECONDS,
) -> bool:
    """Treat a near-immediate repeated ``auto`` call as the same check-in.

    This protects users when the first success response is lost or the QR
    scanner submits twice. Explicit check-out requests are never swallowed.
    """

    if requested_action != "auto" or open_check_in_time is None:
        return False

    comparable_now = now
    if open_check_in_time.tzinfo is None:
        comparable_now = now.replace(tzinfo=None)
    elif now.tzinfo is None:
        comparable_now = now.replace(tzinfo=open_check_in_time.tzinfo)
    else:
        comparable_now = now.astimezone(open_check_in_time.tzinfo)

    age_seconds = (comparable_now - open_check_in_time).total_seconds()
    return -5 <= age_seconds <= max(0, int(grace_seconds))

