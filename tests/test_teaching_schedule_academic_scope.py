from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import learning
from app.services import schedule_reminder_service


class _SettingsQuery:
    def first(self):
        return SimpleNamespace(enable_schedule_reminders="yes")


class _EmptyRows:
    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class _RecordingDb:
    def __init__(self):
        self.calls = []

    def query(self, *_args, **_kwargs):
        return _SettingsQuery()

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return _EmptyRows()


def test_schedule_reminders_query_only_the_current_academic_year(monkeypatch):
    db = _RecordingDb()

    class _FixedDateTime:
        @staticmethod
        def now(timezone=None):
            value = datetime(2026, 8, 24, 10, 0)
            return timezone.localize(value) if timezone is not None else value

    monkeypatch.setattr(schedule_reminder_service, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        schedule_reminder_service,
        "_is_holiday_today",
        lambda _db: False,
    )
    monkeypatch.setattr(
        schedule_reminder_service,
        "_load_shift_hours",
        lambda _db: ((0, 0), (23, 59)),
    )
    monkeypatch.setattr(
        schedule_reminder_service,
        "get_current_academic_id",
        lambda _db: 27,
    )

    result = schedule_reminder_service.send_schedule_reminders(db)

    schedule_sql, schedule_params = next(
        call for call in db.calls if "FROM learning_class_schedules lcs" in call[0]
    )
    assert result == {"sent": 0, "skipped": 0, "teachers": []}
    assert "lcs.academic_id  = :academic_id" in schedule_sql
    assert schedule_params["academic_id"] == 27


def test_teacher_schedule_ignores_requested_historical_year(monkeypatch):
    db = _RecordingDb()
    monkeypatch.setattr(learning, "check_user_permission", lambda *_args: False)
    monkeypatch.setattr(learning, "get_current_academic_id", lambda _db: 27)

    result = learning.get_class_schedules(
        academic_id=3,
        branch_id=None,
        grade_group_id=None,
        grade_id=None,
        program_id=None,
        grade_type_id=None,
        teacher_id=999,
        day_of_week=None,
        is_active=True,
        db=db,
        current_user=SimpleNamespace(id=41, role=4),
    )

    assert result == []
    schedule_sql, params = db.calls[-1]
    assert "lcs.academic_id = :academic_id" in schedule_sql
    assert "lcs.teacher_id = :teacher_id" in schedule_sql
    assert params["academic_id"] == 27
    assert params["teacher_id"] == 41


def test_schedule_mutations_reject_historical_academic_year(monkeypatch):
    monkeypatch.setattr(learning, "get_current_academic_id", lambda _db: 27)

    assert learning._require_current_schedule_academic_year(object(), 27) == 27

    with pytest.raises(HTTPException) as exc_info:
        learning._require_current_schedule_academic_year(object(), 3)

    assert exc_info.value.status_code == 409
    assert "active academic year (27)" in exc_info.value.detail
