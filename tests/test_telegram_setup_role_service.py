import unittest

from app.services.telegram_setup_role_service import (
    APP_ASSIGNABLE_TELEGRAM_ROLES,
    resolve_authorized_chat_role,
    telegram_role_label,
)


class TelegramSetupRoleServiceTests(unittest.TestCase):
    def test_app_roles_activate_directly_after_authorization(self):
        for role in APP_ASSIGNABLE_TELEGRAM_ROLES:
            with self.subTest(role=role):
                self.assertEqual(resolve_authorized_chat_role(role), role)

    def test_legacy_or_invalid_role_stays_unassigned(self):
        self.assertEqual(resolve_authorized_chat_role(None), "pending")
        self.assertEqual(resolve_authorized_chat_role("auth_pending"), "pending")
        self.assertEqual(resolve_authorized_chat_role("unexpected"), "pending")

    def test_role_labels_are_user_facing(self):
        self.assertEqual(telegram_role_label("general"), "General Group")
        self.assertEqual(
            telegram_role_label("notification_only"),
            "Notification Only",
        )
        self.assertEqual(telegram_role_label("pending"), "Awaiting App Setup")


if __name__ == "__main__":
    unittest.main()

