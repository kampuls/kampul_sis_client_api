from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class MarketCategory(Base):
    __tablename__ = "market_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    name_en = Column(String(100), nullable=False, default="")
    name_km = Column(String(100), nullable=False, default="")
    icon_key = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MarketSettings(Base):
    """Singleton marketplace experience settings controlled by App Admins."""

    __tablename__ = "market_settings"

    id = Column(Integer, primary_key=True, default=1)
    welcome_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    welcome_skip_seconds = Column(
        Integer,
        nullable=False,
        default=30,
        server_default="30",
    )
    welcome_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class MarketStore(Base):
    __tablename__ = "market_stores"
    __table_args__ = (
        UniqueConstraint(
            "seller_user_id",
            "seller_user_type",
            name="uq_market_store_seller",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    seller_user_id = Column(Integer, nullable=False, index=True)
    seller_user_type = Column(String(20), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    tagline = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    contact_email = Column(String(120), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_telegram = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    cover_url = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    name_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    listings = relationship(
        "MarketListing",
        back_populates="store",
        cascade="all, delete-orphan",
    )


class MarketListing(Base):
    __tablename__ = "market_listings"
    __table_args__ = (
        Index("ix_market_listings_status_created", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(
        Integer,
        ForeignKey("market_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id = Column(
        Integer,
        ForeignKey("market_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(12, 2), nullable=False, default=0)
    compare_at_price = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=False, default="USD")
    status = Column(String(20), nullable=False, default="active", index=True)
    stock_qty = Column(Integer, nullable=True)
    view_count = Column(Integer, nullable=False, default=0)
    # new | like_new | used  (nullable — older listings have no condition)
    condition = Column(String(20), nullable=True)
    # Nullable so the auto-migrate can ALTER ADD COLUMN on the existing,
    # already-populated table (it omits defaults, so a NOT NULL add would fail).
    # Reads coerce NULL → False; the Python-side default fills new rows.
    is_featured = Column(Boolean, nullable=True, default=False, server_default="0")
    featured_until = Column(DateTime(timezone=True), nullable=True)
    renewed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    store = relationship("MarketStore", back_populates="listings")
    category = relationship("MarketCategory")
    images = relationship(
        "MarketListingImage",
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="MarketListingImage.sort_order",
    )
    orders = relationship("MarketOrder", back_populates="listing")
    reviews = relationship(
        "MarketReview",
        back_populates="listing",
        cascade="all, delete-orphan",
    )


class MarketListingBroadcast(Base):
    """One seller-requested community push for a listing publication cycle."""

    __tablename__ = "market_listing_broadcasts"
    __table_args__ = (
        Index("ix_market_broadcast_store_created", "store_id", "created_at"),
        Index("ix_market_broadcast_listing_created", "listing_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(
        Integer,
        ForeignKey("market_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_id = Column(
        Integer,
        ForeignKey("market_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publication_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MarketListingImage(Base):
    __tablename__ = "market_listing_images"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(
        Integer,
        ForeignKey("market_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url = Column(String(500), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    listing = relationship("MarketListing", back_populates="images")


class MarketOrder(Base):
    __tablename__ = "market_orders"
    __table_args__ = (
        Index("ix_market_orders_buyer", "buyer_user_id", "buyer_user_type"),
        Index("ix_market_orders_seller", "seller_user_id", "seller_user_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(
        Integer,
        ForeignKey("market_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    store_id = Column(
        Integer,
        ForeignKey("market_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_user_id = Column(Integer, nullable=False)
    buyer_user_type = Column(String(20), nullable=False)
    seller_user_id = Column(Integer, nullable=False)
    seller_user_type = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    buyer_note = Column(Text, nullable=True)
    seller_note = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    listing = relationship("MarketListing", back_populates="orders")
    store = relationship("MarketStore")


class MarketSellerBan(Base):
    __tablename__ = "market_seller_bans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_type = Column(String(20), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    banned_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MarketWishlist(Base):
    """A buyer's saved/favorited listing."""

    __tablename__ = "market_wishlists"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "user_type",
            "listing_id",
            name="uq_market_wishlist_once",
        ),
        Index("ix_market_wishlists_user", "user_id", "user_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    user_type = Column(String(20), nullable=False)
    listing_id = Column(
        Integer,
        ForeignKey("market_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MarketReview(Base):
    """A buyer's star rating + comment on a listing (and its store)."""

    __tablename__ = "market_reviews"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "reviewer_user_id",
            "reviewer_user_type",
            name="uq_market_review_once",
        ),
        Index("ix_market_reviews_listing", "listing_id"),
        Index("ix_market_reviews_store", "store_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(
        Integer,
        ForeignKey("market_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    store_id = Column(
        Integer,
        ForeignKey("market_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_user_id = Column(Integer, nullable=False)
    reviewer_user_type = Column(String(20), nullable=False)
    rating = Column(Integer, nullable=False)  # 1..5
    comment = Column(Text, nullable=True)
    # Set when the reviewer has a completed order for the listing → "verified purchase".
    order_id = Column(
        Integer,
        ForeignKey("market_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    listing = relationship("MarketListing", back_populates="reviews")
