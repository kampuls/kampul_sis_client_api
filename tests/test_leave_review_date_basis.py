import unittest
from datetime import date, datetime

from app.api.v1.leave_management import (
    _cambodia_date_filter_utc_bounds,
    _my_request_date_window,
    _review_activity_timestamp,
)


class LeaveReviewDateBasisTests(unittest.TestCase):
    def test_current_month_boundaries_use_cambodia_calendar_days(self):
        start_utc, end_exclusive_utc = _cambodia_date_filter_utc_bounds(
            date(2026, 6, 1),
            date(2026, 6, 30),
        )

        self.assertEqual(start_utc, datetime(2026, 5, 31, 17, 0))
        self.assertEqual(end_exclusive_utc, datetime(2026, 6, 30, 17, 0))

    def test_pending_basis_uses_request_submission_timestamp(self):
        expression = str(_review_activity_timestamp("submitted"))

        self.assertIn("LeaveRequest.created_at", expression)

    def test_processed_basis_uses_approval_or_cancellation_timestamp(self):
        expression = str(_review_activity_timestamp("decision"))

        self.assertIn("leave_requests.approval_date", expression)
        self.assertIn("leave_requests.cancelled_at", expression)

    def test_employee_history_activity_uses_status_specific_timestamp(self):
        expression = str(_review_activity_timestamp("activity"))

        self.assertIn("leave_requests.status", expression)
        self.assertIn("leave_requests.created_at", expression)
        self.assertIn("leave_requests.approval_date", expression)
        self.assertIn("leave_requests.cancelled_at", expression)

    def test_personal_pending_count_can_include_all_leave_dates(self):
        start_date, end_date = _my_request_date_window(None, None, True)

        self.assertIsNone(start_date)
        self.assertIsNone(end_date)

    def test_personal_history_still_defaults_to_current_month(self):
        start_date, end_date = _my_request_date_window(None, None, False)

        self.assertIsNotNone(start_date)
        self.assertIsNotNone(end_date)
        self.assertEqual(start_date[:7], end_date[:7])


if __name__ == "__main__":
    unittest.main()
