from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func, ForeignKey
from .base import Base


class News(Base):
    """Simple news / announcement item shown in the app's Latest News section."""

    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)  # e.g. Academic, Campus, Community
    summary = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    cover_image_url = Column(String(500), nullable=True)
    media_type = Column(
        String(20),
        nullable=False,
        server_default="image",
        comment="Primary media type: image or video",
    )
    video_source = Column(
        String(20),
        nullable=True,
        comment="Video source: upload or youtube",
    )
    video_url = Column(String(1000), nullable=True)
    video_original_url = Column(String(1000), nullable=True)
    video_thumbnail_url = Column(String(1000), nullable=True)
    video_duration_seconds = Column(Integer, nullable=True)
    target_audience = Column(
        String(50),
        nullable=False,
        server_default="all",
        comment="Target audience: all, teachers, students, parents, admins…",
    )
    published_at = Column(DateTime(timezone=True), nullable=True)
    is_published = Column(Boolean, default=True, nullable=False)
    author_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )


class NewsImage(Base):
    """Optional gallery images for a news item."""

    __tablename__ = "news_images"

    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(
        Integer,
        ForeignKey("news.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url = Column(String(500), nullable=False)
    caption = Column(String(255), nullable=True)
    position = Column(Integer, nullable=True)  # ordering within the gallery
    created_at = Column(DateTime(timezone=True), server_default=func.now())
