import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "notification_dedupe.py"
)
SPEC = importlib.util.spec_from_file_location("notification_dedupe", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NotificationDedupeTests(unittest.TestCase):
    def test_exact_duplicate_token_is_sent_once(self):
        rows = [
            {"id": 1, "token": "same-token"},
            {"id": 2, "token": "same-token"},
        ]

        result = MODULE.dedupe_device_tokens(rows)

        self.assertEqual(len(result), 1)

    def test_rotated_tokens_on_one_device_keep_most_recent(self):
        earlier = datetime(2026, 7, 20, 8, 0, 0)
        later = earlier + timedelta(days=1)
        rows = [
            {
                "id": 1,
                "token": "old-token",
                "user_id": 58,
                "user_type": "teacher",
                "device_type": "android",
                "device_name": "Samsung Galaxy S24",
                "last_used_at": earlier,
            },
            {
                "id": 2,
                "token": "new-token",
                "user_id": 58,
                "user_type": "teacher",
                "device_type": "android",
                "device_name": "Samsung Galaxy S24",
                "last_used_at": later,
            },
        ]

        result = MODULE.dedupe_device_tokens(rows)

        self.assertEqual([row["token"] for row in result], ["new-token"])

    def test_same_phone_name_for_different_users_is_not_merged(self):
        rows = [
            {
                "id": 1,
                "token": "token-one",
                "user_id": 58,
                "user_type": "teacher",
                "device_type": "ios",
                "device_name": "iPhone",
            },
            {
                "id": 2,
                "token": "token-two",
                "user_id": 59,
                "user_type": "teacher",
                "device_type": "ios",
                "device_name": "iPhone",
            },
        ]

        result = MODULE.dedupe_device_tokens(rows)

        self.assertEqual(len(result), 2)

    def test_unknown_devices_only_use_exact_token_dedupe(self):
        rows = [
            {"id": 1, "token": "one", "device_name": "unknown"},
            {"id": 2, "token": "two", "device_name": "unknown"},
        ]

        result = MODULE.dedupe_device_tokens(rows)

        self.assertEqual(len(result), 2)

    def test_logical_event_retry_keeps_the_same_key(self):
        data = {"type": "group_message", "message_id": "91"}

        first = MODULE.logical_notification_key("New message", "Hello", data)
        retry = MODULE.logical_notification_key("New message", "Hello", data)

        self.assertEqual(first, retry)

    def test_changed_event_content_gets_a_new_key(self):
        data = {"type": "new_news", "news_id": "12"}

        before = MODULE.logical_notification_key("News", "Before", data)
        after = MODULE.logical_notification_key("News", "After", data)

        self.assertNotEqual(before, after)

    def test_payload_without_event_identifier_stays_unique_per_send(self):
        self.assertIsNone(
            MODULE.logical_notification_key(
                "Permissions updated",
                "Refresh",
                {"type": "home_permission_updated", "user_id": "58"},
            )
        )


if __name__ == "__main__":
    unittest.main()
