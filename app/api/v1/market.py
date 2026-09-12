"""
School marketplace API — stores, listings, orders.
"""

import json
import logging
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple, Union

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload

from ...auth import get_current_active_user
from ...core import get_db
from ...models import Parent, User
from ...models.app_admin import AppAdmin
from ...models.market import (
    MarketCategory,
    MarketListing,
    MarketListingBroadcast,
    MarketListingImage,
    MarketOrder,
    MarketReview,
    MarketSellerBan,
    MarketSettings,
    MarketStore,
    MarketWishlist,
)
from ...models.message import (
    GroupMessage,
    GroupType,
    MemberRole,
    MessageGroup,
    MessageGroupMember,
    UserType,
)
from ...schemas.market import (
    MarketCategoryCreate,
    MarketCategoryResponse,
    MarketCategoryUpdate,
    MarketConversationCreate,
    MarketConversationListItem,
    MarketConversationResponse,
    MarketListingCreate,
    MarketListingImageReorder,
    MarketListingImageResponse,
    MarketListingRenewRequest,
    MarketListingResponse,
    MarketListingUpdate,
    MarketOrderCreate,
    MarketOrderResponse,
    MarketOrderStatusUpdate,
    MarketPaginatedListings,
    MarketPaginatedOrders,
    MarketPaginatedReviews,
    MarketPaginatedSellerBans,
    MarketPaginatedStores,
    MarketReviewCreate,
    MarketReviewResponse,
    MarketSellerBanCreate,
    MarketSellerBanResponse,
    MarketStoreResponse,
    MarketStoreStats,
    MarketStoreUpdate,
    MarketTopListing,
    MarketWelcomeSettingsResponse,
    MarketWelcomeSettingsUpdate,
)
from ...services.market_notification_service import (
    notify_listing_broadcast,
    notify_market_order_event,
    notify_new_interest,
    notify_new_order,
    notify_new_review,
    notify_order_status_change,
)
from ...services.market_listing_lifecycle import (
    effective_published_at,
    listing_renewal_status,
)
from ...services.storage_service import StorageService

router = APIRouter()

STORE_NAME_CHANGE_COOLDOWN = timedelta(days=90)
STORE_DAILY_LISTING_LIMIT = 10
STORE_DAILY_BROADCAST_LIMIT = 3
CAMBODIA_TZ = timezone(timedelta(hours=7))
logger = logging.getLogger(__name__)


def _notify_market_feed_updated() -> None:
    """Hint connected clients that public marketplace listings changed."""
    try:
        from .websocket import notify_public_data_from_sync

        notify_public_data_from_sync("market_listings")
    except Exception:
        logger.warning("market listings broadcast skipped", exc_info=True)

MAX_LISTING_IMAGES = 5
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
ALLOWED_CONDITIONS = {"new", "like_new", "used"}


def _norm_condition(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    return v if v in ALLOWED_CONDITIONS else None


def _validate_listing_prices(price: Decimal, compare_at_price: Optional[Decimal]) -> None:
    if compare_at_price is not None and compare_at_price <= price:
        raise HTTPException(
            status_code=400,
            detail="Original price must be higher than sale price",
        )
DEFAULT_CATEGORIES = [
    ("Books", "សៀវភៅ", "books", 1),
    ("Uniform", "ឯកសណ្ឋាន", "uniform", 2),
    ("Food", "អាហារ", "food", 3),
    ("Electronics", "គ្រឿងអេឡិចត្រូនិច", "electronics", 4),
    ("Other", "ផ្សេងៗ", "other", 99),
]

ACTIVE_BUYER_ORDER_STATUSES = ("pending", "accepted")


def _caller_identity(user) -> Tuple[int, str]:
    if getattr(user, "is_parent", False) or getattr(user, "role", None) == "parent":
        return int(user.id), "parent"
    return int(user.id), "teacher"


def _require_market_user(user) -> Tuple[int, str]:
    uid, utype = _caller_identity(user)
    if utype not in ("parent", "teacher"):
        raise HTTPException(status_code=403, detail="Market is for parents and teachers only")
    return uid, utype


def _require_app_admin(db: Session, current_user: User) -> AppAdmin:
    admin = (
        db.query(AppAdmin)
        .filter(AppAdmin.user_id == current_user.id, AppAdmin.is_locked == False)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=403, detail="Only active App Admins can manage market")
    return admin


def _welcome_settings_response(
    settings: Optional[MarketSettings],
) -> MarketWelcomeSettingsResponse:
    if settings is None:
        return MarketWelcomeSettingsResponse()
    return MarketWelcomeSettingsResponse(
        welcome_enabled=bool(settings.welcome_enabled),
        welcome_skip_seconds=max(0, min(60, int(settings.welcome_skip_seconds))),
        welcome_version=max(1, int(settings.welcome_version)),
    )


def _is_seller_banned(db: Session, user_id: int, user_type: str) -> bool:
    now = datetime.now(timezone.utc)
    ban = (
        db.query(MarketSellerBan)
        .filter(
            MarketSellerBan.user_id == user_id,
            MarketSellerBan.user_type == user_type,
        )
        .order_by(desc(MarketSellerBan.created_at))
        .first()
    )
    if not ban:
        return False
    if ban.banned_until is None:
        return True
    return ban.banned_until.replace(tzinfo=timezone.utc) > now


def _ensure_categories(db: Session) -> None:
    if db.query(MarketCategory).count() > 0:
        return
    for name_en, name_km, icon_key, sort_order in DEFAULT_CATEGORIES:
        db.add(
            MarketCategory(
                name=name_en,
                name_en=name_en,
                name_km=name_km,
                icon_key=icon_key,
                sort_order=sort_order,
            )
        )
    db.commit()


def _category_listing_count(db: Session, category_id: int) -> int:
    return int(
        db.query(func.count(MarketListing.id))
        .filter(MarketListing.category_id == category_id)
        .scalar()
        or 0
    )


def _category_to_response(db: Session, cat: MarketCategory) -> MarketCategoryResponse:
    return MarketCategoryResponse(
        id=cat.id,
        name=cat.name_en,
        name_en=cat.name_en,
        name_km=cat.name_km,
        icon_key=cat.icon_key,
        sort_order=cat.sort_order,
        listing_count=_category_listing_count(db, cat.id),
    )


def _display_name(db: Session, user_id: int, user_type: str) -> str:
    if user_type == "parent":
        p = db.query(Parent).filter(Parent.id == user_id).first()
        if p:
            return (
                p.fatherName or p.motherName or p.gName or p.username or "Parent"
            ).strip()
        return "Parent"
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        return (u.eName or u.kName or u.username or "Seller").strip()
    return "Seller"


def _cambodia_day_bounds_utc() -> Tuple[datetime, datetime]:
    """UTC bounds for the current calendar day in Cambodia (UTC+7)."""
    now_kh = datetime.now(CAMBODIA_TZ)
    start_kh = datetime(now_kh.year, now_kh.month, now_kh.day, tzinfo=CAMBODIA_TZ)
    end_kh = start_kh + timedelta(days=1)
    return start_kh.astimezone(timezone.utc), end_kh.astimezone(timezone.utc)


def _store_listings_created_today(db: Session, store_id: int) -> int:
    start_utc, end_utc = _cambodia_day_bounds_utc()
    return (
        db.query(func.count(MarketListing.id))
        .filter(
            MarketListing.store_id == store_id,
            MarketListing.status != "deleted",
            MarketListing.created_at >= start_utc,
            MarketListing.created_at < end_utc,
        )
        .scalar()
        or 0
    )


def _store_daily_listing_quota(db: Session, store_id: int) -> Tuple[int, int, int]:
    """Posted today, daily limit, remaining today."""
    posted = _store_listings_created_today(db, store_id)
    limit = STORE_DAILY_LISTING_LIMIT
    remaining = max(0, limit - posted)
    return posted, limit, remaining


def _store_daily_broadcast_quota(db: Session, store_id: int) -> Tuple[int, int, int]:
    """Broadcasts sent today, daily limit, and remaining in Cambodia time."""
    start_utc, end_utc = _cambodia_day_bounds_utc()
    sent = int(
        db.query(func.count(MarketListingBroadcast.id))
        .filter(
            MarketListingBroadcast.store_id == store_id,
            MarketListingBroadcast.created_at >= start_utc,
            MarketListingBroadcast.created_at < end_utc,
        )
        .scalar()
        or 0
    )
    limit = STORE_DAILY_BROADCAST_LIMIT
    return sent, limit, max(0, limit - sent)


def _reserve_listing_broadcast(
    db: Session,
    store: MarketStore,
    listing: MarketListing,
) -> None:
    """Reserve at most one push per product/day and three per store/day."""
    # Serialize reservations across simultaneous requests from the same store.
    db.query(MarketStore.id).filter(MarketStore.id == store.id).with_for_update().one()
    publication_at = effective_published_at(listing.created_at, listing.renewed_at)
    if publication_at is None:
        raise HTTPException(status_code=400, detail="Listing publication date is unavailable")

    start_utc, end_utc = _cambodia_day_bounds_utc()
    already_sent = (
        db.query(MarketListingBroadcast.id)
        .filter(
            MarketListingBroadcast.listing_id == listing.id,
            MarketListingBroadcast.created_at >= start_utc,
            MarketListingBroadcast.created_at < end_utc,
        )
        .first()
    )
    if already_sent:
        raise HTTPException(
            status_code=409,
            detail="This product has already notified the community today",
        )

    sent, limit, _ = _store_daily_broadcast_quota(db, store.id)
    if sent >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily marketplace notification limit reached ({limit} broadcasts per day)",
        )

    db.add(
        MarketListingBroadcast(
            store_id=store.id,
            listing_id=listing.id,
            publication_at=publication_at,
        )
    )


def _store_name_change_status(store: MarketStore) -> Tuple[bool, Optional[datetime]]:
    """Whether the seller may rename the store, and when rename unlocks."""
    changed_at = store.name_changed_at
    if changed_at is None:
        return True, None
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    next_at = changed_at + STORE_NAME_CHANGE_COOLDOWN
    now = datetime.now(timezone.utc)
    if now >= next_at:
        return True, None
    return False, next_at


def _get_or_create_store(db: Session, user_id: int, user_type: str) -> MarketStore:
    store = (
        db.query(MarketStore)
        .filter(
            MarketStore.seller_user_id == user_id,
            MarketStore.seller_user_type == user_type,
        )
        .first()
    )
    if store:
        return store
    default_name = f"{_display_name(db, user_id, user_type)}'s Store"
    store = MarketStore(
        seller_user_id=user_id,
        seller_user_type=user_type,
        name=default_name[:150],
        status="active",
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def _profile_contacts(db: Session, user_id: int, user_type: str) -> Tuple[Optional[str], Optional[str]]:
    if user_type == "parent":
        p = db.query(Parent).filter(Parent.id == user_id).first()
        if p:
            phone = (p.fatherPhone or p.motherPhone or p.gPhone or "").strip() or None
            email = (p.pEmail or "").strip() or None
            return email, phone
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        email = (u.email or "").strip() or None
        phone = (u.phone or "").strip() or None
        return email, phone
    return None, None


def _store_listing_count(db: Session, store_id: int, active_only: bool = False) -> int:
    q = db.query(func.count(MarketListing.id)).filter(
        MarketListing.store_id == store_id,
    )
    if active_only:
        q = q.filter(MarketListing.status == "active")
    else:
        q = q.filter(MarketListing.status != "deleted")
    return q.scalar() or 0


def _ratings_for_listings(db: Session, listing_ids: List[int]) -> dict:
    """Batch listing_id -> (avg, count) to avoid per-listing rating queries."""
    if not listing_ids:
        return {}
    rows = (
        db.query(
            MarketReview.listing_id,
            func.avg(MarketReview.rating),
            func.count(MarketReview.id),
        )
        .filter(MarketReview.listing_id.in_(listing_ids))
        .group_by(MarketReview.listing_id)
        .all()
    )
    return {lid: (float(avg or 0), int(cnt or 0)) for lid, avg, cnt in rows}


def _sold_counts_for_listings(db: Session, listing_ids: List[int]) -> dict:
    """Batch listing_id -> units sold (sum of completed-order quantity)."""
    if not listing_ids:
        return {}
    rows = (
        db.query(MarketOrder.listing_id, func.coalesce(func.sum(MarketOrder.quantity), 0))
        .filter(MarketOrder.listing_id.in_(listing_ids), MarketOrder.status == "completed")
        .group_by(MarketOrder.listing_id)
        .all()
    )
    return {lid: int(total or 0) for lid, total in rows}


def _favorited_ids(db: Session, viewer: Optional[Tuple[int, str]], listing_ids: List[int]) -> set:
    if not viewer or not listing_ids:
        return set()
    vid, vtype = viewer
    rows = (
        db.query(MarketWishlist.listing_id)
        .filter(
            MarketWishlist.user_id == vid,
            MarketWishlist.user_type == vtype,
            MarketWishlist.listing_id.in_(listing_ids),
        )
        .all()
    )
    return {r[0] for r in rows}


def _store_rating(db: Session, store_id: int) -> Tuple[float, int]:
    avg, cnt = (
        db.query(func.avg(MarketReview.rating), func.count(MarketReview.id))
        .filter(MarketReview.store_id == store_id)
        .first()
    )
    return float(avg or 0), int(cnt or 0)


def _store_to_response(
    db: Session,
    store: MarketStore,
    listing_count: Optional[int] = None,
    include_suggestions: bool = False,
    include_daily_quota: bool = False,
) -> MarketStoreResponse:
    count = listing_count if listing_count is not None else _store_listing_count(db, store.id)
    suggested_email = suggested_phone = None
    if include_suggestions:
        se, sp = _profile_contacts(db, store.seller_user_id, store.seller_user_type)
        if not (store.contact_email or "").strip():
            suggested_email = se
        if not (store.contact_phone or "").strip():
            suggested_phone = sp
    s_avg, s_cnt = _store_rating(db, store.id)
    name_allowed, name_next = _store_name_change_status(store)
    posted_today = limit_today = remaining_today = None
    broadcasts_today = broadcast_limit = broadcasts_remaining = None
    if include_daily_quota:
        posted_today, limit_today, remaining_today = _store_daily_listing_quota(db, store.id)
        broadcasts_today, broadcast_limit, broadcasts_remaining = (
            _store_daily_broadcast_quota(db, store.id)
        )
    return MarketStoreResponse(
        id=store.id,
        seller_user_id=store.seller_user_id,
        seller_user_type=store.seller_user_type,
        name=store.name,
        tagline=store.tagline,
        description=store.description,
        contact_email=store.contact_email,
        contact_phone=store.contact_phone,
        contact_telegram=store.contact_telegram,
        address=store.address,
        logo_url=store.logo_url,
        cover_url=store.cover_url,
        status=store.status,
        seller_display_name=_display_name(db, store.seller_user_id, store.seller_user_type),
        listing_count=count,
        rating_avg=round(s_avg, 2),
        rating_count=s_cnt,
        created_at=store.created_at,
        suggested_email=suggested_email,
        suggested_phone=suggested_phone,
        name_change_allowed=name_allowed,
        name_next_change_at=name_next,
        listings_posted_today=posted_today,
        daily_listing_limit=limit_today,
        listings_remaining_today=remaining_today,
        broadcasts_sent_today=broadcasts_today,
        daily_broadcast_limit=broadcast_limit,
        broadcasts_remaining_today=broadcasts_remaining,
    )


def _pending_interest_counts(db: Session, listing_ids: List[int]) -> dict:
    if not listing_ids:
        return {}
    rows = (
        db.query(MarketOrder.listing_id, func.count(MarketOrder.id))
        .filter(
            MarketOrder.listing_id.in_(listing_ids),
            MarketOrder.status == "pending",
        )
        .group_by(MarketOrder.listing_id)
        .all()
    )
    return {int(lid): int(cnt) for lid, cnt in rows}


def _active_buyer_orders(
    db: Session, listing_ids: List[int], buyer_id: int, buyer_type: str
) -> dict:
    if not listing_ids:
        return {}
    rows = (
        db.query(MarketOrder)
        .filter(
            MarketOrder.listing_id.in_(listing_ids),
            MarketOrder.buyer_user_id == buyer_id,
            MarketOrder.buyer_user_type == buyer_type,
            MarketOrder.status.in_(ACTIVE_BUYER_ORDER_STATUSES),
        )
        .order_by(desc(MarketOrder.created_at))
        .all()
    )
    out: dict = {}
    for row in rows:
        if row.listing_id not in out:
            out[row.listing_id] = row
    return out


def _viewer_listing_fields(
    db: Session,
    listing: MarketListing,
    store: Optional[MarketStore],
    viewer: Optional[Tuple[int, str]],
    *,
    pending_counts: Optional[dict] = None,
    buyer_orders: Optional[dict] = None,
) -> dict:
    if not viewer or not store:
        return {
            "is_own_listing": False,
            "pending_interest_count": 0,
            "viewer_order_id": None,
            "viewer_order_status": None,
        }
    uid, utype = viewer
    is_own = store.seller_user_id == uid and store.seller_user_type == utype
    if is_own:
        pending = (
            pending_counts.get(listing.id, 0)
            if pending_counts is not None
            else (
                db.query(func.count(MarketOrder.id))
                .filter(
                    MarketOrder.listing_id == listing.id,
                    MarketOrder.status == "pending",
                )
                .scalar()
                or 0
            )
        )
        return {
            "is_own_listing": True,
            "pending_interest_count": int(pending),
            "viewer_order_id": None,
            "viewer_order_status": None,
        }
    order = (
        buyer_orders.get(listing.id)
        if buyer_orders is not None
        else (
            db.query(MarketOrder)
            .filter(
                MarketOrder.listing_id == listing.id,
                MarketOrder.buyer_user_id == uid,
                MarketOrder.buyer_user_type == utype,
                MarketOrder.status.in_(ACTIVE_BUYER_ORDER_STATUSES),
            )
            .order_by(desc(MarketOrder.created_at))
            .first()
        )
    )
    return {
        "is_own_listing": False,
        "pending_interest_count": 0,
        "viewer_order_id": order.id if order else None,
        "viewer_order_status": order.status if order else None,
    }


def _listing_to_response(
    db: Session,
    listing: MarketListing,
    include_store: bool = True,
    *,
    rating: Optional[Tuple[float, int]] = None,
    sold_count: Optional[int] = None,
    is_favorited: bool = False,
    viewer: Optional[Tuple[int, str]] = None,
    pending_counts: Optional[dict] = None,
    buyer_orders: Optional[dict] = None,
) -> MarketListingResponse:
    store = listing.store
    if rating is None:
        rating = _ratings_for_listings(db, [listing.id]).get(listing.id, (0.0, 0))
    rating_avg, rating_count = rating
    if sold_count is None:
        sold_count = _sold_counts_for_listings(db, [listing.id]).get(listing.id, 0)
    can_renew, next_renew_at = listing_renewal_status(
        listing.created_at,
        listing.renewed_at,
    )
    can_renew = can_renew and listing.status == "active"
    published_at = effective_published_at(listing.created_at, listing.renewed_at)
    viewer_fields = _viewer_listing_fields(
        db, listing, store, viewer, pending_counts=pending_counts, buyer_orders=buyer_orders
    )
    return MarketListingResponse(
        id=listing.id,
        store_id=listing.store_id,
        category_id=listing.category_id,
        category_name=listing.category.name if listing.category else None,
        title=listing.title,
        description=listing.description,
        price=listing.price or Decimal("0"),
        compare_at_price=listing.compare_at_price,
        currency=listing.currency or "USD",
        status=listing.status,
        stock_qty=listing.stock_qty,
        view_count=listing.view_count or 0,
        condition=listing.condition,
        is_featured=bool(listing.is_featured),
        rating_avg=round(rating_avg, 2),
        rating_count=rating_count,
        sold_count=sold_count,
        is_favorited=is_favorited,
        images=[
            MarketListingImageResponse(
                id=img.id,
                image_url=img.image_url,
                sort_order=img.sort_order or 0,
            )
            for img in listing.images
        ],
        store_name=store.name if include_store and store else None,
        store_contact_phone=store.contact_phone if include_store and store else None,
        store_contact_email=store.contact_email if include_store and store else None,
        store_contact_telegram=store.contact_telegram if include_store and store else None,
        store_address=store.address if include_store and store else None,
        store_logo_url=store.logo_url if include_store and store else None,
        seller_user_id=store.seller_user_id if store else None,
        seller_user_type=store.seller_user_type if store else None,
        seller_display_name=_display_name(db, store.seller_user_id, store.seller_user_type) if store else None,
        created_at=published_at,
        renewed_at=listing.renewed_at,
        can_renew=can_renew,
        next_renew_at=next_renew_at,
        store_status=store.status if include_store and store else None,
        **viewer_fields,
    )


def _listings_to_responses(
    db: Session,
    listings: List[MarketListing],
    viewer: Optional[Tuple[int, str]] = None,
) -> List[MarketListingResponse]:
    """Build a page of listing responses, computing ratings/sold/favorites in batch."""
    ids = [l.id for l in listings]
    ratings = _ratings_for_listings(db, ids)
    solds = _sold_counts_for_listings(db, ids)
    favs = _favorited_ids(db, viewer, ids)
    pending_counts = None
    buyer_orders = None
    if viewer:
        uid, utype = viewer
        buyer_orders = _active_buyer_orders(db, ids, uid, utype)
        if listings and all(
            l.store
            and l.store.seller_user_id == uid
            and l.store.seller_user_type == utype
            for l in listings
        ):
            pending_counts = _pending_interest_counts(db, ids)
    return [
        _listing_to_response(
            db,
            l,
            rating=ratings.get(l.id, (0.0, 0)),
            sold_count=solds.get(l.id, 0),
            is_favorited=l.id in favs,
            viewer=viewer,
            pending_counts=pending_counts,
            buyer_orders=buyer_orders,
        )
        for l in listings
    ]


def _order_to_response(db: Session, order: MarketOrder) -> MarketOrderResponse:
    listing = order.listing
    image_url = listing.images[0].image_url if listing and listing.images else None
    return MarketOrderResponse(
        id=order.id,
        listing_id=order.listing_id,
        store_id=order.store_id,
        listing_title=listing.title if listing else None,
        listing_image_url=image_url,
        buyer_user_id=order.buyer_user_id,
        buyer_user_type=order.buyer_user_type,
        seller_user_id=order.seller_user_id,
        seller_user_type=order.seller_user_type,
        buyer_display_name=_display_name(db, order.buyer_user_id, order.buyer_user_type),
        seller_display_name=_display_name(db, order.seller_user_id, order.seller_user_type),
        quantity=order.quantity,
        buyer_note=order.buyer_note,
        seller_note=order.seller_note,
        status=order.status,
        price=listing.price if listing else None,
        currency=listing.currency if listing else None,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.get("/categories", response_model=List[MarketCategoryResponse])
def list_categories(db: Session = Depends(get_db)):
    _ensure_categories(db)
    cats = (
        db.query(MarketCategory)
        .order_by(MarketCategory.sort_order, MarketCategory.name_en)
        .all()
    )
    return [_category_to_response(db, c) for c in cats]


@router.get("/stores", response_model=MarketPaginatedStores)
def browse_stores(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_market_user(current_user)
    q = db.query(MarketStore).filter(MarketStore.status == "active")
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                MarketStore.name.ilike(term),
                MarketStore.tagline.ilike(term),
                MarketStore.description.ilike(term),
                MarketStore.address.ilike(term),
            )
        )
    total = q.count()
    stores = q.order_by(desc(MarketStore.created_at)).offset(skip).limit(limit).all()
    items = [
        _store_to_response(
            db,
            s,
            listing_count=_store_listing_count(db, s.id, active_only=True),
        )
        for s in stores
    ]
    return MarketPaginatedStores(total=total, items=items)


@router.get("/stores/me", response_model=MarketStoreResponse)
def get_my_store(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    if _is_seller_banned(db, uid, utype):
        raise HTTPException(status_code=403, detail="You are banned from the marketplace")
    store = _get_or_create_store(db, uid, utype)
    return _store_to_response(
        db,
        store,
        include_suggestions=True,
        include_daily_quota=True,
    )


@router.put("/stores/me", response_model=MarketStoreResponse)
def update_my_store(
    payload: MarketStoreUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    if _is_seller_banned(db, uid, utype):
        raise HTTPException(status_code=403, detail="You are banned from the marketplace")
    store = _get_or_create_store(db, uid, utype)
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="Your store is suspended")
    if payload.name is not None:
        new_name = payload.name.strip()[:150]
        current_name = (store.name or "").strip()
        if new_name != current_name:
            allowed, next_at = _store_name_change_status(store)
            if not allowed:
                raise HTTPException(
                    status_code=400,
                    detail="Store name can only be changed once every 3 months",
                )
            store.name = new_name
            store.name_changed_at = datetime.now(timezone.utc)
    if payload.tagline is not None:
        store.tagline = payload.tagline.strip()[:200] or None
    if payload.description is not None:
        store.description = payload.description.strip() or None
    if payload.contact_email is not None:
        store.contact_email = payload.contact_email.strip()[:120] or None
    if payload.contact_phone is not None:
        store.contact_phone = payload.contact_phone.strip()[:50] or None
    if payload.contact_telegram is not None:
        store.contact_telegram = payload.contact_telegram.strip()[:100] or None
    if payload.address is not None:
        store.address = payload.address.strip()[:255] or None
    db.commit()
    db.refresh(store)
    return _store_to_response(
        db, store, include_suggestions=True, include_daily_quota=True
    )


@router.post("/stores/me/logo", response_model=MarketStoreResponse)
async def upload_store_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    if _is_seller_banned(db, uid, utype):
        raise HTTPException(status_code=403, detail="You are banned from the marketplace")
    store = _get_or_create_store(db, uid, utype)
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="Your store is suspended")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    filename = f"{uuid.uuid4().hex}{ext}"
    if store.logo_url:
        StorageService.delete_file(store.logo_url)
    url = StorageService.upload_file(data, "market/stores", filename, content_type)
    if not url:
        raise HTTPException(status_code=500, detail="Upload failed")
    store.logo_url = url
    db.commit()
    db.refresh(store)
    return _store_to_response(
        db, store, include_suggestions=True, include_daily_quota=True
    )


@router.post("/stores/me/cover", response_model=MarketStoreResponse)
async def upload_store_cover(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    if _is_seller_banned(db, uid, utype):
        raise HTTPException(status_code=403, detail="You are banned from the marketplace")
    store = _get_or_create_store(db, uid, utype)
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="Your store is suspended")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    filename = f"{uuid.uuid4().hex}{ext}"
    if store.cover_url:
        StorageService.delete_file(store.cover_url)
    url = StorageService.upload_file(data, "market/stores", filename, content_type)
    if not url:
        raise HTTPException(status_code=500, detail="Upload failed")
    store.cover_url = url
    db.commit()
    db.refresh(store)
    return _store_to_response(
        db, store, include_suggestions=True, include_daily_quota=True
    )


@router.delete("/stores/me/logo", response_model=MarketStoreResponse)
def delete_store_logo(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    store = _get_or_create_store(db, uid, utype)
    if store.logo_url:
        StorageService.delete_file(store.logo_url)
        store.logo_url = None
        db.commit()
        db.refresh(store)
    return _store_to_response(
        db, store, include_suggestions=True, include_daily_quota=True
    )


@router.delete("/stores/me/cover", response_model=MarketStoreResponse)
def delete_store_cover(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    store = _get_or_create_store(db, uid, utype)
    if store.cover_url:
        StorageService.delete_file(store.cover_url)
        store.cover_url = None
        db.commit()
        db.refresh(store)
    return _store_to_response(
        db, store, include_suggestions=True, include_daily_quota=True
    )


@router.get("/stores/{store_id}", response_model=MarketStoreResponse)
def get_public_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_market_user(current_user)
    store = db.query(MarketStore).filter(MarketStore.id == store_id).first()
    if not store or store.status != "active":
        raise HTTPException(status_code=404, detail="Store not found")
    return _store_to_response(
        db,
        store,
        listing_count=_store_listing_count(db, store.id, active_only=True),
    )


@router.get("/stores/{store_id}/listings", response_model=MarketPaginatedListings)
def get_store_listings(
    store_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    viewer = _require_market_user(current_user)
    store = db.query(MarketStore).filter(MarketStore.id == store_id).first()
    if not store or store.status != "active":
        raise HTTPException(status_code=404, detail="Store not found")
    q = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.store_id == store_id, MarketListing.status == "active")
    )
    total = q.count()
    listings = (
        q.order_by(desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return MarketPaginatedListings(
        total=total,
        items=_listings_to_responses(db, listings, viewer),
    )


@router.get("/feed-stamp")
def market_feed_stamp(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Lightweight revision stamp for new-listing polling on clients."""
    _require_market_user(current_user)
    row = (
        db.query(
            func.count(MarketListing.id),
            func.max(MarketListing.id),
        )
        .join(MarketStore, MarketListing.store_id == MarketStore.id)
        .filter(MarketListing.status == "active", MarketStore.status == "active")
        .one()
    )
    return {"total": int(row[0] or 0), "latest_id": int(row[1] or 0)}


@router.get("/listings", response_model=MarketPaginatedListings)
def browse_listings(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    condition: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "newest",
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    viewer = _require_market_user(current_user)
    q = (
        db.query(MarketListing)
        .join(MarketStore, MarketListing.store_id == MarketStore.id)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.status == "active", MarketStore.status == "active")
    )
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(or_(MarketListing.title.ilike(term), MarketListing.description.ilike(term)))
    if category_id:
        q = q.filter(MarketListing.category_id == category_id)
    cond = _norm_condition(condition)
    if cond:
        q = q.filter(MarketListing.condition == cond)
    if min_price is not None:
        q = q.filter(MarketListing.price >= min_price)
    if max_price is not None:
        q = q.filter(MarketListing.price <= max_price)
    if sort == "price_asc":
        q = q.order_by(MarketListing.price.asc())
    elif sort == "price_desc":
        q = q.order_by(MarketListing.price.desc())
    elif sort == "popular":
        q = q.order_by(
            desc(MarketListing.view_count),
            desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)),
        )
    elif sort == "rating":
        rating_sq = (
            db.query(
                MarketReview.listing_id.label("lid"),
                func.avg(MarketReview.rating).label("avg_r"),
            )
            .group_by(MarketReview.listing_id)
            .subquery()
        )
        q = q.outerjoin(rating_sq, rating_sq.c.lid == MarketListing.id).order_by(
            desc(func.coalesce(rating_sq.c.avg_r, 0)),
            desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)),
        )
    else:
        q = q.order_by(
            desc(MarketListing.is_featured),
            desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)),
        )
    total = q.count()
    listings = q.offset(skip).limit(limit).all()
    return MarketPaginatedListings(
        total=total,
        items=_listings_to_responses(db, listings, viewer),
    )


@router.get("/listings/featured", response_model=MarketPaginatedListings)
def featured_listings(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    viewer = _require_market_user(current_user)
    now = datetime.now(timezone.utc)
    q = (
        db.query(MarketListing)
        .join(MarketStore, MarketListing.store_id == MarketStore.id)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(
            MarketListing.status == "active",
            MarketStore.status == "active",
            MarketListing.is_featured == True,  # noqa: E712
            or_(MarketListing.featured_until.is_(None), MarketListing.featured_until > now),
        )
        .order_by(desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)))
        .limit(limit)
    )
    listings = q.all()
    return MarketPaginatedListings(
        total=len(listings),
        items=_listings_to_responses(db, listings, viewer),
    )


@router.get("/listings/mine", response_model=MarketPaginatedListings)
def my_listings(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    store = _get_or_create_store(db, uid, utype)
    q = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.store_id == store.id, MarketListing.status != "deleted")
    )
    total = q.count()
    listings = (
        q.order_by(desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return MarketPaginatedListings(
        total=total,
        items=_listings_to_responses(db, listings, (uid, utype)),
    )


@router.get("/listings/{listing_id}", response_model=MarketListingResponse)
def get_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    viewer = _require_market_user(current_user)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.id == listing_id)
        .first()
    )
    if not listing or listing.status in ("deleted", "hidden"):
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.store.status != "active" and listing.status != "active":
        raise HTTPException(status_code=404, detail="Listing not found")
    listing.view_count = (listing.view_count or 0) + 1
    db.commit()
    is_fav = listing.id in _favorited_ids(db, viewer, [listing.id])
    return _listing_to_response(db, listing, is_favorited=is_fav, viewer=viewer)


@router.post("/listings", response_model=MarketListingResponse, status_code=status.HTTP_201_CREATED)
def create_listing(
    payload: MarketListingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    if _is_seller_banned(db, uid, utype):
        raise HTTPException(status_code=403, detail="You are banned from the marketplace")
    store = _get_or_create_store(db, uid, utype)
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="Your store is suspended")
    posted, limit, remaining = _store_daily_listing_quota(db, store.id)
    if posted >= limit:
        raise HTTPException(
            status_code=400,
            detail=f"Daily listing limit reached ({limit} items per day). Try again tomorrow.",
        )
    if payload.category_id:
        cat = db.query(MarketCategory).filter(MarketCategory.id == payload.category_id).first()
        if not cat:
            raise HTTPException(status_code=400, detail="Invalid category")
    _validate_listing_prices(payload.price, payload.compare_at_price)
    requested_status = payload.status if payload.status in ("active", "hidden") else "active"
    if payload.send_push_notification and requested_status != "active":
        raise HTTPException(
            status_code=400,
            detail="Only published listings can notify the community",
        )
    if payload.send_push_notification:
        # Lock before the listing insert so simultaneous publishes cannot both
        # pass the per-store daily broadcast limit.
        db.query(MarketStore.id).filter(
            MarketStore.id == store.id,
        ).with_for_update().one()
    listing = MarketListing(
        store_id=store.id,
        category_id=payload.category_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        price=payload.price,
        compare_at_price=payload.compare_at_price,
        currency=(payload.currency or "USD").upper()[:10],
        status=requested_status,
        stock_qty=payload.stock_qty,
        condition=_norm_condition(payload.condition),
    )
    db.add(listing)
    db.flush()
    db.refresh(listing)
    if payload.send_push_notification:
        _reserve_listing_broadcast(db, store, listing)
    db.commit()
    db.refresh(listing)
    if listing.status == "active":
        _notify_market_feed_updated()
    if payload.send_push_notification:
        background_tasks.add_task(notify_listing_broadcast, listing.id)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.id == listing.id)
        .first()
    )
    return _listing_to_response(db, listing)


@router.put("/listings/{listing_id}", response_model=MarketListingResponse)
def update_listing(
    listing_id: int,
    payload: MarketListingUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = _owned_listing(db, listing_id, uid, utype, for_update=True)
    prev_status = listing.status
    if payload.title is not None:
        listing.title = payload.title.strip()
    if payload.description is not None:
        listing.description = payload.description.strip() or None
    if payload.price is not None:
        listing.price = payload.price
    updates = payload.model_dump(exclude_unset=True)
    if "compare_at_price" in updates:
        listing.compare_at_price = updates["compare_at_price"]
    if payload.currency is not None:
        listing.currency = payload.currency.upper()[:10]
    if payload.category_id is not None:
        listing.category_id = payload.category_id
    if payload.stock_qty is not None:
        listing.stock_qty = payload.stock_qty
    if payload.condition is not None:
        listing.condition = _norm_condition(payload.condition)
    if payload.status is not None and payload.status in ("active", "sold", "hidden"):
        listing.status = payload.status
    became_active = listing.status == "active" and prev_status != "active"
    if payload.send_push_notification and not became_active:
        raise HTTPException(
            status_code=400,
            detail="Notifications are available when publishing a draft or renewing an older listing",
        )
    if became_active:
        listing.renewed_at = datetime.now(timezone.utc)
    _validate_listing_prices(listing.price or Decimal("0"), listing.compare_at_price)
    db.flush()
    if payload.send_push_notification:
        _reserve_listing_broadcast(db, listing.store, listing)
    db.commit()
    db.refresh(listing)
    if became_active:
        _notify_market_feed_updated()
    if payload.send_push_notification:
        background_tasks.add_task(notify_listing_broadcast, listing.id)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.id == listing.id)
        .first()
    )
    return _listing_to_response(db, listing)


@router.post("/listings/{listing_id}/renew", response_model=MarketListingResponse)
def renew_listing(
    listing_id: int,
    payload: MarketListingRenewRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = _owned_listing(db, listing_id, uid, utype, for_update=True)
    if listing.status != "active":
        raise HTTPException(status_code=400, detail="Only active listings can be renewed")

    can_renew, next_at = listing_renewal_status(
        listing.created_at,
        listing.renewed_at,
    )
    if not can_renew:
        detail = "Listing can only be renewed once every 3 days"
        if next_at is not None:
            detail = f"Listing can be renewed after {next_at.isoformat()}"
        raise HTTPException(status_code=400, detail=detail)

    listing.renewed_at = datetime.now(timezone.utc)
    db.flush()
    if payload.send_push_notification:
        _reserve_listing_broadcast(db, listing.store, listing)
    db.commit()
    db.refresh(listing)
    _notify_market_feed_updated()
    if payload.send_push_notification:
        background_tasks.add_task(notify_listing_broadcast, listing.id)

    listing = (
        db.query(MarketListing)
        .options(
            joinedload(MarketListing.images),
            joinedload(MarketListing.category),
            joinedload(MarketListing.store),
        )
        .filter(MarketListing.id == listing.id)
        .first()
    )
    return _listing_to_response(db, listing)


def _owned_listing(
    db: Session,
    listing_id: int,
    uid: int,
    utype: str,
    *,
    for_update: bool = False,
) -> MarketListing:
    query = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.store), joinedload(MarketListing.images))
        .filter(MarketListing.id == listing_id)
    )
    if for_update:
        query = query.with_for_update()
    listing = query.first()
    if not listing or listing.status == "deleted":
        raise HTTPException(status_code=404, detail="Listing not found")
    store = listing.store
    if store.seller_user_id != uid or store.seller_user_type != utype:
        raise HTTPException(status_code=403, detail="Not your listing")
    return listing


@router.delete("/listings/{listing_id}")
def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = _owned_listing(db, listing_id, uid, utype)
    listing.status = "deleted"
    db.commit()
    return {"success": True}


@router.post("/listings/{listing_id}/images", response_model=MarketListingImageResponse)
async def upload_listing_image(
    listing_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = _owned_listing(db, listing_id, uid, utype)
    count = db.query(MarketListingImage).filter(MarketListingImage.listing_id == listing_id).count()
    if count >= MAX_LISTING_IMAGES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_LISTING_IMAGES} images per listing")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    filename = f"{uuid.uuid4().hex}{ext}"
    url = StorageService.upload_file(data, "market/listings", filename, content_type)
    if not url:
        raise HTTPException(status_code=500, detail="Upload failed")
    img = MarketListingImage(
        listing_id=listing_id,
        image_url=url,
        sort_order=count,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return MarketListingImageResponse(id=img.id, image_url=img.image_url, sort_order=img.sort_order)


@router.delete("/listings/{listing_id}/images/{image_id}")
def delete_listing_image(
    listing_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    _owned_listing(db, listing_id, uid, utype)
    img = (
        db.query(MarketListingImage)
        .filter(MarketListingImage.id == image_id, MarketListingImage.listing_id == listing_id)
        .first()
    )
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    StorageService.delete_file(img.image_url)
    db.delete(img)
    db.commit()
    return {"success": True}


@router.put("/listings/{listing_id}/images/order")
def reorder_listing_images(
    listing_id: int,
    payload: MarketListingImageReorder,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    _owned_listing(db, listing_id, uid, utype)
    images = (
        db.query(MarketListingImage)
        .filter(MarketListingImage.listing_id == listing_id)
        .all()
    )
    by_id = {img.id: img for img in images}
    if set(payload.image_ids) != set(by_id.keys()):
        raise HTTPException(status_code=400, detail="image_ids must match listing images")
    for order, image_id in enumerate(payload.image_ids):
        by_id[image_id].sort_order = order
    db.commit()
    return {"success": True}


@router.post("/orders", response_model=MarketOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: MarketOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    buyer_id, buyer_type = _require_market_user(current_user)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.store))
        .filter(MarketListing.id == payload.listing_id)
        .first()
    )
    if not listing or listing.status != "active":
        raise HTTPException(status_code=404, detail="Listing not available")
    store = listing.store
    if store.status != "active":
        raise HTTPException(status_code=400, detail="Store is not active")
    if store.seller_user_id == buyer_id and store.seller_user_type == buyer_type:
        raise HTTPException(status_code=400, detail="Cannot order your own listing")
    if listing.stock_qty is not None and payload.quantity > listing.stock_qty:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    existing = (
        db.query(MarketOrder)
        .filter(
            MarketOrder.listing_id == listing.id,
            MarketOrder.buyer_user_id == buyer_id,
            MarketOrder.buyer_user_type == buyer_type,
            MarketOrder.status.in_(ACTIVE_BUYER_ORDER_STATUSES),
        )
        .order_by(desc(MarketOrder.created_at))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have an active request for this item. Continue the conversation with the seller.",
        )
    order = MarketOrder(
        listing_id=listing.id,
        store_id=store.id,
        buyer_user_id=buyer_id,
        buyer_user_type=buyer_type,
        seller_user_id=store.seller_user_id,
        seller_user_type=store.seller_user_type,
        quantity=payload.quantity,
        buyer_note=(payload.buyer_note or "").strip() or None,
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    notify_new_order(
        db,
        seller_user_id=store.seller_user_id,
        seller_user_type=store.seller_user_type,
        buyer_user_id=buyer_id,
        buyer_user_type=buyer_type,
        order_id=order.id,
        listing_id=listing.id,
        listing_title=listing.title,
        quantity=payload.quantity,
    )
    order = (
        db.query(MarketOrder)
        .options(joinedload(MarketOrder.listing).joinedload(MarketListing.images))
        .filter(MarketOrder.id == order.id)
        .first()
    )
    return _order_to_response(db, order)


@router.get("/orders/buying", response_model=MarketPaginatedOrders)
def orders_buying(
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    buyer_id, buyer_type = _require_market_user(current_user)
    q = (
        db.query(MarketOrder)
        .options(joinedload(MarketOrder.listing).joinedload(MarketListing.images))
        .filter(MarketOrder.buyer_user_id == buyer_id, MarketOrder.buyer_user_type == buyer_type)
    )
    if status_filter:
        q = q.filter(MarketOrder.status == status_filter)
    total = q.count()
    orders = q.order_by(desc(MarketOrder.created_at)).offset(skip).limit(limit).all()
    return MarketPaginatedOrders(total=total, items=[_order_to_response(db, o) for o in orders])


@router.get("/orders/selling", response_model=MarketPaginatedOrders)
def orders_selling(
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    seller_id, seller_type = _require_market_user(current_user)
    q = (
        db.query(MarketOrder)
        .options(joinedload(MarketOrder.listing).joinedload(MarketListing.images))
        .filter(MarketOrder.seller_user_id == seller_id, MarketOrder.seller_user_type == seller_type)
    )
    if status_filter:
        q = q.filter(MarketOrder.status == status_filter)
    total = q.count()
    orders = q.order_by(desc(MarketOrder.created_at)).offset(skip).limit(limit).all()
    return MarketPaginatedOrders(total=total, items=[_order_to_response(db, o) for o in orders])


@router.get("/listings/{listing_id}/interests", response_model=MarketPaginatedOrders)
def listing_interests(
    listing_id: int,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.store))
        .filter(MarketListing.id == listing_id, MarketListing.status != "deleted")
        .first()
    )
    if not listing or not listing.store:
        raise HTTPException(status_code=404, detail="Listing not found")
    store = listing.store
    if store.seller_user_id != uid or store.seller_user_type != utype:
        raise HTTPException(status_code=403, detail="Only the listing seller can view interests")
    q = (
        db.query(MarketOrder)
        .options(joinedload(MarketOrder.listing).joinedload(MarketListing.images))
        .filter(MarketOrder.listing_id == listing_id)
    )
    if status_filter:
        q = q.filter(MarketOrder.status == status_filter)
    total = q.count()
    orders = q.order_by(desc(MarketOrder.created_at)).offset(skip).limit(limit).all()
    return MarketPaginatedOrders(total=total, items=[_order_to_response(db, o) for o in orders])


@router.get("/orders/pending-counts")
def orders_pending_counts(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    buyer_id, buyer_type = _require_market_user(current_user)
    seller_id, seller_type = buyer_id, buyer_type
    buying = (
        db.query(func.count(MarketOrder.id))
        .filter(
            MarketOrder.buyer_user_id == buyer_id,
            MarketOrder.buyer_user_type == buyer_type,
            MarketOrder.status == "pending",
        )
        .scalar()
        or 0
    )
    selling = (
        db.query(func.count(MarketOrder.id))
        .filter(
            MarketOrder.seller_user_id == seller_id,
            MarketOrder.seller_user_type == seller_type,
            MarketOrder.status == "pending",
        )
        .scalar()
        or 0
    )
    return {"buying": int(buying), "selling": int(selling)}


@router.get("/orders/{order_id}/conversation", response_model=MarketConversationResponse)
def order_conversation(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    order = _get_order_for_user(db, order_id, uid, utype)
    buyer = (order.buyer_user_id, order.buyer_user_type)
    seller = (order.seller_user_id, order.seller_user_type)
    if (uid, utype) == buyer:
        other = seller
        other_name = _display_name(db, other[0], other[1])
        group = _get_or_create_direct_group(db, buyer, seller, title_hint=other_name)
    else:
        other = buyer
        other_name = _display_name(db, other[0], other[1])
        group = _get_or_create_direct_group(db, seller, buyer, title_hint=other_name)
    _ensure_market_group_tag(db, group)
    return MarketConversationResponse(
        group_id=group.id,
        conversation_name=other_name,
        order_id=order.id,
    )


def _get_order_for_user(db: Session, order_id: int, uid: int, utype: str) -> MarketOrder:
    order = (
        db.query(MarketOrder)
        .options(joinedload(MarketOrder.listing).joinedload(MarketListing.images))
        .filter(MarketOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    is_buyer = order.buyer_user_id == uid and order.buyer_user_type == utype
    is_seller = order.seller_user_id == uid and order.seller_user_type == utype
    if not is_buyer and not is_seller:
        raise HTTPException(status_code=403, detail="Not your order")
    return order


@router.patch("/orders/{order_id}/accept", response_model=MarketOrderResponse)
def accept_order(
    order_id: int,
    payload: MarketOrderStatusUpdate = MarketOrderStatusUpdate(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    order = _get_order_for_user(db, order_id, uid, utype)
    if order.seller_user_id != uid or order.seller_user_type != utype:
        raise HTTPException(status_code=403, detail="Only seller can accept")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Order is not pending")
    order.status = "accepted"
    if payload.seller_note:
        order.seller_note = payload.seller_note.strip()
    listing = order.listing
    if listing and listing.stock_qty is not None:
        listing.stock_qty = max(0, listing.stock_qty - order.quantity)
        if listing.stock_qty == 0:
            listing.status = "sold"
    db.commit()
    _sync_order_request_messages(db, order)
    notify_order_status_change(
        db,
        buyer_user_id=order.buyer_user_id,
        buyer_user_type=order.buyer_user_type,
        order_id=order.id,
        listing_id=order.listing_id,
        listing_title=listing.title if listing else "item",
        status="accepted",
    )
    db.refresh(order)
    return _order_to_response(db, order)


@router.patch("/orders/{order_id}/reject", response_model=MarketOrderResponse)
def reject_order(
    order_id: int,
    payload: MarketOrderStatusUpdate = MarketOrderStatusUpdate(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    order = _get_order_for_user(db, order_id, uid, utype)
    if order.seller_user_id != uid or order.seller_user_type != utype:
        raise HTTPException(status_code=403, detail="Only seller can reject")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Order is not pending")
    order.status = "rejected"
    if payload.seller_note:
        order.seller_note = payload.seller_note.strip()
    db.commit()
    _sync_order_request_messages(db, order)
    listing = order.listing
    notify_order_status_change(
        db,
        buyer_user_id=order.buyer_user_id,
        buyer_user_type=order.buyer_user_type,
        order_id=order.id,
        listing_id=order.listing_id,
        listing_title=listing.title if listing else "item",
        status="rejected",
    )
    db.refresh(order)
    return _order_to_response(db, order)


@router.patch("/orders/{order_id}/cancel", response_model=MarketOrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    order = _get_order_for_user(db, order_id, uid, utype)
    if order.buyer_user_id != uid or order.buyer_user_type != utype:
        raise HTTPException(status_code=403, detail="Only buyer can cancel")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending orders can be cancelled")
    order.status = "cancelled"
    db.commit()
    _sync_order_request_messages(db, order)
    db.refresh(order)
    return _order_to_response(db, order)


@router.patch("/orders/{order_id}/complete", response_model=MarketOrderResponse)
def complete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    order = _get_order_for_user(db, order_id, uid, utype)
    if order.seller_user_id != uid or order.seller_user_type != utype:
        raise HTTPException(status_code=403, detail="Only seller can complete")
    if order.status != "accepted":
        raise HTTPException(status_code=400, detail="Order must be accepted first")
    order.status = "completed"
    db.commit()
    _sync_order_request_messages(db, order)
    listing = order.listing
    notify_order_status_change(
        db,
        buyer_user_id=order.buyer_user_id,
        buyer_user_type=order.buyer_user_type,
        order_id=order.id,
        listing_id=order.listing_id,
        listing_title=listing.title if listing else "item",
        status="completed",
    )
    db.refresh(order)
    return _order_to_response(db, order)


# ── Admin moderation ─────────────────────────────────────────────────────────

@router.get("/welcome-settings", response_model=MarketWelcomeSettingsResponse)
def get_welcome_settings(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Return the effective welcome-tour policy for marketplace users."""
    _require_market_user(current_user)
    settings = db.query(MarketSettings).filter(MarketSettings.id == 1).first()
    return _welcome_settings_response(settings)


@router.get(
    "/admin/welcome-settings",
    response_model=MarketWelcomeSettingsResponse,
)
def admin_get_welcome_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    settings = db.query(MarketSettings).filter(MarketSettings.id == 1).first()
    return _welcome_settings_response(settings)


@router.put(
    "/admin/welcome-settings",
    response_model=MarketWelcomeSettingsResponse,
)
def admin_update_welcome_settings(
    payload: MarketWelcomeSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    settings = db.query(MarketSettings).filter(MarketSettings.id == 1).first()
    if settings is None:
        settings = MarketSettings(id=1)
        db.add(settings)

    if payload.welcome_enabled is not None:
        settings.welcome_enabled = payload.welcome_enabled
    if payload.welcome_skip_seconds is not None:
        settings.welcome_skip_seconds = payload.welcome_skip_seconds
    if payload.reshow_to_everyone:
        settings.welcome_version = max(1, int(settings.welcome_version or 1)) + 1

    db.commit()
    db.refresh(settings)
    return _welcome_settings_response(settings)


@router.get("/admin/listings", response_model=MarketPaginatedListings)
def admin_list_listings(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    q = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.status != "deleted")
    )
    if status and status != "all":
        q = q.filter(MarketListing.status == status)
    total = q.count()
    listings = (
        q.order_by(desc(func.coalesce(MarketListing.renewed_at, MarketListing.created_at)))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return MarketPaginatedListings(
        total=total,
        items=_listings_to_responses(db, listings),
    )


@router.patch("/admin/listings/{listing_id}/hide")
def admin_hide_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    listing = db.query(MarketListing).filter(MarketListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    listing.status = "hidden"
    db.commit()
    return {"success": True}


@router.patch("/admin/listings/{listing_id}/restore")
def admin_restore_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    listing = db.query(MarketListing).filter(MarketListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.status == "deleted":
        raise HTTPException(status_code=400, detail="Deleted listings cannot be restored")
    listing.status = "active"
    db.commit()
    _notify_market_feed_updated()
    return {"success": True}


@router.get("/admin/stores", response_model=MarketPaginatedStores)
def admin_list_stores(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    q = db.query(MarketStore)
    if status and status != "all":
        q = q.filter(MarketStore.status == status)
    total = q.count()
    stores = q.order_by(desc(MarketStore.updated_at), desc(MarketStore.created_at)).offset(skip).limit(limit).all()
    return MarketPaginatedStores(
        total=total,
        items=[_store_to_response(db, s) for s in stores],
    )


@router.patch("/admin/stores/{store_id}/suspend")
def admin_suspend_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    store = db.query(MarketStore).filter(MarketStore.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    store.status = "suspended"
    db.commit()
    return {"success": True}


@router.patch("/admin/stores/{store_id}/restore")
def admin_restore_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    store = db.query(MarketStore).filter(MarketStore.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    store.status = "active"
    db.commit()
    return {"success": True}


@router.get("/admin/sellers/bans", response_model=MarketPaginatedSellerBans)
def admin_list_seller_bans(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    q = db.query(MarketSellerBan)
    total = q.count()
    bans = q.order_by(desc(MarketSellerBan.created_at)).offset(skip).limit(limit).all()
    items = [
        MarketSellerBanResponse(
            id=b.id,
            user_id=b.user_id,
            user_type=b.user_type,
            reason=b.reason,
            banned_until=b.banned_until,
            created_at=b.created_at,
            seller_display_name=_display_name(db, b.user_id, b.user_type),
        )
        for b in bans
    ]
    return MarketPaginatedSellerBans(total=total, items=items)


@router.post("/admin/sellers/ban")
def admin_ban_seller(
    payload: MarketSellerBanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    ban = MarketSellerBan(
        user_id=payload.user_id,
        user_type=payload.user_type,
        reason=payload.reason,
        banned_until=payload.banned_until,
    )
    db.add(ban)
    db.commit()
    return {"success": True, "id": ban.id}


@router.delete("/admin/sellers/bans/{ban_id}")
def admin_remove_seller_ban(
    ban_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    ban = db.query(MarketSellerBan).filter(MarketSellerBan.id == ban_id).first()
    if not ban:
        raise HTTPException(status_code=404, detail="Ban not found")
    db.delete(ban)
    db.commit()
    return {"success": True}


@router.get("/admin/categories", response_model=List[MarketCategoryResponse])
def admin_list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    _ensure_categories(db)
    cats = (
        db.query(MarketCategory)
        .order_by(MarketCategory.sort_order, MarketCategory.name_en)
        .all()
    )
    return [_category_to_response(db, c) for c in cats]


@router.post("/admin/categories", response_model=MarketCategoryResponse)
def admin_create_category(
    payload: MarketCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    name_en = payload.name_en.strip()
    name_km = payload.name_km.strip()
    if db.query(MarketCategory).filter(MarketCategory.name_en == name_en).first():
        raise HTTPException(status_code=400, detail="English name already exists")
    cat = MarketCategory(
        name=name_en,
        name_en=name_en,
        name_km=name_km,
        icon_key=(payload.icon_key or "other").strip().lower() or "other",
        sort_order=payload.sort_order,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return _category_to_response(db, cat)


@router.put("/admin/categories/{category_id}", response_model=MarketCategoryResponse)
def admin_update_category(
    category_id: int,
    payload: MarketCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    cat = db.query(MarketCategory).filter(MarketCategory.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if payload.name_en is not None:
        name_en = payload.name_en.strip()
        exists = (
            db.query(MarketCategory)
            .filter(MarketCategory.name_en == name_en, MarketCategory.id != category_id)
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="English name already exists")
        cat.name_en = name_en
        cat.name = name_en
    if payload.name_km is not None:
        cat.name_km = payload.name_km.strip()
    if payload.icon_key is not None:
        cat.icon_key = payload.icon_key.strip().lower() or "other"
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    db.commit()
    db.refresh(cat)
    return _category_to_response(db, cat)


@router.delete("/admin/categories/{category_id}")
def admin_delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_app_admin(db, current_user)
    cat = db.query(MarketCategory).filter(MarketCategory.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    in_use = _category_listing_count(db, category_id)
    if in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Category is used by {in_use} listing(s) and cannot be deleted",
        )
    db.delete(cat)
    db.commit()
    return {"success": True}


# ── Wishlist / favorites ──────────────────────────────────────────────────────

@router.post("/listings/{listing_id}/favorite")
def favorite_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = db.query(MarketListing).filter(MarketListing.id == listing_id).first()
    if not listing or listing.status == "deleted":
        raise HTTPException(status_code=404, detail="Listing not found")
    exists = (
        db.query(MarketWishlist)
        .filter(
            MarketWishlist.user_id == uid,
            MarketWishlist.user_type == utype,
            MarketWishlist.listing_id == listing_id,
        )
        .first()
    )
    if not exists:
        db.add(MarketWishlist(user_id=uid, user_type=utype, listing_id=listing_id))
        db.commit()
    return {"success": True, "favorited": True}


@router.delete("/listings/{listing_id}/favorite")
def unfavorite_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    db.query(MarketWishlist).filter(
        MarketWishlist.user_id == uid,
        MarketWishlist.user_type == utype,
        MarketWishlist.listing_id == listing_id,
    ).delete()
    db.commit()
    return {"success": True, "favorited": False}


@router.get("/wishlist", response_model=MarketPaginatedListings)
def get_wishlist(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    q = (
        db.query(MarketListing)
        .join(MarketWishlist, MarketWishlist.listing_id == MarketListing.id)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(
            MarketWishlist.user_id == uid,
            MarketWishlist.user_type == utype,
            MarketListing.status != "deleted",
        )
        .order_by(desc(MarketWishlist.created_at))
    )
    total = q.count()
    listings = q.offset(skip).limit(limit).all()
    # Everything here is favorited by definition.
    ids = [l.id for l in listings]
    ratings = _ratings_for_listings(db, ids)
    solds = _sold_counts_for_listings(db, ids)
    items = [
        _listing_to_response(
            db, l,
            rating=ratings.get(l.id, (0.0, 0)),
            sold_count=solds.get(l.id, 0),
            is_favorited=True,
        )
        for l in listings
    ]
    return MarketPaginatedListings(total=total, items=items)


# ── Reviews & ratings ─────────────────────────────────────────────────────────

def _review_to_response(db: Session, review: MarketReview) -> MarketReviewResponse:
    return MarketReviewResponse(
        id=review.id,
        listing_id=review.listing_id,
        store_id=review.store_id,
        rating=review.rating,
        comment=review.comment,
        reviewer_display_name=_display_name(db, review.reviewer_user_id, review.reviewer_user_type),
        is_verified=bool(review.order_id),
        created_at=review.created_at,
    )


@router.get("/listings/{listing_id}/reviews", response_model=MarketPaginatedReviews)
def list_listing_reviews(
    listing_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_market_user(current_user)
    q = db.query(MarketReview).filter(MarketReview.listing_id == listing_id)
    total = q.count()
    avg, cnt = (
        db.query(func.avg(MarketReview.rating), func.count(MarketReview.id))
        .filter(MarketReview.listing_id == listing_id)
        .first()
    )
    items = q.order_by(desc(MarketReview.created_at)).offset(skip).limit(limit).all()
    return MarketPaginatedReviews(
        total=total,
        rating_avg=round(float(avg or 0), 2),
        rating_count=int(cnt or 0),
        items=[_review_to_response(db, r) for r in items],
    )


@router.get("/stores/{store_id}/reviews", response_model=MarketPaginatedReviews)
def list_store_reviews(
    store_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_market_user(current_user)
    q = db.query(MarketReview).filter(MarketReview.store_id == store_id)
    total = q.count()
    s_avg, s_cnt = _store_rating(db, store_id)
    items = q.order_by(desc(MarketReview.created_at)).offset(skip).limit(limit).all()
    return MarketPaginatedReviews(
        total=total,
        rating_avg=round(s_avg, 2),
        rating_count=s_cnt,
        items=[_review_to_response(db, r) for r in items],
    )


@router.post("/listings/{listing_id}/reviews", response_model=MarketReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    listing_id: int,
    payload: MarketReviewCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.store))
        .filter(MarketListing.id == listing_id)
        .first()
    )
    if not listing or listing.status == "deleted":
        raise HTTPException(status_code=404, detail="Listing not found")
    store = listing.store
    if store and store.seller_user_id == uid and store.seller_user_type == utype:
        raise HTTPException(status_code=400, detail="You cannot review your own listing")
    completed = (
        db.query(MarketOrder)
        .filter(
            MarketOrder.listing_id == listing_id,
            MarketOrder.buyer_user_id == uid,
            MarketOrder.buyer_user_type == utype,
            MarketOrder.status == "completed",
        )
        .first()
    )
    review = (
        db.query(MarketReview)
        .filter(
            MarketReview.listing_id == listing_id,
            MarketReview.reviewer_user_id == uid,
            MarketReview.reviewer_user_type == utype,
        )
        .first()
    )
    comment = (payload.comment or "").strip() or None
    if review:
        review.rating = payload.rating
        review.comment = comment
        if completed and not review.order_id:
            review.order_id = completed.id
    else:
        review = MarketReview(
            listing_id=listing_id,
            store_id=store.id if store else listing.store_id,
            reviewer_user_id=uid,
            reviewer_user_type=utype,
            rating=payload.rating,
            comment=comment,
            order_id=completed.id if completed else None,
        )
        db.add(review)
    db.commit()
    db.refresh(review)
    if store:
        try:
            notify_new_review(
                db,
                recipient_user_id=store.seller_user_id,
                recipient_user_type=store.seller_user_type,
                reviewer_user_id=uid,
                reviewer_user_type=utype,
                listing_id=listing_id,
                listing_title=listing.title,
                rating=payload.rating,
            )
        except Exception:
            logger.exception("Failed to send review notification")
    return _review_to_response(db, review)


# ── Listing lifecycle: mark sold / feature ────────────────────────────────────

def _reload_listing(db: Session, listing_id: int) -> MarketListing:
    return (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images), joinedload(MarketListing.category), joinedload(MarketListing.store))
        .filter(MarketListing.id == listing_id)
        .first()
    )


@router.patch("/listings/{listing_id}/mark-sold", response_model=MarketListingResponse)
def mark_listing_sold(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = _owned_listing(db, listing_id, uid, utype)
    listing.status = "sold"
    db.commit()
    return _listing_to_response(db, _reload_listing(db, listing_id))


@router.patch("/listings/{listing_id}/feature", response_model=MarketListingResponse)
def feature_listing(
    listing_id: int,
    featured: bool = True,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    listing = _owned_listing(db, listing_id, uid, utype)
    listing.is_featured = bool(featured)
    listing.featured_until = (
        datetime.now(timezone.utc) + timedelta(days=max(1, days)) if featured else None
    )
    db.commit()
    return _listing_to_response(db, _reload_listing(db, listing_id))


# ── Seller analytics ──────────────────────────────────────────────────────────

@router.get("/stores/me/stats", response_model=MarketStoreStats)
def my_store_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    store = _get_or_create_store(db, uid, utype)

    def _count(*conds) -> int:
        return db.query(func.count(MarketListing.id)).filter(
            MarketListing.store_id == store.id, *conds
        ).scalar() or 0

    listing_count = _count(MarketListing.status != "deleted")
    active_count = _count(MarketListing.status == "active")
    total_views = (
        db.query(func.coalesce(func.sum(MarketListing.view_count), 0))
        .filter(MarketListing.store_id == store.id, MarketListing.status != "deleted")
        .scalar()
        or 0
    )
    order_rows = (
        db.query(MarketOrder.status, func.count(MarketOrder.id))
        .filter(MarketOrder.store_id == store.id)
        .group_by(MarketOrder.status)
        .all()
    )
    omap = {s: c for s, c in order_rows}
    sold_units = (
        db.query(func.coalesce(func.sum(MarketOrder.quantity), 0))
        .filter(MarketOrder.store_id == store.id, MarketOrder.status == "completed")
        .scalar()
        or 0
    )
    est_revenue = (
        db.query(func.coalesce(func.sum(MarketOrder.quantity * MarketListing.price), 0))
        .join(MarketListing, MarketOrder.listing_id == MarketListing.id)
        .filter(MarketOrder.store_id == store.id, MarketOrder.status == "completed")
        .scalar()
        or Decimal("0")
    )
    s_avg, s_cnt = _store_rating(db, store.id)
    posted_today, limit_today, remaining_today = _store_daily_listing_quota(db, store.id)
    tops = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.images))
        .filter(MarketListing.store_id == store.id, MarketListing.status != "deleted")
        .order_by(desc(MarketListing.view_count))
        .limit(5)
        .all()
    )
    sold_map = _sold_counts_for_listings(db, [t.id for t in tops])
    top_listings = [
        MarketTopListing(
            id=t.id,
            title=t.title,
            view_count=t.view_count or 0,
            sold_count=sold_map.get(t.id, 0),
            image_url=t.images[0].image_url if t.images else None,
        )
        for t in tops
    ]
    return MarketStoreStats(
        listing_count=listing_count,
        active_count=active_count,
        sold_count=int(sold_units),
        total_views=int(total_views),
        orders_pending=int(omap.get("pending", 0)),
        orders_accepted=int(omap.get("accepted", 0)),
        orders_completed=int(omap.get("completed", 0)),
        est_revenue=est_revenue,
        rating_avg=round(s_avg, 2),
        rating_count=s_cnt,
        top_listings=top_listings,
        listings_posted_today=posted_today,
        daily_listing_limit=limit_today,
        listings_remaining_today=remaining_today,
    )


# ── In-app chat (direct buyer ↔ seller conversation) ──────────────────────────

MARKET_CONVERSATION_TAG = "market:buyer-seller"


def _other_group_member(
    db: Session, group_id: int, uid: int, utype_e: UserType
) -> Optional[MessageGroupMember]:
    return (
        db.query(MessageGroupMember)
        .filter(
            MessageGroupMember.group_id == group_id,
            or_(
                MessageGroupMember.user_id != uid,
                MessageGroupMember.user_type != utype_e,
            ),
        )
        .first()
    )


def _pair_has_market_order(
    db: Session,
    a_id: int,
    a_type: str,
    b_id: int,
    b_type: str,
) -> bool:
    return (
        db.query(MarketOrder.id)
        .filter(
            or_(
                (
                    (MarketOrder.buyer_user_id == a_id)
                    & (MarketOrder.buyer_user_type == a_type)
                    & (MarketOrder.seller_user_id == b_id)
                    & (MarketOrder.seller_user_type == b_type)
                ),
                (
                    (MarketOrder.buyer_user_id == b_id)
                    & (MarketOrder.buyer_user_type == b_type)
                    & (MarketOrder.seller_user_id == a_id)
                    & (MarketOrder.seller_user_type == a_type)
                ),
            )
        )
        .first()
        is not None
    )


def _is_market_conversation(
    db: Session,
    grp: MessageGroup,
    uid: int,
    utype: str,
    utype_e: UserType,
) -> bool:
    if grp.description == MARKET_CONVERSATION_TAG:
        return True
    other = _other_group_member(db, grp.id, uid, utype_e)
    if not other:
        return False
    other_type = (
        "parent" if other.user_type == UserType.PARENT else "teacher"
    )
    return _pair_has_market_order(
        db, uid, utype, other.user_id, other_type
    )


def _market_role_label(
    db: Session, uid: int, utype: str, other_id: int, other_type: str
) -> str:
    store = (
        db.query(MarketStore)
        .filter(
            MarketStore.seller_user_id == other_id,
            MarketStore.seller_user_type == other_type,
        )
        .first()
    )
    if store:
        return "Seller"
    my_store = (
        db.query(MarketStore)
        .filter(
            MarketStore.seller_user_id == uid,
            MarketStore.seller_user_type == utype,
        )
        .first()
    )
    if my_store:
        return "Buyer"
    return "Market chat"


def _unread_count_for_group(db: Session, group_id: int, viewer_id: int) -> int:
    user_pattern = f'%{viewer_id}%'
    return (
        db.query(func.count(GroupMessage.id))
        .filter(
            GroupMessage.group_id == group_id,
            GroupMessage.sender_id != viewer_id,
            GroupMessage.deleted_at.is_(None),
            or_(
                GroupMessage.read_by.is_(None),
                GroupMessage.read_by == "[]",
                ~GroupMessage.read_by.like(user_pattern),
            ),
        )
        .scalar()
        or 0
    )


def _ensure_market_group_tag(db: Session, grp: MessageGroup) -> None:
    if grp.description != MARKET_CONVERSATION_TAG:
        grp.description = MARKET_CONVERSATION_TAG
        db.add(grp)
        db.commit()


def _member_user_type(utype: str) -> UserType:
    return UserType.PARENT if utype == "parent" else UserType.TEACHER


def _get_or_create_direct_group(
    db: Session,
    a: Tuple[int, str],
    b: Tuple[int, str],
    title_hint: Optional[str] = None,
) -> MessageGroup:
    """Find (or create) a 2-member CUSTOM message group between users a and b."""
    a_id, a_type = a
    b_id, b_type = b
    a_type_e = _member_user_type(a_type)
    b_type_e = _member_user_type(b_type)

    a_group_ids = {
        r[0]
        for r in db.query(MessageGroupMember.group_id)
        .filter(MessageGroupMember.user_id == a_id, MessageGroupMember.user_type == a_type_e)
        .all()
    }
    if a_group_ids:
        shared = (
            db.query(MessageGroupMember.group_id)
            .filter(
                MessageGroupMember.user_id == b_id,
                MessageGroupMember.user_type == b_type_e,
                MessageGroupMember.group_id.in_(a_group_ids),
            )
            .all()
        )
        for (gid,) in shared:
            grp = (
                db.query(MessageGroup)
                .filter(MessageGroup.id == gid, MessageGroup.type == GroupType.CUSTOM)
                .first()
            )
            if not grp:
                continue
            member_count = (
                db.query(func.count(MessageGroupMember.id))
                .filter(MessageGroupMember.group_id == gid)
                .scalar()
                or 0
            )
            if member_count == 2:
                return grp

    grp = MessageGroup(
        name=(title_hint or "Direct chat")[:255],
        type=GroupType.CUSTOM,
        created_by=a_id,
    )
    db.add(grp)
    db.commit()
    db.refresh(grp)
    db.add(MessageGroupMember(group_id=grp.id, user_id=a_id, user_type=a_type_e, role=MemberRole.ADMIN))
    db.add(MessageGroupMember(group_id=grp.id, user_id=b_id, user_type=b_type_e, role=MemberRole.ADMIN))
    db.commit()
    return grp


@router.get("/conversations", response_model=List[MarketConversationListItem])
def list_conversations(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    uid, utype = _require_market_user(current_user)
    utype_e = _member_user_type(utype)

    memberships = (
        db.query(MessageGroupMember.group_id)
        .filter(
            MessageGroupMember.user_id == uid,
            MessageGroupMember.user_type == utype_e,
        )
        .all()
    )
    group_ids = [gid for (gid,) in memberships]
    if not group_ids:
        return []

    items: List[MarketConversationListItem] = []
    for gid in group_ids:
        grp = (
            db.query(MessageGroup)
            .filter(
                MessageGroup.id == gid,
                MessageGroup.type == GroupType.CUSTOM,
            )
            .first()
        )
        if not grp:
            continue
        member_count = (
            db.query(func.count(MessageGroupMember.id))
            .filter(MessageGroupMember.group_id == gid)
            .scalar()
            or 0
        )
        if member_count != 2:
            continue
        if not _is_market_conversation(db, grp, uid, utype, utype_e):
            continue
        if grp.description != MARKET_CONVERSATION_TAG:
            _ensure_market_group_tag(db, grp)

        other = _other_group_member(db, gid, uid, utype_e)
        other_type = (
            "parent"
            if other and other.user_type == UserType.PARENT
            else "teacher"
        )
        other_id = other.user_id if other else 0
        name = grp.name or "Chat"
        if other:
            name = _display_name(db, other_id, other_type)

        last = (
            db.query(GroupMessage)
            .filter(
                GroupMessage.group_id == gid,
                GroupMessage.deleted_at.is_(None),
            )
            .order_by(desc(GroupMessage.created_at))
            .first()
        )
        last_time = None
        if last and last.created_at:
            last_time = last.created_at.isoformat()

        items.append(
            MarketConversationListItem(
                group_id=gid,
                conversation_name=name,
                role_label=_market_role_label(
                    db, uid, utype, other_id, other_type
                )
                if other
                else None,
                last_message=last.content if last else None,
                last_message_time=last_time,
                unread_count=_unread_count_for_group(db, gid, uid),
            )
        )

    items.sort(
        key=lambda x: x.last_message_time or "",
        reverse=True,
    )
    return items


@router.get("/conversations/{group_id}/orders", response_model=MarketPaginatedOrders)
def conversation_orders(
    group_id: int,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Orders between the two members of a market buyer↔seller chat."""
    uid, utype = _require_market_user(current_user)
    utype_e = _member_user_type(utype)

    membership = (
        db.query(MessageGroupMember)
        .filter(
            MessageGroupMember.group_id == group_id,
            MessageGroupMember.user_id == uid,
            MessageGroupMember.user_type == utype_e,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this chat")

    grp = (
        db.query(MessageGroup)
        .filter(MessageGroup.id == group_id, MessageGroup.type == GroupType.CUSTOM)
        .first()
    )
    if not grp:
        raise HTTPException(status_code=404, detail="Conversation not found")

    other = _other_group_member(db, group_id, uid, utype_e)
    if not other:
        return MarketPaginatedOrders(total=0, items=[])

    other_type = "parent" if other.user_type == UserType.PARENT else "teacher"
    q = (
        db.query(MarketOrder)
        .options(joinedload(MarketOrder.listing).joinedload(MarketListing.images))
        .filter(
            or_(
                (
                    (MarketOrder.buyer_user_id == uid)
                    & (MarketOrder.buyer_user_type == utype)
                    & (MarketOrder.seller_user_id == other.user_id)
                    & (MarketOrder.seller_user_type == other_type)
                ),
                (
                    (MarketOrder.buyer_user_id == other.user_id)
                    & (MarketOrder.buyer_user_type == other_type)
                    & (MarketOrder.seller_user_id == uid)
                    & (MarketOrder.seller_user_type == utype)
                ),
            )
        )
    )
    if active_only:
        q = q.filter(MarketOrder.status.in_(ACTIVE_BUYER_ORDER_STATUSES))
    orders = q.order_by(desc(MarketOrder.created_at)).limit(50).all()
    return MarketPaginatedOrders(
        total=len(orders),
        items=[_order_to_response(db, o) for o in orders],
    )


def _order_status_chat_label(status: str) -> str:
    return {
        "accepted": "accepted",
        "completed": "completed",
        "rejected": "declined",
        "cancelled": "cancelled",
    }.get(status, "pending")


def _find_direct_group_for_pair(
    db: Session,
    a: Tuple[int, str],
    b: Tuple[int, str],
) -> Optional[MessageGroup]:
    a_id, a_type = a
    b_id, b_type = b
    a_type_e = _member_user_type(a_type)
    b_type_e = _member_user_type(b_type)

    a_group_ids = {
        r[0]
        for r in db.query(MessageGroupMember.group_id)
        .filter(MessageGroupMember.user_id == a_id, MessageGroupMember.user_type == a_type_e)
        .all()
    }
    if not a_group_ids:
        return None
    shared = (
        db.query(MessageGroupMember.group_id)
        .filter(
            MessageGroupMember.user_id == b_id,
            MessageGroupMember.user_type == b_type_e,
            MessageGroupMember.group_id.in_(a_group_ids),
        )
        .all()
    )
    for (gid,) in shared:
        grp = (
            db.query(MessageGroup)
            .filter(MessageGroup.id == gid, MessageGroup.type == GroupType.CUSTOM)
            .first()
        )
        if not grp:
            continue
        member_count = (
            db.query(func.count(MessageGroupMember.id))
            .filter(MessageGroupMember.group_id == gid)
            .scalar()
            or 0
        )
        if member_count == 2:
            return grp
    return None


def _sync_order_request_messages(db: Session, order: MarketOrder) -> None:
    """Update frozen '(pending)' lines in chat when order status changes."""
    buyer = (order.buyer_user_id, order.buyer_user_type)
    seller = (order.seller_user_id, order.seller_user_type)
    group = _find_direct_group_for_pair(db, buyer, seller)
    if not group:
        return
    label = _order_status_chat_label(order.status)
    prefix = f"Order request #{order.id} ("
    messages = (
        db.query(GroupMessage)
        .filter(
            GroupMessage.group_id == group.id,
            GroupMessage.content.like(f"%Order request #{order.id} (%"),
            GroupMessage.deleted_at.is_(None),
        )
        .all()
    )
    changed = False
    for msg in messages:
        lines = (msg.content or "").split("\n")
        new_lines: List[str] = []
        line_changed = False
        for line in lines:
            if line.startswith(prefix):
                new_lines.append(f"Order request #{order.id} ({label})")
                line_changed = True
            else:
                new_lines.append(line)
        if line_changed:
            msg.content = "\n".join(new_lines)
            changed = True
    if changed:
        setattr(group, "updated_at", datetime.utcnow())
        db.commit()


def _read_by_json_for_new_message(sender_id: int) -> str:
    return json.dumps([int(sender_id)])


def _format_interest_message(
    listing: MarketListing,
    quantity: int,
    note: Optional[str],
    order_id: Optional[int],
    order_status: str = "pending",
) -> str:
    lines = [
        f"Interested in: {listing.title}",
        f"Listing #{listing.id} · {listing.currency} {listing.price} × {quantity}",
    ]
    trimmed = (note or "").strip()
    if trimmed:
        lines.append(f"Note: {trimmed}")
    if order_id is not None:
        lines.append(
            f"Order request #{order_id} ({_order_status_chat_label(order_status)})"
        )
    return "\n".join(lines)


@router.post("/conversations", response_model=MarketConversationResponse)
def start_conversation(
    payload: MarketConversationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    buyer_id, buyer_type = _require_market_user(current_user)
    listing = (
        db.query(MarketListing)
        .options(joinedload(MarketListing.store))
        .filter(MarketListing.id == payload.listing_id)
        .first()
    )
    if not listing or listing.status == "deleted":
        raise HTTPException(status_code=404, detail="Listing not found")
    store = listing.store
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    seller = (store.seller_user_id, store.seller_user_type)
    if seller == (buyer_id, buyer_type):
        raise HTTPException(status_code=400, detail="You cannot chat with yourself")

    if payload.create_order:
        if listing.status != "active":
            raise HTTPException(status_code=404, detail="Listing not available")
        if store.status != "active":
            raise HTTPException(status_code=400, detail="Store is not active")
        if _is_seller_banned(db, store.seller_user_id, store.seller_user_type):
            raise HTTPException(status_code=400, detail="Seller is not available")
        if listing.stock_qty is not None and payload.quantity > listing.stock_qty:
            raise HTTPException(status_code=400, detail="Insufficient stock")

    other_name = store.name or _display_name(db, store.seller_user_id, store.seller_user_type)
    group = _get_or_create_direct_group(db, (buyer_id, buyer_type), seller, title_hint=other_name)
    _ensure_market_group_tag(db, group)

    order_id: Optional[int] = None
    created_new_order = False
    if payload.create_order:
        existing = (
            db.query(MarketOrder)
            .filter(
                MarketOrder.listing_id == listing.id,
                MarketOrder.buyer_user_id == buyer_id,
                MarketOrder.buyer_user_type == buyer_type,
                MarketOrder.status.in_(ACTIVE_BUYER_ORDER_STATUSES),
            )
            .order_by(desc(MarketOrder.created_at))
            .first()
        )
        if existing:
            order_id = existing.id
        else:
            order = MarketOrder(
                listing_id=listing.id,
                store_id=store.id,
                buyer_user_id=buyer_id,
                buyer_user_type=buyer_type,
                seller_user_id=store.seller_user_id,
                seller_user_type=store.seller_user_type,
                quantity=payload.quantity,
                buyer_note=(payload.message or "").strip() or None,
                status="pending",
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            order_id = order.id
            created_new_order = True

    note = (payload.message or "").strip() or None
    if created_new_order or (not payload.create_order and note):
        order_status = "pending"
        if order_id is not None and not created_new_order:
            existing_order = db.query(MarketOrder).filter(MarketOrder.id == order_id).first()
            if existing_order:
                order_status = existing_order.status
        content = (
            _format_interest_message(
                listing, payload.quantity, note, order_id, order_status=order_status
            )
            if payload.create_order
            else note
        )
        new_message = GroupMessage(
            group_id=group.id,
            sender_id=buyer_id,
            content=content,
            message_type="text",
            read_by=_read_by_json_for_new_message(buyer_id),
            is_hidden=0,
        )
        db.add(new_message)
        setattr(group, "updated_at", datetime.utcnow())
        db.commit()
        db.refresh(new_message)
        if created_new_order and order_id is not None:
            notify_new_interest(
                db,
                seller_user_id=store.seller_user_id,
                seller_user_type=store.seller_user_type,
                buyer_user_id=buyer_id,
                buyer_user_type=buyer_type,
                order_id=order_id,
                listing_id=listing.id,
                listing_title=listing.title,
                quantity=payload.quantity,
                group_id=group.id,
                message_id=new_message.id,
                group_name=other_name,
            )

    return MarketConversationResponse(
        group_id=group.id,
        conversation_name=other_name,
        order_id=order_id,
    )
