import unittest
from datetime import datetime, timedelta

from app.services.attendance_reminder_service import (
    AFTER_REMINDER_RETRY_WINDOW_MINUTES,
    _latest_due_reminder_offset,
    attendance_reminder_action_payload,
)


class AttendanceReminderActionPayloadTests(unittest.TestCase):
    def test_check_in_reminder_has_explicit_check_in_action(self):
        payload = attendance_reminder_action_payload("before_in")

        self.assertEqual(payload["is_check_in"], "true")
        self.assertEqual(
            payload["notification_category"],
            "CHECK_IN_REMINDER_CATEGORY",
        )
        self.assertEqual(payload["actions"][0]["id"], "check_in")

    def test_check_out_reminder_has_explicit_check_out_action(self):
        payload = attendance_reminder_action_payload("after_out")

        self.assertEqual(payload["is_check_in"], "false")
        self.assertEqual(
            payload["notification_category"],
            "CHECK_OUT_REMINDER_CATEGORY",
        )
        self.assertEqual(payload["actions"][0]["id"], "check_out")

    def test_unknown_reminder_type_is_rejected(self):
        with self.assertRaises(ValueError):
            attendance_reminder_action_payload("unknown")


class AttendanceReminderDueWindowTests(unittest.TestCase):
    def setUp(self):
        self.event = datetime(2026, 8, 12, 8, 0)

    def test_before_reminder_is_due_at_exact_configured_minute(self):
        offset = _latest_due_reminder_offset(
            now_min=self.event - timedelta(minutes=10),
            event_dt=self.event,
            offsets=[10],
            before_event=True,
        )

        self.assertEqual(offset, 10)

    def test_delayed_before_reminder_remains_due_until_shift_starts(self):
        offset = _latest_due_reminder_offset(
            now_min=self.event - timedelta(minutes=7),
            event_dt=self.event,
            offsets=[10],
            before_event=True,
        )

        self.assertEqual(offset, 10)

    def test_only_latest_due_offset_is_selected_after_scheduler_pause(self):
        offset = _latest_due_reminder_offset(
            now_min=self.event - timedelta(minutes=3),
            event_dt=self.event,
            offsets=[10, 5],
            before_event=True,
        )

        self.assertEqual(offset, 5)

    def test_before_reminder_is_not_sent_after_shift_has_started(self):
        offset = _latest_due_reminder_offset(
            now_min=self.event + timedelta(minutes=1),
            event_dt=self.event,
            offsets=[10],
            before_event=True,
        )

        self.assertIsNone(offset)

    def test_after_reminder_retries_inside_bounded_window(self):
        offset = _latest_due_reminder_offset(
            now_min=self.event + timedelta(minutes=12),
            event_dt=self.event,
            offsets=[10],
            before_event=False,
        )

        self.assertEqual(offset, 10)

    def test_after_reminder_expires_after_retry_window(self):
        offset = _latest_due_reminder_offset(
            now_min=(
                self.event
                + timedelta(
                    minutes=10 + AFTER_REMINDER_RETRY_WINDOW_MINUTES
                )
            ),
            event_dt=self.event,
            offsets=[10],
            before_event=False,
        )

        self.assertIsNone(offset)


if __name__ == "__main__":
    unittest.main()
