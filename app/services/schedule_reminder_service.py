"""
Schedule Reminder Service
=========================
Runs every minute via APScheduler.

Logic:
  1. Skip if today is a public holiday (checks `holidays` table).
  2. Skip if outside school operating hours (derived from MIN/MAX of `shift.start_at/end_at`
     with a 30-minute buffer on each side, cached for 1 hour).
  3. Find active-academic-year classes starting within the NEXT 0–15 minutes
     (not started yet).
  4. For each class, if the teacher has NOT been successfully notified today,
     attempt FCM send.
  5. On SUCCESS → mark as done (dedup). Will NOT retry.
  6. On FAILURE → do NOT mark. Will retry next minute automatically.
  7. Once the class start time passes, it leaves the window → stops naturally.

This guarantees: every teacher gets the notification as long as the class
hasn't started yet, regardless of transient FCM / network failures.

Timezone: Asia/Phnom_Penh (UTC+7)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Set, Tuple

import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

from .notification_service import get_teacher_device_tokens, send_notification
from ..core import get_db, SessionLocal
from ..models.settings import SystemSettings
from ..utils.academic_year import get_current_academic_id

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
SCHOOL_TIMEZONE = pytz.timezone("Asia/Phnom_Penh")
REMINDER_MINUTES_BEFORE = 15  # Start sending reminders this many minutes before class

# ── Fallback operating hours (used when shift table is empty or unreachable) ──
# These are generous defaults; the real window is always read from the DB.
FALLBACK_START_H, FALLBACK_START_M = 5, 30   # 05:30
FALLBACK_END_H,   FALLBACK_END_M   = 20, 0   # 20:00

# ── Shift-hours cache ─────────────────────────────────────────────────────────
# Avoids a DB round-trip every minute. Refreshed once per hour.
_cached_school_start: Optional[Tuple[int, int]] = None   # (hour, minute)
_cached_school_end:   Optional[Tuple[int, int]] = None
_shift_cache_expiry: Optional[datetime]         = None
_SHIFT_CACHE_TTL = timedelta(hours=1)

# ── Deduplication guard ───────────────────────────────────────────────────────
# Stores (teacher_id, schedule_id, reminder_date_str) already notified today.
# Cleared at midnight automatically by using date prefix.
_sent_reminders: Set[Tuple[int, int, str]] = set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear_old_reminders() -> None:
    """Remove entries from previous days to keep memory usage minimal."""
    global _sent_reminders
    today_str = datetime.now(SCHOOL_TIMEZONE).strftime("%Y-%m-%d")
    _sent_reminders = {
        key for key in _sent_reminders if key[2] == today_str
    }


def _timedelta_to_hm(val) -> Tuple[int, int]:
    """
    Parse MySQL TIME (returned as timedelta), datetime.time, or 'HH:MM:SS' string
    into (hour, minute).
    """
    if isinstance(val, timedelta):
        total = int(val.total_seconds())
        return total // 3600, (total % 3600) // 60
    if hasattr(val, 'hour'):            # datetime.time object
        return val.hour, val.minute
    if isinstance(val, str):            # 'HH:MM' or 'HH:MM:SS'
        parts = val.split(':')
        return int(parts[0]), int(parts[1])
    raise ValueError(f"Cannot parse shift time from {type(val)}: {val!r}")


def _load_shift_hours(db: Session) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Query the shift table for the earliest start_at and latest end_at
    across all active shifts. Returns ((start_h, start_m), (end_h, end_m)).
    Falls back to FALLBACK_* constants if the table is empty or unavailable.
    Result is cached for _SHIFT_CACHE_TTL to avoid per-minute DB hits.
    """
    global _cached_school_start, _cached_school_end, _shift_cache_expiry

    now_utc = datetime.utcnow()
    if (
        _cached_school_start is not None
        and _shift_cache_expiry is not None
        and now_utc < _shift_cache_expiry
    ):
        return _cached_school_start, _cached_school_end  # type: ignore[return-value]

    try:
        row = db.execute(text("""
            SELECT MIN(start_at) AS earliest_start,
                   MAX(end_at)   AS latest_end
            FROM shift
            WHERE start_at IS NOT NULL
              AND end_at   IS NOT NULL
        """)).fetchone()

        if row and row[0] is not None and row[1] is not None:
            s_h, s_m = _timedelta_to_hm(row[0])
            e_h, e_m = _timedelta_to_hm(row[1])

            # Apply 30-minute buffer using timedelta arithmetic (handles hour rollover)
            base = datetime(2000, 1, 1)
            start_dt = (base.replace(hour=s_h, minute=s_m) - timedelta(minutes=30))
            end_dt   = (base.replace(hour=e_h, minute=e_m) + timedelta(minutes=30))

            _cached_school_start = (start_dt.hour, start_dt.minute)
            _cached_school_end   = (end_dt.hour,   end_dt.minute)
        else:
            # Shift table is empty — use fallback
            logger.warning("[ScheduleReminder] Shift table empty; using fallback hours.")
            _cached_school_start = (FALLBACK_START_H, FALLBACK_START_M)
            _cached_school_end   = (FALLBACK_END_H,   FALLBACK_END_M)

        _shift_cache_expiry = now_utc + _SHIFT_CACHE_TTL
        logger.info(
            f"[ScheduleReminder] School hours loaded from shift table: "
            f"{_cached_school_start[0]:02d}:{_cached_school_start[1]:02d} – "
            f"{_cached_school_end[0]:02d}:{_cached_school_end[1]:02d} "
            f"(cached for {int(_SHIFT_CACHE_TTL.total_seconds() // 60)} min)"
        )

    except Exception as exc:
        logger.warning(f"[ScheduleReminder] Could not read shift hours: {exc}. Using fallback.")
        _cached_school_start = (FALLBACK_START_H, FALLBACK_START_M)
        _cached_school_end   = (FALLBACK_END_H,   FALLBACK_END_M)
        _shift_cache_expiry  = now_utc + timedelta(minutes=10)  # retry sooner on error

    return _cached_school_start, _cached_school_end  # type: ignore[return-value]


def _is_holiday_today(db: Session) -> bool:
    """
    Return True if today's date is recorded in the `holidays` table.
    Fails open (returns False) on DB errors so reminders are never
    accidentally blocked by a broken holiday check.
    """
    try:
        today_str = datetime.now(SCHOOL_TIMEZONE).strftime("%Y-%m-%d")
        count = db.execute(
            text("SELECT COUNT(*) FROM holidays WHERE date = :today"),
            {"today": today_str},
        ).scalar()
        return (count or 0) > 0
    except Exception as exc:
        logger.warning(f"[ScheduleReminder] Holiday check failed: {exc}. Assuming not a holiday.")
        return False


def _build_reminder_body(subject_name: str, slot_name: str, start_time_str: str) -> str:
    """Build a user-friendly notification body string."""
    time_label = start_time_str
    try:
        dt = datetime.strptime(start_time_str[:5], "%H:%M")
        time_label = dt.strftime("%-I:%M %p")     # e.g. "8:00 AM"
    except Exception:
        pass
    return f"{subject_name} ({slot_name}) starts at {time_label}"


# ── Main cron function ────────────────────────────────────────────────────────

def send_schedule_reminders(db: Session) -> dict:
    """
    Main cron function: find all classes starting in REMINDER_MINUTES_BEFORE
    minutes and send FCM push notifications to their teachers.

    Returns a summary dict with counts for logging/API response.
    """
    # 1. Admin kill-switch
    settings = db.query(SystemSettings).first()
    if settings and settings.enable_schedule_reminders != 'yes':
        logger.info("[ScheduleReminder] Feature disabled by admin. Skipping.")
        return {"sent": 0, "skipped": 0, "teachers": []}

    # 2. Holiday check — skip entirely on public holidays
    if _is_holiday_today(db):
        today_str = datetime.now(SCHOOL_TIMEZONE).strftime("%Y-%m-%d")
        logger.info(f"[ScheduleReminder] {today_str} is a public holiday — skipping.")
        return {"sent": 0, "skipped": 0, "teachers": []}

    # 3. Operating-hours guard — skip outside school shift window
    now = datetime.now(SCHOOL_TIMEZONE)
    (s_h, s_m), (e_h, e_m) = _load_shift_hours(db)
    school_start = now.replace(hour=s_h, minute=s_m, second=0, microsecond=0)
    school_end   = now.replace(hour=e_h, minute=e_m, second=0, microsecond=0)
    if not (school_start <= now <= school_end):
        # Silent return — no log spam during off-hours
        return {"sent": 0, "skipped": 0, "teachers": []}

    _clear_old_reminders()

    # Window: classes that have NOT started yet AND start within the next 15 minutes.
    window_floor = now
    window_ceil  = now + timedelta(minutes=REMINDER_MINUTES_BEFORE)

    target_day_of_week = now.isoweekday()   # 1=Monday … 7=Sunday
    today_str          = now.strftime("%Y-%m-%d")
    now_time_str       = now.strftime("%H:%M")
    ceil_time_str      = window_ceil.strftime("%H:%M")
    active_academic_id = get_current_academic_id(db)

    logger.info(
        f"[ScheduleReminder] Window: {now_time_str} – {ceil_time_str} "
        f"(day={target_day_of_week}, {today_str})"
    )

    try:
        query = text("""
            SELECT
                lcs.id              AS schedule_id,
                lcs.teacher_id,
                lts.start_time,
                lts.slot_name,
                COALESCE(s.subject_name_us, s.subject_name, 'Class') AS subject_name
            FROM learning_class_schedules lcs
            INNER JOIN learning_time_slots lts ON lts.id = lcs.time_slot_id
            LEFT JOIN  subjects            s   ON s.id  = lcs.subject_id
            WHERE lcs.day_of_week  = :day_of_week
              AND lcs.academic_id  = :academic_id
              AND lcs.is_active    = 1
              AND lts.is_active    = 1
              AND TIME_FORMAT(lts.start_time, '%H:%i') >  :now_time
              AND TIME_FORMAT(lts.start_time, '%H:%i') <= :ceil_time
              AND (lcs.start_date IS NULL OR lcs.start_date <= :today)
              AND (lcs.end_date   IS NULL OR lcs.end_date   >= :today)
        """)

        rows = db.execute(query, {
            "day_of_week": target_day_of_week,
            "academic_id": active_academic_id,
            "now_time":    now_time_str,
            "ceil_time":   ceil_time_str,
            "today":       today_str,
        }).fetchall()

        if not rows:
            logger.info("[ScheduleReminder] No classes found for this minute.")
            return {"sent": 0, "skipped": 0, "teachers": []}

        logger.info(f"[ScheduleReminder] Found {len(rows)} schedule(s) to remind.")

        sent_count = 0
        skipped_count = 0
        notified_teachers = []

        for row in rows:
            schedule_id  = row[0]
            teacher_id   = row[1]
            start_time   = str(row[2])
            slot_name    = row[3] or "Period"
            subject_name = row[4]

            dedup_key = (teacher_id, schedule_id, today_str)
            if dedup_key in _sent_reminders:
                logger.debug(
                    f"[ScheduleReminder] Skipping duplicate: teacher={teacher_id}, "
                    f"schedule={schedule_id}"
                )
                skipped_count += 1
                continue

            tokens = get_teacher_device_tokens(db, teacher_id)
            if not tokens:
                logger.warning(
                    f"[ScheduleReminder] Teacher {teacher_id} has no active"
                    f" device tokens — skipping."
                )
                skipped_count += 1
                continue

            title = "📚 Class Starting Soon"
            body  = _build_reminder_body(subject_name, slot_name, start_time)

            success = send_notification(
                device_tokens=tokens,
                title=title,
                body=body,
                data={
                    "type":             "schedule_reminder",
                    "schedule_id":      str(schedule_id),
                    "teacher_id":       str(teacher_id),
                    "academic_id":      str(active_academic_id),
                    "subject":          subject_name,
                    "slot_name":        slot_name,
                    "start_time":       start_time[:5],
                    "reminder_minutes": str(REMINDER_MINUTES_BEFORE),
                },
                color="#1976D2",
                vibrate=True,
                channel_id="schedule_reminder_channel",
                android_show_system_notification=True,
                db=db,
                # Newest class reminder replaces the previous one in the tray.
                collapse_id="schedule_reminder",
            )

            if success:
                _sent_reminders.add(dedup_key)
                sent_count += 1
                notified_teachers.append(teacher_id)
                logger.info(
                    f"[ScheduleReminder] ✓ Sent to teacher={teacher_id}: "
                    f"{subject_name} @ {start_time[:5]}"
                )
            else:
                skipped_count += 1
                logger.warning(
                    f"[ScheduleReminder] ✗ Failed to send to teacher={teacher_id}"
                )

        return {
            "sent":     sent_count,
            "skipped":  skipped_count,
            "teachers": notified_teachers,
        }

    except Exception as e:
        logger.error(f"[ScheduleReminder] Unexpected error: {e}", exc_info=True)
        return {"sent": 0, "skipped": 0, "teachers": [], "error": str(e)}


def run_schedule_reminders() -> None:
    """
    Entry point called by APScheduler every minute.
    Manages its own DB session lifecycle.
    """
    try:
        db: Session = SessionLocal()
        try:
            result = send_schedule_reminders(db)
            if result.get("sent", 0) > 0:
                logger.info(
                    f"[ScheduleReminder] Sent {result['sent']} reminder(s) "
                    f"to teachers: {result['teachers']}"
                )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[ScheduleReminder] DB session error: {e}", exc_info=True)
