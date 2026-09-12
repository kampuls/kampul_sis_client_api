import unittest
from io import BytesIO

from fastapi import HTTPException
from PIL import Image
from app.api.v1.app import (
    QuickActionItem,
    _preserve_quick_action_compatibility_fields,
    _validate_quick_action_icon_upload,
)


def _website_item(**overrides):
    payload = {
        "id": "website_news",
        "kind": "website",
        "title_en": "School news",
        "title_km": "",
        "title_zh": "",
        "url": "https://example.com/news",
        "icon_name": "newspaper",
        "color_hex": "#E11D48",
        "visible": True,
        "sort_order": 0,
        "open_mode": "embedded",
    }
    payload.update(overrides)
    return QuickActionItem(**payload)


class QuickActionSchemaTests(unittest.TestCase):
    def test_legacy_item_defaults_highlight_off_and_accepts_news_icon(self):
        item = _website_item()

        self.assertFalse(item.highlight_new)
        self.assertEqual(item.icon_name, "newspaper")
        self.assertNotIn("highlight_new", item.model_fields_set)

    def test_old_client_save_preserves_existing_highlight(self):
        existing = _website_item(
            highlight_new=True,
            icon_image_url="/uploads/quick_actions/news.png",
        )
        incoming = _website_item(title_en="Updated school news")

        merged = _preserve_quick_action_compatibility_fields(
            [incoming],
            [existing],
        )

        self.assertTrue(merged[0].highlight_new)
        self.assertEqual(
            merged[0].icon_image_url,
            "/uploads/quick_actions/news.png",
        )
        self.assertEqual(merged[0].title_en, "Updated school news")

    def test_new_client_can_turn_highlight_off_explicitly(self):
        existing = _website_item(highlight_new=True)
        incoming = _website_item(highlight_new=False)

        merged = _preserve_quick_action_compatibility_fields(
            [incoming],
            [existing],
        )

        self.assertFalse(merged[0].highlight_new)

    def test_new_client_can_clear_custom_icon_explicitly(self):
        existing = _website_item(
            icon_image_url="/uploads/quick_actions/news.png",
        )
        incoming = _website_item(icon_image_url="")

        merged = _preserve_quick_action_compatibility_fields(
            [incoming],
            [existing],
        )

        self.assertEqual(merged[0].icon_image_url, "")

    def test_square_png_upload_is_verified(self):
        buffer = BytesIO()
        Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(
            buffer,
            format="PNG",
        )

        extension = _validate_quick_action_icon_upload(
            buffer.getvalue(),
            "image/png",
        )

        self.assertEqual(extension, ".png")

    def test_non_square_or_forged_upload_is_rejected(self):
        buffer = BytesIO()
        Image.new("RGB", (80, 40), (255, 0, 0)).save(buffer, format="JPEG")

        with self.assertRaises(HTTPException):
            _validate_quick_action_icon_upload(
                buffer.getvalue(),
                "image/jpeg",
            )

        square = BytesIO()
        Image.new("RGB", (32, 32), (255, 0, 0)).save(square, format="JPEG")
        with self.assertRaises(HTTPException):
            _validate_quick_action_icon_upload(
                square.getvalue(),
                "image/png",
            )


if __name__ == "__main__":
    unittest.main()
