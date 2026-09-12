"""Session-to-session attendance transition policy helpers."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Optional


@dataclass(frozen=True)
class SessionTransitionWait:
    """The remaining enforced wait after a completed session check-out."""

    wait_minutes: int
    remaining_seconds: int
    available_at: datetime


def calculate_session_transition_wait(
    last_check_out: Optional[datetime],
    now: datetime,
    wait_minutes: int,
) -> Optional[SessionTransitionWait]:
    """Return remaining transition wait, or ``None`` when check-in may proceed.

    MySQL commonly returns naive datetimes even when application time is aware.
    Attendance timestamps are school-local, so a naive database value inherits
    the timezone from ``now`` before comparison.
    """

    normalized_wait = max(0, int(wait_minutes or 0))
    if last_check_out is None or normalized_wait == 0:
        return None

    normalized_check_out = last_check_out
    normalized_now = now
    if normalized_check_out.tzinfo is None and normalized_now.tzinfo is not None:
        normalized_check_out = normalized_check_out.replace(tzinfo=normalized_now.tzinfo)
    elif normalized_check_out.tzinfo is not None and normalized_now.tzinfo is None:
        normalized_now = normalized_now.replace(tzinfo=normalized_check_out.tzinfo)
    elif normalized_check_out.tzinfo is not None and normalized_now.tzinfo is not None:
        normalized_check_out = normalized_check_out.astimezone(normalized_now.tzinfo)

    available_at = normalized_check_out + timedelta(minutes=normalized_wait)
    remaining_seconds = math.ceil((available_at - normalized_now).total_seconds())
    if remaining_seconds <= 0:
        return None

    return SessionTransitionWait(
        wait_minutes=normalized_wait,
        remaining_seconds=remaining_seconds,
        available_at=available_at,
    )
