"""Telegram routing policy for persisted attendance security events."""


_TELEGRAM_SUPPRESSED_EVENT_TYPES = frozenset(
    {
        # Employee-requested support reports have their own explicit Telegram
        # route and must not also generate a security alert.
        "employee_problem_report",
        # Outside-geofence attempts remain visible in security logs, but are a
        # common user mistake and would make the Telegram channel too noisy.
        "outside_workplace",
    }
)


def should_send_attendance_security_telegram(
    event_type: str,
    severity: str,
) -> bool:
    """Send only critical security events to the administrator channel.

    Events are persisted before this policy is evaluated, so suppressing a
    Telegram alert never removes the event from the security log.
    """
    event_type_key = str(event_type or "").strip()
    severity_key = str(severity or "").strip().lower()
    return (
        severity_key == "critical"
        and event_type_key not in _TELEGRAM_SUPPRESSED_EVENT_TYPES
    )
