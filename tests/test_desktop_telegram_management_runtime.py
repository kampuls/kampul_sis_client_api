from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.desktop import employee_attendance as desktop_attendance


def test_safe_settings_projection_omits_provider_credential():
    now = datetime.now()
    shared_settings = SimpleNamespace(
        id=4,
        bot_token="server-only-secret",
        chat_id="-1001",
        leave_routing_mode="combined",
        leave_chat_id=None,
        branch_routing_mode="all",
        branch_routes=[],
        enabled=True,
        notify_leave_requests=False,
        notify_leave_decisions=True,
        created_at=now,
        updated_at=now,
    )

    safe = desktop_attendance._safe_telegram_settings(shared_settings)

    assert safe.bot_configured is True
    assert "bot_token" not in safe.model_dump()
    assert safe.chat_id == "-1001"
    assert safe.notify_leave_decisions is True


@pytest.mark.asyncio
async def test_tracked_chats_are_empty_without_an_active_server_bot(monkeypatch):
    monkeypatch.setattr(desktop_attendance, "get_active_bot_token", lambda db: None)

    result = await desktop_attendance.get_desktop_tracked_chats(
        db=object(),
        current_user=SimpleNamespace(role=1),
    )

    assert result == {"chats": []}


@pytest.mark.asyncio
async def test_tracked_chats_are_filtered_by_the_active_server_bot(monkeypatch):
    received = {}

    async def fake_get_tracked_chats(*, db, current_user, bot_token):
        received["bot_token"] = bot_token
        return {"chats": [{"chat_id": "-1001"}]}

    monkeypatch.setattr(
        desktop_attendance,
        "get_active_bot_token",
        lambda db: "server-only-secret",
    )
    monkeypatch.setattr(
        desktop_attendance,
        "get_tracked_chats",
        fake_get_tracked_chats,
    )

    result = await desktop_attendance.get_desktop_tracked_chats(
        db=object(),
        current_user=SimpleNamespace(role=1),
    )

    assert received["bot_token"] == "server-only-secret"
    assert result["chats"][0]["chat_id"] == "-1001"


@pytest.mark.asyncio
async def test_management_endpoints_reject_non_admin_before_database_work():
    with pytest.raises(HTTPException) as error:
        await desktop_attendance.get_desktop_auth_code_status(
            db=object(),
            current_user=SimpleNamespace(role=2),
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_chat_test_uses_server_bot_for_a_tracked_destination(monkeypatch):
    class Result:
        @staticmethod
        def fetchone():
            return ("Attendance group",)

    class Database:
        @staticmethod
        def execute(statement, parameters):
            assert parameters == {
                "chat_id": "-1001",
                "bot_token": "server-only-secret",
            }
            return Result()

    class Response:
        is_success = True

        @staticmethod
        def json():
            return {"ok": True}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert "server-only-secret" in url
            assert json["chat_id"] == "-1001"
            return Response()

    monkeypatch.setattr(
        desktop_attendance,
        "get_active_bot_token",
        lambda db: "server-only-secret",
    )
    monkeypatch.setattr(
        desktop_attendance.httpx,
        "AsyncClient",
        lambda **kwargs: Client(),
    )

    result = await desktop_attendance.test_desktop_tracked_chat(
        chat_id="-1001",
        db=Database(),
        current_user=SimpleNamespace(role=1),
    )

    assert result["ok"] is True
    assert "bot_token" not in result
