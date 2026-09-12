from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Request
import shutil
import os
import uuid
from sqlalchemy.orm import Session

from ....core import get_db
from ....auth import get_current_active_user
from .... import models, schemas
from ..websocket import broadcast_public_data_update
from ....utils.file_utils import delete_local_file
from ....services.storage_service import StorageService

router = APIRouter()


def _is_admin(user: models.User) -> bool:
    """Small helper to restrict admin endpoints."""
    role_id = getattr(user, "role", None)
    if role_id is None:
        return False
    try:
        return int(role_id) == 1
    except (TypeError, ValueError):
        return False


@router.get("/public", response_model=List[schemas.PartnerResponse])
def list_public_partners(
    db: Session = Depends(get_db),
    is_active: bool = True,
) -> List[schemas.PartnerResponse]:
    """
    Public endpoint used by the mobile app.

    Returns active partners ordered by sort_order then name.
    """
    query = db.query(models.Partner)
    if is_active is not None:
        query = query.filter(models.Partner.is_active == is_active)

    partners = (
        query.order_by(
            models.Partner.sort_order.asc(),
            models.Partner.name.asc(),
        )
        .all()
    )
    
    responses = []
    for p in partners:
        p_dict = p.__dict__.copy()
        p_dict['image_urls'] = [img.image_url for img in p.images]
        responses.append(schemas.PartnerResponse.model_validate(p_dict))
    
    return responses


@router.get("", response_model=List[schemas.PartnerResponse])
def list_partners_admin(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    skip: int = 0,
    limit: int = Query(100, le=200),
    is_active: Optional[bool] = None,
    category: Optional[str] = None,
    branch_id: Optional[int] = None,
) -> List[schemas.PartnerResponse]:
    """
    Admin: list partners with optional filters.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    query = db.query(models.Partner)

    if is_active is not None:
        query = query.filter(models.Partner.is_active == is_active)
    if category:
        query = query.filter(models.Partner.category == category)
    if branch_id:
        query = query.filter(models.Partner.branch_id == branch_id)

    partners = (
        query.order_by(
            models.Partner.sort_order.asc(),
            models.Partner.name.asc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    responses = []
    for p in partners:
        p_dict = p.__dict__.copy()
        p_dict['image_urls'] = [img.image_url for img in p.images]
        responses.append(schemas.PartnerResponse.model_validate(p_dict))
    
    return responses


@router.post(
    "",
    response_model=schemas.PartnerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_partner(
    body: schemas.PartnerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.PartnerResponse:
    """
    Admin: create a partner entry for the app home screen.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    data = body.model_dump(exclude_unset=True)
    image_urls = data.pop("image_urls", [])
    
    partner = models.Partner(**data)
    
    for idx, url in enumerate(image_urls):
        partner.images.append(models.PartnerImage(image_url=url, sort_order=idx))
        
    db.add(partner)
    db.commit()
    db.refresh(partner)
    
    await broadcast_public_data_update("partners")
    
    p_dict = partner.__dict__.copy()
    p_dict['image_urls'] = [img.image_url for img in partner.images]
    return schemas.PartnerResponse.model_validate(p_dict)


@router.put("/{partner_id}", response_model=schemas.PartnerResponse)
async def update_partner(
    partner_id: int,
    body: schemas.PartnerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.PartnerResponse:
    """
    Admin: update a partner.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    partner = db.query(models.Partner).filter(models.Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Partner not found",
        )

    data = body.model_dump(exclude_unset=True)

    urls_to_delete_on_success = []

    # Handle logo_url change — mark old file for deletion if replaced
    if "logo_url" in data:
        old_logo = partner.logo_url
        new_logo = data["logo_url"]
        if old_logo and old_logo != new_logo:
             urls_to_delete_on_success.append(old_logo)
    
    if "image_urls" in data:
        image_urls = data.pop("image_urls")
        
        # Mark old images from disk for deletion that are not in the new list
        old_urls = {img.image_url for img in partner.images if img.image_url}
        new_urls = {url for url in image_urls if url}
        urls_to_delete_on_success.extend(old_urls - new_urls)
            
        # Clear existing images
        partner.images.clear()
        
        # Add new images
        for idx, url in enumerate(image_urls):
            partner.images.append(models.PartnerImage(image_url=url, sort_order=idx))

    for field, value in data.items():
        setattr(partner, field, value)

    db.commit()
    db.refresh(partner)
    
    for url in urls_to_delete_on_success:
        from ....models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        StorageService.delete_file(url, settings)
    
    await broadcast_public_data_update("partners")
    
    p_dict = partner.__dict__.copy()
    p_dict['image_urls'] = [img.image_url for img in partner.images]
    return schemas.PartnerResponse.model_validate(p_dict)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> None:
    """
    Admin: delete a partner.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    partner = db.query(models.Partner).filter(models.Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Partner not found",
        )

    # Determine physical files to delete beforehand
    urls_to_delete_on_success = []
    if partner.logo_url:
        urls_to_delete_on_success.append(partner.logo_url)
    for img in partner.images:
        if img.image_url:
            urls_to_delete_on_success.append(img.image_url)

    db.delete(partner)
    db.commit()
    
    # Safely delete physical files post commit
    for url in urls_to_delete_on_success:
        from ....models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        StorageService.delete_file(url, settings)
    
    await broadcast_public_data_update("partners")
    return None

@router.post("/upload-image")
async def upload_partner_image(
    request: Request,
    image: UploadFile = File(...),
    is_logo: bool = Query(False, description="Whether to crop as a 9:4 logo"),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Admin: Upload an image file and return its URL.
    Used for partner logos or gallery images.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    # Validate file type
    if not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File provided is not an image",
        )

    # Create upload directory if it doesn't exist
    upload_dir = "uploads/partners"
    os.makedirs(upload_dir, exist_ok=True)

    # Always save as JPEG for consistency after processing
    unique_filename = f"partner_{uuid.uuid4().hex[:10]}.jpg"
    file_path = os.path.join(upload_dir, unique_filename)

    # Read, center-crop to 1:1 square, resize to 400x400
    try:
        from PIL import Image as PilImage
        import io

        contents = await image.read()
        img = PilImage.open(io.BytesIO(contents)).convert("RGB")

        if is_logo:
            # Center-crop to 9:4 aspect ratio (matches partner card image area)
            w, h = img.size
            target_ratio = 9 / 4  # width:height
            current_ratio = w / h

            if current_ratio > target_ratio:
                # Image is wider than target — crop width
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            else:
                # Image is taller than target — crop height
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))

            # Resize to 450×200 (9:4)
            img = img.resize((450, 200), PilImage.LANCZOS)
        else:
            # For gallery images, just resize if too large but maintain aspect ratio
            img.thumbnail((1920, 1920), PilImage.LANCZOS)

        # Save to buffer as high-quality JPEG
        out_buffer = io.BytesIO()
        img.save(out_buffer, "JPEG", quality=90, optimize=True)
        img_bytes = out_buffer.getvalue()

        # Upload using StorageService
        image_url = StorageService.upload_file(
            file_data=img_bytes,
            folder="partners",
            filename=unique_filename,
            content_type="image/jpeg"
        )
        
        if not image_url:
            raise HTTPException(status_code=500, detail="Failed to upload image via StorageService")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not process image: {str(e)}",
        )

    if image_url.startswith('/'):
        base_url = str(request.base_url).rstrip("/")
        if "192.168" in base_url and base_url.startswith("https"):
            base_url = base_url.replace("https://", "http://")
        final_url = f"{base_url}{image_url}"
    else:
        final_url = image_url
        
    return {"url": final_url}


@router.delete("/upload-image")
async def delete_partner_image(
    url: str,
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Admin: Delete a single partner image file by its relative URL.
    The `url` query parameter should be a relative path like /uploads/partners/...
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    from ....core import SessionLocal
    from ....models.settings import SystemSettings
    with SessionLocal() as db:
        settings = db.query(SystemSettings).first()
        success = StorageService.delete_file(url, settings)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or could not be deleted",
        )
    return {"detail": "deleted"}


