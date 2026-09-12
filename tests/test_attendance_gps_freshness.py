from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_gps_freshness.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "attendance_gps_freshness",
    _MODULE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class AttendanceGpsFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 23, 1, 0, tzinfo=timezone.utc)

    def test_age_is_calculated_in_utc(self):
        cambodia_time = self.now.astimezone(timezone(timedelta(hours=7)))
        self.assertEqual(
            _MODULE.gps_age_seconds(cambodia_time, now=self.now),
            0.0,
        )

    def test_naive_legacy_timestamp_is_treated_as_utc(self):
        naive = self.now.replace(tzinfo=None) - timedelta(seconds=10)
        self.assertEqual(
            _MODULE.gps_age_seconds(naive, now=self.now),
            10.0,
        )

    def test_security_window_boundaries_are_inclusive(self):
        self.assertTrue(_MODULE.is_current_gps_age(-30.0))
        self.assertTrue(_MODULE.is_current_gps_age(120.0))
        self.assertFalse(_MODULE.is_current_gps_age(-30.1))
        self.assertFalse(_MODULE.is_current_gps_age(120.1))

    def test_device_clock_skew_boundaries_are_inclusive(self):
        self.assertFalse(_MODULE.is_device_time_incorrect(-30.0))
        self.assertFalse(_MODULE.is_device_time_incorrect(30.0))
        self.assertTrue(_MODULE.is_device_time_incorrect(-30.1))
        self.assertTrue(_MODULE.is_device_time_incorrect(30.1))

    def test_incorrect_device_time_error_is_structured(self):
        self.assertEqual(
            _MODULE.incorrect_device_time_error_detail(
                3600.123,
                server_time=self.now,
            ),
            {
                "code": "device_time_incorrect",
                "message": (
                    "Attendance blocked: your phone date and time do not match "
                    "the official server time. Enable automatic date and time "
                    "and automatic time zone, then try again."
                ),
                "clock_offset_seconds": 3600.1,
                "server_time_iso": "2026-07-23T01:00:00+00:00",
            },
        )

    def test_stale_error_is_structured_for_mobile_clients(self):
        self.assertEqual(
            _MODULE.stale_gps_error_detail(121.234),
            {
                "code": "stale_gps",
                "message": (
                    "Attendance blocked: the GPS reading is not current. "
                    "Refresh your location and try again."
                ),
                "gps_age_seconds": 121.2,
            },
        )


if __name__ == "__main__":
    unittest.main()
