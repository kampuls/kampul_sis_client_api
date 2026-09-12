import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.telegram_webhook_dedupe import (
    claim_telegram_webhook_event,
    ensure_telegram_webhook_events_table,
    telegram_membership_event_key,
    telegram_update_event_key,
)


class TelegramWebhookDedupeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        ensure_telegram_webhook_events_table(self.db)
        self.db.execute(text("DELETE FROM telegram_webhook_events"))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_same_update_is_claimed_only_once(self):
        key = telegram_update_event_key("123:secret", 9001)

        first = claim_telegram_webhook_event(
            self.db,
            event_key=key,
            event_type="update",
            update_id=9001,
        )
        second = claim_telegram_webhook_event(
            self.db,
            event_key=key,
            event_type="update",
            update_id=9001,
        )

        self.assertTrue(first)
        self.assertFalse(second)

    def test_update_ids_are_isolated_between_bot_tokens(self):
        first = claim_telegram_webhook_event(
            self.db,
            event_key=telegram_update_event_key("123:first", 42),
            event_type="update",
            update_id=42,
        )
        second = claim_telegram_webhook_event(
            self.db,
            event_key=telegram_update_event_key("456:second", 42),
            event_type="update",
            update_id=42,
        )

        self.assertTrue(first)
        self.assertTrue(second)

    def test_message_and_chat_member_share_one_membership_claim(self):
        key_from_message = telegram_membership_event_key(
            "123:secret", "join", -1001, 77
        )
        key_from_chat_member = telegram_membership_event_key(
            "123:secret", "join", -1001, 77
        )

        first = claim_telegram_webhook_event(
            self.db,
            event_key=key_from_message,
            event_type="member_join",
            chat_id=-1001,
            telegram_user_id=77,
            cooldown_seconds=30,
        )
        second = claim_telegram_webhook_event(
            self.db,
            event_key=key_from_chat_member,
            event_type="member_join",
            chat_id=-1001,
            telegram_user_id=77,
            cooldown_seconds=30,
        )

        self.assertTrue(first)
        self.assertFalse(second)

    def test_membership_claim_expires_for_a_real_later_rejoin(self):
        key = telegram_membership_event_key("123:secret", "join", -1001, 77)
        self.assertTrue(
            claim_telegram_webhook_event(
                self.db,
                event_key=key,
                event_type="member_join",
                cooldown_seconds=30,
            )
        )
        self.db.execute(
            text("""
                UPDATE telegram_webhook_events
                SET processed_at = :old_time
                WHERE event_key = :event_key
            """),
            {
                "old_time": datetime.utcnow() - timedelta(seconds=31),
                "event_key": key,
            },
        )
        self.db.commit()

        self.assertTrue(
            claim_telegram_webhook_event(
                self.db,
                event_key=key,
                event_type="member_join",
                cooldown_seconds=30,
            )
        )


if __name__ == "__main__":
    unittest.main()
