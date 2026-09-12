from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
from typing import Optional

class SplashAdBase(BaseModel):
    image_url: str = Field(..., max_length=500, description="URL of the ad image")
    duration_seconds: int = Field(5, ge=1, le=30, description="Duration to show the ad in seconds")
    target_url: Optional[str] = Field(None, max_length=500, description="Optional URL to open on click")
    is_active: bool = Field(True, description="Whether this ad is currently active")
    start_date: Optional[datetime] = Field(None, description="When the ad should start showing")
    end_date: Optional[datetime] = Field(None, description="When the ad should stop showing")

class SplashAdCreate(SplashAdBase):
    pass

class SplashAdUpdate(BaseModel):
    image_url: Optional[str] = Field(None, max_length=500)
    duration_seconds: Optional[int] = Field(None, ge=1, le=30)
    target_url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class SplashAdResponse(SplashAdBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
