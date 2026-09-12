"""App-Admin parent registration review and approval for desktop."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import Parent, User
from ...schemas.parents import AdminParentRegistrationAction
from ..v1.parents import (
    _fetch_linked_students,
    _require_app_admin,
    process_parent_registration,
)
from .data import get_current_desktop_user


router = APIRouter()


def _parent_details(db: Session, parent_id: int) -> Dict[str, Any]:
    parent = db.query(Parent).filter(Parent.id == parent_id).first()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent registration not found",
        )

    students = _fetch_linked_students(db, parent_id, parent.myChilds)
    display_name = (
        parent.fatherName
        or parent.motherName
        or parent.gName
        or parent.username
        or f"Parent #{parent_id}"
    )
    current_status = int(getattr(parent, "status", 0) or 0)
    return {
        "id": int(parent.id),
        "username": parent.username or "",
        "unique_id": parent.uniqueid or "",
        "display_name": display_name,
        "father_name": parent.fatherName,
        "mother_name": parent.motherName,
        "guardian_name": parent.gName,
        "father_phone": parent.fatherPhone,
        "mother_phone": parent.motherPhone,
        "guardian_phone": parent.gPhone,
        "father_job": parent.fatherJob,
        "mother_job": parent.motherJob,
        "email": parent.pEmail,
        "telegram_id": parent.pTelegramId,
        "province": parent.pProvince,
        "district": parent.pDistrict,
        "commune": parent.pCommune,
        "village": parent.pVillage,
        "status": current_status,
        "created_at": parent.created_at,
        "can_approve": current_status != 1,
        "students": [student.model_dump() for student in students],
    }


@router.get("/{parent_id}")
def get_parent_registration(
    parent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Return live parent and linked-child details to an active App Admin."""

    _require_app_admin(db, current_user)
    return _parent_details(db, parent_id)


@router.post("/{parent_id}/approve")
async def approve_parent_registration(
    parent_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Reuse the canonical workflow that activates the parent and linked children."""

    return await process_parent_registration(
        parent_id=parent_id,
        action_data=AdminParentRegistrationAction(action="approve"),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )
