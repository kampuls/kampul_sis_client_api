"""
Ads/Banner API endpoints.
"""

import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Any, Dict, Optional
from datetime import datetime
import uuid
import shutil
from pathlib import Path

from ...core import get_db
from ...auth import get_current_active_user
from ...core.config import settings
from ...utils.file_utils import delete_local_file
from ...services.storage_service import StorageService

router = APIRouter()
logger = logging.getLogger(__name__)

# Directory for storing ad images
UPLOAD_DIR = Path("uploads/ads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Base URL for serving images - will be constructed from request
def get_base_url(request: Optional[Request] = None) -> str:
    """Get base URL for serving images from request or settings"""
    if request:
        # Use request's base URL (works for both localhost and network IP)
        return str(request.base_url).rstrip('/')
    
    # Fallback to settings
    host = getattr(settings, 'host', '0.0.0.0')
    port = getattr(settings, 'port', 8000)
    # For localhost access, use localhost instead of 0.0.0.0
    if host == '0.0.0.0':
        return f'http://localhost:{port}'
    return f'http://{host}:{port}'


def _map_ad_target_audience_to_push_audience(target_audience: Optional[str]) -> str:
    """Map ads.target_audience values to get_device_tokens_by_audience() keys."""
    t = (target_audience or "all").strip().lower()
    if t == "all":
        return "all"
    if t == "teachers":
        return "teacher"
    if t == "parents":
        return "parent"
    if t == "students":
        return "student"
    if t == "staff":
        return "teacher,parent"
    return "all"


def _send_new_ad_push_notifications_task(
    ad_id: int,
    title: str,
    subtitle: Optional[str],
    description: Optional[str],
    target_audience: str,
    image_url: Optional[str] = None,
) -> None:
    """
    Send FCM to registered devices after an ad is created.
    Runs in a FastAPI BackgroundTask so the admin HTTP response is not blocked.
    """
    from ...core.database import SessionLocal
    from ...services.notification_service import (
        get_device_tokens_by_audience,
        send_app_rich_push_notification,
    )

    db = SessionLocal()
    try:
        audience = _map_ad_target_audience_to_push_audience(target_audience)
        tokens = get_device_tokens_by_audience(db, audience)
        if not tokens:
            logger.info(
                "[Ads] No device tokens for audience %s (ad %s)", audience, ad_id
            )
            return

        body = (subtitle or "").strip()
        if not body and description:
            desc = description.strip()
            body = desc[:280] + ("…" if len(desc) > 280 else "")
        if not body:
            body = "Tap to read more."

        if not image_url:
            img_row = db.execute(
                text("SELECT image_url FROM ads WHERE id = :ad_id"),
                {"ad_id": ad_id},
            ).fetchone()
            if img_row:
                image_url = img_row[0]
        payload_data = {
            "type": "new_ad",
            "ad_id": str(ad_id),
            "title": title,
            "body": body,
        }
        if image_url:
            payload_data["image_url"] = str(image_url).strip()

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
                    "[Ads] Notification chunk %s failed for ad %s: %s",
                    i // chunk_size + 1,
                    ad_id,
                    chunk_err,
                )
        logger.info(
            "[Ads] Sent new_ad push for ad %s: %s devices in %s chunks (audience=%s)",
            ad_id,
            len(tokens),
            ((len(tokens) - 1) // chunk_size) + 1,
            audience,
        )
    except Exception as e:
        logger.exception("[Ads] Background push failed for ad %s: %s", ad_id, e)
    finally:
        db.close()


@router.get("/")
async def get_ads(
    request: Request,
    academic_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    user_type: Optional[str] = Query(None),
    include_all: bool = Query(False),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get ads.
    If include_all is False (default): returns active ads within date range.
    If include_all is True: returns all ads (for admin management).
    """
    try:
        now = datetime.now()

        # Base query
        base_sql = """
            SELECT 
                id, title, subtitle, description, image_url, 
                ad_type, action_type, action_data, button_text, button_color,
                target_audience, start_date, end_date, display_order,
                click_count, view_count, created_at, updated_at
            FROM ads
        """
        
        # Parameter bag
        params: Dict[str, Any] = {}
        params["now"] = now

        # Build conditions
        conditions = []
        
        # Public filtering (active & date range) - only if NOT including all
        if not include_all:
            conditions.append("is_active = 1")
            conditions.append("(start_date IS NULL OR start_date <= :now)")
            conditions.append("(end_date IS NULL OR end_date >= :now)")

        # Specific filters
        if academic_id:
            conditions.append("(academic_id IS NULL OR academic_id = :academic_id)")
            params["academic_id"] = academic_id
        
        if branch_id:
            conditions.append("(branch_id IS NULL OR branch_id = :branch_id)")
            params["branch_id"] = branch_id
        
        if user_type and not include_all:
             # Only filter by target audience for public view
            conditions.append("(target_audience = 'all' OR target_audience = :user_type)")
            params["user_type"] = user_type

        sql = base_sql
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        # Add ordering and limit
        sql += " ORDER BY display_order ASC, created_at DESC LIMIT :limit"
        params["limit"] = limit

        query = text(sql)
        result = db.execute(query, params)
        rows = result.fetchall()
        
        ads = []
        for row in rows:
            base_url = get_base_url(request)
            ad = {
                "id": row[0],
                "title": row[1],
                "subtitle": row[2],
                "description": row[3],
                "image_url": f"{base_url}{row[4]}" if row[4] else None,
                "ad_type": row[5],
                "action_type": row[6],
                "action_data": row[7],
                "button_text": row[8],
                "button_color": row[9],
                "target_audience": row[10],
                "start_date": row[11].isoformat() if row[11] else None,
                "end_date": row[12].isoformat() if row[12] else None,
                "display_order": row[13],
                "click_count": row[14],
                "view_count": row[15],
                "created_at": row[16].isoformat() if row[16] else None,
                "updated_at": row[17].isoformat() if row[17] else None,
            }
            ads.append(ad)
        
        return JSONResponse(content={"success": True, "ads": ads})
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch ads: {str(e)}"
        )


@router.get("/{ad_id}")
async def get_ad_detail(
    request: Request,
    ad_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get detailed information about a specific ad."""
    try:
        query = text("""
            SELECT 
                id, title, subtitle, description, image_url, 
                ad_type, action_type, action_data, button_text, button_color,
                target_audience, start_date, end_date, display_order,
                click_count, view_count, created_at, updated_at
            FROM ads
            WHERE id = :ad_id
        """)
        
        result = db.execute(query, {"ad_id": ad_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ad not found"
            )
        
        base_url = get_base_url(request)
        ad = {
            "id": row[0],
            "title": row[1],
            "subtitle": row[2],
            "description": row[3],
            "image_url": f"{base_url}{row[4]}" if row[4] else None,
            "ad_type": row[5],
            "action_type": row[6],
            "action_data": row[7],
            "button_text": row[8],
            "button_color": row[9],
            "target_audience": row[10],
            "start_date": row[11].isoformat() if row[11] else None,
            "end_date": row[12].isoformat() if row[12] else None,
            "display_order": row[13],
            "click_count": row[14],
            "view_count": row[15],
            "created_at": row[16].isoformat() if row[16] else None,
            "updated_at": row[17].isoformat() if row[17] else None,
        }
        
        return JSONResponse(content={"success": True, "ad": ad})
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch ad: {str(e)}"
        )


@router.post("/{ad_id}/click")
async def track_ad_click(
    ad_id: int,
    user_type: Optional[str] = Query(None),
    device_info: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Track when an ad is clicked."""
    try:
        user_id = current_user.id if current_user else None
        
        # Insert click record
        insert_query = text("""
            INSERT INTO ad_clicks (ad_id, user_id, user_type, device_info)
            VALUES (:ad_id, :user_id, :user_type, :device_info)
        """)
        
        db.execute(insert_query, {
            "ad_id": ad_id,
            "user_id": user_id,
            "user_type": user_type or (current_user.user_type if current_user else 'guest'),
            "device_info": device_info
        })
        
        # Update click count
        update_query = text("""
            UPDATE ads SET click_count = click_count + 1 WHERE id = :ad_id
        """)
        db.execute(update_query, {"ad_id": ad_id})
        db.commit()
        
        return JSONResponse(content={"success": True, "message": "Click tracked"})
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to track click: {str(e)}"
        )


@router.post("/{ad_id}/view")
async def track_ad_view(
    ad_id: int,
    user_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Track when an ad is viewed."""
    try:
        # Update view count
        update_query = text("""
            UPDATE ads SET view_count = view_count + 1 WHERE id = :ad_id
        """)
        db.execute(update_query, {"ad_id": ad_id})
        db.commit()
        
        return JSONResponse(content={"success": True, "message": "View tracked"})
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to track view: {str(e)}"
        )


@router.post("/")
async def create_ad(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    subtitle: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    ad_type: str = Form("general"),
    action_type: Optional[str] = Form(None),
    action_data: Optional[str] = Form(None),  # JSON string
    button_text: Optional[str] = Form(None),
    button_color: Optional[str] = Form("#1976D2"),
    target_audience: str = Form("all"),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    display_order: int = Form(0),
    academic_id: Optional[int] = Form(None),
    branch_id: Optional[int] = Form(None),
    send_push_notification: str = Form("true"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create a new ad. Admin only.
    """
    try:
        # Validate file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only JPEG, PNG, and WebP are allowed."
            )
        
        # Validate file size (5MB max) – some type checkers mark size as Optional
        file_size = getattr(image, "size", None)
        if file_size is not None and file_size > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size too large. Maximum size is 5MB."
            )
        
        contents = await image.read()
        image_url = StorageService.upload_file(
            file_data=contents,
            folder="ads",
            filename=image.filename,
            content_type=image.content_type
        )
        
        if not image_url:
            raise HTTPException(status_code=500, detail="Failed to upload image")
            
        file_path = image_url # Use URL as the path/reference
        
        # Parse action_data if provided
        import json
        action_data_json = None
        if action_data:
            try:
                action_data_json = json.loads(action_data)
            except:
                pass
        
        # Parse dates
        start_date_obj = None
        end_date_obj = None
        if start_date:
            try:
                start_date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except:
                pass
        if end_date:
            try:
                end_date_obj = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except:
                pass
        
        user_id = current_user.id if current_user else None
        
        # Insert ad
        insert_query = text("""
            INSERT INTO ads (
                title, subtitle, description, image_url, image_path,
                ad_type, action_type, action_data, button_text, button_color,
                target_audience, start_date, end_date, display_order,
                academic_id, branch_id, created_by
            ) VALUES (
                :title, :subtitle, :description, :image_url, :image_path,
                :ad_type, :action_type, :action_data, :button_text, :button_color,
                :target_audience, :start_date, :end_date, :display_order,
                :academic_id, :branch_id, :created_by
            )
        """)
        
        insert_result = db.execute(
            insert_query,
            {
                "title": title,
                "subtitle": subtitle,
                "description": description,
                "image_url": image_url,
                "image_path": str(file_path),
                "ad_type": ad_type,
                "action_type": action_type,
                "action_data": json.dumps(action_data_json) if action_data_json else None,
                "button_text": button_text,
                "button_color": button_color,
                "target_audience": target_audience,
                "start_date": start_date_obj,
                "end_date": end_date_obj,
                "display_order": display_order,
                "academic_id": academic_id,
                "branch_id": branch_id,
                "created_by": user_id,
            },
        )

        # Use insert cursor id (LAST_INSERT_ID() after commit can be 0 with pooled connections).
        ad_id = getattr(insert_result, "lastrowid", None) or 0
        if not ad_id:
            fallback = db.execute(
                text(
                    "SELECT id FROM ads WHERE created_by = :uid "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"uid": user_id},
            ).fetchone()
            ad_id = fallback[0] if fallback else 0

        db.commit()

        if not ad_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ad created but could not resolve new ad id for notifications",
            )

        notify = send_push_notification.strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if notify:
            background_tasks.add_task(
                _send_new_ad_push_notifications_task,
                int(ad_id),
                title,
                subtitle,
                description,
                target_audience,
                image_url,
            )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"success": True, "message": "Ad created successfully", "ad_id": ad_id}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        # Clean up uploaded file on error
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create ad: {str(e)}"
        )


@router.put("/{ad_id}")
async def update_ad(
    request: Request,
    ad_id: int,
    background_tasks: BackgroundTasks,
    title: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    ad_type: Optional[str] = Form(None),
    action_type: Optional[str] = Form(None),
    action_data: Optional[str] = Form(None),
    button_text: Optional[str] = Form(None),
    button_color: Optional[str] = Form(None),
    target_audience: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    display_order: Optional[int] = Form(None),
    academic_id: Optional[int] = Form(None),
    branch_id: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    send_push_notification: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update an existing ad. Admin only.
    """
    try:
        # Check if ad exists
        check_query = text("SELECT id, image_url FROM ads WHERE id = :ad_id")
        result = db.execute(check_query, {"ad_id": ad_id})
        existing = result.fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ad not found"
            )
        
        old_image_url = existing[1]
        
        # Build update query dynamically
        updates: list[str] = []
        params: Dict[str, Any] = {"ad_id": ad_id}
        
        if title is not None:
            updates.append("title = :title")
            params["title"] = title
        if subtitle is not None:
            updates.append("subtitle = :subtitle")
            params["subtitle"] = subtitle
        if description is not None:
            updates.append("description = :description")
            params["description"] = description
        if ad_type is not None:
            updates.append("ad_type = :ad_type")
            params["ad_type"] = ad_type
        if action_type is not None:
            updates.append("action_type = :action_type")
            params["action_type"] = action_type
        if action_data is not None:
            import json
            try:
                action_data_json = json.loads(action_data)
                updates.append("action_data = :action_data")
                params["action_data"] = json.dumps(action_data_json)
            except:
                pass
        if button_text is not None:
            updates.append("button_text = :button_text")
            params["button_text"] = button_text
        if button_color is not None:
            updates.append("button_color = :button_color")
            params["button_color"] = button_color
        if target_audience is not None:
            updates.append("target_audience = :target_audience")
            params["target_audience"] = target_audience
        if display_order is not None:
            updates.append("display_order = :display_order")
            params["display_order"] = display_order
        if academic_id is not None:
            updates.append("academic_id = :academic_id")
            params["academic_id"] = academic_id
        if branch_id is not None:
            updates.append("branch_id = :branch_id")
            params["branch_id"] = branch_id
        if is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = 1 if is_active else 0

        # Handle date parsing
        if start_date is not None:
            try:
                start_date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                updates.append("start_date = :start_date")
                params["start_date"] = start_date_obj
            except:
                pass
        if end_date is not None:
            try:
                end_date_obj = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                updates.append("end_date = :end_date")
                params["end_date"] = end_date_obj
            except:
                pass

        # Handle image upload if provided
        if image:
            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
            if image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid file type. Only JPEG, PNG, and WebP are allowed."
                )

            # Validate file size
            file_size = getattr(image, "size", None)
            if file_size is not None and file_size > 5 * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File size too large. Maximum size is 5MB."
                )

            contents = await image.read()
            image_url = StorageService.upload_file(
                file_data=contents,
                folder="ads",
                filename=image.filename,
                content_type=image.content_type
            )

            if not image_url:
                raise HTTPException(status_code=500, detail="Failed to upload new image")

            file_path = image_url

            # Update image URLs
            updates.append("image_url = :image_url")
            updates.append("image_path = :image_path")
            params["image_url"] = image_url
            params["image_path"] = str(file_path)

            # Delete old image
            if old_image_url:
                delete_local_file(old_image_url)

        notify = (send_push_notification or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        def _schedule_push_from_db_row() -> None:
            row = db.execute(
                text(
                    "SELECT title, subtitle, description, target_audience, image_url "
                    "FROM ads WHERE id = :ad_id"
                ),
                {"ad_id": ad_id},
            ).fetchone()
            if not row:
                return
            background_tasks.add_task(
                _send_new_ad_push_notifications_task,
                ad_id,
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
            )

        if not updates:
            if notify:
                _schedule_push_from_db_row()
                return JSONResponse(
                    content={
                        "success": True,
                        "message": "Push notification sent",
                    }
                )
            return JSONResponse(
                content={"success": True, "message": "No changes to update"}
            )

        # Execute update
        update_query = text(f"UPDATE ads SET {', '.join(updates)} WHERE id = :ad_id")
        db.execute(update_query, params)
        db.commit()

        if notify:
            _schedule_push_from_db_row()

        return JSONResponse(content={"success": True, "message": "Ad updated successfully"})

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ad: {str(e)}"
        )


@router.delete("/{ad_id}")
async def delete_ad(
    ad_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete an ad. Admin only.
    """
    try:
        # Get ad info to delete image
        query = text("SELECT image_url FROM ads WHERE id = :ad_id")
        result = db.execute(query, {"ad_id": ad_id})
        ad = result.fetchone()
        
        if not ad:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ad not found"
            )
        
        # Delete image file
        image_url_val = ad[0]
        if image_url_val:
            from ...models.settings import SystemSettings
            settings = db.query(SystemSettings).first()
            StorageService.delete_file(image_url_val, settings)
        
        # Delete ad
        delete_query = text("DELETE FROM ads WHERE id = :ad_id")
        db.execute(delete_query, {"ad_id": ad_id})
        db.commit()
        
        return JSONResponse(content={"success": True, "message": "Ad deleted successfully"})
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete ad: {str(e)}"
        )
