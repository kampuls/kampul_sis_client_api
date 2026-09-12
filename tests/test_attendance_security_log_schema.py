from datetime import datetime
import unittest

from app.schemas.employee_attendance import (
    CheckInSecurityEventItem,
    CheckInSecurityEventListResponse,
)


class AttendanceSecurityLogSchemaTests(unittest.TestCase):
    def test_delete_capability_defaults_to_read_only(self):
        response = CheckInSecurityEventListResponse(events=[])
        self.assertFalse(response.can_delete)

    def test_super_admin_delete_capability_can_be_exposed(self):
        response = CheckInSecurityEventListResponse(
            events=[
                CheckInSecurityEventItem(
                    id=1,
                    created_at=datetime(2026, 7, 22, 8, 0, 0),
                    event_type="outside_workplace",
                    severity="warning",
                    message="Blocked outside workplace",
                )
            ],
            can_delete=True,
        )
        self.assertTrue(response.can_delete)
        self.assertEqual(response.events[0].id, 1)


if __name__ == "__main__":
    unittest.main()
