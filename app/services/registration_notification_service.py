"""Reliable staff-registration notification workflows.

Background tasks call these entry points with identifiers only.  Each task owns
its database session so delivery cannot outlive a request-scoped session.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models import User
from . import notification_service


logger = logging.getLogger(__name__)

PENDING_STAFF_PERMISSION = "ViewPendingEmployees"


def _unique_targets(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[tuple[int, str], Dict[str, Any]] = {}
    for target in targets:
        raw_id = target.get("id")
        if raw_id is None:
            continue
        user_id = int(raw_id)
        user_type = str(target.get("user_type") or "teacher").lower()
        if user_type not in {"teacher", "parent", "student"}:
            user_type = "teacher"
        unique[(user_id, user_type)] = {
            "id": user_id,
            "user_type": user_type,
        }
    return list(unique.values())


def get_staff_registration_approver_user_ids(
    db: Session,
) -> List[Dict[str, Any]]:
    """Unlocked App Admins plus active roles allowed to review staff."""

    targets = notification_service.get_app_admin_user_ids(db)
    targets.extend(
        notification_service.get_role_permission_user_ids(
            db,
            PENDING_STAFF_PERMISSION,
        )
    )
    return _unique_targets(targets)


def _staff_label(user: User) -> str:
    display_name = str(user.eName or user.kName or "").strip()
    username = str(user.username or "").strip()
    if display_name and username and display_name.lower() != username.lower():
        return f"{display_name} ({username})"
    return display_name or username or f"Staff #{user.id}"


def notify_approvers_new_staff_registration(user_id: int) -> None:
    """Create approver inbox entries and visible iOS/Android pushes."""

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            logger.warning(
                "Staff registration notification skipped; user %s was not found",
                user_id,
            )
            return

        approvers = get_staff_registration_approver_user_ids(db)
        if not approvers:
            logger.warning(
                "No active staff-registration approvers for user %s",
                user_id,
            )
            return

        tokens = notification_service.resolve_device_tokens_for_users(db, approvers)
        delivered = notification_service.send_notification(
            device_tokens=tokens,
            title="New Staff Registration",
            body=f"{_staff_label(user)} registered and is pending approval.",
            data={
                "type": "new_user_registration",
                "user_role": "employee",
                "target_user_id": str(user.id),
                "notification_key": f"staff_registration:{user.id}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=approvers,
            redirect_route="pending_staff_registrations",
            redirect_args={"user_id": int(user.id)},
        )
        logger.info(
            "Staff registration notification: user_id=%s approvers=%s tokens=%s delivered=%s",
            user.id,
            len(approvers),
            len(tokens),
            delivered,
        )
    except Exception:
        logger.exception(
            "Failed to notify approvers of staff registration %s",
            user_id,
        )
    finally:
        db.close()


def notify_staff_registration_approved(user_id: int) -> None:
    """Tell a newly activated staff member that the account is ready."""

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            logger.warning(
                "Staff approval notification skipped; user %s was not found",
                user_id,
            )
            return

        target = [{"id": int(user.id), "user_type": "teacher"}]
        tokens = notification_service.resolve_device_tokens_for_users(db, target)
        delivered = notification_service.send_notification(
            device_tokens=tokens,
            title="Account Approved",
            body=(
                f"Your staff account ({_staff_label(user)}) has been approved. "
                "You can now sign in."
            ),
            data={
                "type": "staff_registration_approved",
                "target_user_id": str(user.id),
                "notification_key": f"staff_registration_approved:{user.id}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=target,
        )
        logger.info(
            "Staff approval notification: user_id=%s tokens=%s delivered=%s",
            user.id,
            len(tokens),
            delivered,
        )
    except Exception:
        logger.exception("Failed to notify staff user %s of approval", user_id)
    finally:
        db.close()
