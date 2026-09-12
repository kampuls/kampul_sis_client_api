"""Compatibility policy for attendance GPS evidence fields.

App releases before 1.2.7 sent latitude/longitude and the mock-location
signal, but did not send GPS accuracy or the reading timestamp.  Keep those
official legacy builds on the existing server-side geofence checks while new
builds are required to provide the stronger evidence.
"""

from typing import Optional, Tuple


ENHANCED_GPS_EVIDENCE_MIN_VERSION: Tuple[int, int, int] = (1, 2, 7)
OFFICIAL_APP_USER_AGENT_PREFIX = "PAMA-School-App/"


def _parse_version(value: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if not value:
        return None
    raw = value.strip().split("+", 1)[0].split("-", 1)[0]
    parts = raw.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    numbers = [int(part) for part in parts[:3]]
    numbers.extend([0] * (3 - len(numbers)))
    return tuple(numbers)  # type: ignore[return-value]


def requires_enhanced_gps_evidence(
    app_version: Optional[str],
    user_agent: Optional[str],
) -> bool:
    """Return whether accuracy and timestamp evidence must be present.

    Known official versions older than 1.2.7 receive the compatibility path.
    Older official builds that predate ``X-App-Version`` are also compatible.
    Unknown/non-official clients fail closed and must provide full evidence.
    """

    if app_version:
        parsed_version = _parse_version(app_version)
        # A supplied but malformed version is not a recognized legacy build.
        if parsed_version is None:
            return True
        return parsed_version >= ENHANCED_GPS_EVIDENCE_MIN_VERSION

    normalized_user_agent = (user_agent or "").strip()
    return not normalized_user_agent.startswith(OFFICIAL_APP_USER_AGENT_PREFIX)
