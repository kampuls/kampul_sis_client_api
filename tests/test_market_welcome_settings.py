import unittest

from pydantic import ValidationError

from app.schemas.market import (
    MarketWelcomeSettingsResponse,
    MarketWelcomeSettingsUpdate,
)


class MarketWelcomeSettingsTests(unittest.TestCase):
    def test_defaults_preserve_existing_welcome_behavior(self):
        settings = MarketWelcomeSettingsResponse()

        self.assertTrue(settings.welcome_enabled)
        self.assertEqual(settings.welcome_skip_seconds, 30)
        self.assertEqual(settings.welcome_version, 1)

    def test_skip_timer_accepts_supported_range(self):
        self.assertEqual(
            MarketWelcomeSettingsUpdate(
                welcome_skip_seconds=0
            ).welcome_skip_seconds,
            0,
        )
        self.assertEqual(
            MarketWelcomeSettingsUpdate(
                welcome_skip_seconds=60
            ).welcome_skip_seconds,
            60,
        )

    def test_skip_timer_rejects_values_outside_supported_range(self):
        with self.assertRaises(ValidationError):
            MarketWelcomeSettingsUpdate(welcome_skip_seconds=-1)
        with self.assertRaises(ValidationError):
            MarketWelcomeSettingsUpdate(welcome_skip_seconds=61)


if __name__ == "__main__":
    unittest.main()
