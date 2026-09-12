"""Public version and mobile-update compatibility endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


class OtaUpdateConfigResponse(BaseModel):
    """Fail-closed OTA configuration consumed before contacting Shorebird."""

    ota_updates_enabled: bool = False


def read_ota_updates_enabled(db: Session) -> bool:
    """Read the singleton setting, defaulting to off on any schema/DB failure."""
    try:
        value = db.execute(
            text(
                """
                SELECT ota_updates_enabled
                FROM settings
                ORDER BY id
                LIMIT 1
                """
            )
        ).scalar()
        return value is True or value == 1
    except Exception as exc:
        # Older deployments may receive this endpoint before the migration.
        # Never let that accidentally enable OTA or break app startup.
        logger.warning("OTA setting unavailable; defaulting to disabled: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False

@router.get("/version")
async def app_version():
    """
    Compatibility endpoint for Flutter app.
    Returns current API version.
    Note: Flutter app now checks stores directly for updates.
    """
    return {
        "version": "1.0.0",
        "min_required_version": "1.0.0",
        "message": "Flutter app checks Play Store / App Store directly for updates"
    }


@router.get("/update-config", response_model=OtaUpdateConfigResponse)
async def update_config(db: Session = Depends(get_db)):
    """Return the public, non-sensitive OTA kill-switch state."""
    return OtaUpdateConfigResponse(
        ota_updates_enabled=read_ota_updates_enabled(db)
    )
