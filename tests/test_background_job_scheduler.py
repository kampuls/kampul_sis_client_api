import fcntl
from unittest.mock import patch

from app.services.background_job_scheduler import (
    start_background_job_scheduler,
    try_acquire_background_job_lock,
)


class _FakeScheduler:
    def __init__(self, *, timezone):
        self.timezone = timezone
        self.jobs = []
        self.running = False

    def add_job(self, func, **kwargs):
        self.jobs.append((func, kwargs))

    def start(self):
        self.running = True

    def shutdown(self, *, wait):
        self.running = False


def test_background_scheduler_contains_every_singleton_job():
    with patch(
        "app.services.background_job_scheduler.BackgroundScheduler",
        _FakeScheduler,
    ):
        scheduler = start_background_job_scheduler()

    assert scheduler.running is True
    assert scheduler.timezone == "Asia/Phnom_Penh"
    assert {job[1]["id"] for job in scheduler.jobs} == {
        "cache_cleanup",
        "finance_reminders",
        "schedule_reminder",
        "attendance_reminder",
        "pending_student_cleanup",
        "parent_attendance_notification_cleanup",
        "reminder_wish_notification_cleanup",
    }


def test_background_job_lock_can_be_taken_over_after_leader_releases_it(
    tmp_path,
):
    lock_path = str(tmp_path / "background-jobs.lock")
    first_leader = try_acquire_background_job_lock(lock_path)
    assert first_leader is not None
    assert try_acquire_background_job_lock(lock_path) is None

    fcntl.flock(first_leader, fcntl.LOCK_UN)
    first_leader.close()

    replacement_leader = try_acquire_background_job_lock(lock_path)
    assert replacement_leader is not None
    fcntl.flock(replacement_leader, fcntl.LOCK_UN)
    replacement_leader.close()
