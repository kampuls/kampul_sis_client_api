import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_security_alert_policy.py"
)
SPEC = importlib.util.spec_from_file_location(
    "attendance_security_alert_policy",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AttendanceSecurityAlertPolicyTests(unittest.TestCase):
    def test_outside_workplace_is_logged_without_telegram_alert(self):
        self.assertFalse(
            MODULE.should_send_attendance_security_telegram(
                "outside_workplace",
                "warning",
            )
        )

    def test_employee_problem_report_keeps_its_separate_telegram_route(self):
        self.assertFalse(
            MODULE.should_send_attendance_security_telegram(
                "employee_problem_report",
                "critical",
            )
        )

    def test_only_critical_security_events_alert_telegram(self):
        self.assertTrue(
            MODULE.should_send_attendance_security_telegram(
                "mock_location",
                "critical",
            )
        )
        self.assertFalse(
            MODULE.should_send_attendance_security_telegram(
                "attendance_primary_device_mismatch",
                "warning",
            )
        )
        self.assertFalse(
            MODULE.should_send_attendance_security_telegram(
                "shared_nat_burst",
                "info",
            )
        )

    def test_severity_is_normalized_and_unknown_values_are_suppressed(self):
        self.assertTrue(
            MODULE.should_send_attendance_security_telegram(
                "compromised_device",
                " Critical ",
            )
        )
        self.assertFalse(
            MODULE.should_send_attendance_security_telegram(
                "compromised_device",
                "",
            )
        )


if __name__ == "__main__":
    unittest.main()
