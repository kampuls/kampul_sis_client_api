from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.attendance_model import (
    AttendanceRecord,
    AttendanceScheduleException,
    AttendanceScheduleExceptionEnrollment,
)
from app.services.attendance_schedule_exception_service import (
    available_self_enrollment_exceptions,
    enroll_in_schedule_exception_for_attendance,
    get_effective_day_attendance_with_exception,
    resolve_schedule_exception,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    AttendanceScheduleException.__table__.create(engine)
    AttendanceScheduleExceptionEnrollment.__table__.create(engine)
    AttendanceRecord.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _user(user_id: int = 7):
    return SimpleNamespace(
        id=user_id,
        departmentId=3,
        workplace=2,
        isForeigner=1,
    )


def _exception(
    *,
    optional: bool,
    reason: str,
    exception_type: str = "sessions_override",
):
    return AttendanceScheduleException(
        exception_date=date(2026, 8, 3),
        recurrence_type="once",
        exception_type=exception_type,
        sessions=(
            []
            if exception_type == "day_off"
            else [{"start": "09:00", "end": "11:00"}]
        ),
        reason=reason,
        is_active=1,
        self_enrollment_enabled=1 if optional else 0,
    )


def test_optional_exception_never_applies_until_employee_selects_it(db):
    normal_override = _exception(optional=False, reason="Mandatory change")
    meeting = _exception(optional=True, reason="Staff meeting")
    db.add_all([normal_override, meeting])
    db.commit()

    user = _user()
    assert resolve_schedule_exception(db, user, date(2026, 8, 3)).id == normal_override.id
    assert [row.id for row in available_self_enrollment_exceptions(
        db, user, date(2026, 8, 3)
    )] == [meeting.id]

    enroll_in_schedule_exception_for_attendance(
        db, user, date(2026, 8, 3), int(meeting.id)
    )
    db.commit()

    assert resolve_schedule_exception(db, user, date(2026, 8, 3)).id == meeting.id


def test_employee_cannot_change_the_choice_for_the_same_date(db):
    first = _exception(optional=True, reason="Meeting A")
    second = _exception(optional=True, reason="Meeting B")
    db.add_all([first, second])
    db.commit()

    user = _user()
    enroll_in_schedule_exception_for_attendance(
        db, user, date(2026, 8, 3), int(first.id)
    )
    db.commit()

    with pytest.raises(ValueError, match="schedule_exception_selection_locked"):
        enroll_in_schedule_exception_for_attendance(
            db, user, date(2026, 8, 3), int(second.id)
        )


def test_employee_cannot_join_after_attendance_has_started(db):
    meeting = _exception(optional=True, reason="Staff meeting")
    db.add(meeting)
    db.add(
        AttendanceRecord(
            user_id=7,
            attendance_date=date(2026, 8, 3),
            check_in_time=datetime(2026, 8, 3, 9, 0),
            status="present",
        )
    )
    db.commit()

    with pytest.raises(ValueError, match="attendance_already_started"):
        enroll_in_schedule_exception_for_attendance(
            db, _user(), date(2026, 8, 3), int(meeting.id)
        )


def test_employee_can_select_an_optional_day_off(db):
    day_off = _exception(
        optional=True,
        reason="Optional school closure",
        exception_type="day_off",
    )
    db.add(day_off)
    db.commit()

    user = _user()
    choices = available_self_enrollment_exceptions(
        db, user, date(2026, 8, 3)
    )
    assert [row.id for row in choices] == [day_off.id]
    assert resolve_schedule_exception(db, user, date(2026, 8, 3)) is None

    enroll_in_schedule_exception_for_attendance(
        db, user, date(2026, 8, 3), int(day_off.id)
    )
    db.commit()

    selected = resolve_schedule_exception(db, user, date(2026, 8, 3))
    assert selected.id == day_off.id
    effective = get_effective_day_attendance_with_exception(
        user,
        date(2026, 8, 3),
        schedule=None,
        exception=selected,
    )
    assert effective["is_active_day"] is False
    assert effective["sessions"] == []
    assert effective["exception_type"] == "day_off"
