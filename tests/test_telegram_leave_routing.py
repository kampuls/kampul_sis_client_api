import unittest
from types import SimpleNamespace

from app.services.telegram_leave_routing import (
    normalize_leave_routing_mode,
    resolve_leave_notification_chat_id,
)


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Db:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        return _Result(self.row)


class TelegramLeaveRoutingTests(unittest.TestCase):
    def test_legacy_or_combined_mode_uses_attendance_destination(self):
        settings = SimpleNamespace(
            chat_id=" -100-attendance ",
            leave_chat_id="-100-leave",
            leave_routing_mode=None,
        )

        self.assertEqual(
            resolve_leave_notification_chat_id(settings),
            "-100-attendance",
        )

    def test_separate_mode_uses_leave_destination(self):
        settings = SimpleNamespace(
            chat_id="-100-attendance",
            leave_chat_id=" -100-leave ",
            leave_routing_mode="separate",
        )

        self.assertEqual(
            resolve_leave_notification_chat_id(settings),
            "-100-leave",
        )

    def test_separate_mode_never_falls_back_to_attendance(self):
        settings = SimpleNamespace(
            chat_id="-100-attendance",
            leave_chat_id=None,
            leave_routing_mode="separate",
        )

        self.assertIsNone(resolve_leave_notification_chat_id(settings))

    def test_unknown_mode_normalizes_to_combined(self):
        self.assertEqual(normalize_leave_routing_mode("unexpected"), "combined")

    def test_branch_leave_override_wins(self):
        settings = SimpleNamespace(
            id=1,
            chat_id="-100-attendance",
            leave_chat_id="-100-global-leave",
            leave_routing_mode="separate",
            branch_routing_mode="by_branch",
        )

        self.assertEqual(
            resolve_leave_notification_chat_id(
                settings,
                db=_Db(("-100-branch-attendance", "-100-branch-leave")),
                branch_id=2,
            ),
            "-100-branch-leave",
        )

    def test_branch_can_explicitly_share_attendance_in_separate_global_mode(self):
        settings = SimpleNamespace(
            id=1,
            chat_id="-100-attendance",
            leave_chat_id="-100-global-leave",
            leave_routing_mode="separate",
            branch_routing_mode="by_branch",
        )

        self.assertEqual(
            resolve_leave_notification_chat_id(
                settings,
                db=_Db(("-100-branch-attendance", None)),
                branch_id=2,
            ),
            "-100-branch-attendance",
        )

    def test_unmapped_branch_uses_existing_global_leave_rules(self):
        settings = SimpleNamespace(
            id=1,
            chat_id="-100-attendance",
            leave_chat_id="-100-global-leave",
            leave_routing_mode="separate",
            branch_routing_mode="by_branch",
        )

        self.assertEqual(
            resolve_leave_notification_chat_id(
                settings,
                db=_Db(None),
                branch_id=2,
            ),
            "-100-global-leave",
        )


if __name__ == "__main__":
    unittest.main()
