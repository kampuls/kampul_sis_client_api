import unittest
from types import SimpleNamespace

from app.services.telegram_attendance_routing import (
    attendance_notification_chat_ids,
)
from app.services.telegram_branch_routing import (
    normalize_branch_routing_mode,
    resolve_attendance_notification_chat_id,
)
from app.schemas.telegram_attendance import TelegramAttendanceSettingsUpdate


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Db:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error

    def execute(self, *_args, **_kwargs):
        if self.error is not None:
            raise self.error
        return _Result(self.rows)


class TelegramAttendanceRoutingTests(unittest.TestCase):
    def test_prefers_report_then_selected_then_notification_chats(self):
        db = _Db(
            rows=[
                ("-1003", "notification_only"),
                ("-1002", "general"),
                ("-1001", "notification_only"),
            ]
        )

        result = attendance_notification_chat_ids(
            db,
            bot_token="token",
            preferred_chat_id="-1009",
            primary_chat_id="-1001",
        )

        self.assertEqual(result, ["-1009", "-1001", "-1003"])

    def test_excludes_selected_chat_when_it_is_a_general_group(self):
        db = _Db(rows=[("-1002", "general"), ("-1003", "notification_only")])

        result = attendance_notification_chat_ids(
            db,
            bot_token="token",
            primary_chat_id="-1002",
        )

        self.assertEqual(result, ["-1003"])

    def test_excludes_legacy_report_chat_when_it_is_now_a_general_group(self):
        db = _Db(rows=[("-1002", "general"), ("-1003", "notification_only")])

        result = attendance_notification_chat_ids(
            db,
            bot_token="token",
            preferred_chat_id="-1002",
        )

        self.assertEqual(result, ["-1003"])

    def test_legacy_selected_chat_survives_missing_tracked_chat_table(self):
        db = _Db(error=RuntimeError("table unavailable"))

        result = attendance_notification_chat_ids(
            db,
            bot_token="token",
            primary_chat_id="-1001",
        )

        self.assertEqual(result, ["-1001"])

    def test_branch_attendance_override_wins_when_enabled(self):
        settings = SimpleNamespace(
            id=1,
            chat_id="-100-global",
            branch_routing_mode="by_branch",
        )
        db = _Db(rows=[("-100-branch", None)])

        self.assertEqual(
            resolve_attendance_notification_chat_id(
                settings,
                db=db,
                branch_id=7,
            ),
            "-100-branch",
        )

    def test_unmapped_branch_falls_back_to_global_attendance(self):
        settings = SimpleNamespace(
            id=1,
            chat_id=" -100-global ",
            branch_routing_mode="by_branch",
        )

        self.assertEqual(
            resolve_attendance_notification_chat_id(
                settings,
                db=_Db(),
                branch_id=7,
            ),
            "-100-global",
        )

    def test_attendance_route_never_uses_the_separate_leave_group(self):
        settings = SimpleNamespace(
            id=1,
            chat_id="-100-attendance",
            leave_chat_id="-100-leave",
            leave_routing_mode="separate",
            branch_routing_mode="all",
        )

        self.assertEqual(
            resolve_attendance_notification_chat_id(settings, db=_Db()),
            "-100-attendance",
        )

    def test_old_settings_default_to_all_branches(self):
        self.assertEqual(normalize_branch_routing_mode(None), "all")
        self.assertEqual(normalize_branch_routing_mode("unexpected"), "all")

    def test_old_client_update_does_not_clear_branch_configuration(self):
        update = TelegramAttendanceSettingsUpdate(
            bot_token="token",
            chat_id="-100-global",
            enabled=True,
        ).model_dump(exclude_unset=True)

        self.assertNotIn("branch_routing_mode", update)
        self.assertNotIn("branch_routes", update)


if __name__ == "__main__":
    unittest.main()
