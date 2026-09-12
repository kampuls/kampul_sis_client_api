"""Flutter-compatible student profile edit review actions for desktop."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import (
    AppAdmin,
    Permission,
    RolePermission,
    StudentProfileEditRequest,
    User,
)
from ..v1.app_admin import (
    EditRequestAction,
    _approve_profile_edit_core,
    _parse_snapshot,
    _reject_profile_edit_core,
    _resolve_requester_name,
)
from .data import get_current_desktop_user


router = APIRouter()
PROFILE_EDIT_REVIEW_PERMISSION = "ReviewStudentProfileEdits"


class DesktopProfileEditDecision(BaseModel):
    reason: str | None = None


def _has_profile_edit_review_permission(db: Session, current_user: User) -> bool:
    active_app_admin = (
        db.query(AppAdmin.user_id)
        .filter(
            AppAdmin.user_id == current_user.id,
            AppAdmin.is_locked == False,
        )
        .first()
    )
    if active_app_admin is not None:
        return True

    role_id = int(getattr(current_user, "role", 0) or 0)
    if role_id <= 0:
        return False
    return (
        db.query(RolePermission.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(
            RolePermission.role_id == role_id,
            Permission.permission_name == PROFILE_EDIT_REVIEW_PERMISSION,
        )
        .first()
        is not None
    )


def _require_profile_edit_review_permission(
    db: Session,
    current_user: User,
) -> None:
    if not _has_profile_edit_review_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {PROFILE_EDIT_REVIEW_PERMISSION}",
        )


def _mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def _live_student_values(db: Session, student_id: int) -> Dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT
                s.kName,
                s.eName,
                s.gender,
                s.dob,
                s.is_foreigner,
                s.student_phone,
                s.province,
                s.district,
                s.commune,
                s.village,
                s.previousSchool,
                s.student_noted,
                s.branch,
                ur.avatar
            FROM students s
            LEFT JOIN users_resource ur
                ON ur.user_id = s.id AND ur.user_type = 'student'
            WHERE s.id = :student_id
            LIMIT 1
            """
        ),
        {"student_id": student_id},
    ).first()
    if row is None:
        return {}

    values = _mapping(row)
    dob = values.get("dob")
    return {
        "kName": values.get("kName"),
        "eName": values.get("eName"),
        "gender": values.get("gender"),
        "dob": dob.isoformat() if dob else None,
        "is_foreigner": values.get("is_foreigner"),
        "student_phone": values.get("student_phone"),
        "province": values.get("province"),
        "district": values.get("district"),
        "commune": values.get("commune"),
        "village": values.get("village"),
        "previousSchool": values.get("previousSchool"),
        "student_noted": values.get("student_noted"),
        "branch": values.get("branch"),
        "avatar": values.get("avatar"),
    }


def _requested_values(edit_request: StudentProfileEditRequest) -> Dict[str, Any]:
    return {
        "kName": edit_request.kName,
        "eName": edit_request.eName,
        "gender": edit_request.gender,
        "dob": str(edit_request.dob) if edit_request.dob else None,
        "is_foreigner": edit_request.is_foreigner,
        "student_phone": edit_request.student_phone,
        "province": edit_request.province,
        "district": edit_request.district,
        "commune": edit_request.commune,
        "village": edit_request.village,
        "previousSchool": edit_request.previousSchool,
        "student_noted": edit_request.student_noted,
        "branch": edit_request.branch,
        "avatar": edit_request.avatar,
    }


def _profile_edit_details(
    db: Session,
    request_id: int,
) -> Dict[str, Any]:
    edit_request = (
        db.query(StudentProfileEditRequest)
        .filter(StudentProfileEditRequest.id == request_id)
        .first()
    )
    if edit_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile edit request not found",
        )

    request_status = str(edit_request.status or "pending")
    live_values = _live_student_values(db, int(edit_request.student_id))
    snapshot = _parse_snapshot(edit_request.previous_values)
    current_values = (
        live_values
        if request_status == "pending" or not snapshot
        else snapshot
    )
    student_name = (
        current_values.get("eName")
        or current_values.get("kName")
        or live_values.get("eName")
        or live_values.get("kName")
        or f"Student #{edit_request.student_id}"
    )
    return {
        "id": int(edit_request.id),
        "student_id": int(edit_request.student_id),
        "student_name": student_name,
        "current_student_data": current_values,
        "requested_changes": _requested_values(edit_request),
        "requested_by": int(edit_request.requested_by),
        "requester_name": _resolve_requester_name(
            db,
            edit_request.requested_by,
            edit_request.requested_by_type,
        ),
        "requested_by_type": str(edit_request.requested_by_type or ""),
        "status": request_status,
        "reason": edit_request.reason,
        "created_at": edit_request.created_at,
        "updated_at": edit_request.updated_at,
        "can_decide": request_status == "pending",
    }


@router.get("/{request_id}")
def get_student_profile_edit(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Return one live comparison to an authorized desktop reviewer."""

    _require_profile_edit_review_permission(db, current_user)
    return _profile_edit_details(db, request_id)


@router.patch("/{request_id}/approve")
async def approve_student_profile_edit(
    request_id: int,
    action: DesktopProfileEditDecision,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Reuse Flutter's atomic approval and requester-notification workflow."""

    _require_profile_edit_review_permission(db, current_user)
    return await _approve_profile_edit_core(
        request_id=request_id,
        action=EditRequestAction(),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


@router.patch("/{request_id}/reject")
async def reject_student_profile_edit(
    request_id: int,
    action: DesktopProfileEditDecision,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Reuse Flutter's rejection, staged-photo cleanup, and reply workflow."""

    _require_profile_edit_review_permission(db, current_user)
    return await _reject_profile_edit_core(
        request_id=request_id,
        action=EditRequestAction(reason=action.reason),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )
