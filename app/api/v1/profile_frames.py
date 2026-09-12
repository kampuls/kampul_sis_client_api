from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import List, Optional
import uuid
import shutil
from datetime import datetime

from ...core.database import get_db
from ...utils.common import get_current_active_user, get_current_admin_user, security
from ...models.user import User
from ...models.profile_frame import ProfileFrame, ProfileFrameHistory
from ...core.config import settings
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from fastapi.security import HTTPAuthorizationCredentials

from pathlib import Path

UPLOAD_DIR = Path("uploads/frames")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR = Path("uploads/frame_history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()

def get_current_user_info(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        username = payload.get("sub")
        role = payload.get("role")
        user_id = payload.get("user_id")
        if username is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        return {"username": username, "role": role, "user_id": user_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

@router.get("/")
async def list_active_frames(
    db: Session = Depends(get_db),
    user_info: dict = Depends(get_current_user_info)
):
    """Users only see frames that are published, not expired, and past their publish_at schedule."""
    now = datetime.utcnow()
    user_id = user_info.get("user_id")
    role = user_info.get("role")
    
    if role == "parent":
        frames = db.query(ProfileFrame).filter(
            ProfileFrame.is_active == True,
            ProfileFrame.status == 'published',
            or_(ProfileFrame.publish_at.is_(None), ProfileFrame.publish_at <= now),
            or_(ProfileFrame.expires_at.is_(None), ProfileFrame.expires_at > now),
            ProfileFrame.is_public == True
        ).order_by(desc(ProfileFrame.is_featured), desc(ProfileFrame.created_at)).all()
    else:
        frames = db.query(ProfileFrame).filter(
            ProfileFrame.is_active == True,
            ProfileFrame.status == 'published',
            or_(ProfileFrame.publish_at.is_(None), ProfileFrame.publish_at <= now),
            or_(ProfileFrame.expires_at.is_(None), ProfileFrame.expires_at > now),
            or_(ProfileFrame.is_public == True, ProfileFrame.user_id == user_id)
        ).order_by(desc(ProfileFrame.is_featured), desc(ProfileFrame.created_at)).all()
        
    return [{
        "id": f.id,
        "title": f.title,
        "image_url": f.image_url,
        "is_public": f.is_public,
        "is_featured": f.is_featured,
        "user_id": f.user_id,
        "slug": f.slug,
        "created_at": f.created_at
    } for f in frames]

@router.post("/")
async def user_create_frame(
    title: Optional[str] = Form("My Custom Frame"),
    is_public: bool = Form(False),
    slug: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not file.filename.lower().endswith('.png'):
        raise HTTPException(status_code=400, detail="Only PNG files are allowed")
    
    if slug:
        slug = slug.strip().lower().replace(" ", "-")
        existing = db.query(ProfileFrame).filter(ProfileFrame.slug == slug).first()
        if existing:
            raise HTTPException(status_code=400, detail="This URL slug is already taken.")

    filename = f"{uuid.uuid4()}.png"
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    image_url = f"/uploads/frames/{filename}"
    
    frame = ProfileFrame(
        title=title, 
        image_url=image_url, 
        status='published',
        is_active=True,
        user_id=current_user.id,
        is_public=is_public,
        is_featured=False,
        slug=slug
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)
    return {"message": "Frame uploaded successfully", "id": frame.id, "image_url": frame.image_url, "slug": frame.slug}

@router.delete("/{frame_id}")
async def user_delete_frame(
    frame_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    frame = db.query(ProfileFrame).filter(ProfileFrame.id == frame_id).first()
    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")
    if frame.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own frames")
    
    # Physically delete the image file from disk
    try:
        filename = frame.image_url.split("/")[-1]
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"Error removing frame file: {e}")

    db.delete(frame)
    db.commit()
    return {"message": "Frame deleted successfully"}

@router.get("/admin")
async def admin_list_frames(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin sees only admin-created frames (user_id IS NULL).
    User-created frames (user_id IS NOT NULL) are managed by users themselves."""
    now = datetime.utcnow()
    frames = db.query(ProfileFrame).filter(
        ProfileFrame.is_active == True,
        ProfileFrame.user_id.is_(None)   # ← admin frames only
    ).order_by(desc(ProfileFrame.created_at)).all()

    def effective_status(f):
        if f.status == 'published':
            if f.expires_at and f.expires_at <= now:
                return 'expired'
            if f.publish_at and f.publish_at > now:
                return 'scheduled'
        return f.status

    return [{
        "id": f.id,
        "title": f.title,
        "image_url": f.image_url,
        "is_public": f.is_public,
        "is_featured": f.is_featured,
        "user_id": f.user_id,
        "slug": f.slug,
        "status": effective_status(f),
        "publish_at": f.publish_at.isoformat() if f.publish_at else None,
        "expires_at": f.expires_at.isoformat() if f.expires_at else None,
        "created_at": f.created_at
    } for f in frames]

@router.post("/admin")
async def create_frame(
    title: Optional[str] = Form("New Frame"),
    slug: Optional[str] = Form(None),
    status: str = Form('published'),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    if slug:
        slug = slug.strip().lower().replace(" ", "-")
        # Validate uniqueness
        existing = db.query(ProfileFrame).filter(ProfileFrame.slug == slug).first()
        if existing:
            raise HTTPException(status_code=400, detail="Slug already exists. Please choose a different one.")

    filename = f"{uuid.uuid4()}.png"
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    image_url = f"/uploads/frames/{filename}"
    if status not in ('published', 'draft', 'scheduled', 'disabled'):
        status = 'published'
    frame = ProfileFrame(
        title=title, 
        image_url=image_url, 
        slug=slug,
        status=status,
        is_active=True,
        user_id=None,
        is_public=True,
        is_featured=True
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)
    return {"message": "Frame uploaded successfully", "id": frame.id, "image_url": frame.image_url}

@router.get("/admin/{frame_id}/users")
async def admin_get_frame_usage(
    frame_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Get history of users who used this frame"""
    history_records = db.query(ProfileFrameHistory, User)\
        .join(User, ProfileFrameHistory.user_id == User.id)\
        .filter(ProfileFrameHistory.frame_id == frame_id)\
        .order_by(desc(ProfileFrameHistory.created_at)).all()

    return [{
        "history_id": h.id,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "generated_image_url": h.generated_image_url,
        "user_id": u.id,
        "username": u.username,
        "first_name": u.eName or u.kName or u.username
    } for h, u in history_records]

@router.delete("/admin/{frame_id}")
async def delete_frame(
    frame_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    frame = db.query(ProfileFrame).filter(
        ProfileFrame.id == frame_id,
        ProfileFrame.user_id.is_(None)   # only admin-created frames
    ).first()
    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")
    # Physically delete the image file from disk
    try:
        filename = frame.image_url.split("/")[-1]
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"Error removing frame file: {e}")
    db.delete(frame)
    db.commit()
    return {"message": "Frame deleted successfully"}

@router.patch("/admin/{frame_id}/status")
async def update_frame_status(
    frame_id: int,
    status: str = Form(...),
    publish_at: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Update a frame's status. Accepts: published | draft | scheduled | disabled."""
    if status not in ('published', 'draft', 'scheduled', 'disabled'):
        raise HTTPException(status_code=400, detail="Invalid status")
    frame = db.query(ProfileFrame).filter(
        ProfileFrame.id == frame_id,
        ProfileFrame.is_active == True,
        ProfileFrame.user_id.is_(None)   # only admin-created frames
    ).first()
    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")
    frame.status = status
    frame.publish_at = datetime.fromisoformat(publish_at) if publish_at else None
    frame.expires_at = datetime.fromisoformat(expires_at) if expires_at else None
    db.commit()
    return {"message": "Status updated", "status": status}

@router.post("/history")
async def save_history(
    frame_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Save generated profile image to user's history"""
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "png"
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = HISTORY_DIR / filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    image_url = f"/uploads/frame_history/{filename}"
    
    history = ProfileFrameHistory(
        user_id=current_user.id,
        frame_id=frame_id,
        generated_image_url=image_url
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    return {"message": "History saved", "image_url": history.generated_image_url}

@router.get("/history")
async def get_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    history_records = db.query(ProfileFrameHistory)\
        .filter(ProfileFrameHistory.user_id == current_user.id)\
        .order_by(desc(ProfileFrameHistory.created_at))\
        .limit(20).all()
        
    return [{
        "id": h.id,
        "frame_id": h.frame_id,
        "generated_image_url": h.generated_image_url,
        "created_at": h.created_at
    } for h in history_records]

@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a history record — users can only delete their own"""
    record = db.query(ProfileFrameHistory)\
        .filter(ProfileFrameHistory.id == history_id, ProfileFrameHistory.user_id == current_user.id)\
        .first()
    if not record:
        raise HTTPException(status_code=404, detail="History record not found or not yours")

    # Physically delete the file from disk
    try:
        filename = record.generated_image_url.split("/")[-1]
        file_path = HISTORY_DIR / filename
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"Error removing history file: {e}")

    db.delete(record)
    db.commit()
    return {"message": "Deleted successfully"}
