from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ....core import get_db
from ....auth import get_current_active_user
from .... import models, schemas
from ..websocket import broadcast_public_data_update

router = APIRouter()

def _is_admin(user: models.User) -> bool:
    """Small helper to restrict admin endpoints."""
    role_id = getattr(user, "role", None)
    if role_id is None:
        return False
    try:
        return int(role_id) == 1
    except (TypeError, ValueError):
        return False

@router.get("/public", response_model=List[schemas.SchoolOverviewResponse])
def list_public_school_overviews(
    db: Session = Depends(get_db),
    is_active: bool = True,
) -> List[schemas.SchoolOverviewResponse]:
    """
    Public endpoint used by the mobile app.
    Returns active overview items ordered by sort_order.
    """
    query = db.query(models.SchoolOverview)
    if is_active is not None:
        query = query.filter(models.SchoolOverview.is_active == is_active)

    overviews = (
        query.order_by(
            models.SchoolOverview.sort_order.asc(),
            models.SchoolOverview.id.asc(),
        )
        .all()
    )
    return overviews

@router.get("", response_model=List[schemas.SchoolOverviewResponse])
def list_school_overviews_admin(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    skip: int = 0,
    limit: int = Query(100, le=200),
    is_active: Optional[bool] = None,
) -> List[schemas.SchoolOverviewResponse]:
    """
    Admin: list school overviews with optional filters.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    query = db.query(models.SchoolOverview)

    if is_active is not None:
        query = query.filter(models.SchoolOverview.is_active == is_active)

    overviews = (
        query.order_by(
            models.SchoolOverview.sort_order.asc(),
            models.SchoolOverview.id.asc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return overviews

@router.post(
    "",
    response_model=schemas.SchoolOverviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_school_overview(
    body: schemas.SchoolOverviewCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.SchoolOverviewResponse:
    """
    Admin: create a school overview entry for the app home screen.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    overview = models.SchoolOverview(**body.model_dump())
    db.add(overview)
    db.commit()
    db.refresh(overview)
    
    await broadcast_public_data_update("school_overviews")
    return overview

@router.put("/{overview_id}", response_model=schemas.SchoolOverviewResponse)
async def update_school_overview(
    overview_id: int,
    body: schemas.SchoolOverviewUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.SchoolOverviewResponse:
    """
    Admin: update a school overview entry.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    overview = db.query(models.SchoolOverview).filter(models.SchoolOverview.id == overview_id).first()
    if not overview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School overview not found",
        )

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(overview, field, value)

    db.commit()
    db.refresh(overview)
    await broadcast_public_data_update("school_overviews")
    return overview

@router.delete("/{overview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_school_overview(
    overview_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> None:
    """
    Admin: delete a school overview entry.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    overview = db.query(models.SchoolOverview).filter(models.SchoolOverview.id == overview_id).first()
    if not overview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School overview not found",
        )

    db.delete(overview)
    db.commit()
    await broadcast_public_data_update("school_overviews")
    return None
