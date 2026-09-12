"""Who is allowed to see a given student.

``parents.myChilds`` is a comma-separated list of student IDs, and the check
"is this student one of mine?" was written out by hand at eleven call sites.
Two of them forgot it entirely, which is what this module exists to prevent:
one place to ask the question, so a new endpoint cannot quietly skip it.

Staff are allowed through — teachers legitimately view students they teach, and
that coarser boundary is enforced by the employee permission system.
"""

import logging
from typing import Any, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.dependencies import principal_from_user

logger = logging.getLogger(__name__)


def is_parent(current_user: Any) -> bool:
    """True when the caller is a parent rather than an employee."""
    return principal_from_user(current_user).kind == "parent"


def parent_child_ids(db: Session, parent_id: int) -> Set[int]:
    """The student IDs listed in this parent's ``myChilds``.

    Tolerates the shapes the column actually holds in production: empty, NULL,
    stray spaces, trailing commas and non-numeric junk.
    """
    if not parent_id:
        return set()
    row = db.execute(
        text("SELECT myChilds FROM parents WHERE id = :pid"),
        {"pid": parent_id},
    ).fetchone()
    if not row or not row[0]:
        return set()

    out: Set[int] = set()
    for part in str(row[0]).split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def parent_owns_student(db: Session, parent_id: int, student_id: int) -> bool:
    return int(student_id) in parent_child_ids(db, parent_id)


def assert_can_access_student(
    db: Session, current_user: Any, student_id: int, action: str = "view"
) -> None:
    """403 unless the caller is staff, or a parent of this student."""
    if not is_parent(current_user):
        return  # employee/admin — governed by the staff permission system

    parent_id = int(getattr(current_user, "id", 0) or 0)
    if parent_owns_student(db, parent_id, student_id):
        return

    logger.warning(
        "Parent %s tried to %s student %s who is not their child",
        parent_id,
        action,
        student_id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You can only access your own children",
    )


def assert_can_access_parent_record(
    db: Session, current_user: Any, parent_id: int
) -> None:
    """403 unless the caller is staff, or is that parent.

    For endpoints keyed by ``parent_id`` rather than a student: without this a
    parent can walk the ID space and read every other family's records.
    """
    if not is_parent(current_user):
        return

    own_id = int(getattr(current_user, "id", 0) or 0)
    if own_id and int(parent_id) == own_id:
        return

    logger.warning(
        "Parent %s tried to read parent record %s", own_id, parent_id
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You can only access your own family's records",
    )
