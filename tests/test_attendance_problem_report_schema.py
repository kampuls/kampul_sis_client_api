import unittest
from pydantic import ValidationError

from app.schemas.employee_attendance import AttendanceProblemReportRequest


class AttendanceProblemReportSchemaTests(unittest.TestCase):
    def test_attendance_problem_report_accepts_allowlisted_diagnostic(self):
        report = AttendanceProblemReportRequest(
            issue_code="stale_gps",
            surface="quick_attendance",
            technical_message="GPS reading was stale.",
        )

        self.assertEqual(report.issue_code, "stale_gps")
        self.assertEqual(report.surface, "quick_attendance")

    def test_attendance_problem_report_rejects_untrusted_categories(self):
        for field, value in [
            ("issue_code", "password_dump"),
            ("surface", "arbitrary_screen"),
        ]:
            with self.subTest(field=field, value=value):
                payload = {
                    "issue_code": "stale_gps",
                    "surface": "quick_attendance",
                    "technical_message": "Short diagnostic",
                }
                payload[field] = value

                with self.assertRaises(ValidationError):
                    AttendanceProblemReportRequest(**payload)

    def test_attendance_problem_report_limits_diagnostic_length(self):
        with self.assertRaises(ValidationError):
            AttendanceProblemReportRequest(
                issue_code="unknown",
                surface="employee_attendance",
                technical_message="x" * 501,
            )

