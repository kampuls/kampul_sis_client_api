import unittest

from app.services.telegram_member_verification_service import (
    get_member_verification_enabled,
    member_chat_permissions,
)


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Database:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error

    def execute(self, _query, _params):
        if self.error:
            raise self.error
        return _Result(self.row)


class TelegramMemberVerificationServiceTests(unittest.TestCase):
    def test_verification_defaults_to_disabled_for_unconfigured_group(self):
        self.assertFalse(get_member_verification_enabled(_Database(), "group-1"))

    def test_saved_disabled_setting_is_respected(self):
        self.assertFalse(
            get_member_verification_enabled(_Database(row=(False,)), "group-1")
        )

    def test_database_failure_uses_disabled_default(self):
        self.assertFalse(
            get_member_verification_enabled(
                _Database(error=RuntimeError("database unavailable")),
                "group-1",
            )
        )

    def test_locked_permissions_prevent_all_message_types(self):
        permissions = member_chat_permissions(can_chat=False)

        self.assertTrue(permissions)
        self.assertTrue(all(value is False for value in permissions.values()))

    def test_unlocked_permissions_restore_chat_and_invites(self):
        permissions = member_chat_permissions(can_chat=True)

        self.assertTrue(all(value is True for value in permissions.values()))
        self.assertTrue(permissions["can_invite_users"])


if __name__ == "__main__":
    unittest.main()
