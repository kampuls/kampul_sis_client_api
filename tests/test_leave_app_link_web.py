import asyncio
import json
import unittest

from app.main import (
    form_app_link,
    ios_apple_app_site_association,
    leave_request_app_link,
)


class LeaveAppLinkWebTests(unittest.TestCase):
    def test_browser_fallback_contains_app_uri_without_leave_details(self):
        response = asyncio.run(leave_request_app_link(123))
        body = bytes(response.body).decode("utf-8")

        self.assertIn("pamais://leave/123", body)
        self.assertIn("intent://leave/123", body)
        self.assertIn('params.get("manual") === "1"', body)
        self.assertIn("window.location.replace", body)
        self.assertIn("app-id=6759542788", body)
        self.assertIn("Your account permissions will be checked", body)
        self.assertNotIn("employee", body.lower())

    def test_form_browser_fallback_contains_app_uri(self):
        response = asyncio.run(form_app_link(42))
        body = bytes(response.body).decode("utf-8")

        self.assertIn("pamais://form/42", body)
        self.assertIn("intent://form/42", body)
        self.assertIn("window.location.replace", body)
        self.assertIn("app-id=6759542788", body)
        self.assertIn("Open form in PAMAIS", body)
        self.assertIn("App Store", body)

    def test_ios_association_uses_team_id_and_bundle_id(self):
        response = asyncio.run(ios_apple_app_site_association())
        payload = json.loads(bytes(response.body))

        self.assertEqual(
            payload["applinks"]["details"][0]["appID"],
            "G8X75BJYQB.com.pamais.edu.kh",
        )


if __name__ == "__main__":
    unittest.main()
