from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class ProfileFrame(Base):
    __tablename__ = "profile_frames"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    image_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    # Status: 'published' | 'draft' | 'scheduled' | 'disabled'
    status = Column(String(20), default='published')
    publish_at = Column(DateTime, nullable=True)   # for scheduled visibility
    expires_at = Column(DateTime, nullable=True)   # auto-expire after this date
    
    # New fields for User Uploads
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # null = admin/system created
    is_public = Column(Boolean, default=True) # public or private
    is_featured = Column(Boolean, default=False) # admin created frames are featured
    slug = Column(String(255), unique=True, index=True, nullable=True) # Custom slug for URL
    
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    
    user = relationship("User", foreign_keys=[user_id])

class ProfileFrameHistory(Base):
    __tablename__ = "profile_frame_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    frame_id = Column(Integer, ForeignKey("profile_frames.id", ondelete="SET NULL"), nullable=True)
    generated_image_url = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    frame = relationship("ProfileFrame")
