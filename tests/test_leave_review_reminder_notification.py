import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.leave_notification_service import (
    ROUTE_APPROVER_INBOX,
    notify_leave_review_reminder,
)


class LeaveReviewReminderNotificationTests(unittest.TestCase):
    @patch("app.services.leave_notification_service._push_to_users")
    @patch("app.services.leave_notification_service._load_request")
    @patch("app.services.leave_notification_service.SessionLocal")
    def test_reminder_targets_exact_request_with_decision_copy(
        self,
        session_local,
        load_request,
        push_to_users,
    ):
        db = MagicMock()
        session_local.return_value = db
        request = SimpleNamespace(
            id=42,
            user_id=10,
            status="pending",
            total_days=2.0,
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 24),
        )
        requester = SimpleNamespace(
            id=10,
            eName="Employee One",
            kName="",
            username="employee",
        )
        leave_type = SimpleNamespace(name="Annual Leave")
        sender = SimpleNamespace(
            id=11,
            eName="Read-only Reviewer",
            kName="",
            username="reviewer",
        )
        load_request.return_value = (request, requester, leave_type)
        db.query.return_value.filter.return_value.first.return_value = sender

        notify_leave_review_reminder(42, 11, [20, 21])

        push_to_users.assert_called_once()
        args = push_to_users.call_args.args
        kwargs = push_to_users.call_args.kwargs
        self.assertIs(args[0], db)
        self.assertEqual(args[1], [20, 21])
        self.assertEqual(
            kwargs["title"],
            "Leave Request Awaiting Your Decision",
        )
        self.assertIn("Read-only Reviewer", kwargs["body"])
        self.assertIn("Employee One", kwargs["body"])
        self.assertIn("Tap to review and decide", kwargs["body"])
        self.assertEqual(kwargs["redirect_route"], ROUTE_APPROVER_INBOX)
        self.assertEqual(kwargs["request_id"], 42)
        self.assertEqual(kwargs["notification_type"], "leave_request")
        db.close.assert_called_once()

    @patch("app.services.leave_notification_service._push_to_users")
    @patch("app.services.leave_notification_service._load_request")
    @patch("app.services.leave_notification_service.SessionLocal")
    def test_requester_reminder_uses_clear_decision_copy(
        self,
        session_local,
        load_request,
        push_to_users,
    ):
        db = MagicMock()
        session_local.return_value = db
        request = SimpleNamespace(
            id=42,
            user_id=10,
            status="pending",
            total_days=2.0,
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 24),
        )
        requester = SimpleNamespace(
            id=10,
            eName="Employee One",
            kName="",
            username="employee",
        )
        load_request.return_value = (
            request,
            requester,
            SimpleNamespace(name="Annual Leave"),
        )
        db.query.return_value.filter.return_value.first.return_value = requester

        notify_leave_review_reminder(42, 10, [20, 21])

        kwargs = push_to_users.call_args.kwargs
        self.assertEqual(
            kwargs["title"],
            "Pending Leave Request — Decision Needed",
        )
        self.assertIn(
            "Employee One has a pending 2-day Annual Leave request",
            kwargs["body"],
        )
        self.assertIn("waiting for your decision", kwargs["body"])
        self.assertIn("approve or reject", kwargs["body"])
        self.assertEqual(kwargs["request_id"], 42)


if __name__ == "__main__":
    unittest.main()
