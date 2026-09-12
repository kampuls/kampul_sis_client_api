import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api.v1.leave_management import _serialize_requests


class LeaveRequestContactSerializationTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(
            id=10,
            eName="Employee One",
            kName="បុគ្គលិក មួយ",
            phone="  +855 12 345 678  ",
            departmentId=None,
            workplace=None,
        )
        self.leave_type = SimpleNamespace(id=3, name="Annual Leave", is_paid=True)
        self.request = SimpleNamespace(
            id=42,
            user_id=10,
            leave_type_id=3,
            academic_id=1,
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 24),
            total_days=2.0,
            reason="Family matter",
            status="pending",
            approver_id=None,
            approval_date=None,
            rejection_reason=None,
            cancelled_by=None,
            cancelled_at=None,
            cancel_reason=None,
            created_at=None,
            created_by=None,
            creation_source="employee",
            replacement_user_id=None,
            replacement_note=None,
            proof_image_path=None,
            days=[],
        )
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.all.return_value = [
            self.leave_type
        ]

    @patch(
        "app.api.v1.leave_management._name_maps",
        return_value=({}, {}),
    )
    @patch("app.api.v1.leave_management._user_maps")
    def test_phone_is_only_populated_for_reviewer_responses(
        self,
        user_maps,
        _name_maps,
    ):
        user_maps.return_value = ({10: self.user}, {})

        general = _serialize_requests(self.db, [self.request])[0]
        reviewer = _serialize_requests(
            self.db,
            [self.request],
            include_user_phone=True,
        )[0]

        self.assertIsNone(general.user_phone)
        self.assertEqual(reviewer.user_phone, "+855 12 345 678")
        self.assertEqual(general.user_name_en, "Employee One")
        self.assertEqual(general.user_name_kh, "បុគ្គលិក មួយ")


if __name__ == "__main__":
    unittest.main()
