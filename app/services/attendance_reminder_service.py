"""
Attendance Check-In & Check-Out Reminder Service
=================================================
Runs every minute via APScheduler.

Logic:
  1. Skip if today is a public holiday (checks `holidays` table).
  2. Load global attendance settings and check toggles/timing lists.
  3. Find all active employees (users with status = 1).
  4. For each employee, resolve their effective schedule and scheduled sessions for today.
  5. Calculate target times for before/after check-in and check-out reminders.
  6. If a target time is due (including the bounded retry/catch-up window):
     - For check-in: Verify if the user has NOT checked in yet.
     - For check-out: Verify if the user has checked in but NOT checked out yet.
     - Dispatch FCM push notifications and save in-app notification.
  7. Successful sends are deduplicated; failed sends retry while still relevant.

Timezone: Asia/Phnom_Penh (UTC+7)
"""
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Set, Tuple, List, Dict, Any
import json
import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

from .notification_service import send_notification
from ..core import get_db, SessionLocal
from ..models.attendance_model import AttendanceSystemSettings, AttendanceRecord
from ..models.user import User
from ..api.v1.employee_attendance import get_effective_schedule
from .attendance_schedule_exception_service import get_effective_day_attendance
from .attendance_processing_access_service import filter_enabled_users

logger = logging.getLogger(__name__)

# Timezone Configuration
SCHOOL_TIMEZONE = pytz.timezone("Asia/Phnom_Penh")

# Deduplication Guard
# Format: (user_id, session_index, reminder_type, mins_offset, date_str)
# reminder_type can be 'before_in', 'after_in', 'before_out', 'after_out'
_sent_attendance_reminders: Set[Tuple[int, int, str, int, str]] = set()

# After-event reminders remain retryable for a few minutes. Before-event
# reminders remain useful until the shift boundary itself. This avoids losing
# an alert when APScheduler is delayed or a worker is replaced at the exact
# configured minute.
AFTER_REMINDER_RETRY_WINDOW_MINUTES = 5


def attendance_reminder_action_payload(reminder_type: str) -> dict:
    """Return explicit cross-platform action metadata for a reminder."""

    normalized = str(reminder_type or "").strip().lower()
    is_check_in = normalized in {"before_in", "after_in"}
    if not is_check_in and normalized not in {"before_out", "after_out"}:
        raise ValueError(f"Unsupported attendance reminder type: {reminder_type}")
    action_id = "check_in" if is_check_in else "check_out"
    action_title = "Check in" if is_check_in else "Check out"
    return {
        "is_check_in": "true" if is_check_in else "false",
        "notification_category": (
            "CHECK_IN_REMINDER_CATEGORY"
            if is_check_in
            else "CHECK_OUT_REMINDER_CATEGORY"
        ),
        "actions": [
            {"id": action_id, "title": action_title, "action": action_id},
            {"id": "dismiss", "title": "Later", "action": "dismiss"},
        ],
    }


def _clear_old_attendance_reminders() -> None:
    """Remove entries from previous days to keep memory usage minimal."""
    global _sent_attendance_reminders
    today_str = datetime.now(SCHOOL_TIMEZONE).strftime("%Y-%m-%d")
    _sent_attendance_reminders = {
        key for key in _sent_attendance_reminders if key[4] == today_str
    }


def _is_holiday_today(db: Session) -> bool:
    """Return True if today's date is recorded in the `holidays` table."""
    try:
        today_str = datetime.now(SCHOOL_TIMEZONE).strftime("%Y-%m-%d")
        count = db.execute(
            text("SELECT COUNT(*) FROM holidays WHERE date = :today"),
            {"today": today_str},
        ).scalar()
        return (count or 0) > 0
    except Exception as exc:
        logger.warning(f"[AttendanceReminder] Holiday check failed: {exc}. Assuming not a holiday.")
        return False


def _format_time_12h(time_str: str) -> str:
    """Format time string (HH:MM or HH:MM:SS) to 12-hour AM/PM format."""
    try:
        dt = datetime.strptime(time_str[:5], "%H:%M")
        return dt.strftime("%-I:%M %p")
    except Exception:
        return time_str


def _coerce_minutes_list(val) -> List[int]:
    """Coerce various formats (JSON lists, strings, lists) to a list of ints."""
    if not val:
        return []
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [int(x) for x in parsed if str(x).isdigit()]
        except Exception:
            return [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
    if isinstance(val, list):
        return [int(x) for x in val if str(x).isdigit()]
    return []


def _latest_due_reminder_offset(
    *,
    now_min: datetime,
    event_dt: datetime,
    offsets: List[int],
    before_event: bool,
) -> Optional[int]:
    """Return only the newest relevant offset that is due right now.

    Selecting one offset prevents two catch-up pushes in the same scheduler
    run when, for example, both 10-minute and 5-minute reminders were missed
    during a worker restart.
    """
    candidates: List[Tuple[datetime, int]] = []
    for raw_offset in offsets:
        try:
            offset = int(raw_offset)
        except (TypeError, ValueError):
            continue
        if offset < 0:
            continue

        target_dt = event_dt + timedelta(
            minutes=(-offset if before_event else offset)
        )
        if before_event:
            is_due = target_dt <= now_min <= event_dt
        else:
            retry_until = target_dt + timedelta(
                minutes=AFTER_REMINDER_RETRY_WINDOW_MINUTES
            )
            is_due = target_dt <= now_min < retry_until
        if is_due:
            candidates.append((target_dt, offset))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def send_attendance_reminders(db: Session) -> dict:
    """
    Main background reminders processor.
    Calculates boundaries for the current minute and dispatches FCM notifications.
    """
    try:
        # 1. Load global settings and config
        settings = db.query(AttendanceSystemSettings).first()
        
        # Determine features toggles & timings with robust defaults
        notify_enable_before = True
        notify_minutes_before = [10, 5]
        notify_enable_after = True
        notify_minutes_after = [10, 30]
        notify_enable_before_checkout = True
        notify_minutes_before_checkout = [0]
        notify_enable_after_checkout = True
        notify_minutes_after_checkout = [5]

        if settings:
            notify_enable_before = bool(
                True
                if getattr(settings, "notify_enable_before", None) is None
                else getattr(settings, "notify_enable_before")
            )
            notify_minutes_before = _coerce_minutes_list(
                getattr(settings, "notify_minutes_before", None) or [10, 5]
            )
            notify_enable_after = bool(
                True
                if getattr(settings, "notify_enable_after", None) is None
                else getattr(settings, "notify_enable_after")
            )
            notify_minutes_after = _coerce_minutes_list(
                getattr(settings, "notify_minutes_after", None) or [10, 30]
            )
            notify_enable_before_checkout = bool(
                True
                if getattr(settings, "notify_enable_before_checkout", None) is None
                else getattr(settings, "notify_enable_before_checkout")
            )
            notify_minutes_before_checkout = _coerce_minutes_list(
                getattr(settings, "notify_minutes_before_checkout", None) or [0]
            )
            notify_enable_after_checkout = bool(
                True
                if getattr(settings, "notify_enable_after_checkout", None) is None
                else getattr(settings, "notify_enable_after_checkout")
            )
            notify_minutes_after_checkout = _coerce_minutes_list(
                getattr(settings, "notify_minutes_after_checkout", None) or [5]
            )

        # If everything is disabled, nothing to process
        if (not notify_enable_before and not notify_enable_after and
                not notify_enable_before_checkout and not notify_enable_after_checkout):
            return {"sent": 0, "skipped": 0, "users": []}

        # 2. Holiday guard
        if _is_holiday_today(db):
            today_str = datetime.now(SCHOOL_TIMEZONE).strftime("%Y-%m-%d")
            logger.info(f"[AttendanceReminder] {today_str} is a public holiday — skipping reminders.")
            return {"sent": 0, "skipped": 0, "users": []}

        _clear_old_attendance_reminders()

        # 3. Get current time in local timezone truncated to the minute
        now = datetime.now(SCHOOL_TIMEZONE)
        now_min = now.replace(second=0, microsecond=0)
        today = now.date()
        today_str = today.strftime("%Y-%m-%d")

        # 4. Fetch active users (status = 1)
        active_users = filter_enabled_users(
            db,
            db.query(User).filter(User.status == 1).all(),
        )
        if not active_users:
            return {"sent": 0, "skipped": 0, "users": []}

        sent_count = 0
        skipped_count = 0
        notified_users = []

        # Approved leave today → no check-in/out reminders for covered sessions.
        from .leave_integration_service import get_approved_leave_map, leave_covers_session

        leave_today_map = get_approved_leave_map(
            db, [int(u.id) for u in active_users], today, today
        )

        # 5. Process each active user
        for user in active_users:
            schedule = get_effective_schedule(db, user, today)
            day_info = get_effective_day_attendance(db, user, today, schedule=schedule)
            if not day_info.get("is_active_day"):
                continue

            sessions = day_info.get("sessions") or []
            if not sessions:
                continue

            user_leave_entry = leave_today_map.get(int(user.id), {}).get(today)

            # Evaluate each active shift session
            for idx, session in enumerate(sessions):
                session_index = idx + 1
                if leave_covers_session(user_leave_entry, session_index):
                    continue
                start_time_str = session.get('start')
                end_time_str = session.get('end')
                if not start_time_str or not end_time_str:
                    continue

                try:
                    sh, sm = map(int, start_time_str.split(':'))
                    eh, em = map(int, end_time_str.split(':'))
                    session_start_dt = now_min.replace(hour=sh, minute=sm)
                    session_end_dt = now_min.replace(hour=eh, minute=em)
                except Exception:
                    continue

                # Helpers to check database check-in/out records
                def has_checked_in() -> bool:
                    rec = db.query(AttendanceRecord).filter(
                        AttendanceRecord.user_id == user.id,
                        AttendanceRecord.attendance_date == today,
                        AttendanceRecord.session_index == session_index,
                        AttendanceRecord.check_in_time.isnot(None)
                    ).first()
                    return rec is not None

                def has_checked_in_but_not_out() -> bool:
                    rec = db.query(AttendanceRecord).filter(
                        AttendanceRecord.user_id == user.id,
                        AttendanceRecord.attendance_date == today,
                        AttendanceRecord.session_index == session_index,
                        AttendanceRecord.check_in_time.isnot(None),
                        AttendanceRecord.check_out_time.is_(None)
                    ).first()
                    return rec is not None

                # Send execution helper
                def send_reminder(reminder_type: str, offset_mins: int, title: str, body: str, target_time_str: str) -> bool:
                    nonlocal sent_count, skipped_count
                    action_payload = attendance_reminder_action_payload(
                        reminder_type
                    )
                    success = send_notification(
                        device_tokens=None,
                        title=title,
                        body=body,
                        data={
                            "type": "attendance_reminder",
                            "notification_key": (
                                f"attendance:{today_str}:{user.id}:"
                                f"{session_index}:{reminder_type}:{offset_mins}"
                            ),
                            "session_index": str(session_index),
                            "reminder_type": reminder_type,
                            "is_check_in": action_payload["is_check_in"],
                            "notification_category": action_payload[
                                "notification_category"
                            ],
                            "offset_minutes": str(offset_mins),
                            "target_time": target_time_str,
                        },
                        actions=action_payload["actions"],
                        color="#E53935" if "after" in reminder_type else "#1E88E5",
                        vibrate=True,
                        channel_id="attendance_channel",
                        # Android data-only delivery lets the app post every
                        # reminder with one stable local id. A system-rendered
                        # FCM notification receives an opaque OS id and cannot
                        # be reliably removed after an in-app check-in/out.
                        android_show_system_notification=False,
                        db=db,
                        user_ids=[{"id": user.id, "user_type": "teacher"}],
                        # Only the latest reminder matters: each new one
                        # replaces the previous in the tray so users never
                        # see (and re-tap) a stack of stale reminders.
                        collapse_id="attendance_reminder",
                    )
                    if success:
                        notified_users.append(user.id)
                        sent_count += 1
                        logger.info(
                            f"[AttendanceReminder] Sent {reminder_type} reminder ({offset_mins}m) "
                            f"to user={user.id} ({user.eName}) for session {session_index}."
                        )
                    else:
                        skipped_count += 1
                        logger.warning(
                            f"[AttendanceReminder] Failed to send reminder to user={user.id}"
                        )
                    return success

                # A. Before-Checkin Reminders
                if notify_enable_before:
                    mins = _latest_due_reminder_offset(
                        now_min=now_min,
                        event_dt=session_start_dt,
                        offsets=notify_minutes_before,
                        before_event=True,
                    )
                    if mins is not None:
                        dedup_key = (user.id, session_index, 'before_in', mins, today_str)
                        if dedup_key not in _sent_attendance_reminders:
                            if has_checked_in():
                                _sent_attendance_reminders.add(dedup_key)
                            else:
                                remaining_mins = max(
                                    0,
                                    int(
                                        (session_start_dt - now_min).total_seconds()
                                        // 60
                                    ),
                                )
                                body_text = (
                                    f"Your scheduled work shift starts now at {_format_time_12h(start_time_str)}. Please check in."
                                    if remaining_mins == 0
                                    else f"Your scheduled work shift starts in {remaining_mins} minutes at {_format_time_12h(start_time_str)}. Please check in."
                                )
                                if send_reminder(
                                    reminder_type='before_in',
                                    offset_mins=mins,
                                    title="⏰ Work Shift Starting Soon",
                                    body=body_text,
                                    target_time_str=start_time_str,
                                ):
                                    _sent_attendance_reminders.add(dedup_key)

                # B. After-Checkin Reminders (Late / Missing check-in)
                if notify_enable_after:
                    mins = _latest_due_reminder_offset(
                        now_min=now_min,
                        event_dt=session_start_dt,
                        offsets=notify_minutes_after,
                        before_event=False,
                    )
                    if mins is not None:
                        dedup_key = (user.id, session_index, 'after_in', mins, today_str)
                        if dedup_key not in _sent_attendance_reminders:
                            if has_checked_in():
                                _sent_attendance_reminders.add(dedup_key)
                            else:
                                late_mins = max(
                                    mins,
                                    int(
                                        (now_min - session_start_dt).total_seconds()
                                        // 60
                                    ),
                                )
                                if send_reminder(
                                    reminder_type='after_in',
                                    offset_mins=mins,
                                    title="⚠️ Late Check-In Alert",
                                    body=f"You are {late_mins} minutes late for your shift starting at {_format_time_12h(start_time_str)}. Please check in now.",
                                    target_time_str=start_time_str,
                                ):
                                    _sent_attendance_reminders.add(dedup_key)

                # C. Before-Checkout Reminders
                if notify_enable_before_checkout:
                    mins = _latest_due_reminder_offset(
                        now_min=now_min,
                        event_dt=session_end_dt,
                        offsets=notify_minutes_before_checkout,
                        before_event=True,
                    )
                    if mins is not None:
                        dedup_key = (user.id, session_index, 'before_out', mins, today_str)
                        if (
                            dedup_key not in _sent_attendance_reminders
                            and has_checked_in_but_not_out()
                        ):
                            remaining_mins = max(
                                0,
                                int(
                                    (session_end_dt - now_min).total_seconds()
                                    // 60
                                ),
                            )
                            body_text = (
                                f"Your shift session ends now at {_format_time_12h(end_time_str)}. Please remember to clock out."
                                if remaining_mins == 0
                                else f"Your shift session ends in {remaining_mins} minute(s) at {_format_time_12h(end_time_str)}. Please remember to clock out."
                            )
                            if send_reminder(
                                reminder_type='before_out',
                                offset_mins=mins,
                                title="⏰ End of Shift Reminder",
                                body=body_text,
                                target_time_str=end_time_str,
                            ):
                                _sent_attendance_reminders.add(dedup_key)

                # D. After-Checkout Reminders (Missing checkout)
                if notify_enable_after_checkout:
                    mins = _latest_due_reminder_offset(
                        now_min=now_min,
                        event_dt=session_end_dt,
                        offsets=notify_minutes_after_checkout,
                        before_event=False,
                    )
                    if mins is not None:
                        dedup_key = (user.id, session_index, 'after_out', mins, today_str)
                        if (
                            dedup_key not in _sent_attendance_reminders
                            and has_checked_in_but_not_out()
                            and send_reminder(
                                reminder_type='after_out',
                                offset_mins=mins,
                                title="⚠️ Missing Clock-Out Alert",
                                body=f"Your shift session ended at {_format_time_12h(end_time_str)} but you haven't clocked out yet. Please check out now.",
                                target_time_str=end_time_str,
                            )
                        ):
                            _sent_attendance_reminders.add(dedup_key)

        return {
            "sent": sent_count,
            "skipped": skipped_count,
            "users": notified_users
        }

    except Exception as e:
        logger.error(f"[AttendanceReminder] Unexpected processing error: {e}", exc_info=True)
        return {"sent": 0, "skipped": 0, "users": [], "error": str(e)}


def run_attendance_reminders() -> None:
    """
    Entry point called by APScheduler every minute.
    Handles its own database session lifecycle.
    """
    try:
        db: Session = SessionLocal()
        try:
            result = send_attendance_reminders(db)
            if result.get("sent", 0) > 0:
                logger.info(
                    f"[AttendanceReminder] Completed: sent {result['sent']} reminders "
                    f"to users: {result['users']}"
                )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[AttendanceReminder] DB session initialization error: {e}", exc_info=True)
