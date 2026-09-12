from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PartnerBase(BaseModel):
    name: str
    short_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None

    logo_url: Optional[str] = None
    icon_name: Optional[str] = None
    image_urls: Optional[List[str]] = []

    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    branch_id: Optional[int] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


    is_active: Optional[bool] = True


class PartnerCreate(BaseModel):
    name: str
    short_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None

    logo_url: Optional[str] = None
    icon_name: Optional[str] = None
    image_urls: Optional[List[str]] = []

    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    branch_id: Optional[int] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None

    logo_url: Optional[str] = None
    icon_name: Optional[str] = None
    image_urls: Optional[List[str]] = None

    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    branch_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class PartnerResponse(BaseModel):
    id: int
    name: str
    short_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None

    logo_url: Optional[str] = None
    icon_name: Optional[str] = None
    image_urls: List[str] = []

    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    branch_id: Optional[int] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True

    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


