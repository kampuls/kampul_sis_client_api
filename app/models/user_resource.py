"""
User Resource model for storing user media and social information.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Enum, UniqueConstraint
from sqlalchemy.sql import func
from .base import Base

class UserResource(Base):
    """User Resource model for storing avatars, covers, and bio."""
    
    __tablename__ = "users_resource"
    __table_args__ = (
        UniqueConstraint('user_id', 'user_type', name='uq_user_resource_owner'),
    )
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Polymorphic association
    user_id = Column(Integer, nullable=False, index=True)
    user_type = Column(Enum('teacher', 'student', 'parent', 'employee'), nullable=False, index=True)
    
    # Media
    avatar = Column(String(255), nullable=True)  # Path/URL to image
    cover_image = Column(String(255), nullable=True)  # Path/URL to image
    cover_focus_y = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )  # -100..100
    
    # Social & Bio
    bio = Column(Text, nullable=True)
    status_message = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)
    
    # Status
    status = Column(Integer, nullable=False, default=1)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self):
        return f"<UserResource(id={self.id}, user_id={self.user_id}, type='{self.user_type}')>"
