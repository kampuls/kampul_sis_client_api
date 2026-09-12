"""Server-side freshness policy for attendance GPS evidence."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


GPS_MAX_AGE_SECONDS = 120.0
GPS_MAX_FUTURE_SKEW_SECONDS = 30.0
DEVICE_TIME_MAX_SKEW_SECONDS = 30.0


def gps_age_seconds(
    gps_timestamp: datetime,
    *,
    now: Optional[datetime] = None,
) -> float:
    """Return reading age using UTC, treating legacy naive values as UTC."""

    gps_utc = gps_timestamp
    if gps_utc.tzinfo is None:
        gps_utc = gps_utc.replace(tzinfo=timezone.utc)
    else:
        gps_utc = gps_utc.astimezone(timezone.utc)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return (current - gps_utc).total_seconds()


def is_current_gps_age(age_seconds: float) -> bool:
    """Return whether a reading is inside the server's trusted time window."""

    return -GPS_MAX_FUTURE_SKEW_SECONDS <= age_seconds <= GPS_MAX_AGE_SECONDS


def is_device_time_incorrect(age_seconds: float) -> bool:
    """Return whether the phone clock is too far from authoritative time."""

    return abs(age_seconds) > DEVICE_TIME_MAX_SKEW_SECONDS


def incorrect_device_time_error_detail(
    age_seconds: float,
    *,
    server_time: datetime,
) -> Dict[str, Any]:
    """Stable recovery contract for phones with manually changed clocks."""

    server_utc = server_time
    if server_utc.tzinfo is None:
        server_utc = server_utc.replace(tzinfo=timezone.utc)
    else:
        server_utc = server_utc.astimezone(timezone.utc)
    return {
        "code": "device_time_incorrect",
        "message": (
            "Attendance blocked: your phone date and time do not match the "
            "official server time. Enable automatic date and time and automatic "
            "time zone, then try again."
        ),
        "clock_offset_seconds": round(age_seconds, 1),
        "server_time_iso": server_utc.isoformat(),
    }


def stale_gps_error_detail(age_seconds: float) -> Dict[str, Any]:
    """Stable machine-readable error contract for mobile clients and support."""

    return {
        "code": "stale_gps",
        "message": (
            "Attendance blocked: the GPS reading is not current. "
            "Refresh your location and try again."
        ),
        "gps_age_seconds": round(age_seconds, 1),
    }
