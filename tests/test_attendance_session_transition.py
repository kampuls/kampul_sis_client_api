from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_session_transition.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "attendance_session_transition",
    _MODULE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
calculate_session_transition_wait = _MODULE.calculate_session_transition_wait


class AttendanceSessionTransitionTests(unittest.TestCase):
    def test_wait_is_disabled_when_configured_as_zero(self):
        result = calculate_session_transition_wait(
            datetime(2026, 7, 21, 11, 0),
            datetime(2026, 7, 21, 11, 0),
            0,
        )

        self.assertIsNone(result)

    def test_immediate_next_session_check_in_is_blocked(self):
        result = calculate_session_transition_wait(
            datetime(2026, 7, 21, 11, 0),
            datetime(2026, 7, 21, 11, 0, 1),
            10,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.wait_minutes, 10)
        self.assertEqual(result.remaining_seconds, 599)
        self.assertEqual(result.available_at, datetime(2026, 7, 21, 11, 10))

    def test_check_in_is_allowed_when_wait_has_elapsed(self):
        result = calculate_session_transition_wait(
            datetime(2026, 7, 21, 11, 0),
            datetime(2026, 7, 21, 11, 10),
            10,
        )

        self.assertIsNone(result)

    def test_wait_reapplies_between_each_session_on_a_three_session_day(self):
        after_session_one = calculate_session_transition_wait(
            datetime(2026, 7, 21, 9, 0),
            datetime(2026, 7, 21, 9, 5),
            10,
        )
        after_session_two = calculate_session_transition_wait(
            datetime(2026, 7, 21, 12, 0),
            datetime(2026, 7, 21, 12, 2),
            10,
        )
        session_three_after_wait = calculate_session_transition_wait(
            datetime(2026, 7, 21, 12, 0),
            datetime(2026, 7, 21, 12, 10),
            10,
        )

        self.assertIsNotNone(after_session_one)
        self.assertEqual(after_session_one.remaining_seconds, 300)
        self.assertIsNotNone(after_session_two)
        self.assertEqual(after_session_two.remaining_seconds, 480)
        self.assertIsNone(session_three_after_wait)

    def test_naive_database_time_uses_school_timezone_from_now(self):
        school_tz = timezone.utc
        result = calculate_session_transition_wait(
            datetime(2026, 7, 21, 11, 0),
            datetime(2026, 7, 21, 11, 5, tzinfo=school_tz),
            10,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.remaining_seconds, 300)
        self.assertEqual(result.available_at.tzinfo, school_tz)


if __name__ == "__main__":
    unittest.main()
