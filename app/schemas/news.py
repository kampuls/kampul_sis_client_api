from datetime import datetime
from typing import Optional, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NewsBase(BaseModel):
    title: str
    category: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    cover_image_url: Optional[str] = None
    media_type: Literal["image", "video"] = "image"
    video_source: Optional[Literal["upload", "youtube"]] = None
    video_url: Optional[str] = None
    video_original_url: Optional[str] = None
    video_thumbnail_url: Optional[str] = None
    video_duration_seconds: Optional[int] = Field(default=None, ge=0)
    target_audience: str = "all"
    is_published: bool = True
    published_at: Optional[datetime] = None


class NewsCreate(NewsBase):
    """Payload for creating news from admin."""

    images: Optional[List[str]] = None
    send_push_notification: bool = Field(
        default=True,
        description="When true, queue FCM to devices matching target_audience after create.",
    )

    @model_validator(mode="after")
    def validate_primary_media(self):
        if self.media_type == "video":
            if self.video_source not in {"upload", "youtube"}:
                raise ValueError("video_source is required for video news")
            if not (self.video_url or "").strip():
                raise ValueError("video_url is required for video news")
        return self


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    cover_image_url: Optional[str] = None
    media_type: Optional[Literal["image", "video"]] = None
    video_source: Optional[Literal["upload", "youtube"]] = None
    video_url: Optional[str] = None
    video_original_url: Optional[str] = None
    video_thumbnail_url: Optional[str] = None
    video_duration_seconds: Optional[int] = Field(default=None, ge=0)
    target_audience: Optional[str] = None
    is_published: Optional[bool] = None
    published_at: Optional[datetime] = None
    images: Optional[List[str]] = None
    send_push_notification: Optional[bool] = Field(
        default=None,
        description="When true, queue FCM again for this news (e.g. after edit). Omit to skip.",
    )


class NewsResponse(NewsBase):
    id: int
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    images: List[str] = []

    model_config = ConfigDict(from_attributes=True)
