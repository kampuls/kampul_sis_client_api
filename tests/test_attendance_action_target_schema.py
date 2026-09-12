import unittest

from pydantic import ValidationError

from app.schemas.employee_attendance import CheckInOutRequest


class AttendanceActionTargetSchemaTests(unittest.TestCase):
    def test_explicit_checkout_accepts_one_based_session_target(self):
        request = CheckInOutRequest(action="check_out", session_index=1)

        self.assertEqual(request.action, "check_out")
        self.assertEqual(request.session_index, 1)

    def test_session_target_must_be_positive(self):
        with self.assertRaises(ValidationError):
            CheckInOutRequest(action="check_out", session_index=0)


if __name__ == "__main__":
    unittest.main()
