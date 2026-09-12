from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from .base import Base

class SplashAd(Base):
    """Configuration for the App's Splash Screen Ad."""

    __tablename__ = "splash_ads"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String(500), nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=5)
    target_url = Column(String(500), nullable=True) # Optional URL to open when ad is clicked
    
    is_active = Column(Boolean, default=True, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
