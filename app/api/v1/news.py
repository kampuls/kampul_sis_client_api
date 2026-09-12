"""
News API: simple school news / announcements for the app home page.
"""

import asyncio
import logging
import subprocess
import tempfile
from typing import List, Dict, cast, Optional

from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Request,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import uuid, shutil
from pathlib import Path

from ...core import get_db
from ...core.config import settings
from ...auth import get_current_active_user
from ...models import News, NewsImage, User
from ...schemas import NewsCreate, NewsUpdate, NewsResponse
from .websocket import broadcast_public_data_update
from ...utils.file_utils import delete_local_file
from ...services.storage_service import StorageService
from ...services.news_video_service import (
    canonical_youtube_url,
    download_youtube_video,
    extract_youtube_video_id,
    optimize_video,
    validate_video_upload,
    youtube_thumbnail_url,
)

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/news")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _absolute_storage_url(request: Request, url: str) -> str:
    return f"{_get_base_url(request)}{url}" if url.startswith("/") else url


def _normalize_video_media(
    *,
    media_type: str,
    video_source: Optional[str],
    video_url: Optional[str],
    video_original_url: Optional[str],
    video_thumbnail_url: Optional[str],
    video_duration_seconds: Optional[int],
) -> dict:
    """Normalize client media metadata and reject unsafe/incomplete embeds."""
    if media_type == "image":
        return {
            "media_type": "image",
            "video_source": None,
            "video_url": None,
            "video_original_url": None,
            "video_thumbnail_url": None,
            "video_duration_seconds": None,
        }
    if media_type != "video" or video_source not in {"upload", "youtube"}:
        raise HTTPException(status_code=400, detail="Invalid news video source")

    clean_url = (video_url or "").strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="A video URL is required")

    clean_thumbnail = (video_thumbnail_url or "").strip() or None
    clean_original = (video_original_url or "").strip() or None
    if video_source == "youtube":
        video_id = extract_youtube_video_id(clean_url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube video URL")
        clean_url = canonical_youtube_url(video_id)
        clean_original = clean_url
        clean_thumbnail = clean_thumbnail or youtube_thumbnail_url(video_id)
        video_duration_seconds = None
    elif not (
        clean_url.startswith("/uploads/")
        or clean_url.startswith("https://")
        or clean_url.startswith("http://")
    ):
        raise HTTPException(status_code=400, detail="Invalid uploaded video URL")
    if clean_original:
        original_id = extract_youtube_video_id(clean_original)
        if not original_id:
            raise HTTPException(
                status_code=400,
                detail="Invalid original YouTube video URL",
            )
        clean_original = canonical_youtube_url(original_id)

    return {
        "media_type": "video",
        "video_source": video_source,
        "video_url": clean_url,
        "video_original_url": clean_original,
        "video_thumbnail_url": clean_thumbnail,
        "video_duration_seconds": video_duration_seconds,
    }


def _resolve_author_names(db: Session, items: list) -> Dict[int, str]:
    """Batch-resolve author_id -> display name from the User table."""
    author_ids = {cast(int, n.author_id) for n in items if n.author_id}
    if not author_ids:
        return {}
    users = db.query(User).filter(User.id.in_(author_ids)).all()
    return {
        cast(int, u.id): (cast(str, u.eName) if u.eName else cast(str, u.kName))
        for u in users
    }


def _is_admin(user: User) -> bool:
    """Very small helper to gate admin-only endpoints."""
    role_id = getattr(user, "role", None)
    if role_id is None:
        return False
    # Simple heuristic: role 1 is usually admin in this project.
    # You can refine this later if needed.
    return int(role_id) == 1


def _map_news_target_audience_to_push_audience(target_audience: Optional[str]) -> str:
    """Map news.target_audience values to get_device_tokens_by_audience() keys."""
    t = (target_audience or "all").strip().lower()
    if t == "all":
        return "all"
    if t == "teachers":
        return "teacher"
    if t == "parents":
        return "parent"
    if t == "students":
        return "student"
    if t == "admins":
        return "admin"
    if t == "staff":
        return "teacher,parent"
    return "all"


def _send_new_news_push_notifications_task(
    news_id: int,
    title: str,
    summary: Optional[str],
    content: Optional[str],
    target_audience: str,
) -> None:
    """
    Send FCM after news is created/updated or from admin notify action.
    Runs in a FastAPI BackgroundTask so the HTTP response is not blocked.
    """
    from ...core.database import SessionLocal
    from ...services.notification_service import (
        get_device_tokens_by_audience,
        send_app_rich_push_notification,
    )

    db = SessionLocal()
    try:
        audience = _map_news_target_audience_to_push_audience(target_audience)
        tokens = get_device_tokens_by_audience(db, audience)
        if not tokens:
            logger.info(
                "[News] No device tokens for audience %s (news %s)", audience, news_id
            )
            return

        body = (summary or "").strip()
        if not body and content:
            c = content.strip()
            body = c[:280] + ("…" if len(c) > 280 else "")
        if not body:
            body = "Tap to read more."

        cover_row = db.query(News).filter(News.id == news_id).first()
        cover_url = None
        if cover_row:
            cover_url = (
                getattr(cover_row, "video_thumbnail_url", None)
                or getattr(cover_row, "cover_image_url", None)
            )

        payload_data = {
            "type": "new_news",
            "news_id": str(news_id),
            "title": title,
            "body": body,
        }
        if cover_url:
            payload_data["image_url"] = str(cover_url).strip()

        chunk_size = 500
        for i in range(0, len(tokens), chunk_size):
            chunk = tokens[i : i + chunk_size]
            try:
                send_app_rich_push_notification(
                    device_tokens=chunk,
                    title=title,
                    body=body,
                    data=payload_data,
                    db=db,
                )
            except Exception as chunk_err:
                logger.warning(
                    "[News] Notification chunk %s failed for news %s: %s",
                    i // chunk_size + 1,
                    news_id,
                    chunk_err,
                )
        logger.info(
            "[News] Sent new_news push for news %s: %s devices in %s chunks (audience=%s)",
            news_id,
            len(tokens),
            ((len(tokens) - 1) // chunk_size) + 1,
            audience,
        )
    except Exception as e:
        logger.exception("[News] Background push failed for news %s: %s", news_id, e)
    finally:
        db.close()


@router.get("/public", response_model=List[NewsResponse])
async def list_public_news(
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Public endpoint used by the mobile app.
    Returns latest published news items, newest first.
    (Audience targeting is based on the news.target_audience field:
    'all', 'teachers', 'students', 'parents', etc.)
    """
    now = datetime.utcnow()
    query = (
        db.query(News)
        .filter(News.is_published == True)
        .filter((News.published_at == None) | (News.published_at <= now))
        .order_by(desc(News.published_at), desc(News.created_at))
        .limit(limit)
    )
    items = query.all()

    # Load gallery images for all returned news in a single query
    news_ids = [cast(int, n.id) for n in items]
    images_by_news: Dict[int, List[str]] = {nid: [] for nid in news_ids}
    if news_ids:
        imgs = (
            db.query(NewsImage)
            .filter(NewsImage.news_id.in_(news_ids))
            .order_by(NewsImage.position.asc(), NewsImage.id.asc())
            .all()
        )
        for img in imgs:
            nid = cast(int, img.news_id)
            url = cast(str, img.image_url)
            images_by_news.setdefault(nid, []).append(url)

    author_names = _resolve_author_names(db, items)

    responses: List[NewsResponse] = []
    for item in items:
        base = NewsResponse.model_validate(item)
        key = cast(int, item.id)
        aid = cast(int, item.author_id) if item.author_id else None
        responses.append(base.model_copy(update={
            "images": images_by_news.get(key, []),
            "author_name": author_names.get(aid) if aid else None,  # type: ignore[arg-type]
        }))

    return responses


@router.get("/public/{news_id}", response_model=NewsResponse)
async def get_public_news_item(news_id: int, db: Session = Depends(get_db)):
    """
    Single published news item for deep links / push notification tap.
    Same visibility rules as GET /public list (published, not future-dated).
    """
    now = datetime.utcnow()
    item = db.query(News).filter(News.id == news_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if not cast(bool, item.is_published):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    published_at = getattr(item, "published_at", None)
    if published_at is not None and published_at > now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    imgs = (
        db.query(NewsImage)
        .filter(NewsImage.news_id == item.id)
        .order_by(NewsImage.position.asc(), NewsImage.id.asc())
        .all()
    )
    image_urls = [cast(str, img.image_url) for img in imgs]
    author_names = _resolve_author_names(db, [item])
    aid = cast(int, item.author_id) if item.author_id else None
    base = NewsResponse.model_validate(item)
    return base.model_copy(update={
        "images": image_urls,
        "author_name": author_names.get(aid) if aid else None,  # type: ignore[arg-type]
    })


@router.get("", response_model=List[NewsResponse])
async def list_news_admin(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: list all news items."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    items = (
        db.query(News)
        .order_by(desc(News.published_at), desc(News.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    news_ids = [cast(int, n.id) for n in items]
    images_by_news: Dict[int, List[str]] = {nid: [] for nid in news_ids}
    if news_ids:
        imgs = (
            db.query(NewsImage)
            .filter(NewsImage.news_id.in_(news_ids))
            .order_by(NewsImage.position.asc(), NewsImage.id.asc())
            .all()
        )
        for img in imgs:
            nid = cast(int, img.news_id)
            url = cast(str, img.image_url)
            images_by_news.setdefault(nid, []).append(url)

    author_names = _resolve_author_names(db, items)

    responses: List[NewsResponse] = []
    for item in items:
        base = NewsResponse.model_validate(item)
        key = cast(int, item.id)
        aid = cast(int, item.author_id) if item.author_id else None
        responses.append(base.model_copy(update={
            "images": images_by_news.get(key, []),
            "author_name": author_names.get(aid) if aid else None,  # type: ignore[arg-type]
        }))

    return responses


@router.post("", response_model=NewsResponse)
async def create_news(
    body: NewsCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: create a news item."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    published_at = body.published_at or datetime.utcnow()
    if body.media_type == "video" and not settings.news_video_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="News video publishing is temporarily disabled",
        )
    media = _normalize_video_media(
        media_type=body.media_type,
        video_source=body.video_source,
        video_url=body.video_url,
        video_original_url=body.video_original_url,
        video_thumbnail_url=body.video_thumbnail_url,
        video_duration_seconds=body.video_duration_seconds,
    )
    item = News(
        title=body.title,
        category=body.category,
        summary=body.summary,
        content=body.content,
        cover_image_url=body.cover_image_url,
        **media,
        target_audience=body.target_audience or "all",
        is_published=body.is_published,
        published_at=published_at,
        author_id=getattr(current_user, "id", None),
    )
    db.add(item)
    db.flush()

    # Optional gallery images
    if body.images:
        for idx, url in enumerate(body.images):
            if not url:
                continue
            img = NewsImage(
                news_id=item.id,
                image_url=url,
                position=idx + 1,
            )
            db.add(img)

        # If no explicit cover image is set, use the first gallery image as cover
        # Use setattr/getattr to avoid static type confusion with SQLAlchemy columns.
        if not getattr(item, "cover_image_url", None):
            setattr(item, "cover_image_url", body.images[0])

    db.commit()
    db.refresh(item)

    # Load images for response
    images = (
        db.query(NewsImage)
        .filter(NewsImage.news_id == item.id)
        .order_by(NewsImage.position.asc(), NewsImage.id.asc())
        .all()
    )
    image_urls = [img.image_url for img in images]
    base = NewsResponse.model_validate(item)
    
    await broadcast_public_data_update("news")
    
    author_names = _resolve_author_names(db, [item])
    aid = getattr(item, "author_id", None)
    aname = author_names.get(aid) if aid else None

    if body.send_push_notification:
        nid = cast(int, item.id)
        background_tasks.add_task(
            _send_new_news_push_notifications_task,
            nid,
            cast(str, item.title),
            getattr(item, "summary", None),
            getattr(item, "content", None),
            cast(str, getattr(item, "target_audience", None) or "all"),
        )

    return base.model_copy(update={"images": image_urls, "author_name": aname})


@router.put("/{news_id}", response_model=NewsResponse)
async def update_news(
    news_id: int,
    body: NewsUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: update a news item."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    item = db.query(News).filter(News.id == news_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    data = body.model_dump(exclude_unset=True)
    notify_requested = data.pop("send_push_notification", None)
    images = data.pop("images", None)
    pending_file_deletes: set[str] = set()

    # Snapshot old cover image
    old_cover = getattr(item, "cover_image_url", None)
    old_video_source = getattr(item, "video_source", None)
    old_video_url = getattr(item, "video_url", None)
    old_video_thumbnail = getattr(item, "video_thumbnail_url", None)

    media_fields = {
        "media_type",
        "video_source",
        "video_url",
        "video_original_url",
        "video_thumbnail_url",
        "video_duration_seconds",
    }
    if any(field in data for field in media_fields):
        candidate_media_type = data.get(
            "media_type", getattr(item, "media_type", "image") or "image"
        )
        if candidate_media_type == "video" and not settings.news_video_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="News video publishing is temporarily disabled",
            )
        data.update(_normalize_video_media(
            media_type=candidate_media_type,
            video_source=data.get(
                "video_source", getattr(item, "video_source", None)
            ),
            video_url=data.get("video_url", getattr(item, "video_url", None)),
            video_original_url=data.get(
                "video_original_url",
                getattr(item, "video_original_url", None),
            ),
            video_thumbnail_url=data.get(
                "video_thumbnail_url",
                getattr(item, "video_thumbnail_url", None),
            ),
            video_duration_seconds=data.get(
                "video_duration_seconds",
                getattr(item, "video_duration_seconds", None),
            ),
        ))

    for field, value in data.items():
        setattr(item, field, value)

    # Replace gallery images if provided
    if images is not None:
        old_images = db.query(NewsImage).filter(NewsImage.news_id == item.id).all()
        old_urls = {img.image_url for img in old_images if img.image_url}
        new_urls = {url for url in images if url}
        
        # Delete unused images from disk
        urls_to_delete = old_urls - new_urls
        for url in urls_to_delete:
            pending_file_deletes.add(url)
            
        db.query(NewsImage).filter(NewsImage.news_id == item.id).delete()

        for idx, url in enumerate(images):
            if not url:
                continue
            img = NewsImage(
                news_id=item.id,
                image_url=url,
                position=idx + 1,
            )
            db.add(img)
        if not getattr(item, "cover_image_url", None) and images:
            setattr(item, "cover_image_url", images[0])

    # Delete old cover image if it was replaced and not reused in gallery
    new_cover = getattr(item, "cover_image_url", None)
    if old_cover and new_cover != old_cover:
        current_gallery_urls = {img.image_url for img in db.query(NewsImage).filter(NewsImage.news_id == item.id).all() if img.image_url}
        if old_cover not in current_gallery_urls:
            pending_file_deletes.add(old_cover)

    new_video_source = getattr(item, "video_source", None)
    new_video_url = getattr(item, "video_url", None)
    new_video_thumbnail = getattr(item, "video_thumbnail_url", None)
    if old_video_source == "upload" and old_video_url != new_video_url:
        if old_video_url:
            pending_file_deletes.add(old_video_url)
    if (
        old_video_source == "upload"
        and old_video_thumbnail
        and old_video_thumbnail != new_video_thumbnail
        and old_video_thumbnail != new_cover
    ):
        pending_file_deletes.add(old_video_thumbnail)

    db.commit()
    db.refresh(item)
    for stale_url in pending_file_deletes:
        delete_local_file(stale_url)

    imgs = (
        db.query(NewsImage)
        .filter(NewsImage.news_id == item.id)
        .order_by(NewsImage.position.asc(), NewsImage.id.asc())
        .all()
    )
    image_urls = [img.image_url for img in imgs]
    base = NewsResponse.model_validate(item)
    
    await broadcast_public_data_update("news")
    
    author_names = _resolve_author_names(db, [item])
    aid = getattr(item, "author_id", None)
    aname = author_names.get(aid) if aid else None

    if notify_requested is True:
        nid = cast(int, item.id)
        background_tasks.add_task(
            _send_new_news_push_notifications_task,
            nid,
            cast(str, item.title),
            getattr(item, "summary", None),
            getattr(item, "content", None),
            cast(str, getattr(item, "target_audience", None) or "all"),
        )

    return base.model_copy(update={"images": image_urls, "author_name": aname})


@router.post("/{news_id}/notify")
async def notify_news_push(
    news_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: queue an FCM push for this news without editing the row."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    item = db.query(News).filter(News.id == news_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    background_tasks.add_task(
        _send_new_news_push_notifications_task,
        cast(int, item.id),
        cast(str, item.title),
        getattr(item, "summary", None),
        getattr(item, "content", None),
        cast(str, getattr(item, "target_audience", None) or "all"),
    )
    return JSONResponse(
        content={"success": True, "message": "Push notification queued"},
    )


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(
    news_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: delete a news item."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    item = db.query(News).filter(News.id == news_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    # Snapshot files first, but delete only after the DB commit. This prevents a
    # failed delete transaction from leaving a live row pointing to a lost file.
    cover_url = getattr(item, "cover_image_url", None)
    video_source = getattr(item, "video_source", None)
    video_url = getattr(item, "video_url", None)
    video_thumbnail_url = getattr(item, "video_thumbnail_url", None)
    gallery_images = db.query(NewsImage).filter(NewsImage.news_id == item.id).all()
    files_to_delete = {url for url in (cover_url,) if url}
    for img in gallery_images:
        if img.image_url:
            files_to_delete.add(img.image_url)
    if video_source == "upload":
        if video_url:
            files_to_delete.add(video_url)
        if video_thumbnail_url:
            files_to_delete.add(video_thumbnail_url)

    db.delete(item)
    db.commit()
    for file_url in files_to_delete:
        delete_local_file(file_url)
    
    await broadcast_public_data_update("news")
    
    return None


@router.post("/upload-image")
async def upload_news_image(
    request: Request,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a single image file for news. Returns the full URL."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    allowed = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    if image.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP allowed")

    contents = await image.read()
    
    # Use Storage Service for dynamic upload
    url_path = StorageService.upload_file(
        file_data=contents, 
        folder="news", 
        filename=image.filename,
        content_type=image.content_type
    )

    if not url_path:
        raise HTTPException(status_code=500, detail="Failed to upload image")

    # If it's a relative local URL, we might want to prepend base url like before,
    # but the app can usually handle relative URLs if we configured it correctly.
    # To maintain exact backwards compatibility with the returned JSON format:
    if url_path.startswith('/'):
        base = _get_base_url(request)
        final_url = f"{base}{url_path}"
    else:
        final_url = url_path # Cloudinary/S3 return absolute URLs

    return JSONResponse(content={"url": final_url})


from pydantic import BaseModel

class DeleteImageRequest(BaseModel):
    url: str

@router.delete("/upload-image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news_image(
    body: DeleteImageRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Admin: explicitly delete an uploaded image from disk."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
        
    delete_local_file(body.url)
    return None


@router.post("/media/video")
async def upload_news_video(
    request: Request,
    video: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    """
    Upload and optimize one news video.

    Input is streamed to a temporary file to avoid holding the original upload
    in memory. FFmpeg creates a broadly compatible MP4 with fast-start metadata,
    allowing playback to begin before the full file has downloaded.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    if not settings.news_video_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="News video uploads are temporarily disabled",
        )
    try:
        suffix = validate_video_upload(video.filename, video.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    max_bytes = settings.news_video_max_upload_mb * 1024 * 1024
    uploaded_video_url: Optional[str] = None
    with tempfile.TemporaryDirectory(prefix="pama-news-video-") as temp_dir:
        temp_path = Path(temp_dir)
        source = temp_path / f"source{suffix}"
        written = 0
        try:
            with source.open("wb") as destination:
                while chunk := await video.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                "Video is too large. Maximum size is "
                                f"{settings.news_video_max_upload_mb} MB"
                            ),
                        )
                    destination.write(chunk)
        finally:
            await video.close()

        if written == 0:
            raise HTTPException(status_code=400, detail="Uploaded video is empty")

        optimized = temp_path / "optimized.mp4"
        thumbnail = temp_path / "thumbnail.jpg"
        try:
            output, thumbnail_path, duration = await asyncio.to_thread(
                optimize_video, source, optimized, thumbnail
            )
        except (RuntimeError, subprocess.SubprocessError) as exc:
            logger.exception("News video optimization failed")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not process this video: {exc}",
            ) from exc

        unique = uuid.uuid4().hex
        output_bytes = await asyncio.to_thread(output.read_bytes)
        stored_video = await asyncio.to_thread(
            StorageService.upload_file,
            output_bytes,
            "news/videos",
            f"news_{unique}.mp4",
            "video/mp4",
        )
        if not stored_video:
            raise HTTPException(status_code=500, detail="Failed to store video")
        uploaded_video_url = stored_video

        stored_thumbnail: Optional[str] = None
        if thumbnail_path:
            thumb_bytes = await asyncio.to_thread(thumbnail_path.read_bytes)
            stored_thumbnail = await asyncio.to_thread(
                StorageService.upload_file,
                thumb_bytes,
                "news/thumbnails",
                f"news_{unique}.jpg",
                "image/jpeg",
            )

    return JSONResponse(content={
        "url": _absolute_storage_url(request, uploaded_video_url),
        "thumbnail_url": (
            _absolute_storage_url(request, stored_thumbnail)
            if stored_thumbnail
            else None
        ),
        "duration_seconds": duration,
        "source": "upload",
    })


class YoutubeImportRequest(BaseModel):
    url: str


@router.post("/media/youtube")
async def import_news_youtube_video(
    body: YoutubeImportRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """
    Import a school-owned YouTube video into first-party storage.

    The mobile app then uses the normal MP4 player, so no YouTube iframe,
    branding, recommendations, captions, or native controls are rendered.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )
    if (
        not settings.news_video_enabled
        or not settings.news_youtube_mirroring_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube video importing is temporarily disabled",
        )
    video_id = extract_youtube_video_id(body.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube video URL")

    original_url = canonical_youtube_url(video_id)
    max_bytes = settings.news_video_max_upload_mb * 1024 * 1024
    uploaded_video_url: Optional[str] = None
    with tempfile.TemporaryDirectory(prefix="pama-news-youtube-") as temp_dir:
        temp_path = Path(temp_dir)
        try:
            source = await asyncio.to_thread(
                download_youtube_video,
                original_url,
                temp_path,
                max_bytes,
            )
            optimized = temp_path / "optimized.mp4"
            thumbnail = temp_path / "thumbnail.jpg"
            output, thumbnail_path, duration = await asyncio.to_thread(
                optimize_video,
                source,
                optimized,
                thumbnail,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (RuntimeError, subprocess.SubprocessError) as exc:
            logger.exception("YouTube news video import failed")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not import this YouTube video: {exc}",
            ) from exc

        if output.stat().st_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    "Imported video is too large. Maximum size is "
                    f"{settings.news_video_max_upload_mb} MB"
                ),
            )

        unique = uuid.uuid4().hex
        output_bytes = await asyncio.to_thread(output.read_bytes)
        stored_video = await asyncio.to_thread(
            StorageService.upload_file,
            output_bytes,
            "news/videos",
            f"news_youtube_{video_id}_{unique}.mp4",
            "video/mp4",
        )
        if not stored_video:
            raise HTTPException(status_code=500, detail="Failed to store video")
        uploaded_video_url = stored_video

        stored_thumbnail: Optional[str] = None
        if thumbnail_path:
            thumb_bytes = await asyncio.to_thread(thumbnail_path.read_bytes)
            stored_thumbnail = await asyncio.to_thread(
                StorageService.upload_file,
                thumb_bytes,
                "news/thumbnails",
                f"news_youtube_{video_id}_{unique}.jpg",
                "image/jpeg",
            )

    return JSONResponse(content={
        "url": _absolute_storage_url(request, uploaded_video_url),
        "thumbnail_url": (
            _absolute_storage_url(request, stored_thumbnail)
            if stored_thumbnail
            else youtube_thumbnail_url(video_id)
        ),
        "duration_seconds": duration,
        "source": "upload",
        "original_url": original_url,
    })


class DeleteVideoRequest(BaseModel):
    url: str
    thumbnail_url: Optional[str] = None


@router.delete("/media/video", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news_video(
    body: DeleteVideoRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Delete an uploaded news video and its generated thumbnail."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    delete_local_file(body.url)
    if body.thumbnail_url and body.thumbnail_url != body.url:
        delete_local_file(body.thumbnail_url)
    return None
