"""Construction of the background scheduler shared by leader workers.

Keeping this in one function lets a surviving Gunicorn worker take over the
file-lock leadership after the previous leader is recycled.  The old inline
startup path could only build the scheduler once during process startup.
"""

from typing import IO, Optional

from apscheduler.schedulers.background import BackgroundScheduler


def try_acquire_background_job_lock(
    path: str = "/tmp/pama_leader.lock",
) -> Optional[IO[str]]:
    """Return an open, exclusively locked file handle or ``None`` if busy."""
    import fcntl

    lock_fh = open(path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        return None
    return lock_fh


def start_background_job_scheduler() -> BackgroundScheduler:
    """Create, configure, and start all singleton background jobs."""
    from .attendance_reminder_service import run_attendance_reminders
    from .cache import permissions_cache, settings_cache, social_links_cache
    from .schedule_reminder_service import run_schedule_reminders
    from ..core.attendance_notification_cleanup import (
        cleanup_old_parent_attendance_notifications,
    )
    from ..core.pending_student_cleanup import cleanup_stale_pending_children
    from ..core.reminder_notification_cleanup import (
        cleanup_reminder_and_wish_notifications,
    )

    scheduler = BackgroundScheduler(timezone="Asia/Phnom_Penh")
    from .finance_reminders import run_finance_reminders
    scheduler.add_job(run_finance_reminders, trigger="interval", minutes=15,
                      id="finance_reminders", replace_existing=True, max_instances=1,
                      misfire_grace_time=300)

    scheduler.add_job(
        lambda: (
            permissions_cache.cleanup_expired(),
            social_links_cache.cleanup_expired(),
            settings_cache.cleanup_expired(),
        ),
        trigger="interval",
        minutes=5,
        id="cache_cleanup",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_schedule_reminders,
        trigger="interval",
        minutes=1,
        id="schedule_reminder",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        run_attendance_reminders,
        trigger="interval",
        minutes=1,
        id="attendance_reminder",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        cleanup_stale_pending_children,
        trigger="cron",
        hour=23,
        minute=0,
        id="pending_student_cleanup",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        cleanup_old_parent_attendance_notifications,
        trigger="cron",
        hour=23,
        minute=5,
        id="parent_attendance_notification_cleanup",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        cleanup_reminder_and_wish_notifications,
        trigger="cron",
        hour=23,
        minute=50,
        id="reminder_wish_notification_cleanup",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    try:
        scheduler.start()
    except Exception:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        raise
    return scheduler
