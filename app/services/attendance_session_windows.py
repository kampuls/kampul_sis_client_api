"""Pure helpers for attendance session time-window decisions."""

from typing import Optional, Tuple


def is_session_check_in_open(
    *,
    now_minutes: int,
    window_open_minutes: int,
    session_end_minutes: int,
) -> bool:
    """Return whether a pending session may receive a check-in now.

    Late checkout allowance is intentionally absent: it applies only after a
    check-in exists and must never reopen a completely missed earlier session.
    """
    return (
        int(window_open_minutes)
        <= int(now_minutes)
        <= int(session_end_minutes)
    )


def open_check_out_is_available(
    *,
    now_minutes: int,
    session_end_minutes: Optional[int],
    allow_late_clock_out_minutes: Optional[int],
) -> bool:
    """Whether an unfinished check-out may still be completed.

    The window is the session's own end plus ``allow_late_clock_out_minutes``,
    so an administrator sets how long a forgotten check-out stays completable.
    A generous allowance deliberately reaches into later sessions: with three
    hours, a session ending 11:15 stays closeable until 14:15, so a tap early
    in the afternoon session finishes the morning instead of starting the
    afternoon. The employee then waits out the session transition before
    checking in properly.

    ``None`` means unlimited, matching the documented meaning of the column.
    Beware pairing that with literal work-hour accounting: an unbounded window
    lets a late-night tap record the whole day against one session.
    """
    if session_end_minutes is None or allow_late_clock_out_minutes is None:
        return True
    buffer_minutes = max(0, int(allow_late_clock_out_minutes))
    return int(now_minutes) <= int(session_end_minutes) + buffer_minutes


def is_late_check_out(
    *,
    check_out_minutes: int,
    session_end_minutes: int,
    allow_late_clock_out_minutes: int,
) -> bool:
    """Whether a check-out landed outside its configured window.

    A late check-out is always accepted — a session that was checked into must
    remain closeable, otherwise the employee's next tap silently abandons it —
    so this only classifies the check-out for the report, never blocks it.
    """
    buffer_minutes = max(0, int(allow_late_clock_out_minutes or 0))
    return int(check_out_minutes) > int(session_end_minutes) + buffer_minutes


def resolve_automatic_attendance_target(
    *,
    actionable_open_session_index: int,
    check_in_session_index: int,
) -> Tuple[str, int]:
    """Resolve legacy ``auto`` using the existing session rollover policy.

    An open record is checked out only while its configured checkout window is
    actionable. After that deadline, the unfinished checkout remains missing
    and attendance may proceed to the current check-in session.
    """
    if int(actionable_open_session_index) >= 0:
        return "check_out", int(actionable_open_session_index)
    return "check_in", int(check_in_session_index)


def resolve_explicit_attendance_target(
    *,
    requested_action: str,
    requested_session_index: int,
    requested_session_actionable: bool,
    current_check_in_session_index: int,
) -> Tuple[str, int]:
    """Recover a stale explicit target without ever moving attendance backward.

    The mobile app submits the action/session it showed to the employee. That
    snapshot can become stale while GPS or a reason prompt is in progress, and
    older app versions could also select an expired missed session. If the
    requested target is no longer actionable and a *later* session is currently
    open for check-in, roll forward to it. An actionable checkout is preserved,
    so a previous session must still be completed while its window is open.
    """
    requested_index = int(requested_session_index)
    current_index = int(current_check_in_session_index)
    action = str(requested_action)

    if requested_session_actionable or current_index <= requested_index:
        return action, requested_index
    return "check_in", current_index
