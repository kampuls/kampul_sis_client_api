"""Pure validation helpers for attendance mutation request provenance.

The QR fields describe which ordinary attendance path the employee used. They
must never grant permission, but validating their shape prevents ambiguous or
tampered requests from silently falling back to an employee's primary branch.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple


ATTENDANCE_REQUEST_CONTEXT_MIN_VERSION: Tuple[int, int, int] = (1, 2, 8)
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


def requires_attendance_request_context(
    app_version: Optional[str],
    user_agent: Optional[str],
) -> bool:
    """Return whether QR/Quick-Attendance context must be explicit.

    Recognized official releases older than 1.2.8 retain their historical
    request format. Unknown clients and malformed versions fail closed.
    """

    if app_version:
        parsed_version = _parse_version(app_version)
        if parsed_version is None:
            return True
        return parsed_version >= ATTENDANCE_REQUEST_CONTEXT_MIN_VERSION

    normalized_user_agent = (user_agent or "").strip()
    return not normalized_user_agent.startswith(OFFICIAL_APP_USER_AGENT_PREFIX)


class AttendanceRequestContextViolation(NamedTuple):
    code: str
    message: str


def validate_attendance_request_context(
    *,
    qr_type: Optional[str],
    qr_id: Optional[int],
    branch_id: Optional[int],
    app_version: Optional[str],
    user_agent: Optional[str],
) -> Optional[AttendanceRequestContextViolation]:
    """Validate route-specific fields without treating them as authority."""

    context_required = requires_attendance_request_context(
        app_version,
        user_agent,
    )
    if qr_type is None and qr_id is None:
        if not context_required:
            return None
        return AttendanceRequestContextViolation(
            code="attendance_request_context_required",
            message=(
                "Attendance must be started from Quick Attendance or by scanning "
                "an attendance QR code in the latest official app."
            ),
        )

    if qr_type is None or qr_id is None:
        return AttendanceRequestContextViolation(
            code="invalid_attendance_request_context",
            message=(
                "This attendance request is incomplete. Please return to the app "
                "and start attendance again."
            ),
        )

    if qr_type == "branch":
        if branch_id is None or int(qr_id) != int(branch_id):
            return AttendanceRequestContextViolation(
                code="invalid_branch_qr_context",
                message=(
                    "This branch QR code does not match the selected branch. "
                    "Please scan the branch QR code again."
                ),
            )
        return None

    if qr_type == "t_attendance":
        if int(qr_id) != 1 or branch_id is not None:
            return AttendanceRequestContextViolation(
                code="invalid_quick_attendance_context",
                message=(
                    "Quick Attendance cannot select a branch manually. "
                    "Your branch must be determined by the server from live GPS."
                ),
            )
        return None

    if qr_type == "r_attendance":
        if int(qr_id) != 1 or branch_id is not None:
            return AttendanceRequestContextViolation(
                code="invalid_admin_attendance_context",
                message=(
                    "This administrator attendance QR code is invalid. "
                    "Please generate or scan it again."
                ),
            )
        return None

    return AttendanceRequestContextViolation(
        code="unsupported_attendance_request_context",
        message="This attendance request type is not supported.",
    )


def is_attendance_branch_authorized(
    branch_id: Optional[int],
    authorized_branch_ids: set[int],
    *,
    is_admin_override: bool,
) -> bool:
    """Only the explicit administrator override may bypass branch membership."""

    if is_admin_override:
        return True
    if branch_id is None:
        return False
    return int(branch_id) in authorized_branch_ids
