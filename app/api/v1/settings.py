from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ...core import get_db
from ...auth import get_current_active_user
from ...models.user import User
from ...models.settings import SystemSettings
from ...schemas.settings import SettingsUpdate, SettingsResponse

router = APIRouter()

def _is_admin(user: User) -> bool:
    role_id = getattr(user, "role", None)
    return role_id is not None and int(role_id) == 1

@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get the company/system settings. Returns row id=1."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
        
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if not settings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settings not found")
        
    return settings

@router.put("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update company/system settings. Updates row id=1."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
        
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if not settings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settings not found")
        
    for key, value in body.model_dump().items():
        setattr(settings, key, value)
        
    db.commit()
    db.refresh(settings)
    return settings
