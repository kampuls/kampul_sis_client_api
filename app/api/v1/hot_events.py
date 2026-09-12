"""
Hot Events API: admin-pushed banner on app home with expiry and audience.
"""

from datetime import datetime
import logging
from typing import List, Optional, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...core import get_db
from ...auth import get_current_active_user
from ...models import User, HotEvent, HotEventImpression
from ...schemas import HotEventCreate, HotEventUpdate, HotEventResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _is_admin(user: object, db: Session) -> bool:
    """Check if current user is admin (by role name)."""
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    role_id = getattr(user, "role", None)
    if role_id is None:
        return False
    row = db.execute(
        text("SELECT role_name FROM roles WHERE id = :rid"),
        {"rid": role_id},
    ).fetchone()
    if not row:
        return False
    name = (row[0] or "").lower()
    return "admin" in name or "super" in name


def _user_audience(user: object) -> str:
    """Return audience string for current user (teacher, parent, student, etc.)."""
    # Check for ParentAsUser or Parent type FIRST
    if getattr(user, "is_parent", False):
        logger.debug("_user_audience detected PARENT via is_parent flag.")
        return "parent"
        
    if hasattr(user, "__class__") and "Parent" in type(user).__name__:
        logger.debug("_user_audience detected PARENT via class name.")
        return "parent"
        
    role = getattr(user, "role", None)
    if role is None:
        logger.debug("_user_audience defaulted to ALL (no role, not parent).")
        return "all"
    # Map role_id or use a lookup; common: 1=admin, 2=teacher, 3=student, 4=parent
    role_str = str(role).lower()
    return "all"


def _resolve_user_audience(user: object, db: Session) -> str:
    """Resolve the audience label used by Hot Event visibility checks."""
    audience = _user_audience(user)
    role_id = getattr(user, "role", None)
    if audience == "parent" or role_id is None:
        return audience

    row = db.execute(
        text("SELECT role_name FROM roles WHERE id = :rid"),
        {"rid": role_id},
    ).fetchone()
    if not row:
        return audience

    role_name = (row[0] or "").strip().lower()
    return role_name or audience


def _matches_audience(event_audience: Optional[str], user_audience: str) -> bool:
    """Keep audience matching consistent for banners, popups, and history."""
    audience_parts = [
        part.strip().lower()
        for part in (event_audience or "all").split(",")
        if part.strip()
    ]
    if not audience_parts or "all" in audience_parts:
        return True
    return any(
        part == user_audience
        or part in user_audience
        or user_audience in part
        for part in audience_parts
    )


@router.get("/active")
async def get_active_hot_event(
    type: str = "banner",
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """
    Get the current active hot event for the authenticated user.
    Filters by: is_active, start_at <= now <= end_at, audience matches user role.
    Also checks frequency limits (max_impressions, interval_minutes).
    Audience can be 'all' or comma-separated e.g. 'teacher,parent'.
    Optional 'type' query param (default 'banner') to filter by event_type.
    """
    now = datetime.now()
    user_id = getattr(current_user, "id", None)
    
    audience = _resolve_user_audience(current_user, db)

    query = (
        db.query(HotEvent)
        .filter(HotEvent.is_active == True)
        .filter(HotEvent.end_at >= now)
        .filter((HotEvent.start_at == None) | (HotEvent.start_at <= now))
    )
    
    if type:
        if type == 'popup':
            # Fuzzy match for any popup sub-type (popup_promotion, popup_announcement, etc.)
            query = query.filter(HotEvent.event_type.like('popup%'))
        else:
            query = query.filter(HotEvent.event_type == type)
        
    events = query.order_by(HotEvent.end_at.asc()).all()
    
    # Filter by audience first
    candidate_events = [
        ev for ev in events if _matches_audience(ev.audience, audience)
    ]

    # Now check frequency/impressions for candidates
    # If multiple match, we might return the first one that passes frequency checks, 
    # or all of them? The function name is singular `get_active_hot_event`, implying one.
    # Existing code returned the first match. We will do the same but apply frequency checks.
    
    for ev in candidate_events:
        # Check max_impressions and interval if applicable
        # If tracking is required, we need to check hot_event_impressions
        if getattr(ev, "max_impressions", None) or getattr(ev, "interval_minutes", None):
            if not user_id:
                # Anonymous user? stricter logic or allowed? 
                # Assuming valid user as per Depends(get_current_active_user)
                continue

            impression = db.query(HotEventImpression).filter(
                HotEventImpression.hot_event_id == ev.id,
                HotEventImpression.user_id == user_id
            ).first()

            if impression:
                # Check max impressions
                if ev.max_impressions and impression.impression_count >= ev.max_impressions:
                    continue # Skip this event, limit reached

                # Check interval
                last_viewed = getattr(impression, "last_viewed_at", None)
                if getattr(ev, "interval_minutes", None) and last_viewed:
                    diff = now - last_viewed
                    minutes_since = diff.total_seconds() / 60
                    if minutes_since < ev.interval_minutes:
                         continue # Skip, too soon
            
            # If no impression record, it's safe to show (count=0, last_viewed=None)
        
        # If we get here, the event is valid to show
        return HotEventResponse.model_validate(ev)

    return None

@router.get("/active-list", response_model=List[HotEventResponse])
async def get_active_hot_events_list(
    type: str = "banner",
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """
    Get all current active hot events for the authenticated user.
    Returns a sequence of valid events respecting impression limits and intervals.
    """
    now = datetime.now()
    user_id = getattr(current_user, "id", None)
    
    audience = _resolve_user_audience(current_user, db)

    query = (
        db.query(HotEvent)
        .filter(HotEvent.is_active == True)
        .filter(HotEvent.end_at >= now)
        .filter((HotEvent.start_at == None) | (HotEvent.start_at <= now))
    )
    
    if type:
        if type == 'popup':
            query = query.filter(HotEvent.event_type.like('popup%'))
        else:
            query = query.filter(HotEvent.event_type == type)
        
    events = query.order_by(HotEvent.end_at.asc()).all()
    
    candidate_events = [
        ev for ev in events if _matches_audience(ev.audience, audience)
    ]

    valid_events = []
    for ev in candidate_events:
        if getattr(ev, "max_impressions", None) or getattr(ev, "interval_minutes", None):
            if not user_id:
                continue

            impression = db.query(HotEventImpression).filter(
                HotEventImpression.hot_event_id == ev.id,
                HotEventImpression.user_id == user_id
            ).first()

            if impression:
                if ev.max_impressions and impression.impression_count >= ev.max_impressions:
                    continue

                last_viewed = getattr(impression, "last_viewed_at", None)
                if getattr(ev, "interval_minutes", None) and last_viewed:
                    diff = now - last_viewed
                    minutes_since = diff.total_seconds() / 60
                    if minutes_since < ev.interval_minutes:
                         continue
            
        valid_events.append(HotEventResponse.model_validate(ev))

    return valid_events


@router.get("/history", response_model=List[HotEventResponse])
async def get_visible_hot_event_history(
    type: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """Return every non-hidden Hot Event assigned to the current user.

    Unlike the active endpoints, this intentionally includes scheduled and
    expired events and ignores impression limits. This gives users a place to
    revisit posts they missed. Deleted events disappear because they are no
    longer present in ``hot_events``.
    """
    audience = _resolve_user_audience(current_user, db)
    safe_skip = max(skip, 0)
    safe_limit = min(max(limit, 1), 500)

    query = db.query(HotEvent).filter(HotEvent.is_active == True)
    if type:
        if type == "popup":
            query = query.filter(HotEvent.event_type.like("popup%"))
        else:
            query = query.filter(HotEvent.event_type == type)

    events = query.order_by(HotEvent.created_at.desc(), HotEvent.id.desc()).all()
    visible_events = [
        HotEventResponse.model_validate(event)
        for event in events
        if _matches_audience(event.audience, audience)
    ]
    return visible_events[safe_skip : safe_skip + safe_limit]


@router.post("/{event_id}/view")
async def record_impression(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """
    Record that a user has viewed a hot event.
    Updates or creates a HotEventImpression record.
    """
    user_id = getattr(current_user, "id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")

    # Verify event exists
    ev = db.query(HotEvent).filter(HotEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Hot event not found")

    impression = db.query(HotEventImpression).filter(
        HotEventImpression.hot_event_id == event_id,
        HotEventImpression.user_id == user_id
    ).first()

    if impression:
        setattr(impression, "impression_count", getattr(impression, "impression_count", 0) + 1)
        setattr(impression, "last_viewed_at", datetime.now())
    else:
        impression = HotEventImpression(
            hot_event_id=event_id,
            user_id=user_id,
            impression_count=1,
            last_viewed_at=datetime.now()
        )
        db.add(impression)
    
    db.commit()
    return {"status": "success", "impression_count": getattr(impression, "impression_count", 0)}


@router.get("", response_model=List[HotEventResponse])
async def list_hot_events(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """List all hot events (admin only)."""
    if not _is_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Admin only")
    events = (
        db.query(HotEvent)
        .order_by(HotEvent.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [HotEventResponse.model_validate(e) for e in events]


def _send_notifications_in_background(event_id: int, body_send: bool) -> None:
    """
    Sends push notifications for a hot event in the background.
    Uses a fresh DB session so it is safe after the request scope ends.
    """
    if not body_send:
        return
    from ...core.database import SessionLocal
    from ...services.notification_service import (
        get_device_tokens_by_audience,
        send_app_rich_push_notification,
    )

    db = SessionLocal()
    try:
        ev = db.query(HotEvent).filter(HotEvent.id == event_id).first()
        if not ev or not bool(getattr(ev, "is_active", True)):
            return

        title = str(getattr(ev, "title", None) or "New Announcement")
        body_text = str(getattr(ev, "message", ""))
        audience = str(getattr(ev, "audience", "all"))
        link_url = str(getattr(ev, "link_url", None) or "")
        tokens = get_device_tokens_by_audience(db, audience)

        if not tokens:
            return

        chunk_size = 500
        for i in range(0, len(tokens), chunk_size):
            chunk = tokens[i : i + chunk_size]
            try:
                send_app_rich_push_notification(
                    device_tokens=chunk,
                    title=title,
                    body=body_text,
                    data={
                        "type": "hot_event",
                        "event_id": str(getattr(ev, "id", "")),
                        "link_url": link_url,
                        "title": title,
                        "body": body_text,
                    },
                    db=db,
                )
            except Exception as chunk_err:
                logger.warning(
                    "[HotEvent] Notification chunk %s failed: %s",
                    i // chunk_size + 1,
                    chunk_err,
                )

        logger.info(
            "[HotEvent] Sent notifications to %s devices in %s chunks.",
            len(tokens),
            ((len(tokens) - 1) // chunk_size) + 1,
        )
    except Exception as e:
        logger.exception("[HotEvent] Background notification error: %s", e)
    finally:
        db.close()


@router.post("", response_model=HotEventResponse)
async def create_hot_event(
    body: HotEventCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """Create a hot event (admin only)."""
    if not _is_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Admin only")
    user_id = getattr(current_user, "id", None)
    ev = HotEvent(
        title=body.title,
        message=body.message,
        start_at=body.start_at,
        end_at=body.end_at,
        audience=body.audience or "all",
        event_type=body.event_type,
        frequency=body.frequency,
        interval_minutes=body.interval_minutes,
        max_impressions=body.max_impressions,
        link_url=body.link_url,
        status_text=body.status_text,
        is_active=body.is_active,
        created_by=user_id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    is_active = bool(getattr(ev, "is_active", True))
    if is_active and body.send_notification:
        background_tasks.add_task(
            _send_notifications_in_background,
            cast(int, ev.id),
            bool(body.send_notification),
        )

    return HotEventResponse.model_validate(ev)



@router.get("/{event_id}", response_model=HotEventResponse)
async def get_hot_event(
  event_id: int,
  db: Session = Depends(get_db),
  current_user: object = Depends(get_current_active_user),
):
    """Get one hot event by id (admin only)."""
    if not _is_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Admin only")
    ev = db.query(HotEvent).filter(HotEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Hot event not found")
    return HotEventResponse.model_validate(ev)


@router.patch("/{event_id}", response_model=HotEventResponse)
async def update_hot_event(
    event_id: int,
    body: HotEventUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """Update a hot event (admin only)."""
    if not _is_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Admin only")
    ev = db.query(HotEvent).filter(HotEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Hot event not found")
    data = body.model_dump(exclude_unset=True)
    notify_requested = data.pop("send_notification", None)
    for k, v in data.items():
        setattr(ev, k, v)
    db.commit()
    db.refresh(ev)
    if notify_requested is True and bool(getattr(ev, "is_active", True)):
        background_tasks.add_task(
            _send_notifications_in_background,
            cast(int, ev.id),
            True,
        )
    return HotEventResponse.model_validate(ev)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hot_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: object = Depends(get_current_active_user),
):
    """Delete a hot event (admin only)."""
    if not _is_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Admin only")
    ev = db.query(HotEvent).filter(HotEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Hot event not found")
    db.delete(ev)
    db.commit()
    return None
