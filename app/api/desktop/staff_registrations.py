"""Permission-aware pending staff registration actions for desktop."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import Permission, RolePermission, User
from .data import get_current_desktop_user


router = APIRouter()

PENDING_STAFF_PERMISSION = "ViewPendingEmployees"
PENDING_STAFF_STATUS = 2
ACTIVE_STAFF_STATUS = 1


def _has_pending_staff_permission(db: Session, current_user: User) -> bool:
    role_id = int(getattr(current_user, "role", 0) or 0)
    if role_id <= 0:
        return False
    return (
        db.query(RolePermission.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(
            RolePermission.role_id == role_id,
            Permission.permission_name == PENDING_STAFF_PERMISSION,
        )
        .first()
        is not None
    )


def _require_pending_staff_permission(db: Session, current_user: User) -> None:
    if not _has_pending_staff_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {PENDING_STAFF_PERMISSION}",
        )


def _mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def _registration_details(db: Session, user_id: int) -> Dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT
                u.id,
                u.username,
                u.uniqueId AS unique_id,
                u.kName AS k_name,
                u.eName AS e_name,
                u.gender,
                u.dob,
                u.email,
                u.phone,
                u.status,
                u.created_at,
                b.branch_name,
                d.department AS department_name,
                p.position AS position_name,
                r.role_name
            FROM users u
            LEFT JOIN branch b ON b.id = u.workplace
            LEFT JOIN department d ON d.id = u.departmentId
            LEFT JOIN position p ON p.id = u.positionId
            LEFT JOIN roles r ON r.id = u.role
            WHERE u.id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff registration not found",
        )

    values = _mapping(row)
    current_status = int(values.get("status") or 0)
    english_name = str(values.get("e_name") or "").strip()
    khmer_name = str(values.get("k_name") or "").strip()
    display_name = english_name or khmer_name or str(values.get("username") or "")
    return {
        "id": int(values["id"]),
        "username": values.get("username") or "",
        "unique_id": values.get("unique_id") or "",
        "k_name": khmer_name,
        "e_name": english_name,
        "display_name": display_name,
        "gender": values.get("gender"),
        "dob": values.get("dob"),
        "email": values.get("email"),
        "phone": values.get("phone"),
        "branch_name": values.get("branch_name"),
        "department_name": values.get("department_name"),
        "position_name": values.get("position_name"),
        "role_name": values.get("role_name"),
        "status": current_status,
        "created_at": values.get("created_at"),
        "can_approve": current_status == PENDING_STAFF_STATUS,
    }


@router.get("/{user_id}")
def get_pending_staff_registration(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Return live registration details after checking the caller's role."""

    _require_pending_staff_permission(db, current_user)
    return _registration_details(db, user_id)


@router.post("/{user_id}/approve")
def approve_pending_staff_registration(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Atomically activate a pending staff account (status 2 -> 1)."""

    _require_pending_staff_permission(db, current_user)
    target = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff registration not found",
        )

    current_status = int(getattr(target, "status", 0) or 0)
    if current_status == ACTIVE_STAFF_STATUS:
        return {
            "success": True,
            "user_id": int(target.id),
            "status": ACTIVE_STAFF_STATUS,
            "already_approved": True,
        }
    if current_status != PENDING_STAFF_STATUS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This staff registration is no longer pending approval",
        )

    try:
        target.status = ACTIVE_STAFF_STATUS
        target.updated_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise

    from ...services.registration_notification_service import (
        notify_staff_registration_approved,
    )

    background_tasks.add_task(notify_staff_registration_approved, int(target.id))

    return {
        "success": True,
        "user_id": int(target.id),
        "status": ACTIVE_STAFF_STATUS,
        "already_approved": False,
    }
