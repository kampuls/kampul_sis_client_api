"""
User Social Link model.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class UserSocialLink(Base):
    """Model for storing multiple social media links for a user resource."""
    
    __tablename__ = "users_social_links"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_resource_id = Column(Integer, ForeignKey("users_resource.id", ondelete="CASCADE"), nullable=False)
    
    platform_name = Column(String(50), nullable=False) # e.g. Facebook, LinkedIn, Telegram, Website
    link = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationship back to UserResource (optional, but good for ORM)
    # user_resource = relationship("UserResource", back_populates="social_links")

    def __repr__(self):
        return f"<UserSocialLink(id={self.id}, platform='{self.platform_name}')>"
