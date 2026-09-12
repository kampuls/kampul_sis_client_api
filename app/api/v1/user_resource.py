"""
User Resource (Profile) API endpoints.
Handles avatar/cover uploads, bio, social links for all user types.
"""

import os
import uuid
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import User, UserResource, UserSocialLink
from ...schemas.user_resource import (
    UserResourceUpdate, UserResourceResponse,
    SocialLinkUpsert, SocialLinkResponse,
)
from ...auth import get_current_active_user
from ...utils.file_utils import delete_local_file
from ...services.storage_service import StorageService

router = APIRouter()

# ─── Paths ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # project root
UPLOADS_DIR = BASE_DIR / "uploads"
AVATARS_DIR = UPLOADS_DIR / "avatars"
COVERS_DIR = UPLOADS_DIR / "covers"

AVATARS_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _get_or_create_resource(
    db: Session,
    user_id: int,
    user_type: str,
) -> UserResource:
    """Return the UserResource row, creating it if it doesn't exist."""
    resource = (
        db.query(UserResource)
        .filter(UserResource.user_id == user_id, UserResource.user_type == user_type)
        .first()
    )
    if resource is None:
        resource = UserResource(user_id=user_id, user_type=user_type, status=1)
        db.add(resource)
        db.commit()
        db.refresh(resource)
    return resource


def _resolve_user_type(user) -> str:
    """
    Determine user_type string from the current_user object.
    Handles both regular User (has .role int) and ParentAsUser / similar
    adapters (which expose .user_type and .is_parent directly).

    School Management Role IDs (from users table):
      1 = Admin    → 'employee'
      2 = Teacher  → 'teacher'
      3+ = Other   → 'employee'
    """
    # ParentAsUser and similar adapters set user_type explicitly
    if hasattr(user, "user_type") and user.user_type:
        return str(user.user_type)

    # is_parent flag set by ParentAsUser adapter
    if getattr(user, "is_parent", False):
        return "parent"

    # Regular User model — use role integer
    # NOTE: In this school management system, role=1 is Admin and role=2 is Teacher.
    role_id = getattr(user, "role", None)
    if role_id == 2:
        return "teacher"
    if role_id == 3:
        return "parent"
    # role=1 (admin) and any other role → employee
    return "employee"


_UNSET = object()


def _resource_to_response(
    resource: UserResource,
    db: Session,
    *,
    avatar=_UNSET,
    cover_image=_UNSET,
    cover_focus_y=_UNSET,
) -> UserResourceResponse:
    """Build response including social links.
    Optional avatar/cover_image override merged staff profiles (teacher + employee rows).
    """
    eff_avatar = resource.avatar if avatar is _UNSET else avatar
    eff_cover = resource.cover_image if cover_image is _UNSET else cover_image
    eff_cover_focus = (
        resource.cover_focus_y if cover_focus_y is _UNSET else cover_focus_y
    )
    links = (
        db.query(UserSocialLink)
        .filter(UserSocialLink.user_resource_id == resource.id)
        .all()
    )
    data = {
        "id": resource.id,
        "user_id": resource.user_id,
        "user_type": resource.user_type,
        "avatar": eff_avatar,
        "cover_image": eff_cover,
        "cover_focus_y": eff_cover_focus or 0,
        "bio": resource.bio,
        "status_message": resource.status_message,
        "website": resource.website,
        "status": resource.status,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
        "social_links": [
            SocialLinkResponse(
                id=l.id,
                user_resource_id=l.user_resource_id,
                platform_name=l.platform_name,
                link=l.link,
                is_active=int(l.is_active) if isinstance(l.is_active, bool) else (l.is_active or 1),
                created_at=l.created_at,
                updated_at=l.updated_at,
            )
            for l in links
        ],
    }
    return UserResourceResponse(**data)


# ─── GET /profile/me ─────────────────────────────────────────
@router.get("/me", response_model=UserResourceResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get current user's profile resource (avatar, cover, bio, social links)."""
    user_type = _resolve_user_type(current_user)
    resource = _get_or_create_resource(db, current_user.id, user_type)
    return _resource_to_response(resource, db)


# ─── PUT /profile/me ─────────────────────────────────────────
@router.put("/me", response_model=UserResourceResponse)
async def update_my_profile(
    payload: UserResourceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update bio, status_message, website."""
    user_type = _resolve_user_type(current_user)
    resource = _get_or_create_resource(db, current_user.id, user_type)

    update_data = payload.model_dump(exclude_unset=True, exclude_none=False)
    for field, value in update_data.items():
        if hasattr(resource, field):
            setattr(resource, field, value)

    db.commit()
    db.refresh(resource)
    return _resource_to_response(resource, db)


# ─── POST /profile/me/avatar ─────────────────────────────────
@router.post("/me/avatar", response_model=UserResourceResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Upload/replace avatar image."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, WEBP, GIF are allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 5 MB.",
        )

    # Generate a unique filename while preserving the original extension
    ext = os.path.splitext(file.filename)[1]
    if not ext:
        ext = ".jpg"
    unique_filename = f"avatar_{uuid.uuid4().hex[:10]}{ext}"

    # Use Storage Service for dynamic upload
    avatar_url = StorageService.upload_file(
        file_data=contents, 
        folder="avatars", 
        filename=unique_filename,
        content_type=file.content_type
    )

    if not avatar_url:
        raise HTTPException(status_code=500, detail="Failed to upload avatar")

    user_type = _resolve_user_type(current_user)
    resource = _get_or_create_resource(db, current_user.id, user_type)

    # Delete old avatar file if it was previously stored locally
    if resource.avatar:
        from ...models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        StorageService.delete_file(resource.avatar, settings)

    resource.avatar = avatar_url
    db.commit()
    db.refresh(resource)
    return _resource_to_response(resource, db)


# ─── POST /profile/me/cover ──────────────────────────────────
@router.post("/me/cover", response_model=UserResourceResponse)
async def upload_cover(
    file: UploadFile = File(...),
    cover_focus_y: int = Form(0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Upload/replace cover image."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, WEBP, GIF are allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 5 MB.",
        )

    # Generate a unique filename while preserving the original extension
    ext = os.path.splitext(file.filename)[1]
    if not ext:
        ext = ".jpg"
    unique_filename = f"cover_{uuid.uuid4().hex[:10]}{ext}"

    # Use Storage Service for dynamic upload
    cover_url = StorageService.upload_file(
        file_data=contents, 
        folder="covers", 
        filename=unique_filename,
        content_type=file.content_type
    )

    if not cover_url:
        raise HTTPException(status_code=500, detail="Failed to upload cover")

    user_type = _resolve_user_type(current_user)
    resource = _get_or_create_resource(db, current_user.id, user_type)

    if resource.cover_image:
        from ...models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        StorageService.delete_file(resource.cover_image, settings)

    resource.cover_image = cover_url
    resource.cover_focus_y = max(-100, min(100, int(cover_focus_y)))
    db.commit()
    db.refresh(resource)
    return _resource_to_response(resource, db)


# ─── PUT /profile/me/social-links ────────────────────────────
@router.put("/me/social-links", response_model=UserResourceResponse)
async def upsert_social_links(
    links: List[SocialLinkUpsert],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Bulk upsert social links.
    - Rows WITH id → update existing row.
    - Rows WITHOUT id → create new row.
    - Existing rows not mentioned → deleted.
    """
    user_type = _resolve_user_type(current_user)
    resource = _get_or_create_resource(db, current_user.id, user_type)

    # IDs of rows that should survive
    keep_ids = {l.id for l in links if l.id is not None}

    # Delete rows not in keep_ids
    existing = (
        db.query(UserSocialLink)
        .filter(UserSocialLink.user_resource_id == resource.id)
        .all()
    )
    for row in existing:
        if row.id not in keep_ids:
            db.delete(row)

    for link in links:
        if link.id is not None:
            # Update existing
            row = db.query(UserSocialLink).filter(UserSocialLink.id == link.id).first()
            if row and row.user_resource_id == resource.id:
                row.platform_name = link.platform_name
                row.link = link.link
                row.is_active = link.is_active
        else:
            # Create new
            new_link = UserSocialLink(
                user_resource_id=resource.id,
                platform_name=link.platform_name,
                link=link.link,
                is_active=link.is_active,
            )
            db.add(new_link)

    db.commit()
    db.refresh(resource)
    return _resource_to_response(resource, db)


# ─── GET /profile/{user_type}/{user_id} ──────────────────────
@router.get("/{user_type}/{user_id}", response_model=UserResourceResponse)
async def get_user_profile(
    user_type: str,
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get any user's public profile by type + ID."""
    # Virtual type: any staff row in `users` may store media under `teacher` (role=2)
    # or `employee` (admin/other). Clients should use `staff` so one URL works for all.
    allowed_types = {"teacher", "student", "parent", "employee", "staff"}
    if user_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid user_type")

    if user_type == "staff":
        teacher = (
            db.query(UserResource)
            .filter(UserResource.user_id == user_id, UserResource.user_type == "teacher")
            .first()
        )
        employee = (
            db.query(UserResource)
            .filter(UserResource.user_id == user_id, UserResource.user_type == "employee")
            .first()
        )
        if teacher is None and employee is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        # Prefer teacher as canonical row (id, social_links). Merge media from either row
        # so avatars/covers stored only on employee (or only on teacher) still resolve.
        base = teacher if teacher is not None else employee
        merged_avatar = (teacher.avatar if teacher else None) or (
            employee.avatar if employee else None
        )
        merged_cover = (teacher.cover_image if teacher else None) or (
            employee.cover_image if employee else None
        )
        merged_cover_focus = (
            (teacher.cover_focus_y if teacher and teacher.cover_image else None)
            if teacher is not None
            else None
        ) or (
            (employee.cover_focus_y if employee and employee.cover_image else None)
            if employee is not None
            else None
        ) or 0
        return _resource_to_response(
            base,
            db,
            avatar=merged_avatar,
            cover_image=merged_cover,
            cover_focus_y=merged_cover_focus,
        )

    resource = (
        db.query(UserResource)
        .filter(UserResource.user_id == user_id, UserResource.user_type == user_type)
        .first()
    )

    # For staff types (teacher/employee), both rows belong to the same users table person.
    # Merge avatar/cover from the sibling row if the requested row is missing them.
    if user_type in ("teacher", "employee"):
        sibling_type = "employee" if user_type == "teacher" else "teacher"
        sibling = (
            db.query(UserResource)
            .filter(UserResource.user_id == user_id, UserResource.user_type == sibling_type)
            .first()
        )
        if resource is None and sibling is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        base = resource if resource is not None else sibling
        merged_avatar = (resource.avatar if resource else None) or (
            sibling.avatar if sibling else None
        )
        merged_cover = (resource.cover_image if resource else None) or (
            sibling.cover_image if sibling else None
        )
        merged_cover_focus = (
            (resource.cover_focus_y if resource and resource.cover_image else None)
            if resource is not None
            else None
        ) or (
            (sibling.cover_focus_y if sibling and sibling.cover_image else None)
            if sibling is not None
            else None
        ) or 0
        return _resource_to_response(
            base,
            db,
            avatar=merged_avatar,
            cover_image=merged_cover,
            cover_focus_y=merged_cover_focus,
        )

    if resource is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return _resource_to_response(resource, db)
