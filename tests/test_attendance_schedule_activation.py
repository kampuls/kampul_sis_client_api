import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.employee_attendance import (
    update_attendance_schedule_activation,
)


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *_args):
        return self

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, schedule):
        self.schedule = schedule
        self.committed = False
        self.rolled_back = False

    def query(self, _model):
        return _FakeQuery(self.schedule)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_deactivation_keeps_schedule_row_and_marks_it_inactive():
    schedule = SimpleNamespace(id=7, is_active=1)
    session = _FakeSession(schedule)

    with (
        patch(
            "app.api.v1.employee_attendance._require_attendance_admin"
        ),
        patch(
            "app.api.v1.employee_attendance._ensure_default_flag_column"
        ),
        patch(
            "app.api.v1.employee_attendance._get_default_fallback_schedule",
            return_value=SimpleNamespace(id=99),
        ),
    ):
        response = asyncio.run(
            update_attendance_schedule_activation(
                schedule_id=7,
                payload={"is_active": False},
                db=session,
                current_user=SimpleNamespace(id=1),
            )
        )

    assert schedule.is_active == 0
    assert session.committed is True
    assert response["is_active"] is False


def test_default_schedule_cannot_be_deactivated():
    schedule = SimpleNamespace(id=7, is_active=1)
    session = _FakeSession(schedule)

    with (
        patch(
            "app.api.v1.employee_attendance._require_attendance_admin"
        ),
        patch(
            "app.api.v1.employee_attendance._ensure_default_flag_column"
        ),
        patch(
            "app.api.v1.employee_attendance._get_default_fallback_schedule",
            return_value=schedule,
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                update_attendance_schedule_activation(
                    schedule_id=7,
                    payload={"is_active": False},
                    db=session,
                    current_user=SimpleNamespace(id=1),
                )
            )

    assert exc.value.status_code == 400
    assert "default fallback" in str(exc.value.detail).lower()
    assert schedule.is_active == 1
    assert session.rolled_back is True
