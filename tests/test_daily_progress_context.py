import asyncio
from datetime import datetime
from unittest.mock import patch

from app.api.v1 import employee_attendance


class _MissingAttendanceTableDb:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("attendance table unavailable")


class _Employee:
    id = 58


def test_daily_progress_always_includes_authoritative_server_time():
    with patch.object(
        employee_attendance,
        "_require_attendance_processing",
        lambda *_args, **_kwargs: None,
    ):
        result = asyncio.run(
            employee_attendance.get_user_daily_progress(
                db=_MissingAttendanceTableDb(),
                current_user=_Employee(),
            )
        )

    server_time = datetime.fromisoformat(result["server_time_iso"])
    assert server_time.utcoffset() is not None
    assert result["server_time_minutes"] == (
        server_time.hour * 60 + server_time.minute
    )
    assert 0 <= result["server_time_minutes"] < 24 * 60
