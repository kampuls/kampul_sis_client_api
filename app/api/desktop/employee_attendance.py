"""Desktop employee-attendance API backed by the canonical application logic.

The desktop client is intentionally credential-free. Telegram bot credentials
remain server-owned while the desktop receives the same attendance settings and
group-management capabilities used by the Flutter administration screen.
"""

from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import User
from ...schemas.telegram_attendance import TelegramAttendanceSettingsUpdate
from ..v1.employee_attendance import (
    get_telegram_settings as get_shared_telegram_settings,
    router as shared_employee_attendance_router,
    update_telegram_settings as update_shared_telegram_settings,
)
from ..v1.telegram_webhook import (
    TelegramGroupReplySettingsUpdate,
    TelegramMemberVerificationUpdate,
    TelegramModerationPolicyUpdate,
    _require_telegram_admin,
    generate_bot_auth_code,
    get_active_bot_token,
    get_bot_auth_code_status,
    get_tracked_chat_auto_replies,
    get_tracked_chat_member_verification,
    get_tracked_chat_moderation,
    get_tracked_chats,
    leave_tracked_chat,
    update_tracked_chat_auto_replies,
    update_tracked_chat_member_verification,
    update_tracked_chat_moderation,
    update_tracked_chat_role,
)
from .data import get_current_desktop_user


router = APIRouter()


class DesktopTelegramBranchRoute(BaseModel):
    branch_id: int = Field(..., gt=0)
    attendance_chat_id: Optional[str] = Field(None, max_length=100)
    leave_chat_id: Optional[str] = Field(None, max_length=100)


class DesktopTelegramSettingsUpdate(BaseModel):
    """Credential-free settings accepted from the desktop client."""

    chat_id: Optional[str] = Field(None, max_length=100)
    leave_routing_mode: str = Field("combined", pattern="^(combined|separate)$")
    leave_chat_id: Optional[str] = Field(None, max_length=100)
    branch_routing_mode: str = Field("all", pattern="^(all|by_branch)$")
    branch_routes: list[DesktopTelegramBranchRoute] = Field(default_factory=list)
    enabled: bool = False
    notify_leave_requests: bool = False
    notify_leave_decisions: bool = False


class DesktopTelegramSettingsResponse(DesktopTelegramSettingsUpdate):
    """Telegram attendance settings without provider credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_configured: bool = False
    created_at: datetime
    updated_at: datetime


def _safe_telegram_settings(settings: object) -> DesktopTelegramSettingsResponse:
    """Project the shared ORM/response object into the desktop-safe schema."""

    return DesktopTelegramSettingsResponse(
        id=int(getattr(settings, "id")),
        bot_configured=bool(str(getattr(settings, "bot_token", "") or "").strip()),
        chat_id=getattr(settings, "chat_id", None),
        leave_routing_mode=getattr(settings, "leave_routing_mode", None) or "combined",
        leave_chat_id=getattr(settings, "leave_chat_id", None),
        branch_routing_mode=getattr(settings, "branch_routing_mode", None) or "all",
        branch_routes=getattr(settings, "branch_routes", None) or [],
        enabled=bool(getattr(settings, "enabled", False)),
        notify_leave_requests=bool(
            getattr(settings, "notify_leave_requests", False)
        ),
        notify_leave_decisions=bool(
            getattr(settings, "notify_leave_decisions", False)
        ),
        created_at=getattr(settings, "created_at"),
        updated_at=getattr(settings, "updated_at"),
    )


@router.get(
    "/admin/telegram-settings",
    response_model=DesktopTelegramSettingsResponse,
)
async def get_desktop_telegram_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    settings = await get_shared_telegram_settings(
        db=db,
        current_user=current_user,
    )
    return _safe_telegram_settings(settings)


@router.post(
    "/admin/telegram-settings",
    response_model=DesktopTelegramSettingsResponse,
)
async def update_desktop_telegram_settings(
    payload: DesktopTelegramSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    # Deliberately omit bot_token. The canonical update keeps the existing
    # server-owned credential while applying the supplied routing settings.
    shared_payload = TelegramAttendanceSettingsUpdate(**payload.model_dump())
    settings = await update_shared_telegram_settings(
        settings_update=shared_payload,
        db=db,
        current_user=current_user,
    )
    return _safe_telegram_settings(settings)


management_prefix = "/admin/telegram-management"


@router.get(f"{management_prefix}/tracked-chats")
async def get_desktop_tracked_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    # Filtering by the active server token prevents chats belonging to an old
    # bot configuration from appearing in the desktop destination picker.
    bot_token = get_active_bot_token(db)
    if not bot_token:
        return {"chats": []}
    return await get_tracked_chats(
        db=db,
        current_user=current_user,
        bot_token=bot_token,
    )


@router.post(f"{management_prefix}/tracked-chats/{{chat_id}}/leave")
async def leave_desktop_tracked_chat(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await leave_tracked_chat(chat_id=chat_id, db=db, current_user=current_user)


@router.post(f"{management_prefix}/tracked-chats/{{chat_id}}/test")
async def test_desktop_tracked_chat(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    """Send a safe test through the attendance bot selected on the server."""

    _require_telegram_admin(current_user)
    bot_token = get_active_bot_token(db)
    if not bot_token:
        raise HTTPException(status_code=409, detail="Telegram bot is not configured")
    tracked = db.execute(text("""
        SELECT chat_title
        FROM telegram_tracked_chats
        WHERE chat_id = :chat_id
          AND is_active = TRUE
          AND bot_token = :bot_token
        LIMIT 1
    """), {"chat_id": str(chat_id), "bot_token": bot_token}).fetchone()
    if not tracked:
        raise HTTPException(status_code=404, detail="Tracked chat not found")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": str(chat_id),
                    "text": (
                        "✅ <b>ការសាកល្បងជោគជ័យ</b>\n\n"
                        "ក្រុមនេះអាចទទួលសារជូនដំណឹងវត្តមាន"
                        "ពីកម្មវិធីសាលាបាន។"
                    ),
                    "parse_mode": "HTML",
                    "disable_notification": True,
                },
            )
        payload = response.json()
        if not response.is_success or not bool(payload.get("ok")):
            raise HTTPException(
                status_code=502,
                detail=str(payload.get("description") or "Telegram rejected the test"),
            )
        return {
            "ok": True,
            "chat_id": str(chat_id),
            "chat_title": tracked[0],
            "message": "Test message sent",
        }
    except HTTPException:
        raise
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Telegram test service is temporarily unavailable",
        ) from exc


@router.post(f"{management_prefix}/tracked-chats/{{chat_id}}/role")
async def update_desktop_tracked_chat_role(
    chat_id: str,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await update_tracked_chat_role(
        chat_id=chat_id, role=role, db=db, current_user=current_user
    )


@router.get(f"{management_prefix}/tracked-chats/{{chat_id}}/member-verification")
async def get_desktop_member_verification(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await get_tracked_chat_member_verification(
        chat_id=chat_id, db=db, current_user=current_user
    )


@router.put(f"{management_prefix}/tracked-chats/{{chat_id}}/member-verification")
async def update_desktop_member_verification(
    chat_id: str,
    payload: TelegramMemberVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await update_tracked_chat_member_verification(
        chat_id=chat_id, payload=payload, db=db, current_user=current_user
    )


@router.get(f"{management_prefix}/tracked-chats/{{chat_id}}/moderation")
async def get_desktop_moderation(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await get_tracked_chat_moderation(
        chat_id=chat_id, db=db, current_user=current_user
    )


@router.put(f"{management_prefix}/tracked-chats/{{chat_id}}/moderation")
async def update_desktop_moderation(
    chat_id: str,
    payload: TelegramModerationPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await update_tracked_chat_moderation(
        chat_id=chat_id, payload=payload, db=db, current_user=current_user
    )


@router.get(f"{management_prefix}/tracked-chats/{{chat_id}}/auto-replies")
async def get_desktop_auto_replies(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await get_tracked_chat_auto_replies(
        chat_id=chat_id, db=db, current_user=current_user
    )


@router.put(f"{management_prefix}/tracked-chats/{{chat_id}}/auto-replies")
async def update_desktop_auto_replies(
    chat_id: str,
    payload: TelegramGroupReplySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await update_tracked_chat_auto_replies(
        chat_id=chat_id, payload=payload, db=db, current_user=current_user
    )


@router.post(f"{management_prefix}/auth-code/generate")
async def generate_desktop_auth_code(
    intended_role: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await generate_bot_auth_code(
        intended_role=intended_role, db=db, current_user=current_user
    )


@router.get(f"{management_prefix}/auth-code/status")
async def get_desktop_auth_code_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    _require_telegram_admin(current_user)
    return await get_bot_auth_code_status(db=db, current_user=current_user)


# Preserve every shared attendance route except the two credential-bearing
# settings routes replaced above. This keeps schedules, reports, tests, and
# permissions on the canonical implementation used by Flutter.
for shared_route in shared_employee_attendance_router.routes:
    if shared_route.path == "/admin/telegram-settings":
        continue
    router.routes.append(shared_route)
