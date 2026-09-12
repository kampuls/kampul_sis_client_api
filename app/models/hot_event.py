from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func
from .base import Base


class HotEvent(Base):
    """Admin-pushed hot event banner shown on app home. Supports expiry and audience."""
    __tablename__ = "hot_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    start_at = Column(DateTime(timezone=False), nullable=True)
    end_at = Column(DateTime(timezone=False), nullable=False)
    audience = Column(String(100), nullable=False, default="all")
    # Display / behaviour fields for banners & popups
    event_type = Column(String(50), nullable=False, default="banner")
    frequency = Column(String(50), nullable=False, default="always")
    interval_minutes = Column(Integer, nullable=True)
    max_impressions = Column(Integer, nullable=True)
    link_url = Column(String(500), nullable=True)
    status_text = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class HotEventImpression(Base):
    """Tracks per-user view count and last viewed time for hot events (frequency/impression limits)."""
    __tablename__ = "hot_event_impressions"

    id = Column(Integer, primary_key=True, index=True)
    hot_event_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    impression_count = Column(Integer, default=0, nullable=False)
    last_viewed_at = Column(DateTime(timezone=True), nullable=True)
