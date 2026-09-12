"""Push notifications for marketplace order events."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def notify_listing_broadcast(listing_id: int) -> None:
    """Push a newly published or renewed listing to parents and staff."""
    from sqlalchemy.orm import joinedload

    from ..core.database import SessionLocal
    from ..models.market import MarketListing
    from ..services.notification_service import (
        get_device_tokens_by_audience,
        send_app_rich_push_notification,
    )

    db = SessionLocal()
    try:
        listing = (
            db.query(MarketListing)
            .options(
                joinedload(MarketListing.images),
                joinedload(MarketListing.store),
            )
            .filter(MarketListing.id == listing_id)
            .first()
        )
        if not listing or listing.status != "active" or not listing.store:
            return

        audience_tokens = get_device_tokens_by_audience(
            db,
            "teacher,parent,employee",
        )
        tokens = []
        seen_tokens = set()
        for token in audience_tokens:
            value = token.get("token")
            if value and value not in seen_tokens:
                seen_tokens.add(value)
                tokens.append(token)
        if not tokens:
            logger.info("No parent/staff devices for market listing %s", listing_id)
            return

        store_name = (listing.store.name or "School Market").strip()
        currency = (listing.currency or "USD").upper()
        price = listing.price or 0
        price_text = f"{price:.2f}".rstrip("0").rstrip(".")
        title = f"New item from {store_name}"
        body = f"{listing.title} • {currency} {price_text}"
        data = {
            "type": "market_listing",
            "listing_id": str(listing.id),
            "store_id": str(listing.store_id),
            "is_market": "true",
            "deep_link": f"pamais://market/listing/{listing.id}",
            "title": title,
            "body": body,
        }
        images = sorted(listing.images, key=lambda image: image.sort_order or 0)
        if images and images[0].image_url:
            data["image_url"] = images[0].image_url

        chunk_size = 500
        for i in range(0, len(tokens), chunk_size):
            send_app_rich_push_notification(
                device_tokens=tokens[i : i + chunk_size],
                title=title,
                body=body,
                data=data,
                db=db,
            )
        logger.info(
            "Sent market listing %s broadcast to %s parent/staff devices",
            listing_id,
            len(tokens),
        )
    except Exception:
        logger.exception("Market listing %s broadcast failed", listing_id)
    finally:
        db.close()


def _display_name_for(db: Session, user_id: int, user_type: str) -> str:
    from sqlalchemy import text

    try:
        if user_type == "parent":
            row = db.execute(
                text(
                    "SELECT COALESCE(NULLIF(TRIM(fatherName), ''), NULLIF(TRIM(motherName), ''), "
                    "NULLIF(TRIM(gName), ''), NULLIF(TRIM(username), ''), 'Parent') "
                    "FROM parents WHERE id = :uid"
                ),
                {"uid": user_id},
            ).fetchone()
        else:
            row = db.execute(
                text(
                    "SELECT COALESCE(NULLIF(TRIM(eName), ''), NULLIF(TRIM(kName), ''), "
                    "NULLIF(TRIM(username), ''), 'Seller') "
                    "FROM users WHERE id = :uid"
                ),
                {"uid": user_id},
            ).fetchone()
        return str(row[0]) if row and row[0] else user_type.title()
    except Exception:
        return user_type.title()


def _tokens_for_user(db: Session, user_id: int, user_type: str):
    from ..services.notification_service import (
        get_parent_user_device_tokens,
        get_teacher_device_tokens,
    )

    if user_type == "parent":
        return get_parent_user_device_tokens(db, user_id)
    return get_teacher_device_tokens(db, user_id)


def notify_market_order_event(
    db: Session,
    *,
    recipient_user_id: int,
    recipient_user_type: str,
    title: str,
    body: str,
    order_id: int,
    listing_id: int,
    group_id: Optional[int] = None,
    message_id: Optional[int] = None,
    group_name: Optional[str] = None,
) -> None:
    from ..services.notification_service import send_notification

    try:
        tokens = _tokens_for_user(db, recipient_user_id, recipient_user_type)
        data = {
            "type": "market_order",
            "order_id": str(order_id),
            "listing_id": str(listing_id),
            "is_market": "true",
            "deep_link": f"pamais://market/order/{order_id}",
        }
        if group_id is not None:
            data["group_id"] = str(group_id)
        if message_id is not None:
            data["message_id"] = str(message_id)
        if group_name:
            data["group_name"] = group_name
        send_notification(
            device_tokens=tokens,
            title=title,
            body=body,
            data=data,
            channel_id="message_channel",
            db=db,
            user_ids=[
                {"id": recipient_user_id, "user_type": recipient_user_type},
            ],
            redirect_route="market_order",
            redirect_args={"order_id": order_id},
        )
    except Exception as exc:
        logger.error("Market order notification failed: %s", exc, exc_info=True)


def notify_new_review(
    db: Session,
    *,
    recipient_user_id: int,
    recipient_user_type: str,
    reviewer_user_id: int,
    reviewer_user_type: str,
    listing_id: int,
    listing_title: str,
    rating: int,
) -> None:
    """Review notifications open the listing (its reviews), not an order —
    they must not be sent as ``market_order`` with a dead ``order_id=0``."""
    from ..services.notification_service import send_notification

    try:
        tokens = _tokens_for_user(db, recipient_user_id, recipient_user_type)
        reviewer_name = _display_name_for(db, reviewer_user_id, reviewer_user_type)
        data = {
            "type": "market_review",
            "listing_id": str(listing_id),
            "is_market": "true",
            "deep_link": f"pamais://market/review/{listing_id}",
        }
        send_notification(
            device_tokens=tokens,
            title="New review",
            body=f"{reviewer_name} rated \"{listing_title}\" {rating}★",
            data=data,
            channel_id="message_channel",
            db=db,
            user_ids=[
                {"id": recipient_user_id, "user_type": recipient_user_type},
            ],
            redirect_route="market_review",
            redirect_args={"listing_id": listing_id},
        )
    except Exception as exc:
        logger.error("Market review notification failed: %s", exc, exc_info=True)


def notify_new_interest(
    db: Session,
    *,
    seller_user_id: int,
    seller_user_type: str,
    buyer_user_id: int,
    buyer_user_type: str,
    order_id: int,
    listing_id: int,
    listing_title: str,
    quantity: int,
    group_id: Optional[int] = None,
    message_id: Optional[int] = None,
    group_name: Optional[str] = None,
) -> None:
    buyer_name = _display_name_for(db, buyer_user_id, buyer_user_type)
    notify_market_order_event(
        db,
        recipient_user_id=seller_user_id,
        recipient_user_type=seller_user_type,
        title=f"New interest in {listing_title}",
        body=f"{buyer_name} is interested ({quantity}x) — open chat to reply",
        order_id=order_id,
        listing_id=listing_id,
        group_id=group_id,
        message_id=message_id,
        group_name=group_name,
    )


def notify_new_order(
    db: Session,
    *,
    seller_user_id: int,
    seller_user_type: str,
    buyer_user_id: int,
    buyer_user_type: str,
    order_id: int,
    listing_id: int,
    listing_title: str,
    quantity: int,
) -> None:
    buyer_name = _display_name_for(db, buyer_user_id, buyer_user_type)
    notify_market_order_event(
        db,
        recipient_user_id=seller_user_id,
        recipient_user_type=seller_user_type,
        title="New order request",
        body=f"{buyer_name} requested {quantity}x {listing_title}",
        order_id=order_id,
        listing_id=listing_id,
    )


def notify_order_status_change(
    db: Session,
    *,
    buyer_user_id: int,
    buyer_user_type: str,
    order_id: int,
    listing_id: int,
    listing_title: str,
    status: str,
) -> None:
    status_text = {
        "accepted": "accepted your order",
        "rejected": "rejected your order",
        "completed": "marked your order as completed",
        "cancelled": "cancelled the order",
    }.get(status, f"updated order to {status}")
    notify_market_order_event(
        db,
        recipient_user_id=buyer_user_id,
        recipient_user_type=buyer_user_type,
        title="Order update",
        body=f"Your request for {listing_title} was {status_text}",
        order_id=order_id,
        listing_id=listing_id,
    )
