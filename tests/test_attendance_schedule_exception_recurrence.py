from datetime import date
from types import SimpleNamespace
import unittest

from app.services.attendance_schedule_exception_service import (
    schedule_exception_occurs_in_range,
    schedule_exception_occurs_on,
    schedule_exception_recurrence_type,
)


def _row(
    start: date,
    *,
    recurrence_type: str | None = "once",
    end: date | None = None,
):
    return SimpleNamespace(
        exception_date=start,
        end_date=end,
        recurrence_type=recurrence_type,
    )


class ScheduleExceptionRecurrenceTests(unittest.TestCase):
    def test_once_only_matches_the_selected_date(self):
        row = _row(date(2026, 7, 19))

        self.assertTrue(schedule_exception_occurs_on(row, date(2026, 7, 19)))
        self.assertFalse(schedule_exception_occurs_on(row, date(2026, 7, 20)))
        self.assertFalse(schedule_exception_occurs_on(row, date(2026, 8, 19)))

    def test_date_range_is_inclusive_and_legacy_ranges_are_preserved(self):
        row = _row(
            date(2026, 7, 19),
            recurrence_type=None,
            end=date(2026, 7, 21),
        )

        self.assertEqual(schedule_exception_recurrence_type(row), "date_range")
        self.assertTrue(schedule_exception_occurs_on(row, date(2026, 7, 19)))
        self.assertTrue(schedule_exception_occurs_on(row, date(2026, 7, 21)))
        self.assertFalse(schedule_exception_occurs_on(row, date(2026, 7, 22)))

    def test_monthly_repeats_on_same_calendar_day_until_optional_end(self):
        row = _row(
            date(2026, 7, 19),
            recurrence_type="monthly",
            end=date(2026, 10, 19),
        )

        self.assertTrue(schedule_exception_occurs_on(row, date(2026, 8, 19)))
        self.assertFalse(schedule_exception_occurs_on(row, date(2026, 8, 20)))
        self.assertTrue(schedule_exception_occurs_on(row, date(2026, 10, 19)))
        self.assertFalse(schedule_exception_occurs_on(row, date(2026, 11, 19)))

    def test_monthly_day_31_skips_shorter_months(self):
        row = _row(date(2026, 1, 31), recurrence_type="monthly")

        self.assertFalse(
            schedule_exception_occurs_in_range(
                row,
                date(2026, 2, 1),
                date(2026, 2, 28),
            )
        )
        self.assertTrue(
            schedule_exception_occurs_in_range(
                row,
                date(2026, 3, 1),
                date(2026, 3, 31),
            )
        )


if __name__ == "__main__":
    unittest.main()
