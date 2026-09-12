from datetime import date

from app.api.v1.employee_attendance import _approved_leave_days_for_dates


def test_approved_leave_total_includes_upcoming_dates_in_selected_period():
    leave_by_date = {
        date(2026, 7, 23): {"fraction": 1.0},
        date(2026, 7, 24): {"fraction": 1.0},
        date(2026, 7, 25): {"fraction": 0.5},
    }

    assert _approved_leave_days_for_dates(
        leave_by_date,
        {
            date(2026, 7, 23),
            date(2026, 7, 24),
            date(2026, 7, 25),
        },
    ) == 2.5


def test_approved_leave_total_excludes_dates_outside_report_filter():
    leave_by_date = {
        date(2026, 7, 23): {"fraction": 1.0},
        date(2026, 8, 1): {"fraction": 1.0},
    }

    assert _approved_leave_days_for_dates(
        leave_by_date,
        {date(2026, 7, 23)},
    ) == 1.0


def test_approved_leave_total_defensively_caps_each_user_day():
    leave_by_date = {
        date(2026, 7, 23): {"fraction": 4.0},
        date(2026, 7, 24): {"fraction": -1.0},
        date(2026, 7, 25): {"fraction": "invalid"},
    }

    assert _approved_leave_days_for_dates(
        leave_by_date,
        set(leave_by_date),
    ) == 1.0
