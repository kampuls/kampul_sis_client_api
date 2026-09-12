"""
Schemas for users_resource and users_social_links tables.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


# ─── Social Links ────────────────────────────────────────────
class SocialLinkBase(BaseModel):
    platform_name: str       # e.g. "telegram", "facebook", "website"
    link: str
    is_active: Optional[int] = 1


class SocialLinkResponse(SocialLinkBase):
    id: int
    user_resource_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SocialLinkUpsert(BaseModel):
    """Used in bulk upsert — include id to update, omit to create."""
    id: Optional[int] = None
    platform_name: str
    link: str
    is_active: Optional[int] = 1


# ─── User Resource ───────────────────────────────────────────
class UserResourceUpdate(BaseModel):
    """Patch request — all optional."""
    bio: Optional[str] = None
    status_message: Optional[str] = None
    website: Optional[str] = None
    cover_focus_y: Optional[int] = None


class UserResourceResponse(BaseModel):
    id: int
    user_id: int
    user_type: str
    avatar: Optional[str] = None
    cover_image: Optional[str] = None
    cover_focus_y: int = 0
    bio: Optional[str] = None
    status_message: Optional[str] = None
    website: Optional[str] = None
    status: int
    created_at: datetime
    updated_at: datetime
    social_links: List[SocialLinkResponse] = []

    model_config = ConfigDict(from_attributes=True)
