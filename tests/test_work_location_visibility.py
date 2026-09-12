import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.employee_attendance import get_work_locations
from app.schemas.employee_attendance import WorkLocationResponse


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filter_calls = 0

    def filter(self, *_args):
        self.filter_calls += 1
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, rows):
        self.query_result = _FakeQuery(rows)

    def query(self, _model):
        return self.query_result


def test_admin_show_all_keeps_inactive_locations_visible():
    inactive_location = SimpleNamespace(
        id=7,
        name="Old campus gate",
        latitude=10.63,
        longitude=103.55,
        radius_meters=50,
        branch_id=2,
        is_active=False,
    )
    session = _FakeSession([inactive_location])

    with patch(
        "app.api.v1.employee_attendance._is_attendance_admin",
        return_value=True,
    ):
        result = asyncio.run(
            get_work_locations(
                show_all=True,
                branch_id=None,
                db=session,
                current_user=SimpleNamespace(id=1),
            )
        )

    assert session.query_result.filter_calls == 0
    assert result[0]["is_active"] is False
    assert WorkLocationResponse.model_validate(result[0]).is_active is False


def test_normal_location_list_still_applies_active_filter():
    session = _FakeSession([])

    with patch(
        "app.api.v1.employee_attendance._is_attendance_admin",
        return_value=True,
    ):
        asyncio.run(
            get_work_locations(
                show_all=False,
                branch_id=None,
                db=session,
                current_user=SimpleNamespace(id=1),
            )
        )

    assert session.query_result.filter_calls == 1
