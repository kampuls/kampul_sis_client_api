import unittest
from datetime import datetime
from unittest.mock import patch

from app.services.telegram_message_format import (
    safe_telegram_html,
    telegram_status_card,
)
from app.services.telegram_notification_service import (
    TelegramNotificationService,
)


class _SuccessfulResponse:
    status_code = 200
    text = '{"ok": true}'


class _RecordingAsyncClient:
    payloads = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, json):
        self.payloads.append(json)
        return _SuccessfulResponse()


class TelegramMessageFormatTests(unittest.TestCase):
    def test_status_card_has_consistent_sections(self):
        message = telegram_status_card(
            "✅",
            "Setup complete",
            message="The bot is ready.",
            fields=(("👥", "Group type", "General Group"),),
            action_title="Manage settings",
            action="Use the PAMA app.",
            note="This code can be used only once.",
        )

        self.assertTrue(message.startswith("✅ <b>Setup complete</b>"))
        self.assertIn("👥 <b>Group type:</b> General Group", message)
        self.assertIn("✅ <b>Manage settings</b>", message)
        self.assertIn("ℹ️ <i>This code can be used only once.</i>", message)

    def test_every_plain_text_value_is_html_escaped(self):
        message = telegram_status_card(
            "⚠️",
            "<Unsafe>",
            message="A & B < C",
            fields=(("👤", "Member", "<script>alert('x')</script>"),),
            action="Open <Settings> & retry.",
            note="Do not show <b>raw markup</b>.",
        )

        self.assertNotIn("<script>", message)
        self.assertNotIn("<Unsafe>", message)
        self.assertIn("&lt;Unsafe&gt;", message)
        self.assertIn("A &amp; B &lt; C", message)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", message)
        self.assertIn("Open &lt;Settings&gt; &amp; retry.", message)

    def test_safe_html_normalizes_and_shortens_long_values(self):
        value = "  unsafe   <name>  " + "x" * 100

        result = safe_telegram_html(value, limit=30)

        self.assertNotIn("  ", result)
        self.assertIn("&lt;name&gt;", result)
        self.assertTrue(result.endswith("…"))

    def test_steps_are_numbered_and_escaped(self):
        message = telegram_status_card(
            "🔐",
            "Authorization required",
            steps=("Open PAMA", "Choose General & continue"),
        )

        self.assertIn("1. Open PAMA", message)
        self.assertIn("2. Choose General &amp; continue", message)


class TelegramNotificationMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_attendance_notification_escapes_dynamic_html(self):
        _RecordingAsyncClient.payloads = []
        with patch(
            "app.services.telegram_notification_service.httpx.AsyncClient",
            _RecordingAsyncClient,
        ):
            sent = await TelegramNotificationService.send_attendance_notification(
                "token",
                "chat",
                "<Admin & Staff>",
                "check_in",
                datetime(2026, 7, 22, 8, 30),
                location_name="Main <Campus>",
                notes="Use <b>door A</b>",
                status="present",
            )

        self.assertTrue(sent)
        text = _RecordingAsyncClient.payloads[0]["text"]
        self.assertIn("&lt;Admin &amp; Staff&gt;", text)
        self.assertIn("Main &lt;Campus&gt;", text)
        self.assertIn("Use &lt;b&gt;door A&lt;/b&gt;", text)
        self.assertNotIn("<Admin", text)


if __name__ == "__main__":
    unittest.main()
