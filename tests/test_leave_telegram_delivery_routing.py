import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services import leave_notification_service


def _request(*, status: str) -> SimpleNamespace:
    leave_day = SimpleNamespace(
        leave_date=date(2026, 7, 25),
        scope="full_day",
        session_indexes=None,
        time_from=None,
        time_to=None,
    )
    return SimpleNamespace(
        id=41,
        user_id=7,
        total_days=1.0,
        start_date=leave_day.leave_date,
        end_date=leave_day.leave_date,
        status=status,
        reason="Family appointment",
        rejection_reason=None,
        cancel_reason=None,
        replacement_user_id=None,
        days=[leave_day],
    )


def _requester() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        eName="Employee One",
        kName=None,
        username="employee.one",
        workplace=2,
    )


def _separate_settings() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        bot_token="test-token",
        chat_id="-100-attendance",
        leave_chat_id="-100-leave",
        leave_routing_mode="separate",
        branch_routing_mode="all",
        notify_leave_requests=True,
        notify_leave_decisions=True,
    )


class LeaveTelegramDeliveryRoutingTests(unittest.TestCase):
    def test_employee_request_is_sent_to_configured_leave_group(self):
        db = Mock()
        request = _request(status="pending")
        requester = _requester()
        leave_type = SimpleNamespace(name="Annual Leave")

        with (
            patch.object(leave_notification_service, "SessionLocal", return_value=db),
            patch.object(
                leave_notification_service,
                "_load_request",
                return_value=(request, requester, leave_type),
            ),
            patch.object(
                leave_notification_service,
                "_telegram_settings",
                return_value=_separate_settings(),
            ),
            patch.object(
                leave_notification_service,
                "_eligible_approvers",
                return_value=[],
            ),
            patch.object(
                leave_notification_service,
                "_replacement_user",
                return_value=None,
            ),
            patch.object(leave_notification_service, "_push_to_users"),
            patch.object(leave_notification_service, "_send_telegram") as send,
        ):
            leave_notification_service.notify_leave_request_created(request.id)

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], "-100-leave")
        self.assertNotEqual(send.call_args.args[1], "-100-attendance")
        db.close.assert_called_once()

    def test_approval_is_sent_to_same_configured_leave_group(self):
        db = Mock()
        request = _request(status="approved")
        requester = _requester()
        leave_type = SimpleNamespace(name="Annual Leave")
        decider = SimpleNamespace(
            id=9,
            eName="Approver One",
            kName=None,
            username="approver.one",
        )
        db.query.return_value.filter.return_value.first.return_value = decider

        with (
            patch.object(leave_notification_service, "SessionLocal", return_value=db),
            patch.object(
                leave_notification_service,
                "_load_request",
                return_value=(request, requester, leave_type),
            ),
            patch.object(
                leave_notification_service,
                "_telegram_settings",
                return_value=_separate_settings(),
            ),
            patch.object(
                leave_notification_service,
                "_eligible_approvers",
                return_value=[],
            ),
            patch.object(
                leave_notification_service,
                "_replacement_user",
                return_value=None,
            ),
            patch.object(leave_notification_service, "_push_to_users"),
            patch.object(leave_notification_service, "_notify_replacement_assigned"),
            patch.object(leave_notification_service, "_send_telegram") as send,
        ):
            leave_notification_service.notify_leave_request_decided(
                request.id,
                decider.id,
            )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], "-100-leave")
        self.assertNotEqual(send.call_args.args[1], "-100-attendance")
        self.assertIn("Leave Approved", send.call_args.args[2])
        db.close.assert_called_once()

    def test_rejection_is_sent_to_same_configured_leave_group(self):
        db = Mock()
        request = _request(status="rejected")
        request.rejection_reason = "Coverage unavailable"
        requester = _requester()
        leave_type = SimpleNamespace(name="Annual Leave")
        decider = SimpleNamespace(
            id=9,
            eName="Approver One",
            kName=None,
            username="approver.one",
        )
        db.query.return_value.filter.return_value.first.return_value = decider

        with (
            patch.object(leave_notification_service, "SessionLocal", return_value=db),
            patch.object(
                leave_notification_service,
                "_load_request",
                return_value=(request, requester, leave_type),
            ),
            patch.object(
                leave_notification_service,
                "_telegram_settings",
                return_value=_separate_settings(),
            ),
            patch.object(
                leave_notification_service,
                "_eligible_approvers",
                return_value=[],
            ),
            patch.object(
                leave_notification_service,
                "_replacement_user",
                return_value=None,
            ),
            patch.object(leave_notification_service, "_push_to_users"),
            patch.object(leave_notification_service, "_send_telegram") as send,
        ):
            leave_notification_service.notify_leave_request_decided(
                request.id,
                decider.id,
            )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], "-100-leave")
        self.assertNotEqual(send.call_args.args[1], "-100-attendance")
        self.assertIn("Leave Rejected", send.call_args.args[2])
        db.close.assert_called_once()

    def test_cancellation_is_sent_to_same_configured_leave_group(self):
        db = Mock()
        request = _request(status="cancelled")
        request.cancel_reason = "Plans changed"
        requester = _requester()
        leave_type = SimpleNamespace(name="Annual Leave")
        canceller = SimpleNamespace(
            id=7,
            eName="Employee One",
            kName=None,
            username="employee.one",
        )
        db.query.return_value.filter.return_value.first.return_value = canceller

        with (
            patch.object(leave_notification_service, "SessionLocal", return_value=db),
            patch.object(
                leave_notification_service,
                "_load_request",
                return_value=(request, requester, leave_type),
            ),
            patch.object(
                leave_notification_service,
                "_telegram_settings",
                return_value=_separate_settings(),
            ),
            patch.object(
                leave_notification_service,
                "_eligible_approvers",
                return_value=[],
            ),
            patch.object(leave_notification_service, "_push_to_users"),
            patch.object(leave_notification_service, "_send_telegram") as send,
        ):
            leave_notification_service.notify_leave_request_cancelled(
                request.id,
                canceller.id,
            )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], "-100-leave")
        self.assertNotEqual(send.call_args.args[1], "-100-attendance")
        self.assertIn("Leave Request Cancelled", send.call_args.args[2])
        self.assertIn("Plans changed", send.call_args.args[2])
        db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
