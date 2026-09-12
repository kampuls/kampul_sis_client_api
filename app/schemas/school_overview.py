from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

class SchoolOverviewBase(BaseModel):
    # Legacy single-language fields (for backward compatibility)
    title: str = Field(..., max_length=255)
    content: str

    # New multilingual fields
    title_en: Optional[str] = Field(None, max_length=255)
    title_km: Optional[str] = Field(None, max_length=255)
    content_en: Optional[str] = None
    content_km: Optional[str] = None
    icon_name: Optional[str] = Field(None, max_length=100)
    color_code: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True

class SchoolOverviewCreate(SchoolOverviewBase):
    pass

class SchoolOverviewUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    title_en: Optional[str] = Field(None, max_length=255)
    title_km: Optional[str] = Field(None, max_length=255)
    content_en: Optional[str] = None
    content_km: Optional[str] = None
    icon_name: Optional[str] = Field(None, max_length=100)
    color_code: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class SchoolOverviewResponse(SchoolOverviewBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
