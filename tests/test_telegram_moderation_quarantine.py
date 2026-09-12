import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import telegram_moderation_service as moderation


def _album_document(message_id: int, file_name: str) -> dict:
    return {
        "message_id": message_id,
        "media_group_id": "album-42",
        "chat": {"id": -100123, "type": "supergroup"},
        "from": {"id": 77, "first_name": "Teacher", "is_bot": False},
        "document": {
            "file_id": f"file-{message_id}",
            "file_name": file_name,
            "mime_type": "application/octet-stream",
        },
    }


def _link_message(message_id: int, url: str) -> dict:
    return {
        "message_id": message_id,
        "chat": {"id": -100123, "type": "supergroup"},
        "from": {"id": 77, "first_name": "Teacher", "is_bot": False},
        "text": url,
        "entities": [{"type": "url", "offset": 0, "length": len(url)}],
    }


class TelegramModerationInPlaceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    async def test_safe_album_items_stay_as_their_original_messages(self):
        delete_mock = AsyncMock(return_value=(True, None))
        warning_mock = AsyncMock()
        messages = [
            _album_document(100, "lesson.pdf"),
            _album_document(101, "worksheet.docx"),
        ]

        with (
            patch.object(
                moderation,
                "_delete_telegram_messages",
                new=delete_mock,
            ),
            patch.object(
                moderation,
                "_send_moderation_warning",
                new=warning_mock,
            ),
        ):
            results = [
                await moderation.moderate_general_group_message(
                    self.db,
                    message,
                    "123:test-token",
                )
                for message in messages
            ]

        self.assertEqual(results, [{"handled": False}, {"handled": False}])
        delete_mock.assert_not_awaited()
        warning_mock.assert_not_awaited()
        self.assertFalse(
            hasattr(moderation, "_restore_quarantined_media_group"),
            "Safe Telegram posts must never be deleted and resent by the bot",
        )

    async def test_only_the_unsafe_album_item_is_removed(self):
        delete_mock = AsyncMock(return_value=(True, None))
        warning_mock = AsyncMock(return_value=(True, None))
        messages = [
            _album_document(200, "lesson.pdf"),
            _album_document(201, "installer.exe"),
        ]

        with (
            patch.object(
                moderation,
                "_delete_telegram_messages",
                new=delete_mock,
            ),
            patch.object(
                moderation,
                "_send_moderation_warning",
                new=warning_mock,
            ),
        ):
            safe_result = await moderation.moderate_general_group_message(
                self.db,
                messages[0],
                "123:test-token",
            )
            blocked_result = await moderation.moderate_general_group_message(
                self.db,
                messages[1],
                "123:test-token",
            )

        self.assertEqual(safe_result, {"handled": False})
        self.assertTrue(blocked_result["handled"])
        self.assertTrue(blocked_result["deleted"])
        delete_mock.assert_awaited_once_with(
            -100123,
            [201],
            "123:test-token",
        )
        warning_mock.assert_awaited_once()

        event = self.db.execute(
            text("SELECT message_id, action FROM telegram_moderation_events")
        ).fetchone()
        self.assertEqual(event, ("201", "deleted"))

    async def test_default_policy_leaves_google_and_other_links_untouched(self):
        delete_mock = AsyncMock(return_value=(True, None))
        links = [
            _link_message(250, "https://docs.google.com/document/d/abc"),
            _link_message(251, "https://example.edu/class-materials"),
        ]

        with patch.object(
            moderation,
            "_delete_telegram_messages",
            new=delete_mock,
        ):
            results = [
                await moderation.moderate_general_group_message(
                    self.db,
                    message,
                    "123:test-token",
                )
                for message in links
            ]

        self.assertEqual(results, [{"handled": False}, {"handled": False}])
        delete_mock.assert_not_awaited()

    async def test_custom_strict_policy_still_allows_google_subdomains(self):
        strict_policy = {
            **moderation.default_moderation_policy("-100123"),
            "file_policy": "allowlist",
            "link_policy": "allowlist",
        }
        delete_mock = AsyncMock(return_value=(True, None))

        with (
            patch.object(
                moderation,
                "get_moderation_policy",
                return_value=strict_policy,
            ),
            patch.object(
                moderation,
                "_delete_telegram_messages",
                new=delete_mock,
            ),
        ):
            result = await moderation.moderate_general_group_message(
                self.db,
                _link_message(275, "https://drive.google.com/file/d/abc"),
                "123:test-token",
            )

        self.assertEqual(result, {"handled": False})
        delete_mock.assert_not_awaited()

    async def test_already_deleted_message_is_a_successful_end_state(self):
        class FakeResponse:
            text = "Bad Request: message to delete not found"

            @staticmethod
            def json():
                return {
                    "ok": False,
                    "description": "Bad Request: message to delete not found",
                }

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def post(self, url, json):
                return FakeResponse()

        with patch.object(moderation.httpx, "AsyncClient", FakeAsyncClient):
            deleted, error = await moderation._delete_telegram_messages(
                -100123,
                [225],
                "123:test-token",
            )

        self.assertTrue(deleted)
        self.assertIsNone(error)

    async def test_warning_uses_plain_text_fallback_when_html_is_rejected(self):
        calls = []
        responses = [
            {
                "ok": False,
                "description": "Bad Request: can't parse entities",
            },
            {"ok": True},
        ]

        class FakeResponse:
            text = ""

            def __init__(self, data):
                self.data = data

            def json(self):
                return self.data

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def post(self, url, json):
                calls.append(json)
                return FakeResponse(responses.pop(0))

        violation = {
            "content_type": "document",
            "file_name": "installer.exe",
            "reason_code": "blocked_file_type",
            "blocked_label": ".exe",
            "reason": "Blocked file type: .exe",
        }
        with patch.object(moderation.httpx, "AsyncClient", FakeAsyncClient):
            sent, error = await moderation._send_moderation_warning(
                _album_document(280, "installer.exe"),
                violation,
                "123:test-token",
            )

        self.assertTrue(sent)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["parse_mode"], "HTML")
        self.assertNotIn("parse_mode", calls[1])
        fallback_text = calls[1]["text"]
        self.assertIn("📎 File removed", fallback_text)
        self.assertIn("👤 Member: Teacher", fallback_text)
        self.assertIn("📄 File: installer.exe", fallback_text)
        self.assertIn("File type .exe is blocked", fallback_text)
        self.assertIn("malware and unsafe downloads", fallback_text)

    def test_dangerous_mime_cannot_hide_behind_a_pdf_name(self):
        policy = moderation.default_moderation_policy("-100123")
        message = _album_document(300, "homework.pdf")
        message["document"]["mime_type"] = "application/x-msdownload"

        violation = moderation.inspect_message(message, policy)

        self.assertEqual(violation["reason_code"], "blocked_file_type")
        self.assertEqual(
            violation["blocked_label"],
            "application/x-msdownload",
        )


if __name__ == "__main__":
    unittest.main()
