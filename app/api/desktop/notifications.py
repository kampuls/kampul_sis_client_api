"""Shared Flutter/desktop notification inbox for authenticated staff."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import User
from ...models.notification import Notification
from .data import get_current_desktop_user


router = APIRouter()

# Flutter stores employee notifications under the teacher audience. Desktop
# staff must use that same audience so both clients show one server-owned inbox.
STAFF_NOTIFICATION_USER_TYPE = "teacher"


def _notification_query(db: Session, current_user: User):
    return db.query(Notification).filter(
        Notification.user_id == int(current_user.id),
        Notification.user_type == STAFF_NOTIFICATION_USER_TYPE,
    )


def _serialize_notification(notification: Notification) -> Dict[str, Any]:
    return {
        "id": int(notification.id),
        "title": notification.title or "",
        "body": notification.body or "",
        "data": notification.data,
        "is_read": bool(notification.is_read),
        "is_deletable": bool(notification.is_deletable),
        "redirect_route": notification.redirect_route,
        "redirect_args": notification.redirect_args,
        "created_at": notification.created_at,
        "updated_at": notification.updated_at,
    }


@router.get("")
def get_desktop_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    """Return the current staff member's live Flutter notification inbox."""

    query = _notification_query(db, current_user)
    total = query.count()
    unread_count = query.filter(Notification.is_read.is_(False)).count()
    items = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "unread_count": unread_count,
        "items": [_serialize_notification(item) for item in items],
    }


def _owned_notification(
    db: Session,
    current_user: User,
    notification_id: int,
) -> Notification:
    notification = _notification_query(db, current_user).filter(
        Notification.id == notification_id
    ).first()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notification


@router.post("/read-all")
def mark_all_desktop_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    updated = _notification_query(db, current_user).filter(
        Notification.is_read.is_(False)
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"success": True, "updated": int(updated or 0)}


@router.delete("")
def delete_all_desktop_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    deleted = _notification_query(db, current_user).filter(
        Notification.is_deletable.is_(True)
    ).delete(synchronize_session=False)
    db.commit()
    return {"success": True, "deleted": int(deleted or 0)}


@router.post("/{notification_id}/read")
def mark_desktop_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    notification = _owned_notification(db, current_user, notification_id)
    notification.is_read = True
    db.commit()
    return {"success": True}


@router.post("/{notification_id}/unread")
def mark_desktop_notification_unread(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    notification = _owned_notification(db, current_user, notification_id)
    notification.is_read = False
    db.commit()
    return {"success": True}


@router.delete("/{notification_id}")
def delete_desktop_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> Dict[str, Any]:
    notification = _owned_notification(db, current_user, notification_id)
    if not bool(notification.is_deletable):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This notification cannot be deleted",
        )
    db.delete(notification)
    db.commit()
    return {"success": True, "deleted": 1}
