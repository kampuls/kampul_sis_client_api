"""Desktop leave surface backed by the canonical Flutter leave workflows."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, or_
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...models import Branch, User
from ..v1.leave_management import (
    _current_workplace_id,
    _department_name_map,
    router as shared_leave_router,
)
from .data import get_current_desktop_user


router = APIRouter()

# Reuse the production Flutter routes so calculations, validation, approvals,
# attendance integration, history, notifications, and transaction boundaries
# cannot drift between mobile and desktop clients.
router.include_router(shared_leave_router)


def _require_leave_admin(current_user: User) -> None:
    if int(getattr(current_user, "role", 0) or 0) != 1:
        raise HTTPException(status_code=403, detail="Admin access required")


def _employee_name(user: User) -> str:
    for field in ("eName", "kName", "username"):
        value = str(getattr(user, field, "") or "").strip()
        if value:
            return value
    return f"User #{user.id}"


@router.get("/admin/employee-options")
def desktop_leave_employee_options(
    search: str = Query("", max_length=100),
    branch_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    """Active employees available to the admin approver assignment picker."""
    _require_leave_admin(current_user)
    query = db.query(User).filter(User.status == 1)
    if branch_id is not None:
        query = query.filter(User.workplace == branch_id)
    value = search.strip()
    if value:
        term = f"%{value}%"
        conditions = [
            User.eName.like(term),
            User.kName.like(term),
            User.username.like(term),
            User.email.like(term),
        ]
        if value.isdigit():
            conditions.append(User.id == int(value))
        query = query.filter(or_(*conditions))

    users = (
        query.order_by(User.eName.asc(), User.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    department_ids = {
        int(user.departmentId) for user in users if user.departmentId is not None
    }
    branch_ids = {int(user.workplace) for user in users if user.workplace is not None}
    department_names = _department_name_map(db, department_ids)
    branch_names = {
        int(row.id): str(row.app_display_name or row.branch_name or f"Branch #{row.id}")
        for row in db.query(Branch).filter(Branch.id.in_(branch_ids)).all()
    } if branch_ids else {}
    return [
        {
            "user_id": int(user.id),
            "user_name": _employee_name(user),
            "user_name_en": str(user.eName) if user.eName else None,
            "user_name_kh": str(user.kName) if user.kName else None,
            "department_id": user.departmentId,
            "department_name": department_names.get(int(user.departmentId or 0)),
            "branch_id": user.workplace,
            "branch_name": branch_names.get(int(user.workplace or 0)),
            "avatar": user.image,
        }
        for user in users
    ]


@router.get("/admin/scope-options")
def desktop_leave_scope_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
):
    """Branch and department choices used by the approver editor."""
    _require_leave_admin(current_user)
    departments = db.execute(
        text(
            """
            SELECT id, department, translate
            FROM department
            ORDER BY department ASC, id ASC
            """
        )
    ).all()
    branches = db.query(Branch).order_by(Branch.branch_name.asc(), Branch.id.asc()).all()
    return {
        "departments": [
            {
                "id": int(row[0]),
                "name": str(row[1] or row[2] or f"Department #{row[0]}"),
            }
            for row in departments
        ],
        "branches": [
            {
                "id": int(row.id),
                "name": str(
                    (row.app_display_name or "").strip()
                    or (row.branch_name or "").strip()
                    or f"Branch #{row.id}"
                ),
            }
            for row in branches
            if row is not None and row.id is not None
        ],
        "current_branch_id": _current_workplace_id(current_user),
    }
