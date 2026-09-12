import unittest

from app.services.telegram_group_reply_service import (
    APP_SMART_DOWNLOAD_URL,
    build_default_app_reply_html,
    default_group_reply_settings,
    match_group_reply_feature,
    normalize_group_reply_settings,
    render_telegram_reply_html,
    validate_telegram_reply_html,
)


class TelegramGroupReplyServiceTests(unittest.TestCase):
    def test_defaults_match_address_in_english_and_khmer(self):
        settings = default_group_reply_settings("group-1")

        self.assertEqual(
            match_group_reply_feature("Address", settings)["key"],
            "location",
        )
        self.assertEqual(
            match_group_reply_feature("អាសយដ្ឋាន", settings)["key"],
            "location",
        )

    def test_defaults_match_school_app_in_english_and_khmer(self):
        settings = default_group_reply_settings("group-1")

        self.assertEqual(
            match_group_reply_feature("Download app", settings)["key"],
            "app",
        )
        self.assertEqual(
            match_group_reply_feature("កម្មវិធីសាលា", settings)["key"],
            "app",
        )

    def test_old_saved_settings_receive_new_app_feature_defaults(self):
        settings = normalize_group_reply_settings(
            {
                "features": [
                    {
                        "key": "location",
                        "enabled": True,
                        "triggers": ["address"],
                    }
                ]
            },
            "group-1",
        )

        self.assertEqual(
            [feature["key"] for feature in settings["features"]],
            ["location", "phone", "school", "app"],
        )

    def test_default_app_reply_uses_only_the_official_smart_link(self):
        reply = build_default_app_reply_html()

        self.assertIn(f'href="{APP_SMART_DOWNLOAD_URL}"', reply)
        self.assertEqual(reply.count("href="), 1)
        self.assertNotIn("play.google.com", reply)
        self.assertNotIn("apps.apple.com", reply)
        validate_telegram_reply_html(reply)

    def test_matching_requires_the_whole_message(self):
        settings = default_group_reply_settings("group-1")

        self.assertIsNone(
            match_group_reply_feature("Can you send the address?", settings)
        )

    def test_custom_trigger_and_reply_are_normalized(self):
        settings = normalize_group_reply_settings(
            {
                "enabled": True,
                "features": [
                    {
                        "key": "location",
                        "enabled": True,
                        "triggers": ["Our Campus"],
                        "reply_text": "We are beside the central market.",
                    }
                ],
            },
            "group-1",
        )

        match = match_group_reply_feature("  OUR   CAMPUS! ", settings)
        self.assertIsNotNone(match)
        self.assertEqual(match["reply_text"], "We are beside the central market.")

    def test_disabled_feature_does_not_reply(self):
        settings = default_group_reply_settings("group-1")
        settings["features"][0]["enabled"] = False

        self.assertIsNone(match_group_reply_feature("address", settings))

    def test_enabled_feature_requires_a_trigger(self):
        with self.assertRaisesRegex(ValueError, "at least one trigger"):
            normalize_group_reply_settings(
                {
                    "features": [
                        {
                            "key": "location",
                            "enabled": True,
                            "triggers": [],
                            "reply_text": "Reply",
                        }
                    ]
                },
                "group-1",
            )

    def test_same_trigger_cannot_belong_to_two_features(self):
        with self.assertRaisesRegex(ValueError, "already used"):
            normalize_group_reply_settings(
                {
                    "features": [
                        {
                            "key": "location",
                            "triggers": ["details"],
                        },
                        {
                            "key": "phone",
                            "triggers": ["DETAILS"],
                        },
                    ]
                },
                "group-1",
            )

    def test_supported_telegram_html_is_accepted(self):
        validate_telegram_reply_html(
            '<b>Address</b>\n<a href="https://maps.google.com">Open map</a>'
        )

    def test_unbalanced_or_unsafe_telegram_html_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not closed"):
            validate_telegram_reply_html("<b>Address")
        with self.assertRaisesRegex(ValueError, "must use http"):
            validate_telegram_reply_html(
                '<a href="javascript:alert(1)">Unsafe</a>'
            )

    def test_plain_special_characters_are_escaped_when_rendered(self):
        self.assertEqual(
            render_telegram_reply_html("<b>PAMA & School</b>"),
            "<b>PAMA &amp; School</b>",
        )


if __name__ == "__main__":
    unittest.main()
