from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import extract

from ....core import get_db
from ....auth import get_current_active_user
from .... import models, schemas
from ..websocket import broadcast_public_data_update

router = APIRouter()


def _is_admin(user: models.User) -> bool:
    role_id = getattr(user, "role", None)
    if role_id is None:
        return False
    try:
        return int(role_id) == 1
    except (TypeError, ValueError):
        return False


# ─────────────────────────────────────────────
# PUBLIC
# ─────────────────────────────────────────────

@router.get("/public", response_model=List[schemas.SchoolEventResponse])
def list_public_school_events(
    db: Session = Depends(get_db),
    academic_year: Optional[str] = None,
    event_type: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    skip: int = 0,
    limit: int = Query(200, le=500),
) -> List[schemas.SchoolEventResponse]:
    """Public endpoint — returns active events ordered by date."""
    query = db.query(models.SchoolEvent).filter(models.SchoolEvent.is_active == True)

    if academic_year:
        query = query.filter(models.SchoolEvent.academic_year == academic_year)
    if event_type:
        query = query.filter(models.SchoolEvent.event_type == event_type)
    if month is not None:
        query = query.filter(extract("month", models.SchoolEvent.event_date) == month)

    events = (
        query.order_by(models.SchoolEvent.event_date.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return events


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

@router.get("", response_model=List[schemas.SchoolEventResponse])
def list_school_events_admin(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    academic_year: Optional[str] = None,
    event_type: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = Query(200, le=500),
) -> List[schemas.SchoolEventResponse]:
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    query = db.query(models.SchoolEvent)
    if academic_year:
        query = query.filter(models.SchoolEvent.academic_year == academic_year)
    if event_type:
        query = query.filter(models.SchoolEvent.event_type == event_type)
    if month is not None:
        query = query.filter(extract("month", models.SchoolEvent.event_date) == month)
    if is_active is not None:
        query = query.filter(models.SchoolEvent.is_active == is_active)

    return (
        query.order_by(models.SchoolEvent.event_date.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("", response_model=schemas.SchoolEventResponse, status_code=status.HTTP_201_CREATED)
async def create_school_event(
    body: schemas.SchoolEventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.SchoolEventResponse:
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    event = models.SchoolEvent(**body.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    await broadcast_public_data_update("school_events")
    return event


@router.put("/{event_id}", response_model=schemas.SchoolEventResponse)
async def update_school_event(
    event_id: int,
    body: schemas.SchoolEventUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.SchoolEventResponse:
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    event = db.query(models.SchoolEvent).filter(models.SchoolEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(event, field, value)

    db.commit()
    db.refresh(event)
    await broadcast_public_data_update("school_events")
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_school_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> None:
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    event = db.query(models.SchoolEvent).filter(models.SchoolEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    db.delete(event)
    db.commit()
    await broadcast_public_data_update("school_events")
    return None
