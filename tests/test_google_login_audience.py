import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1 import auth


def test_google_login_verifies_token_for_configured_web_client(monkeypatch):
    expected_client_id = "web-client.apps.googleusercontent.com"
    captured = {}

    monkeypatch.setattr(auth, "GOOGLE_AUTH_AVAILABLE", True)
    monkeypatch.setattr(auth.settings, "firebase_project_id", "multischool-pro")
    monkeypatch.setattr(auth.settings, "google_client_id", expected_client_id)

    def reject_after_capturing(token, request, audience):
        captured["token"] = token
        captured["audience"] = audience
        raise ValueError("stop after argument verification")

    monkeypatch.setattr(
        auth.google_id_token,
        "verify_oauth2_token",
        reject_after_capturing,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            auth.login_with_google(
                auth.GoogleLoginRequest(google_token="test-id-token"),
                db=object(),
            )
        )

    assert exc_info.value.status_code == 401
    assert captured == {
        "token": "test-id-token",
        "audience": expected_client_id,
    }
