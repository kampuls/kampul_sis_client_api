from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from .base import Base

class SchoolOverview(Base):
    __tablename__ = "school_overviews"

    id = Column(Integer, primary_key=True, index=True)
    # Legacy base fields (kept for backward compatibility)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)

    # Multilingual fields
    title_en = Column(String(255), nullable=True)
    title_km = Column(String(255), nullable=True)
    content_en = Column(Text, nullable=True)
    content_km = Column(Text, nullable=True)
    
    # Optional styling fields
    icon_name = Column(String(100), nullable=True)     # e.g., 'Icons.flag' mapped on frontend
    color_code = Column(String(50), nullable=True)     # e.g., '#FF9800' or 'orange'
    
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
