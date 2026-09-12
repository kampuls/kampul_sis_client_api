"""
Notification API endpoints for device token management and sending notifications.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
import logging

from ...core import get_db, settings
from ...auth.dependencies import get_current_user_id
import json
import logging
from datetime import datetime

from ...models.notification import Notification
from ...models.device import DeviceToken
from ...models.user import User
from ...models.app_admin import AppAdmin

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)


def _require_active_notification_admin(db: Session, user_id: int) -> None:
    user = db.query(User).filter(User.id == int(user_id), User.status == 1).first()
    if user is None:
        raise HTTPException(status_code=403, detail="Active administrator access required")
    if int(getattr(user, "role", 0) or 0) == 1:
        return
    delegated = (
        db.query(AppAdmin.id)
        .filter(
            AppAdmin.user_id == int(user_id),
            AppAdmin.is_locked == False,  # noqa: E712
        )
        .first()
    )
    if delegated is None:
        raise HTTPException(status_code=403, detail="Administrator access required")


def get_user_info_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Extract user_id and user_type (role) from JWT token.
    Works for all user types: teacher, student, parent.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = payload.get("user_id")
        user_type = payload.get("role")  # role in JWT = user_type in database
        token_version = payload.get("token_version")

        if not user_id:
            raise credentials_exception

        # Map JWT role to device_tokens.user_type (must match register-token rows).
        if user_type in ("parent",):
            user_type = "parent"
        elif user_type in ("student",):
            user_type = "student"
        elif user_type in ("teacher", "employee", "admin", "app_admin"):
            # Staff / app admins register FCM rows as user_type = 'teacher'.
            user_type = "teacher"
        else:
            user_type = user_type or "teacher"

        return {
            "id": user_id,
            "user_type": user_type,
            "token_version": token_version,
        }
    except JWTError:
        raise credentials_exception


class RegisterTokenRequest(BaseModel):
    device_token: str
    device_type: Optional[str] = None
    device_name: Optional[str] = None
    app_version: Optional[str] = None


class UnregisterTokenRequest(BaseModel):
    device_token: Optional[str] = None


class NotificationPreferencesRequest(BaseModel):
    device_token: str
    notifications_enabled: bool = True
    attendance_enabled: bool = True
    leave_enabled: bool = True
    messages_enabled: bool = True
    announcements_enabled: bool = True
    marketplace_enabled: bool = True
    other_enabled: bool = True


def _preference_enabled(value: object) -> bool:
    """Only an explicit false/zero is an opt-out; legacy NULL stays enabled."""
    return True if value is None else bool(value)


def _notification_preferences_payload(
    row: Optional[DeviceToken],
    *,
    registered: bool,
) -> dict:
    return {
        "registered": registered,
        "notifications_enabled": _preference_enabled(
            getattr(row, "notifications_enabled", True) if row else True
        ),
        "attendance_enabled": _preference_enabled(
            getattr(row, "attendance_notifications_enabled", True) if row else True
        ),
        "leave_enabled": _preference_enabled(
            getattr(row, "leave_notifications_enabled", True) if row else True
        ),
        "messages_enabled": _preference_enabled(
            getattr(row, "message_notifications_enabled", True) if row else True
        ),
        "announcements_enabled": _preference_enabled(
            getattr(row, "announcement_notifications_enabled", True) if row else True
        ),
        "marketplace_enabled": _preference_enabled(
            getattr(row, "market_notifications_enabled", True) if row else True
        ),
        "other_enabled": _preference_enabled(
            getattr(row, "other_notifications_enabled", True) if row else True
        ),
    }


@router.get("/preferences")
async def get_notification_preferences(
    device_token: str,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """Return push preferences for this signed-in app installation."""
    token = device_token.strip()
    row = (
        db.query(DeviceToken)
        .filter(
            DeviceToken.user_id == int(user_info["id"]),
            DeviceToken.user_type == user_info["user_type"],
            DeviceToken.device_token == token,
        )
        .first()
        if token
        else None
    )
    return _notification_preferences_payload(row, registered=row is not None)


@router.put("/preferences")
async def update_notification_preferences(
    request: NotificationPreferencesRequest,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """Persist push categories for this signed-in app installation."""
    token = request.device_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="device_token is required")

    row = (
        db.query(DeviceToken)
        .filter(
            DeviceToken.user_id == int(user_info["id"]),
            DeviceToken.user_type == user_info["user_type"],
            DeviceToken.device_token == token,
        )
        .first()
    )
    if row is None:
        row = DeviceToken(
            user_id=int(user_info["id"]),
            user_type=user_info["user_type"],
            device_token=token,
            device_type="unknown",
            device_name="unknown",
            is_active=True,
        )
        db.add(row)

    row.notifications_enabled = request.notifications_enabled
    row.attendance_notifications_enabled = request.attendance_enabled
    row.leave_notifications_enabled = request.leave_enabled
    row.message_notifications_enabled = request.messages_enabled
    row.announcement_notifications_enabled = request.announcements_enabled
    row.market_notifications_enabled = request.marketplace_enabled
    row.other_notifications_enabled = request.other_enabled
    row.is_active = True
    row.last_used_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _notification_preferences_payload(row, registered=True)


class NotificationActionRequest(BaseModel):
    action: str  # "COMMENT" or "NOTED"
    student_id: int
    teacher_id: int
    attendance_date: str
    comment: Optional[str] = None  # Required if action is "COMMENT"


@router.post("/register-token")
async def register_device_token(
    request: RegisterTokenRequest,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Register or update a device token for push notifications.
    Works for all user types: teacher, student, parent.
    """
    try:
        user_id = user_info.get("id")
        user_type = user_info.get("user_type", "teacher")

        logger.info(
            f"Registering device token for user_id={user_id}, user_type={user_type}, device_token={request.device_token[:30]}..."
        )

        if not user_id:
            logger.error("User ID not found in token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in token",
            )



        # Preserve preferences across an FCM token rotation on the same phone.
        # A brand-new installation starts enabled. ON DUPLICATE below deliberately
        # does not overwrite preferences already saved for the current token.
        preference_values = {
            "notifications_enabled": True,
            "attendance_notifications_enabled": True,
            "leave_notifications_enabled": True,
            "message_notifications_enabled": True,
            "announcement_notifications_enabled": True,
            "market_notifications_enabled": True,
            "other_notifications_enabled": True,
        }
        device_name = (request.device_name or "").strip()
        if device_name and device_name.lower() != "unknown":
            previous = db.execute(
                text("""
                    SELECT notifications_enabled,
                           attendance_notifications_enabled,
                           leave_notifications_enabled,
                           message_notifications_enabled,
                           announcement_notifications_enabled,
                           market_notifications_enabled,
                           other_notifications_enabled
                    FROM device_tokens
                    WHERE user_id = :user_id
                      AND user_type = :user_type
                      AND device_token <> :device_token
                      AND COALESCE(device_name, '') = :device_name
                      AND COALESCE(device_type, '') = COALESCE(:device_type, '')
                    ORDER BY is_active DESC,
                             COALESCE(last_used_at, created_at) DESC,
                             id DESC
                    LIMIT 1
                """),
                {
                    "user_id": user_id,
                    "user_type": user_type,
                    "device_token": request.device_token,
                    "device_name": device_name,
                    "device_type": request.device_type,
                },
            ).mappings().first()
            if previous is not None:
                preference_values = {
                    key: _preference_enabled(previous.get(key))
                    for key in preference_values
                }

        # Insert or update device token. Preference values are explicit so token
        # registration remains safe even on a database whose defaults drifted.
        query = text("""
            INSERT INTO device_tokens (
                user_id, user_type, device_token, device_type, 
                device_name, app_version, is_active, last_used_at,
                notifications_enabled, attendance_notifications_enabled,
                leave_notifications_enabled, message_notifications_enabled,
                announcement_notifications_enabled, market_notifications_enabled,
                other_notifications_enabled
            ) VALUES (
                :user_id, :user_type, :device_token, :device_type,
                :device_name, :app_version, 1, NOW(),
                :notifications_enabled, :attendance_notifications_enabled,
                :leave_notifications_enabled, :message_notifications_enabled,
                :announcement_notifications_enabled, :market_notifications_enabled,
                :other_notifications_enabled
            )
            ON DUPLICATE KEY UPDATE
                user_type = VALUES(user_type), -- Constructive fix: Ensure user_type is updated
                device_type = VALUES(device_type),
                device_name = VALUES(device_name),
                app_version = VALUES(app_version),
                is_active = 1,
                last_used_at = NOW(),
                updated_at = NOW()
        """)

        db.execute(
            query,
            {
                "user_id": user_id,
                "user_type": user_type,
                "device_token": request.device_token,
                "device_type": request.device_type,
                "device_name": request.device_name,
                "app_version": request.app_version,
                **preference_values,
            },
        )

        # An FCM token identifies one app installation. If logout cleanup was
        # interrupted and the same phone later signs in as another account,
        # retire the old ownership row so audience broadcasts cannot send the
        # same logical notification to that installation more than once.
        db.execute(
            text("""
                UPDATE device_tokens
                SET is_active = 0, updated_at = NOW()
                WHERE device_token = :device_token
                  AND NOT (user_id = :user_id AND user_type = :user_type)
                  AND is_active = 1
            """),
            {
                "user_id": user_id,
                "user_type": user_type,
                "device_token": request.device_token,
            },
        )

        # FCM rotates tokens (reinstall/update/restore) and the old token can
        # stay deliverable for a while — leaving its row active means the same
        # device gets every push twice. When a device (identified by
        # device_name + device_type) registers, retire its other tokens.
        # Deactivation is reversible: if two identical devices share a name,
        # the other one re-registers (and reactivates) on its next app start.
        if device_name and device_name.lower() != "unknown":
            db.execute(
                text("""
                    UPDATE device_tokens
                    SET is_active = 0, updated_at = NOW()
                    WHERE user_id = :user_id
                      AND user_type = :user_type
                      AND device_token <> :device_token
                      AND COALESCE(device_name, '') = :device_name
                      AND COALESCE(device_type, '') = COALESCE(:device_type, '')
                      AND is_active = 1
                """),
                {
                    "user_id": user_id,
                    "user_type": user_type,
                    "device_token": request.device_token,
                    "device_name": device_name,
                    "device_type": request.device_type,
                },
            )

        db.commit()

        logger.info(
            f"Device token registered successfully for user_id={user_id}, user_type={user_type}"
        )
        return {"success": True, "message": "Device token registered successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error registering device token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register device token: {str(e)}",
        )


@router.post("/unregister-token")
async def unregister_device_token(
    request: UnregisterTokenRequest,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Remove this device's push token on logout (per device only).

    Deletes the row matching user_id + user_type + device_token so other
    phones logged in as the same account keep their tokens and pushes.
    """
    try:
        user_id = user_info.get("id")
        user_type = user_info.get("user_type", "teacher")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in token",
            )

        token = (request.device_token or "").strip()
        if not token:
            return {
                "success": True,
                "message": "No device_token provided; nothing removed",
                "deleted": 0,
            }

        result = db.execute(
            text("""
                DELETE FROM device_tokens
                WHERE user_id = :user_id
                  AND user_type = :user_type
                  AND device_token = :device_token
            """),
            {
                "user_id": user_id,
                "user_type": user_type,
                "device_token": token,
            },
        )
        deleted = result.rowcount or 0
        db.commit()

        logger.info(
            "Logout device token cleanup user_id=%s user_type=%s deleted=%s",
            user_id,
            user_type,
            deleted,
        )

        return {
            "success": True,
            "message": "Device token removed for this device",
            "deleted": deleted,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unregister device token: {str(e)}",
        )


@router.post("/action")
async def handle_notification_action(
    request: NotificationActionRequest,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Handle notification action (Comment or Noted) from parent.
    Sends notification back to teacher.
    """
    try:
        parent_id = user_info.get("id")
        parent_type = user_info.get("user_type")

        if parent_type != "parent":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only parents can perform notification actions",
            )

        if request.action == "COMMENT" and not request.comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comment is required for COMMENT action",
            )

        # Get teacher device tokens
        from ...services.notification_service import (
            get_teacher_device_tokens,
            send_notification_async,
        )

        teacher_tokens = get_teacher_device_tokens(db, request.teacher_id)

        if not teacher_tokens:
            logger.warning(f"No device tokens found for teacher {request.teacher_id}")
            return {
                "success": False,
                "message": "Teacher not available for notifications",
            }

        # Get student name for notification
        student_query = text("SELECT kName, eName FROM students WHERE id = :student_id")
        student_result = db.execute(student_query, {"student_id": request.student_id})
        student_row = student_result.fetchone()

        if not student_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
            )

        student_kname = student_row[0] or ""
        student_ename = student_row[1] or ""
        student_name = student_kname if student_kname else student_ename

        # Get parent name
        parent_query = text("SELECT kName, eName FROM parents WHERE id = :parent_id")
        parent_result = db.execute(parent_query, {"parent_id": parent_id})
        parent_row = parent_result.fetchone()

        parent_name = "Parent"
        if parent_row:
            parent_kname = parent_row[0] or ""
            parent_ename = parent_row[1] or ""
            parent_name = parent_kname if parent_kname else parent_ename

        # Create notification based on action
        if request.action == "COMMENT":
            title = "Parent Comment"
            body = f"{parent_name} commented on {student_name}'s attendance: {request.comment}"
            color = "#2196F3"  # Blue
            icon = "ic_comment"
        else:  # NOTED
            title = "Attendance Noted"
            body = f"{parent_name} has noted {student_name}'s attendance for {request.attendance_date}"
            color = "#4CAF50"  # Green
            icon = "ic_check"

        # Prepare data payload
        data = {
            "type": "attendance_response",
            "action": request.action,
            "student_id": str(request.student_id),
            "student_name": student_name,
            "parent_id": str(parent_id),
            "parent_name": parent_name,
            "attendance_date": request.attendance_date,
            "comment": request.comment or "",
        }

        # Send notification to teacher
        result = await send_notification_async(
            device_tokens=teacher_tokens,
            title=title,
            body=body,
            data=data,
            color=color,
            icon=icon,
            vibrate=True,
        )

        if result:
            logger.info(
                f"Notification action '{request.action}' sent to teacher {request.teacher_id}"
            )
            return {
                "success": True,
                "message": f"Action '{request.action}' processed successfully",
            }
        else:
            return {
                "success": False,
                "message": "Failed to send notification to teacher",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling notification action: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process notification action: {str(e)}",
        )


@router.get("/")
async def get_notifications(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Get notifications for current user.
    """
    user_id = user_info.get("id")
    user_type = user_info.get("user_type")

    # Normalize user_type
    if user_type not in ["teacher", "parent", "student"]:
        user_type = "teacher"

    query = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.user_type == user_type)
        .order_by(Notification.created_at.desc())
    )

    total = query.count()
    notifications = query.offset(skip).limit(limit).all()

    # Check for unread count
    unread_count = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.user_type == user_type,
            Notification.is_read == False,
        )
        .count()
    )

    return {"total": total, "unread_count": unread_count, "items": notifications}


@router.post("/{id}/read")
async def mark_notification_read(
    id: int,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Mark a notification as read.
    """
    user_id = user_info.get("id")
    user_type = user_info.get("user_type")

    # Normalize user_type
    if user_type not in ["teacher", "parent", "student"]:
        user_type = "teacher"

    notification = (
        db.query(Notification)
        .filter(
            Notification.id == id,
            Notification.user_id == user_id,
            Notification.user_type == user_type,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()

    return {"success": True}


@router.post("/{id}/unread")
def mark_notification_as_unread(
    id: int,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    try:
        from ...services import notification_service

        user_id = user_info.get("id")
        user_type = user_info.get("user_type")
        notification = notification_service.mark_as_unread(db, id, user_id, user_type)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"message": "Notification marked as unread"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read-all")
async def mark_all_notifications_read(
    db: Session = Depends(get_db), user_info: dict = Depends(get_user_info_from_token)
):
    """
    Mark all notifications as read for current user.
    """
    user_id = user_info.get("id")
    user_type = user_info.get("user_type")

    # Normalize user_type
    if user_type not in ["teacher", "parent", "student"]:
        user_type = "teacher"

    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.user_type == user_type,
        Notification.is_read == False,
    ).update({"is_read": True})

    db.commit()

    return {"success": True}


@router.delete("/delete-all")
async def delete_all_notifications(
    db: Session = Depends(get_db), user_info: dict = Depends(get_user_info_from_token)
):
    """
    Delete all notifications for current user.
    """
    user_id = user_info.get("id")
    user_type = user_info.get("user_type")

    # Normalize user_type
    if user_type not in ["teacher", "parent", "student"]:
        user_type = "teacher"

    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.user_type == user_type,
    ).delete()

    db.commit()

    return {"success": True}


@router.delete("/{id}")
async def delete_notification(
    id: int,
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Delete a notification.
    """
    user_id = user_info.get("id")
    user_type = user_info.get("user_type")

    # Normalize user_type
    if user_type not in ["teacher", "parent", "student"]:
        user_type = "teacher"

    notification = (
        db.query(Notification)
        .filter(
            Notification.id == id,
            Notification.user_id == user_id,
            Notification.user_type == user_type,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notification)
    db.commit()

    return {"success": True}


@router.post("/send-schedule-reminders")
async def trigger_schedule_reminders(
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    Admin-only: Manually trigger the 15-minute schedule reminder cron.
    Useful for testing. In production this runs automatically every minute.
    """
    _require_active_notification_admin(db, int(user_info.get("id") or 0))
    try:
        from ...services.schedule_reminder_service import send_schedule_reminders

        result = send_schedule_reminders(db)
        return {
            "success": True,
            "sent": result.get("sent", 0),
            "skipped": result.get("skipped", 0),
            "teachers_notified": result.get("teachers", []),
            "error": result.get("error"),
        }
    except Exception as e:
        logger.error(f"Error triggering schedule reminders: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger reminders: {str(e)}",
        )


@router.post("/cleanup-attendance")
async def trigger_attendance_notification_cleanup(
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_user_info_from_token),
):
    """
    App Admin only: Manually delete parent attendance inbox rows older than 7 days.
    Useful for testing. In production this runs automatically daily at 23:05 ICT.
    """
    from ...models.app_admin import AppAdmin

    admin = (
        db.query(AppAdmin)
        .filter(
            AppAdmin.user_id == user_info.get("id"),
            AppAdmin.is_locked == False,
        )
        .first()
    )
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only active App Admins can trigger attendance notification cleanup",
        )

    try:
        from ...core.attendance_notification_cleanup import (
            cleanup_old_parent_attendance_notifications,
        )

        deleted = cleanup_old_parent_attendance_notifications()
        return {"success": True, "deleted": deleted}
    except Exception as e:
        logger.error(
            "Error triggering attendance notification cleanup: %s", e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run attendance notification cleanup: {str(e)}",
        )
