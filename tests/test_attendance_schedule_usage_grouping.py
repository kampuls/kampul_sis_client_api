from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.employee_attendance import (
    _group_active_users_by_effective_schedule,
)
from app.models.attendance_model import (
    AttendanceSchedule,
    AttendanceUserAssignment,
)
from app.models.user import User


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, schedules, users, assignments):
        self._rows = {
            AttendanceSchedule: schedules,
            User: users,
            AttendanceUserAssignment: assignments,
        }

    def query(self, model):
        return _FakeQuery(self._rows[model])


def test_usage_count_includes_direct_and_department_users():
    schedule = SimpleNamespace(
        id=7,
        user_id=None,
        department_id=5,
        branch_id=None,
    )
    direct_user = SimpleNamespace(id=10, departmentId=None, workplace=None)
    department_user = SimpleNamespace(id=11, departmentId=5, workplace=None)
    direct_assignment = SimpleNamespace(
        id=1,
        user_id=10,
        schedule_id=7,
        start_date=date(2026, 1, 1),
        end_date=None,
    )
    session = _FakeSession(
        schedules=[schedule],
        users=[direct_user, department_user],
        assignments=[direct_assignment],
    )

    with patch(
        "app.api.v1.employee_attendance._get_default_fallback_schedule",
        return_value=SimpleNamespace(id=99),
    ):
        grouped = _group_active_users_by_effective_schedule(
            session,
            date(2026, 8, 12),
        )

    assert [user.id for user, _source in grouped[7]] == [10, 11]
    assert [source for _user, source in grouped[7]] == [
        "assignment",
        "department",
    ]
