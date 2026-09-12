from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import shutil
import uuid
from pathlib import Path

from ...core import get_db
from ...auth.dependencies import require_admin
from ...schemas.splash_ad import SplashAdCreate, SplashAdUpdate, SplashAdResponse
from ...services.splash_ad_service import splash_ad_service
from ...utils.file_utils import delete_local_file
from ...services.storage_service import StorageService

UPLOAD_DIR = Path("uploads/splash_ads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
from ...services.splash_ad_service import splash_ad_service

router = APIRouter(prefix="/splash-ads", tags=["splash_ads"])

@router.get("/active", response_model=SplashAdResponse)
def get_active_splash_ad(db: Session = Depends(get_db)):
    """
    Get the currently active splash ad. 
    This is a public endpoint used by the mobile app on startup.
    Returns 404 if no ad is currently configured to show.
    """
    ad = splash_ad_service.get_active_ad(db)
    if not ad:
        raise HTTPException(status_code=404, detail="No active splash ad found")
    return ad

# --- Admin Endpoints ---

@router.get("", response_model=List[SplashAdResponse], dependencies=[Depends(require_admin)])
def list_splash_ads(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all splash ads (Admin only)"""
    return splash_ad_service.get_all(db, skip=skip, limit=limit)

@router.post("", response_model=SplashAdResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_splash_ad(
    db: Session = Depends(get_db),
    duration_seconds: int = Form(5),
    target_url: Optional[str] = Form(None),
    is_active: bool = Form(True),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    image: UploadFile = File(...)
):
    """Create a new splash ad configuration (Admin only)"""
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, and WebP are allowed."
        )

    contents = await image.read()
    image_url = StorageService.upload_file(
        file_data=contents,
        folder="splash_ads",
        filename=image.filename,
        content_type=image.content_type
    )
    
    if not image_url:
        raise HTTPException(status_code=500, detail="Failed to upload splash ad image")

    start_date_obj = None
    end_date_obj = None
    try:
        if start_date: start_date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if end_date: end_date_obj = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except Exception:
        pass

    ad_in = SplashAdCreate(
        image_url=image_url,
        duration_seconds=duration_seconds,
        target_url=target_url,
        is_active=is_active,
        start_date=start_date_obj,
        end_date=end_date_obj
    )
    return splash_ad_service.create(db, ad_in)

@router.get("/{ad_id}", response_model=SplashAdResponse, dependencies=[Depends(require_admin)])
def get_splash_ad(ad_id: int, db: Session = Depends(get_db)):
    """Get a specific splash ad configuration (Admin only)"""
    ad = splash_ad_service.get_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Splash ad not found")
    return ad

@router.put("/{ad_id}", response_model=SplashAdResponse, dependencies=[Depends(require_admin)])
async def update_splash_ad(
    ad_id: int, 
    db: Session = Depends(get_db),
    duration_seconds: Optional[int] = Form(None),
    target_url: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None)
):
    """Update a splash ad configuration (Admin only)"""
    ad = splash_ad_service.get_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Splash ad not found")

    image_url = None
    if image:
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only JPEG, PNG, and WebP are allowed."
            )
        contents = await image.read()
        image_url = StorageService.upload_file(
            file_data=contents,
            folder="splash_ads",
            filename=image.filename,
            content_type=image.content_type
        )
        if not image_url:
            raise HTTPException(status_code=500, detail="Failed to upload new image")

        # Delete old image if it exists
        if ad.image_url:
            from ...models.settings import SystemSettings
            settings = db.query(SystemSettings).first()
            StorageService.delete_file(ad.image_url, settings)

    update_data = {}
    if duration_seconds is not None: update_data['duration_seconds'] = duration_seconds
    if target_url is not None: update_data['target_url'] = target_url if target_url.strip() else None
    if is_active is not None: update_data['is_active'] = is_active
    if image_url is not None: update_data['image_url'] = image_url

    try:
        if start_date is not None: update_data['start_date'] = datetime.fromisoformat(start_date.replace('Z', '+00:00')) if start_date else None
        if end_date is not None: update_data['end_date'] = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None
    except Exception:
        pass

    ad_update = SplashAdUpdate(**update_data)
    return splash_ad_service.update(db, ad, ad_update)

@router.delete("/{ad_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_splash_ad(ad_id: int, db: Session = Depends(get_db)):
    """Delete a splash ad configuration (Admin only)"""
    ad = splash_ad_service.get_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Splash ad not found")
        
    # Delete associated image
    if ad.image_url:
        from ...models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        StorageService.delete_file(ad.image_url, settings)
            
    splash_ad_service.delete(db, ad)
    return None
