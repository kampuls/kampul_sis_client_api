import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.leave_notification_service import (
    _fmt_days_summary,
    _leave_dates_tree,
    _leave_request_link,
    _send_telegram,
    _telegram_message,
)
from app.core.config import settings


class LeaveTelegramMessageFormatTests(unittest.TestCase):
    def test_each_full_leave_day_is_rendered_on_its_own_nested_line(self):
        request = SimpleNamespace(
            days=[
                SimpleNamespace(
                    leave_date=date(2026, 7, 25),
                    scope="full_day",
                    session_indexes=None,
                    time_from=None,
                    time_to=None,
                ),
                SimpleNamespace(
                    leave_date=date(2026, 7, 24),
                    scope="full_day",
                    session_indexes=None,
                    time_from=None,
                    time_to=None,
                ),
            ]
        )

        dates = _fmt_days_summary(request)
        message = _telegram_message(
            "✅ Leave Approved",
            [
                "Name: MOUT Sokhy",
                _leave_dates_tree(request),
                "By: CHHIT Khey",
            ],
        )

        self.assertIn(
            "├ 🗓️ Leave dates\n"
            "│  ├ 24/07/2026\n"
            "│  │  └ Full day\n"
            "│  └ 25/07/2026\n"
            "│     └ Full day",
            message,
        )
        self.assertEqual(
            dates,
            "24/07/2026\n"
            "   └ Full day\n"
            "25/07/2026\n"
            "   └ Full day",
        )
        self.assertNotIn("📅", message)
        self.assertNotIn("25/07/2026 — Full day", message)

    def test_session_scope_is_nested_below_date_with_compact_labels(self):
        request = SimpleNamespace(
            days=[
                SimpleNamespace(
                    leave_date=date(2026, 8, 3),
                    scope="sessions",
                    session_indexes=[1, 2],
                    time_from="08:00",
                    time_to="15:30",
                )
            ]
        )

        self.assertEqual(
            _fmt_days_summary(request),
            "03/08/2026\n   └ S1, S2 · 08:00–15:30",
        )
        self.assertIn(
            "└ 🗓️ Leave dates\n"
            "   └ 03/08/2026\n"
            "      └ S1, S2 · 08:00–15:30",
            _telegram_message(
                "📝 Leave Request",
                [_leave_dates_tree(request)],
            ),
        )

    def test_leave_request_link_contains_only_the_request_reference(self):
        with patch.dict(
            "os.environ",
            {"PAMA_APP_LINK_BASE_URL": "https://pamais.duckdns.org"},
        ):
            self.assertEqual(
                _leave_request_link(123),
                "https://pamais.duckdns.org/leave/123",
            )

    def test_leave_request_link_follows_the_configured_public_server(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "PAMA_APP_LINK_BASE_URL": "",
                    "PUBLIC_API_BASE_URL": "https://new-school.example",
                },
            ),
            patch.object(settings, "pama_app_link_base_url", ""),
        ):
            self.assertEqual(
                _leave_request_link(456),
                "https://new-school.example/leave/456",
            )

    def test_leave_request_link_is_omitted_without_a_valid_public_server(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "PAMA_APP_LINK_BASE_URL": "",
                    "PUBLIC_API_BASE_URL": "",
                },
            ),
            patch.object(settings, "pama_app_link_base_url", ""),
            patch.object(settings, "public_api_base_url", ""),
        ):
            self.assertIsNone(_leave_request_link(789))

    def test_production_never_uses_a_developer_lan_fallback(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "PAMA_APP_LINK_BASE_URL": "",
                    "PUBLIC_API_BASE_URL": "",
                },
            ),
            patch.object(settings, "environment", "production"),
            patch.object(
                settings,
                "public_api_base_url",
                "http://192.168.88.240:8000",
            ),
        ):
            self.assertIsNone(_leave_request_link(790))

    def test_telegram_message_uses_a_url_button_for_the_leave_request(self):
        payloads = []

        class _Response:
            status_code = 200
            text = "ok"

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, _url, json):
                payloads.append(json)
                return _Response()

        with patch("httpx.AsyncClient", return_value=_Client()):
            _send_telegram(
                "token",
                "-1001",
                "message",
                action_url="https://pamais.duckdns.org/leave/123",
            )

        self.assertEqual(
            payloads[0]["reply_markup"]["inline_keyboard"][0][0]["url"],
            "https://pamais.duckdns.org/leave/123",
        )

    def test_telegram_delivery_retries_transient_failures(self):
        attempts = 0

        class _Response:
            def __init__(self, status_code, text):
                self.status_code = status_code
                self.text = text

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, _url, json):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("temporary network error")
                if attempts == 2:
                    return _Response(503, "temporary Telegram error")
                return _Response(200, "ok")

        with (
            patch("httpx.AsyncClient", return_value=_Client()),
            patch(
                "app.services.leave_notification_service.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.leave_notification_service.logger.error",
            ) as log_error,
        ):
            _send_telegram("token", "-1001", "message")

        self.assertEqual(attempts, 3)
        log_error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
