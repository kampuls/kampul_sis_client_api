from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class MarketWelcomeSettingsResponse(BaseModel):
    welcome_enabled: bool = True
    welcome_skip_seconds: int = 30
    welcome_version: int = 1


class MarketWelcomeSettingsUpdate(BaseModel):
    welcome_enabled: Optional[bool] = None
    welcome_skip_seconds: Optional[int] = Field(None, ge=0, le=60)
    reshow_to_everyone: bool = False


class MarketCategoryResponse(BaseModel):
    id: int
    name: str
    name_en: str
    name_km: str
    icon_key: Optional[str] = None
    sort_order: int = 0
    listing_count: int = 0

    class Config:
        from_attributes = True


class MarketCategoryCreate(BaseModel):
    name_en: str = Field(..., min_length=1, max_length=100)
    name_km: str = Field(..., min_length=1, max_length=100)
    icon_key: Optional[str] = Field(None, max_length=50)
    sort_order: int = 0


class MarketCategoryUpdate(BaseModel):
    name_en: Optional[str] = Field(None, min_length=1, max_length=100)
    name_km: Optional[str] = Field(None, min_length=1, max_length=100)
    icon_key: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None


class MarketStoreUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    tagline: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    contact_email: Optional[str] = Field(None, max_length=120)
    contact_phone: Optional[str] = Field(None, max_length=50)
    contact_telegram: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=255)


class MarketStoreResponse(BaseModel):
    id: int
    seller_user_id: int
    seller_user_type: str
    name: str
    tagline: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_telegram: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    status: str
    seller_display_name: Optional[str] = None
    listing_count: int = 0
    rating_avg: float = 0.0
    rating_count: int = 0
    created_at: Optional[datetime] = None
    suggested_email: Optional[str] = None
    suggested_phone: Optional[str] = None
    name_change_allowed: bool = True
    name_next_change_at: Optional[datetime] = None
    listings_posted_today: Optional[int] = None
    daily_listing_limit: Optional[int] = None
    listings_remaining_today: Optional[int] = None
    broadcasts_sent_today: Optional[int] = None
    daily_broadcast_limit: Optional[int] = None
    broadcasts_remaining_today: Optional[int] = None

    class Config:
        from_attributes = True


class MarketListingImageResponse(BaseModel):
    id: int
    image_url: str
    sort_order: int = 0

    class Config:
        from_attributes = True


class MarketListingImageReorder(BaseModel):
    image_ids: List[int] = Field(..., min_length=1)


class MarketListingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: Decimal = Field(..., ge=0)
    compare_at_price: Optional[Decimal] = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=10)
    category_id: Optional[int] = None
    stock_qty: Optional[int] = Field(None, ge=0)
    condition: Optional[str] = Field(None, max_length=20)  # new | like_new | used
    status: Optional[str] = Field(default="active", max_length=20)
    send_push_notification: bool = False


class MarketListingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    compare_at_price: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    category_id: Optional[int] = None
    stock_qty: Optional[int] = Field(None, ge=0)
    condition: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = None
    send_push_notification: bool = False


class MarketListingRenewRequest(BaseModel):
    send_push_notification: bool = False


class MarketListingResponse(BaseModel):
    id: int
    store_id: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    price: Decimal
    compare_at_price: Optional[Decimal] = None
    currency: str
    status: str
    stock_qty: Optional[int] = None
    view_count: int = 0
    condition: Optional[str] = None
    is_featured: bool = False
    rating_avg: float = 0.0
    rating_count: int = 0
    sold_count: int = 0
    is_favorited: bool = False
    images: List[MarketListingImageResponse] = []
    store_name: Optional[str] = None
    store_contact_phone: Optional[str] = None
    store_contact_email: Optional[str] = None
    store_contact_telegram: Optional[str] = None
    store_address: Optional[str] = None
    store_logo_url: Optional[str] = None
    seller_user_id: Optional[int] = None
    seller_user_type: Optional[str] = None
    seller_display_name: Optional[str] = None
    created_at: Optional[datetime] = None
    renewed_at: Optional[datetime] = None
    can_renew: bool = False
    next_renew_at: Optional[datetime] = None
    is_own_listing: bool = False
    pending_interest_count: int = 0
    viewer_order_id: Optional[int] = None
    viewer_order_status: Optional[str] = None
    store_status: Optional[str] = None

    class Config:
        from_attributes = True


class MarketOrderCreate(BaseModel):
    listing_id: int
    quantity: int = Field(default=1, ge=1)
    buyer_note: Optional[str] = Field(None, max_length=500)


class MarketOrderStatusUpdate(BaseModel):
    seller_note: Optional[str] = Field(None, max_length=500)


class MarketOrderResponse(BaseModel):
    id: int
    listing_id: int
    store_id: int
    listing_title: Optional[str] = None
    listing_image_url: Optional[str] = None
    buyer_user_id: int
    buyer_user_type: str
    seller_user_id: int
    seller_user_type: str
    buyer_display_name: Optional[str] = None
    seller_display_name: Optional[str] = None
    quantity: int
    buyer_note: Optional[str] = None
    seller_note: Optional[str] = None
    status: str
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MarketSellerBanCreate(BaseModel):
    user_id: int
    user_type: str = Field(..., pattern="^(parent|teacher)$")
    reason: Optional[str] = None
    banned_until: Optional[datetime] = None


class MarketSellerBanResponse(BaseModel):
    id: int
    user_id: int
    user_type: str
    reason: Optional[str] = None
    banned_until: Optional[datetime] = None
    created_at: Optional[datetime] = None
    seller_display_name: Optional[str] = None

    class Config:
        from_attributes = True


class MarketPaginatedSellerBans(BaseModel):
    total: int
    items: List[MarketSellerBanResponse]


class MarketPaginatedListings(BaseModel):
    total: int
    items: List[MarketListingResponse]


class MarketPaginatedStores(BaseModel):
    total: int
    items: List[MarketStoreResponse]


class MarketPaginatedOrders(BaseModel):
    total: int
    items: List[MarketOrderResponse]


# ── Reviews & ratings ─────────────────────────────────────────────────────────

class MarketReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class MarketReviewResponse(BaseModel):
    id: int
    listing_id: int
    store_id: int
    rating: int
    comment: Optional[str] = None
    reviewer_display_name: Optional[str] = None
    is_verified: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MarketPaginatedReviews(BaseModel):
    total: int
    rating_avg: float = 0.0
    rating_count: int = 0
    items: List[MarketReviewResponse]


# ── Seller analytics ──────────────────────────────────────────────────────────

class MarketTopListing(BaseModel):
    id: int
    title: str
    view_count: int = 0
    sold_count: int = 0
    image_url: Optional[str] = None


class MarketStoreStats(BaseModel):
    listing_count: int = 0
    active_count: int = 0
    sold_count: int = 0
    total_views: int = 0
    orders_pending: int = 0
    orders_accepted: int = 0
    orders_completed: int = 0
    est_revenue: Decimal = Decimal("0")
    rating_avg: float = 0.0
    rating_count: int = 0
    top_listings: List[MarketTopListing] = []
    listings_posted_today: int = 0
    daily_listing_limit: int = 10
    listings_remaining_today: int = 10


# ── In-app chat (direct conversation) ─────────────────────────────────────────

class MarketConversationCreate(BaseModel):
    listing_id: int
    quantity: int = Field(default=1, ge=1)
    message: Optional[str] = Field(None, max_length=500)
    create_order: bool = True


class MarketConversationResponse(BaseModel):
    group_id: int
    conversation_name: str
    order_id: Optional[int] = None


class MarketConversationListItem(BaseModel):
    group_id: int
    conversation_name: str
    role_label: Optional[str] = None
    last_message: Optional[str] = None
    last_message_time: Optional[str] = None
    unread_count: int = 0
