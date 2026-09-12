"""Marketplace publication and renewal timing rules."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


LISTING_RENEWAL_COOLDOWN = timedelta(days=3)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def effective_published_at(
    created_at: Optional[datetime],
    renewed_at: Optional[datetime],
) -> Optional[datetime]:
    """Return the instant that controls feed order and the displayed post age."""
    if renewed_at is not None:
        return _as_utc(renewed_at)
    if created_at is not None:
        return _as_utc(created_at)
    return None


def listing_renewal_status(
    created_at: Optional[datetime],
    renewed_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
) -> Tuple[bool, Optional[datetime]]:
    """Return whether a listing can renew now and its next eligible instant."""
    published_at = effective_published_at(created_at, renewed_at)
    if published_at is None:
        return False, None
    next_at = published_at + LISTING_RENEWAL_COOLDOWN
    current = _as_utc(now or datetime.now(timezone.utc))
    return current >= next_at, next_at
