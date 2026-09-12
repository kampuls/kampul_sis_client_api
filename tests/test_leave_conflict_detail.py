import unittest
from datetime import date

from app.api.v1.leave_management import _leave_date_conflict_detail


class LeaveConflictDetailTests(unittest.TestCase):
    def test_conflict_detail_is_structured_and_sorts_unique_dates(self):
        detail = _leave_date_conflict_detail(
            [
                date(2026, 8, 7),
                date(2026, 8, 5),
                date(2026, 8, 5),
            ]
        )

        self.assertEqual(detail["code"], "leave_date_conflict")
        self.assertEqual(
            detail["conflict_dates"],
            ["2026-08-05", "2026-08-07"],
        )
        self.assertIn("05/08/2026, 07/08/2026", detail["message"])

    def test_manual_conflict_names_the_employee(self):
        detail = _leave_date_conflict_detail(
            [date(2026, 8, 5)],
            employee_name="Employee One",
        )

        self.assertEqual(
            detail["message"],
            "Employee One already has pending or approved leave on 05/08/2026",
        )


if __name__ == "__main__":
    unittest.main()
