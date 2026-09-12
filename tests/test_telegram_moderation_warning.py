import unittest

from app.services.telegram_moderation_service import (
    DEFAULT_ALLOWED_DOMAINS,
    _domain_allowed,
    _moderation_warning_text,
    _upgrade_legacy_strict_defaults,
    default_moderation_policy,
)


class TelegramModerationWarningTests(unittest.TestCase):
    def test_new_general_groups_use_practical_safe_sharing_defaults(self):
        policy = default_moderation_policy("group-1")

        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["file_policy"], "blocklist")
        self.assertEqual(policy["link_policy"], "allow_all")
        self.assertFalse(policy["exempt_admins"])

    def test_default_domains_include_safe_school_google_and_youtube_links(self):
        for domain in (
            "pamais.duckdns.org",
            "pamainternationalschool.com",
            "goo.gl",
            "maps.app.goo.gl",
            "youtube.com",
            "youtu.be",
            "apps.apple.com",
        ):
            self.assertIn(domain, DEFAULT_ALLOWED_DOMAINS)

        self.assertTrue(
            _domain_allowed("www.youtube.com", DEFAULT_ALLOWED_DOMAINS)
        )
        self.assertFalse(
            _domain_allowed("youtube.com.scam-example.test", DEFAULT_ALLOWED_DOMAINS)
        )

    def test_old_untouched_strict_preset_receives_new_trusted_domains(self):
        old_policy = default_moderation_policy("group-1")
        old_policy["file_policy"] = "allowlist"
        old_policy["link_policy"] = "allowlist"
        old_policy["allowed_domains"] = [
            "google.com",
            "googleusercontent.com",
            "gstatic.com",
            "youtube.com",
            "youtu.be",
            "t.me",
        ]

        upgraded = _upgrade_legacy_strict_defaults(old_policy)

        self.assertEqual(
            set(upgraded["allowed_domains"]),
            set(DEFAULT_ALLOWED_DOMAINS),
        )

    def test_custom_strict_domain_list_is_not_replaced(self):
        custom_policy = default_moderation_policy("group-1")
        custom_policy["file_policy"] = "allowlist"
        custom_policy["link_policy"] = "allowlist"
        custom_policy["allowed_domains"] = ["school.example"]

        upgraded = _upgrade_legacy_strict_defaults(custom_policy)

        self.assertEqual(upgraded["allowed_domains"], ["school.example"])

    def test_link_warning_does_not_repeat_the_blocked_domain(self):
        warning = _moderation_warning_text(
            "Member",
            {
                "content_type": "link",
                "domain": "scam-example.test",
                "reason_code": "unapproved_link",
                "reason": "Domain is not allowed: scam-example.test",
            },
        )

        self.assertNotIn("scam-example.test", warning)
        self.assertIn("🔗 <b>Link removed</b>", warning)
        self.assertIn("This website is not approved", warning)
        self.assertIn("phishing, scams, and unsafe websites", warning)
        self.assertIn("ask a group administrator", warning)

    def test_file_warning_keeps_the_safe_reason_and_explains_the_rule(self):
        warning = _moderation_warning_text(
            "Member",
            {
                "content_type": "document",
                "file_name": "installer.exe",
                "reason_code": "blocked_file_type",
                "blocked_label": ".exe",
                "reason": "Blocked file type: .exe",
            },
        )

        self.assertIn("📎 <b>File removed</b>", warning)
        self.assertIn("<code>installer.exe</code>", warning)
        self.assertIn("File type <code>.exe</code> is blocked", warning)
        self.assertIn("malware and unsafe downloads", warning)
        self.assertIn("ask a group administrator", warning)

    def test_warning_escapes_and_shortens_an_unsafe_file_name(self):
        warning = _moderation_warning_text(
            '<a href="tg://user?id=1">Member</a>',
            {
                "content_type": "document",
                "file_name": "<script>alert('unsafe')</script>" + "x" * 100,
                "reason_code": "unapproved_file_type",
                "reason": "This file type is not on the allowed list",
            },
        )

        self.assertNotIn("<script>", warning)
        self.assertIn("&lt;script&gt;", warning)
        self.assertIn("…</code>", warning)
        self.assertIn("not approved for this group", warning)

    def test_disabled_links_have_a_clear_specific_reason(self):
        warning = _moderation_warning_text(
            "Member",
            {
                "content_type": "link",
                "reason_code": "links_disabled",
                "reason": "Links are not allowed in this group",
            },
        )

        self.assertIn("Links are disabled in this group", warning)
        self.assertIn("Share information without the link", warning)


if __name__ == "__main__":
    unittest.main()
