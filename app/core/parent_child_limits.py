"""Child limits for parents pending admin approval (self-registration)."""

from __future__ import annotations

from typing import List

from fastapi import HTTPException, status

from ..models import Parent

# During parent registration flow (before / while pending approval)
MAX_CHILDREN_DURING_REGISTRATION = 5
# One additional child from the "waiting for approval" home experience
MAX_CHILDREN_WHILE_PENDING_APPROVAL = 1
# Total while parent.status != 1 (active)
MAX_CHILDREN_PENDING_PARENT_TOTAL = (
    MAX_CHILDREN_DURING_REGISTRATION + MAX_CHILDREN_WHILE_PENDING_APPROVAL
)


def parse_parent_child_ids(parent: Parent) -> List[str]:
    raw = getattr(parent, "myChilds", None) or ""
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def parent_child_count(parent: Parent) -> int:
    return len(parse_parent_child_ids(parent))


def validate_pending_parent_child_add(
    parent: Parent,
    phase: str | None,
) -> None:
    """
    Enforce child limits for unapproved parents.

    - registration: up to 5 children
    - pending_approval: only when count is 0 (first child while waiting) or 5 (+1 sixth)
    - total while pending: 6
    """
    if getattr(parent, "status", 0) == 1:
        return

    count = parent_child_count(parent)
    if count >= MAX_CHILDREN_PENDING_PARENT_TOTAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You have reached the maximum of {MAX_CHILDREN_PENDING_PARENT_TOTAL} "
                "children while your account is pending approval."
            ),
        )

    normalized = (phase or "registration").strip().lower()

    if normalized == "registration":
        if count >= MAX_CHILDREN_DURING_REGISTRATION:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You can add up to {MAX_CHILDREN_DURING_REGISTRATION} children "
                    "during registration."
                ),
            )
        return

    if normalized == "pending_approval":
        if count >= MAX_CHILDREN_PENDING_PARENT_TOTAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You have reached the maximum of {MAX_CHILDREN_PENDING_PARENT_TOTAL} "
                    "children while waiting for approval."
                ),
            )
        if count not in (0, MAX_CHILDREN_DURING_REGISTRATION):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "While waiting for approval, you can add one child only if you have "
                    f"none yet, or one more after you have registered "
                    f"{MAX_CHILDREN_DURING_REGISTRATION} children during registration."
                ),
            )
        return

    # Unknown phase: apply registration cap for pending parents
    if count >= MAX_CHILDREN_DURING_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You can add up to {MAX_CHILDREN_DURING_REGISTRATION} children "
                "while your account is pending approval."
            ),
        )
