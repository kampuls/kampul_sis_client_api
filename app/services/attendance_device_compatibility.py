"""Compatibility policy for primary attendance-phone identity.

App releases before 1.2.8 cannot send the per-install attendance identity.
Keep recognized official legacy builds working during rollout while requiring
the new identity from 1.2.8 and later.  The compatibility switch can be turned
off server-side after the rollout window without another app release.
"""

from typing import Optional, Tuple


ATTENDANCE_DEVICE_IDENTITY_MIN_VERSION: Tuple[int, int, int] = (1, 2, 8)
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


def requires_attendance_device_identity(
    app_version: Optional[str],
    user_agent: Optional[str],
    *,
    allow_legacy_compatibility: bool = True,
) -> bool:
    """Return whether this client must supply primary-phone identity.

    Known official releases older than 1.2.8 receive the compatibility path.
    Official builds that predate ``X-App-Version`` are also compatible.
    Unknown clients, malformed version headers, and all clients after the
    compatibility switch is disabled fail closed.
    """

    if not allow_legacy_compatibility:
        return True

    if app_version:
        parsed_version = _parse_version(app_version)
        if parsed_version is None:
            return True
        return parsed_version >= ATTENDANCE_DEVICE_IDENTITY_MIN_VERSION

    normalized_user_agent = (user_agent or "").strip()
    return not normalized_user_agent.startswith(OFFICIAL_APP_USER_AGENT_PREFIX)
