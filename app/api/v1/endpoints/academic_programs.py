from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, List, Dict, Optional
import uuid, shutil
from pathlib import Path
from ....core.database import get_db
from ....auth.dependencies import get_current_active_user
from app import models, schemas
from ....api.v1.websocket import broadcast_public_data_update
from ....utils.file_utils import delete_local_file
from ....services.storage_service import StorageService

router = APIRouter()

UPLOAD_DIR = Path("uploads/academic_programs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class DeleteImageRequest(BaseModel):
    url: str

def _get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("", response_model=List[schemas.AcademicProgram])
def read_academic_programs(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None
) -> Any:
    """
    Retrieve academic programs.
    """
    query = db.query(models.AcademicProgram)
    if is_active is not None:
        query = query.filter(models.AcademicProgram.is_active == is_active)
    
    programs = query.order_by(models.AcademicProgram.sort_order.asc(), models.AcademicProgram.id.asc()).offset(skip).limit(limit).all()
    
    # Fetch images
    program_ids = [p.id for p in programs]
    images_by_program: Dict[int, List[str]] = {pid: [] for pid in program_ids}
    if program_ids:
        imgs = (
            db.query(models.AcademicProgramImage)
            .filter(models.AcademicProgramImage.program_id.in_(program_ids))
            .order_by(models.AcademicProgramImage.position.asc(), models.AcademicProgramImage.id.asc())
            .all()
        )
        for img in imgs:
            images_by_program.setdefault(img.program_id, []).append(img.image_url)

    responses = []
    for p in programs:
        base = schemas.AcademicProgram.model_validate(p)
        responses.append(base.model_copy(update={"images": images_by_program.get(p.id, [])}))
        
    return responses

@router.post("", response_model=schemas.AcademicProgram, status_code=status.HTTP_201_CREATED)
async def create_academic_program(
    *,
    db: Session = Depends(get_db),
    program_in: schemas.AcademicProgramCreate,
    current_user: models.User = Depends(get_current_active_user)
) -> Any:
    """
    Create new academic program.
    """
    data = program_in.model_dump(exclude_unset=True)
    images = data.pop("images", [])
    
    program = models.AcademicProgram(**data)
    db.add(program)
    db.flush()
    
    if images:
        for idx, url in enumerate(images):
            if not url: continue
            img = models.AcademicProgramImage(
                program_id=program.id,
                image_url=url,
                position=idx + 1
            )
            db.add(img)
            
    db.commit()
    db.refresh(program)
    
    await broadcast_public_data_update("academic_programs")
    
    base = schemas.AcademicProgram.model_validate(program)
    return base.model_copy(update={"images": images})

@router.put("/{program_id}", response_model=schemas.AcademicProgram)
async def update_academic_program(
    *,
    db: Session = Depends(get_db),
    program_id: int,
    program_in: schemas.AcademicProgramUpdate,
    current_user: models.User = Depends(get_current_active_user)
) -> Any:
    """
    Update an academic program.
    """
    program = db.query(models.AcademicProgram).filter(models.AcademicProgram.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    
    update_data = program_in.model_dump(exclude_unset=True)
    images = update_data.pop("images", None)

    urls_to_delete_on_success = []

    # Detect custom_logo_url change and mark old file for deletion if replaced or removed
    if "custom_logo_url" in update_data:
        old_logo = program.custom_logo_url
        new_logo = update_data.get("custom_logo_url")
        if old_logo and old_logo != new_logo:
            urls_to_delete_on_success.append(old_logo)

    for field, value in update_data.items():
        setattr(program, field, value)
        
    if images is not None:
        old_images = db.query(models.AcademicProgramImage).filter(models.AcademicProgramImage.program_id == program.id).all()
        old_urls = {img.image_url for img in old_images if img.image_url}
        new_urls = {url for url in images if url}
        urls_to_delete_on_success.extend(old_urls - new_urls)

        db.query(models.AcademicProgramImage).filter(models.AcademicProgramImage.program_id == program.id).delete()
        for idx, url in enumerate(images):
            if not url: continue
            img = models.AcademicProgramImage(
                program_id=program.id,
                image_url=url,
                position=idx + 1
            )
            db.add(img)
            
    db.commit()
    db.refresh(program)
    
    # Safely delete physical files post commit
    for url in urls_to_delete_on_success:
        settings = db.query(models.SystemSettings).first()
        StorageService.delete_file(url, settings)
    
    # Reload images
    imgs = (
        db.query(models.AcademicProgramImage)
        .filter(models.AcademicProgramImage.program_id == program.id)
        .order_by(models.AcademicProgramImage.position.asc(), models.AcademicProgramImage.id.asc())
        .all()
    )
    image_urls = [img.image_url for img in imgs]
    
    await broadcast_public_data_update("academic_programs")
    
    base = schemas.AcademicProgram.model_validate(program)
    return base.model_copy(update={"images": image_urls})

@router.delete("/{program_id}", response_model=schemas.AcademicProgram)
async def delete_academic_program(
    *,
    db: Session = Depends(get_db),
    program_id: int,
    current_user: models.User = Depends(get_current_active_user)
) -> Any:
    """
    Delete an academic program.
    """
    program = db.query(models.AcademicProgram).filter(models.AcademicProgram.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
        
    # Determine physical files to delete beforehand
    urls_to_delete_on_success = []
    if program.custom_logo_url:
        urls_to_delete_on_success.append(program.custom_logo_url)
    images = db.query(models.AcademicProgramImage).filter(models.AcademicProgramImage.program_id == program.id).all()
    for img in images:
        if img.image_url:
            urls_to_delete_on_success.append(img.image_url)

    db.delete(program)
    db.commit()
    
    # Safely delete physical files post commit
    for url in urls_to_delete_on_success:
        settings = db.query(models.SystemSettings).first()
        StorageService.delete_file(url, settings)
    
    await broadcast_public_data_update("academic_programs")
    
    # Pydantic validation might complain if we return a deleted object directly, 
    # but since response_model is schemas.AcademicProgram, it's safer to just return None 
    # and change status code to 204 or return empty dict if it didn't complain before. 
    # To keep consistency, we'll try to just return the program.
    # Note: images will be empty array for deleted object usually.
    return program

@router.post("/upload-image")
async def upload_program_image(
    request: Request,
    image: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Upload an image for an academic program.
    """
    if str(current_user.role) != "1": # basic admin check
        raise HTTPException(status_code=403, detail="Admin only")

    allowed = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    if image.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP allowed")

    contents = await image.read()
    url_path = StorageService.upload_file(
        file_data=contents,
        folder="academic_programs",
        filename=image.filename,
        content_type=image.content_type
    )

    if not url_path:
        raise HTTPException(status_code=500, detail="Failed to upload image")

    if url_path.startswith('/'):
        base = _get_base_url(request)
        final_url = f"{base}{url_path}"
    else:
        final_url = url_path
        
    return JSONResponse(content={"url": final_url})

@router.delete("/upload-image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program_image(
    body: DeleteImageRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Physically delete an uploaded Academic Program image from the server.
    """
    if str(current_user.role) != "1":
        raise HTTPException(status_code=403, detail="Admin only")

    try:
        settings = db.query(models.SystemSettings).first()
        StorageService.delete_file(body.url, settings)
    except Exception:
        pass  # File may already be gone, that's fine
