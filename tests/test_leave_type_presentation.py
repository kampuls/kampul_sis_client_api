import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.api.v1.leave_management import _leave_type_ordering, _leave_type_out
from app.schemas.leave_management import LeaveTypeCreate, LeaveTypeUpdate


class LeaveTypePresentationTests(unittest.TestCase):
    def test_create_schema_accepts_order_and_preset_color(self):
        payload = LeaveTypeCreate(
            name="Annual Leave",
            display_order=2,
            color_hex="#7C3AED",
        )

        self.assertEqual(payload.display_order, 2)
        self.assertEqual(payload.color_hex, "#7C3AED")

    def test_schema_rejects_invalid_card_color(self):
        with self.assertRaises(ValidationError):
            LeaveTypeUpdate(color_hex="purple")

    def test_leave_type_output_includes_presentation_fields(self):
        leave_type = SimpleNamespace(
            id=7,
            name="Study Leave",
            description=None,
            max_days_per_year=3,
            is_paid=True,
            requires_approval=True,
            requires_proof=False,
            is_active=True,
            display_order=4,
            color_hex="#0d9488",
            created_at=None,
        )

        output = _leave_type_out(leave_type)

        self.assertEqual(output.display_order, 4)
        self.assertEqual(output.color_hex, "#0D9488")

    def test_default_order_falls_back_to_creation_date(self):
        ordering = _leave_type_ordering()

        self.assertIn("coalesce", str(ordering[0]).lower())
        self.assertIn("created_at", str(ordering[1]).lower())
        self.assertIn("id", str(ordering[2]).lower())


if __name__ == "__main__":
    unittest.main()
