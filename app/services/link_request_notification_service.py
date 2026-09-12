"""Reliable parent/student link-request notification workflows."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from . import notification_service


logger = logging.getLogger(__name__)
_LINK_REVIEW_PERMISSIONS = (
    "AdminViewApp",
    "AdminUpdateApp",
    "AdminDeleteApp",
)


def _unique_targets(
    target_groups: Iterable[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    unique: Dict[tuple[int, str], Dict[str, Any]] = {}
    for targets in target_groups:
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


def get_link_request_approver_user_ids(db: Session) -> List[Dict[str, Any]]:
    """Active admins and delegated roles allowed to review link requests."""
    role_one = [
        {"id": int(row[0]), "user_type": "teacher"}
        for row in db.execute(
            text("SELECT id FROM users WHERE status = 1 AND role = 1")
        ).fetchall()
        if row[0]
    ]
    permission_groups = [
        notification_service.get_role_permission_user_ids(db, permission)
        for permission in _LINK_REVIEW_PERMISSIONS
    ]
    return _unique_targets(
        [role_one, notification_service.get_app_admin_user_ids(db), *permission_groups]
    )


def notify_admins_new_link_request(request_id: int) -> None:
    """Save admin inbox entries and send visible pushes for a new request."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT plr.id, plr.parent_id, s.id, s.studentid,
                       s.kName, s.eName,
                       COALESCE(NULLIF(p.fatherName, ''),
                                NULLIF(p.motherName, ''),
                                NULLIF(p.gName, ''),
                                CONCAT('Parent #', p.id)) AS parent_name,
                       plr.updated_at
                FROM parent_student_link_requests plr
                JOIN students s ON s.id = plr.student_id
                JOIN parents p ON p.id = plr.parent_id
                WHERE plr.id = :request_id AND plr.status = 'pending'
                LIMIT 1
                """
            ),
            {"request_id": int(request_id)},
        ).first()
        if row is None:
            logger.warning("Pending link request %s was not found", request_id)
            return

        student_name = str(row[4] or row[5] or row[3] or f"Student #{row[2]}")
        parent_name = str(row[6] or f"Parent #{row[1]}")
        approvers = get_link_request_approver_user_ids(db)
        if not approvers:
            logger.warning("No active approvers for link request %s", request_id)
            return

        tokens = notification_service.resolve_device_tokens_for_users(db, approvers)
        notification_service.send_notification(
            device_tokens=tokens,
            title="New Student Link Request",
            body=f"{parent_name} requested to link {student_name} ({row[3]}).",
            data={
                "type": "link_request",
                "request_id": str(row[0]),
                "student_id": str(row[2]),
                "student_string_id": str(row[3] or ""),
                "notification_key": f"link_request:{row[0]}:{row[7]}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=approvers,
            redirect_route="admin_link_requests",
            redirect_args={"request_id": int(row[0])},
        )
    except Exception:
        logger.exception("Failed to notify admins for link request %s", request_id)
    finally:
        db.close()


def notify_parent_link_request_decision(request_id: int) -> None:
    """Save and push the final admin decision to the requesting parent."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT plr.id, plr.parent_id, plr.student_id, plr.status,
                       s.studentid, s.kName, s.eName
                FROM parent_student_link_requests plr
                JOIN students s ON s.id = plr.student_id
                WHERE plr.id = :request_id
                  AND plr.status IN ('approved', 'rejected')
                LIMIT 1
                """
            ),
            {"request_id": int(request_id)},
        ).first()
        if row is None:
            logger.warning("Decided link request %s was not found", request_id)
            return

        approved = str(row[3]).lower() == "approved"
        decision = "Approved" if approved else "Rejected"
        student_name = str(row[5] or row[6] or row[4] or f"Student #{row[2]}")
        target = [{"id": int(row[1]), "user_type": "parent"}]
        tokens = notification_service.resolve_device_tokens_for_users(db, target)
        notification_service.send_notification(
            device_tokens=tokens,
            title=f"Link Request {decision}",
            body=f"Your request to link {student_name} has been {decision.lower()}.",
            data={
                "type": "link_request_reply",
                "request_id": str(row[0]),
                "student_id": str(row[2]),
                "student_string_id": str(row[4] or ""),
                "decision": "approve" if approved else "reject",
                "notification_key": f"link_request_reply:{row[0]}:{row[3]}",
            },
            color="#4CAF50" if approved else "#F44336",
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=target,
            redirect_route="my_children",
            redirect_args={
                "request_id": int(row[0]),
                "student_id": int(row[2]),
                "decision": "approve" if approved else "reject",
            },
        )
    except Exception:
        logger.exception("Failed to notify parent for link request %s", request_id)
    finally:
        db.close()
