from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime, date

class AcademicProgramBase(BaseModel):
    program_name: str
    icon_name: Optional[str] = None
    custom_logo_url: Optional[str] = None
    color_start: Optional[str] = None
    color_end: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True
    description: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    facebook_url: Optional[str] = None
    telegram_url: Optional[str] = None
    youtube_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    registration_start_date: Optional[date] = None
    registration_end_date: Optional[date] = None

class AcademicProgramCreate(AcademicProgramBase):
    images: Optional[List[str]] = []

class AcademicProgramUpdate(AcademicProgramBase):
    program_name: Optional[str] = None
    images: Optional[List[str]] = None

class AcademicProgram(AcademicProgramBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    images: List[str] = []

    @field_validator("images", mode="before")
    def extract_image_urls(cls, v: Any) -> List[str]:
        if not v:
            return []
        # If it's already a list of strings, just return it
        if isinstance(v[0], str):
            return v
        # Otherwise, assume they are SQLAlchemy models and extract image_url
        return [getattr(img, "image_url", str(img)) for img in v]

    class Config:
        from_attributes = True
