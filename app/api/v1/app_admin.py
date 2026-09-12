from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
import json
import logging


def _parse_snapshot(raw) -> dict:
    """Parse a request's `previous_values` JSON snapshot into a dict (safe)."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

from ...core.database import get_db
from ...auth.dependencies import get_current_active_user
from ...models.user import User
from ...models.app_admin import AppAdmin
from ...models.feature_lock import FeatureLock
from ...models.student_profile_edit_request import StudentProfileEditRequest
from ...services import notification_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=['App Admin Control'])

class AppAdminResponse(BaseModel):
    user_id: int
    username: str
    is_super_admin: bool
    can_reset_attendance_devices: bool = False
    is_locked: bool
    locked_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class SetSuperAdminRequest(BaseModel):
    user_id: int
    is_super_admin: bool


class SetAttendanceDeviceResetPermissionRequest(BaseModel):
    user_id: int
    enabled: bool


class OtaUpdatesSettingRequest(BaseModel):
    enabled: bool


class LockFeatureRequest(BaseModel):
    feature_name: str
    is_locked: bool
    reason: Optional[str] = None


def _require_active_super_admin(db: Session, current_user: User) -> AppAdmin:
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_super_admin.in_([True, 1]),
        AppAdmin.is_locked.in_([False, 0]),
    ).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only active Super Admins can manage OTA updates",
        )
    return admin


def _read_ota_setting(db: Session) -> bool:
    try:
        value = db.execute(text("""
            SELECT ota_updates_enabled
            FROM settings
            ORDER BY id
            LIMIT 1
        """)).scalar()
        return value is True or value == 1
    except Exception as exc:
        logger.warning("Could not read OTA update setting: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False


@router.get('/ota-updates')
async def get_ota_updates_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the OTA kill switch for the Super Admin control screen."""
    _require_active_super_admin(db, current_user)
    return {'enabled': _read_ota_setting(db)}


@router.put('/ota-updates')
async def set_ota_updates_setting(
    request: OtaUpdatesSettingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enable or pause future Shorebird checks for all app installations."""
    _require_active_super_admin(db, current_user)
    try:
        settings_id = db.execute(
            text("SELECT id FROM settings ORDER BY id LIMIT 1")
        ).scalar()
        if settings_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="System settings are not initialized",
            )

        db.execute(
            text("""
                UPDATE settings
                SET ota_updates_enabled = :enabled
                WHERE id = :settings_id
            """),
            {
                'enabled': 1 if request.enabled else 0,
                'settings_id': settings_id,
            },
        )
        db.commit()

        try:
            db.execute(text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """), {
                'user_id': current_user.id,
                'action': 'OTA_UPDATES_SETTING_CHANGED',
                'details': (
                    'OTA updates enabled'
                    if request.enabled
                    else 'OTA updates paused'
                ),
                'timestamp': datetime.utcnow(),
            })
            db.commit()
        except Exception as log_error:
            db.rollback()
            logger.warning("Could not audit OTA setting change: %s", log_error)

        return {'success': True, 'enabled': bool(request.enabled)}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Could not update OTA setting: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update OTA setting",
        )

@router.get('/check-initial-setup')
async def check_initial_setup(db: Session = Depends(get_db)):
    """Check if app admin control is initialized"""
    try:
        result = db.execute(text("SELECT COUNT(*) FROM app_admins")).scalar()
        has_admins = result > 0
        
        return {
            'initialized': has_admins,
            'needs_setup': not has_admins
        }
    except Exception as e:
        logger.error(f"Error checking setup: {e}")
        return {'initialized': False, 'needs_setup': True}

@router.post('/initialize-super-admin')
async def initialize_super_admin(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Initialize the first Super Admin.
    This can only be called once when no admins exist.
    """
    try:
        # Check if any admins exist
        result = db.execute(text("SELECT COUNT(*) FROM app_admins")).scalar()
        if result > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="App admin control is already initialized. Cannot create another Super Admin this way."
            )
        
        # Create Super Admin
        app_admin = AppAdmin(
            user_id=current_user.id,
            is_super_admin=True,
            is_locked=False
        )
        db.add(app_admin)
        db.commit()  # Commit the admin record first — log is optional
        
        # Try to log the action (non-fatal if admin_logs table doesn't exist)
        try:
            log_query = text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """)
            db.execute(log_query, {
                'user_id': current_user.id,
                'action': 'SUPER_ADMIN_INITIALIZED',
                'details': f'User {current_user.username} initialized as first Super Admin',
                'timestamp': datetime.utcnow()
            })
            db.commit()
        except Exception as log_err:
            logger.warning(f"Could not write to admin_logs (table may not exist): {log_err}")
            db.rollback()
        
        logger.info(f"Initialized Super Admin: user_id={current_user.id}")
        
        return {
            'success': True,
            'message': 'You are now the Super Admin of this application',
            'user_id': current_user.id
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error initializing Super Admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize Super Admin: {str(e)}"
        )

@router.get('/list')
async def list_app_admins(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all app admins"""
    try:
        # Get all admins with explicit join
        admins = db.query(AppAdmin).join(User, AppAdmin.user_id == User.id).all()
        
        return [
            {
                'user_id': a.user_id,
                'username': a.user.username,
                'eName': a.user.eName,
                'kName': a.user.kName,
                'is_super_admin': a.is_super_admin,
                'can_reset_attendance_devices': bool(
                    getattr(a, 'can_reset_attendance_devices', False)
                ),
                'is_locked': a.is_locked,
                'locked_at': a.locked_at,
                'created_at': a.created_at
            }
            for a in admins
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing admins: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post('/set-attendance-device-reset-permission')
async def set_attendance_device_reset_permission(
    request: SetAttendanceDeviceResetPermissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Grant/revoke the sensitive primary-attendance-phone reset permission."""
    caller = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_super_admin.in_([True, 1]),
        AppAdmin.is_locked.in_([False, 0]),
    ).first()
    if not caller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only active Super Admins can grant attendance device reset access",
        )

    target = db.query(AppAdmin).filter(
        AppAdmin.user_id == request.user_id
    ).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not an App Admin",
        )
    if target.is_super_admin:
        return {
            'success': True,
            'message': 'Super Admins always have attendance device reset access',
            'enabled': True,
        }

    try:
        target.can_reset_attendance_devices = bool(request.enabled)
        db.commit()
        try:
            db.execute(text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """), {
                'user_id': current_user.id,
                'action': 'ATTENDANCE_DEVICE_RESET_PERMISSION_CHANGED',
                'details': (
                    f'Attendance device reset permission for user '
                    f'{request.user_id} set to {bool(request.enabled)}'
                ),
                'timestamp': datetime.utcnow(),
            })
            db.commit()
        except Exception as log_err:
            db.rollback()
            logger.warning(
                "Could not write attendance device permission admin log: %s",
                log_err,
            )
        return {
            'success': True,
            'message': 'Attendance device reset permission updated',
            'enabled': bool(request.enabled),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            "Error updating attendance device reset permission: %s",
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update attendance device reset permission",
        )

@router.post('/set-super-admin')
async def set_super_admin(
    request: SetSuperAdminRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Set/unset Super Admin status (Super Admin only)"""
    try:
        # Verify current user is Super Admin
        admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == current_user.id,
            AppAdmin.is_super_admin.in_([True, 1])
        ).first()
        
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Admins can modify Super Admin status"
            )
        
        # Cannot modify self
        if request.user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify your own Super Admin status"
            )
        
        # Update target user
        target_admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == request.user_id
        ).first()
        
        if not target_admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not an app admin"
            )
        
        target_admin.is_super_admin = request.is_super_admin
        db.commit()
        
        # Try to log the action (non-fatal if admin_logs table doesn't exist)
        try:
            log_query = text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """)
            db.execute(log_query, {
                'user_id': current_user.id,
                'action': 'SUPER_ADMIN_MODIFIED',
                'details': f'Super Admin status for user {request.user_id} set to {request.is_super_admin}',
                'timestamp': datetime.utcnow()
            })
            # Separate commit for log to avoid rolling back main transaction if it fails
            db.commit()
        except Exception as log_err:
            db.rollback()
            logger.warning(f"Could not write to admin_logs (table may not exist): {log_err}")
            
        return {'success': True, 'message': 'Super Admin status updated'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting Super Admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

class AddAdminRequest(BaseModel):
    user_id: int
    is_super_admin: Optional[bool] = False

@router.post('/add-admin')
async def add_admin(
    request: AddAdminRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Add a new App Admin"""
    try:
        admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == current_user.id,
            AppAdmin.is_super_admin.in_([True, 1]),
            AppAdmin.is_locked.in_([False, 0])
        ).first()
        
        if not admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only active Super Admins can add new admins")
            
        if request.is_super_admin and not admin.is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admins can create new Super Admins")

        target_user = db.query(User).filter(User.id == request.user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        existing_admin = db.query(AppAdmin).filter(AppAdmin.user_id == request.user_id).first()
        if existing_admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already an App Admin")
            
        new_admin = AppAdmin(
            user_id=request.user_id,
            is_super_admin=request.is_super_admin,
            is_locked=False
        )
        db.add(new_admin)
        db.commit()
        
        # Try to log the action (non-fatal if admin_logs table doesn't exist)
        try:
            log_query = text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """)
            db.execute(log_query, {
                'user_id': current_user.id,
                'action': 'ADMIN_ADDED',
                'details': f'Added user {request.user_id} as App Admin (Super: {request.is_super_admin})',
                'timestamp': datetime.utcnow()
            })
            db.commit()
        except Exception as log_err:
            db.rollback()
            logger.warning(f"Could not write to admin_logs (table may not exist): {log_err}")
            
        return {'success': True, 'message': 'Admin added successfully'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding admin: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post('/remove-admin')
async def remove_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Remove an App Admin"""
    try:
        admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == current_user.id,
            AppAdmin.is_super_admin.in_([True, 1]),
            AppAdmin.is_locked.in_([False, 0])
        ).first()
        
        if not admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only active Super Admins can remove admins")
            
        target_admin = db.query(AppAdmin).filter(AppAdmin.user_id == user_id).first()
        if not target_admin:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
            
        if target_admin.is_super_admin and not admin.is_super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sub Admins cannot remove Super Admins")
            
        db.delete(target_admin)
        db.commit()
        
        # Try to log the action (non-fatal if admin_logs table doesn't exist)
        try:
            log_query = text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """)
            db.execute(log_query, {
                'user_id': current_user.id,
                'action': 'ADMIN_REMOVED',
                'details': f'Removed user {user_id} from App Admins',
                'timestamp': datetime.utcnow()
            })
            db.commit()
        except Exception as log_err:
            db.rollback()
            logger.warning(f"Could not write to admin_logs (table may not exist): {log_err}")
            
        return {'success': True, 'message': 'Admin removed successfully'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing admin: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post('/lock-admin')
async def lock_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lock an admin (Super Admin only)"""
    try:
        # Verify current user is an active Super Admin
        admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == current_user.id,
            AppAdmin.is_super_admin.in_([True, 1]),
            AppAdmin.is_locked.in_([False, 0])
        ).first()
        
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only active Super Admins can lock admins"
            )
        
        # Cannot lock self
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot lock yourself"
            )
        
        # Lock the admin
        target_admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == user_id
        ).first()
        
        if not target_admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin not found"
            )
            
        if target_admin.is_super_admin and not admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sub Admins cannot lock Super Admins"
            )
        
        target_admin.is_locked = True
        target_admin.locked_at = datetime.utcnow()
        target_admin.locked_by = current_user.id
        db.commit()
        
        # Try to log the action (non-fatal if admin_logs table doesn't exist)
        try:
            log_query = text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """)
            db.execute(log_query, {
                'user_id': current_user.id,
                'action': 'ADMIN_LOCKED',
                'details': f'Locked admin user {user_id}',
                'timestamp': datetime.utcnow()
            })
            db.commit()
        except Exception as log_err:
            db.rollback()
            logger.warning(f"Could not write to admin_logs (table may not exist): {log_err}")
            
        return {'success': True, 'message': 'Admin locked successfully'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error locking admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post('/unlock-admin')
async def unlock_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Unlock an admin (Super Admin only)"""
    try:
        admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == current_user.id,
            AppAdmin.is_super_admin.in_([True, 1]),
            AppAdmin.is_locked.in_([False, 0])
        ).first()
        
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only active Super Admins can unlock admins"
            )
        
        target_admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == user_id
        ).first()
        
        if not target_admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin not found"
            )
            
        if target_admin.is_super_admin and not admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sub Admins cannot unlock Super Admins"
            )
        
        target_admin.is_locked = False
        target_admin.locked_at = None
        target_admin.locked_by = None
        db.commit()
        
        # Try to log the action (non-fatal if admin_logs table doesn't exist)
        try:
            log_query = text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """)
            db.execute(log_query, {
                'user_id': current_user.id,
                'action': 'ADMIN_UNLOCKED',
                'details': f'Unlocked admin user {user_id}',
                'timestamp': datetime.utcnow()
            })
            db.commit()
        except Exception as log_err:
            db.rollback()
            logger.warning(f"Could not write to admin_logs (table may not exist): {log_err}")
            
        return {'success': True, 'message': 'Admin unlocked successfully'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error unlocking admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get('/check-permission')
async def check_permission(
    feature: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Check if user has permission for a feature"""
    try:
        # Check if user is an app admin
        admin = db.query(AppAdmin).filter(
            AppAdmin.user_id == current_user.id
        ).first()
        
        if not admin:
            return {
                'has_permission': False,
                'reason': 'Not an app admin'
            }
        
        if admin.is_locked:
            return {
                'has_permission': False,
                'reason': 'Admin account is locked',
                'locked_at': admin.locked_at
            }
        
        # Super Admin has all permissions
        if admin.is_super_admin:
            return {
                'has_permission': True,
                'is_super_admin': True
            }
        
        # Regular admin - check feature lock (feature_locks is where
        # lock-feature/unlock-feature write; admin_features is legacy)
        lock = db.query(FeatureLock).filter(
            FeatureLock.feature_id == feature,
            FeatureLock.is_locked.in_([True, 1])
        ).first()

        if lock:
            return {
                'has_permission': False,
                'reason': 'Feature is locked',
                'feature': feature
            }
        
        return {
            'has_permission': True,
            'is_super_admin': False
        }
    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        return {
            'has_permission': False,
            'reason': f'Error: {str(e)}'
        }

@router.get('/feature-locks')
async def get_feature_locks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all feature locks (available to all authenticated users)"""
    try:
        locks = db.query(FeatureLock).all()
        return {
            'locked_features': {lock.feature_id: lock.is_locked for lock in locks},
            'feature_names': {lock.feature_id: lock.feature_name for lock in locks}
        }
    except Exception as e:
        logger.error(f"Error getting feature locks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post('/lock-feature')
async def lock_feature(
    feature_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lock a feature (auto-creates if doesn't exist)"""
    try:
        admin = db.query(AppAdmin).filter(AppAdmin.user_id == current_user.id).first()
        if not admin or not admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Admins can lock features"
            )
        
        # Get or create feature
        feature = db.query(FeatureLock).filter(FeatureLock.feature_id == feature_id).first()
        if not feature:
            # Auto-create feature with human-readable name
            feature_name = feature_id.replace('_', ' ').title()
            feature = FeatureLock(
                feature_id=feature_id,
                feature_name=feature_name,
                is_locked=True,
                locked_by=current_user.id,
                locked_at=datetime.utcnow()
            )
            db.add(feature)
            logger.info(f"Auto-created feature: {feature_name}")
        else:
            feature.is_locked = True
            feature.locked_by = current_user.id
            feature.locked_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Super Admin {current_user.id} locked feature {feature_id}")
        
        return {'success': True, 'message': f'Feature {feature.feature_name} locked'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error locking feature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post('/unlock-feature')
async def unlock_feature(
    feature_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Unlock a feature (auto-creates if doesn't exist)"""
    try:
        admin = db.query(AppAdmin).filter(AppAdmin.user_id == current_user.id).first()
        if not admin or not admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Admins can unlock features"
            )
        
        # Get or create feature
        feature = db.query(FeatureLock).filter(FeatureLock.feature_id == feature_id).first()
        if not feature:
            # Auto-create feature as unlocked
            feature_name = feature_id.replace('_', ' ').title()
            feature = FeatureLock(
                feature_id=feature_id,
                feature_name=feature_name,
                is_locked=False
            )
            db.add(feature)
            logger.info(f"Auto-created feature: {feature_name}")
        else:
            feature.is_locked = False
            feature.locked_by = None
            feature.locked_at = None
        
        db.commit()
        
        logger.info(f"Super Admin {current_user.id} unlocked feature {feature_id}")
        
        return {'success': True, 'message': f'Feature {feature.feature_name} unlocked'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error unlocking feature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

class BulkFeatureLockRequest(BaseModel):
    # Full list of known feature ids from the client. Rows are upserted so
    # features that were never toggled individually (no row yet) still get
    # locked/unlocked by the bulk actions.
    feature_ids: Optional[List[str]] = None


def _upsert_feature_locks(db: Session, feature_ids: List[str]):
    existing = {f.feature_id for f in db.query(FeatureLock.feature_id).all()}
    for fid in feature_ids:
        if fid not in existing:
            db.add(FeatureLock(
                feature_id=fid,
                feature_name=fid.replace('_', ' ').title(),
                is_locked=False
            ))
    db.flush()


@router.post('/lock-all-features')
async def lock_all_features(
    request: Optional[BulkFeatureLockRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lock all features"""
    try:
        admin = db.query(AppAdmin).filter(AppAdmin.user_id == current_user.id).first()
        if not admin or not admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Admins can lock all features"
            )

        if request and request.feature_ids:
            _upsert_feature_locks(db, request.feature_ids)

        db.query(FeatureLock).update({
            FeatureLock.is_locked: True,
            FeatureLock.locked_by: current_user.id,
            FeatureLock.locked_at: datetime.utcnow()
        })
        db.commit()
        
        logger.info(f"Super Admin {current_user.id} locked all features")
        
        return {'success': True, 'message': 'All features locked'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error locking all features: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post('/unlock-all-features')
async def unlock_all_features(
    request: Optional[BulkFeatureLockRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Unlock all features"""
    try:
        admin = db.query(AppAdmin).filter(AppAdmin.user_id == current_user.id).first()
        if not admin or not admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Admins can unlock all features"
            )

        if request and request.feature_ids:
            _upsert_feature_locks(db, request.feature_ids)

        db.query(FeatureLock).update({
            FeatureLock.is_locked: False,
            FeatureLock.locked_by: None,
            FeatureLock.locked_at: None
        })
        db.commit()
        
        logger.info(f"Super Admin {current_user.id} unlocked all features")
        
        return {'success': True, 'message': 'All features unlocked'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error unlocking all features: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# ---------------------------------------------------------
# Student Profile Edit Requests
# ---------------------------------------------------------

from ...models.student_profile_edit_request import StudentProfileEditRequest

class EditRequestAction(BaseModel):
    reason: Optional[str] = None
    # Provide fields here to override the requested changes before approval
    kName: Optional[str] = None
    eName: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    is_foreigner: Optional[int] = None
    student_phone: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None
    commune: Optional[str] = None
    village: Optional[str] = None
    student_noted: Optional[str] = None
    branch: Optional[str] = None
    previousSchool: Optional[str] = None


def _resolve_requester_name(db: Session, requested_by: int, requested_by_type) -> str:
    """Resolve a profile-edit requester's display name from the CORRECT table.

    Parents are stored in `parents` (and ``requested_by`` holds parents.id for a
    parent); teachers/admins are in `users`. Looking a parent up in `users`
    returns the wrong row (or nothing) — that is what made requester names show
    as "Unknown". We query the table that matches ``requested_by_type`` first,
    then fall back to the other table so a mislabelled request still resolves.
    """
    parent_sql = "SELECT fatherName, motherName FROM parents WHERE id = :rid"
    user_sql = "SELECT kName, eName FROM users WHERE id = :rid"
    is_parent = (requested_by_type or "").lower() == "parent"
    for sql in ([parent_sql, user_sql] if is_parent else [user_sql, parent_sql]):
        try:
            row = db.execute(text(sql), {"rid": requested_by}).fetchone()
            if row and (row[0] or row[1]):
                return row[0] or row[1]
        except Exception as e:
            logger.error(
                f"Error resolving requester name for {requested_by} ({requested_by_type}): {e}"
            )
    return f"ID:{requested_by}"


@router.get('/pending-profile-edits')
async def get_pending_profile_edits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all pending student profile edit requests."""
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_locked == False
    ).first()
    if not admin:
        raise HTTPException(status_code=403, detail="Only active App Admins can view these requests")
        
    requests = db.query(StudentProfileEditRequest).filter(StudentProfileEditRequest.status == 'pending').all()
    
    # We can also fetch student names for context
    result = []
    for req in requests:
        student_data = db.execute(text("""
            SELECT kName, eName, gender, dob, is_foreigner, student_phone,
                   province, district, commune, village, student_noted, branch, previousSchool
            FROM students WHERE id = :sid
        """), {"sid": req.student_id}).fetchone()

        # User who requested — resolved from the correct table (parents vs users)
        req_name = _resolve_requester_name(db, req.requested_by, req.requested_by_type)

        # Student's current avatar (so the UI can show the photo change).
        avatar_row = db.execute(text(
            "SELECT avatar FROM users_resource WHERE user_id = :sid AND user_type = 'student' LIMIT 1"
        ), {"sid": req.student_id}).fetchone()
        current_avatar = avatar_row[0] if avatar_row else None

        result.append({
            "id": req.id,
            "student_id": req.student_id,
            "current_student_data": {
                "kName": student_data[0] if student_data else None,
                "eName": student_data[1] if student_data else None,
                "gender": student_data[2] if student_data else None,
                "dob": student_data[3].isoformat() if student_data and student_data[3] else None,
                "is_foreigner": student_data[4] if student_data else None,
                "student_phone": student_data[5] if student_data else None,
                "province": student_data[6] if student_data else None,
                "district": student_data[7] if student_data else None,
                "commune": student_data[8] if student_data else None,
                "village": student_data[9] if student_data else None,
                "student_noted": student_data[10] if student_data else None,
                "branch": student_data[11] if student_data else None,
                "previousSchool": student_data[12] if student_data else None,
                "avatar": current_avatar,
            },
            "requested_by": req.requested_by,
            "requester_name": req_name,
            "requested_by_type": req.requested_by_type,
            "requested_changes": {
                "kName": req.kName,
                "eName": req.eName,
                "gender": req.gender,
                "dob": req.dob,
                "is_foreigner": req.is_foreigner,
                "student_phone": req.student_phone,
                "province": req.province,
                "district": req.district,
                "commune": req.commune,
                "village": req.village,
                "previousSchool": req.previousSchool,
                "student_noted": req.student_noted,
                "branch": req.branch,
                "avatar": req.avatar,
            },
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        })
        
    return {"requests": result}

import calendar
from datetime import date, datetime, timedelta

@router.get('/profile-edit-history')
async def get_profile_edit_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get history of approved/rejected student profile edit requests."""
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_locked == False
    ).first()
    if not admin:
        raise HTTPException(status_code=403, detail="Only active App Admins can view history")

    query = db.query(StudentProfileEditRequest).filter(
        StudentProfileEditRequest.status.in_(['approved', 'rejected'])
    )

    if start_date and end_date:
        query = query.filter(
            StudentProfileEditRequest.created_at >= f"{start_date} 00:00:00",
            StudentProfileEditRequest.created_at <= f"{end_date} 23:59:59"
        )
    else:
        # Default to current month
        today = date.today()
        first_day = today.replace(day=1)
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        query = query.filter(
            StudentProfileEditRequest.created_at >= f"{first_day} 00:00:00",
            StudentProfileEditRequest.created_at <= f"{last_day} 23:59:59"
        )

    requests = query.order_by(StudentProfileEditRequest.created_at.desc()).limit(100).all()

    result = []
    for req in requests:
        try:
            # Get requester name from the correct table (parents vs users)
            req_name = _resolve_requester_name(db, req.requested_by, req.requested_by_type)

            # Get student name
            student_row = db.execute(text("SELECT kName, eName FROM students WHERE id = :sid"), {"sid": req.student_id}).fetchone()
            student_name = (student_row[0] or student_row[1]) if student_row else f"Student #{req.student_id}"

            result.append({
                "id": req.id,
                "student_id": req.student_id,
                "student_name": student_name,
                "current_student_data": _parse_snapshot(req.previous_values),
                "requested_by": req.requested_by,
                "requester_name": req_name,
                "requested_by_type": str(req.requested_by_type or ''),
                "status": str(req.status or ''),
                "reason": str(req.reason) if req.reason else None,
                "requested_changes": {
                    "kName": req.kName,
                    "eName": req.eName,
                    "gender": req.gender,
                    "dob": str(req.dob) if req.dob else None,
                    "is_foreigner": req.is_foreigner,
                    "student_phone": req.student_phone,
                    "province": req.province,
                    "district": req.district,
                    "commune": req.commune,
                    "village": req.village,
                    "previousSchool": req.previousSchool,
                    "student_noted": req.student_noted,
                    "branch": req.branch,
                    "avatar": req.avatar,
                },
                "created_at": req.created_at.isoformat() if req.created_at else None,
                "updated_at": req.updated_at.isoformat() if req.updated_at else None,
            })
        except Exception as ex:
            logger.error(f"Error serializing history record {req.id}: {ex}")
            continue

    return {"requests": result}


@router.get('/my-profile-edit-history')
async def get_my_profile_edit_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get own profile edit request history (for parents/non-admins)."""
    # requested_by stores current_user.id — that is parents.id for a parent and
    # users.id for a teacher/admin. Either way it matches the caller's own id here.
    my_id = current_user.id

    query = db.query(StudentProfileEditRequest).filter(
        StudentProfileEditRequest.requested_by == my_id,
    )

    if start_date and end_date:
        query = query.filter(
            StudentProfileEditRequest.created_at >= f"{start_date} 00:00:00",
            StudentProfileEditRequest.created_at <= f"{end_date} 23:59:59"
        )
    else:
        # Default to current month
        today = date.today()
        first_day = today.replace(day=1)
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        query = query.filter(
            StudentProfileEditRequest.created_at >= f"{first_day} 00:00:00",
            StudentProfileEditRequest.created_at <= f"{last_day} 23:59:59"
        )

    reqs = query.order_by(StudentProfileEditRequest.created_at.desc()).limit(50).all()

    result = []
    for req in reqs:
        try:
            student_row = db.execute(text("SELECT kName, eName FROM students WHERE id = :sid"), {"sid": req.student_id}).fetchone()
            student_name = (student_row[0] or student_row[1]) if student_row else f"Student #{req.student_id}"
            result.append({
                "id": req.id,
                "student_id": req.student_id,
                "student_name": student_name,
                "current_student_data": _parse_snapshot(req.previous_values),
                "status": str(req.status or 'pending'),
                "reason": str(req.reason) if req.reason else None,
                "requested_changes": {
                    "kName": req.kName,
                    "eName": req.eName,
                    "gender": req.gender,
                    "dob": str(req.dob) if req.dob else None,
                    "is_foreigner": req.is_foreigner,
                    "student_phone": req.student_phone,
                    "province": req.province,
                    "district": req.district,
                    "commune": req.commune,
                    "village": req.village,
                    "previousSchool": req.previousSchool,
                    "student_noted": req.student_noted,
                    "branch": req.branch,
                    "avatar": req.avatar,
                },
                "created_at": req.created_at.isoformat() if req.created_at else None,
                "updated_at": req.updated_at.isoformat() if req.updated_at else None,
            })
        except Exception as ex:
            logger.error(f"Error serializing own history record {req.id}: {ex}")
            continue

    return {"requests": result}

def _send_profile_edit_reply_bg(
    request_id: int,
    student_id: int,
    requested_by: int,
    requested_by_type: str,
    status: str,
    admin_name: str,
    reason: Optional[str] = None
):
    from ...core.database import SessionLocal
    from ...services import notification_service
    db = SessionLocal()
    try:
        student_data = db.execute(text("SELECT kName, eName FROM students WHERE id = :sid"), {"sid": student_id}).fetchone()
        student_name = f"{student_data[0]} ({student_data[1]})" if (student_data and student_data[0] and student_data[1]) else (student_data[0] or student_data[1] if student_data else f"Student #{student_id}")
        
        title = "Profile Edit Approved" if status == 'approved' else "Profile Edit Rejected"
        if status == 'approved':
            body = f"Your request to edit {student_name}'s profile has been approved by {admin_name}."
        else:
            body = f"Your request to edit {student_name}'s profile has been rejected by {admin_name}. Reason: {reason or 'No reason provided'}"
            
        if requested_by_type == 'parent':
            user_type = 'parent'
            device_tokens = notification_service.get_parent_user_device_tokens(
                db,
                requested_by,
            )
        else:
            user_type = 'teacher'
            device_tokens = notification_service.get_teacher_device_tokens(
                db,
                requested_by,
            )
        
        notification_service.send_notification(
            device_tokens=device_tokens,
            title=title,
            body=body,
            data={
                "type": "profile_edit_reply",
                "request_id": str(request_id),
                "student_id": str(student_id),
                "notification_key": f"profile_edit_reply:{request_id}:{status}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=[{"id": requested_by, "user_type": user_type}],
            collapse_id=f"profile_edit_reply_{request_id}",
        )
    except Exception as e:
        logger.error(f"Error in background profile edit notification task: {e}")
    finally:
        db.close()

async def _approve_profile_edit_core(
    request_id: int,
    action: EditRequestAction,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
):
    """Apply an approval after the calling surface has authorized the reviewer."""
    edit_req = db.query(StudentProfileEditRequest).filter(StudentProfileEditRequest.id == request_id).first()
    if not edit_req or edit_req.status != 'pending':
        raise HTTPException(status_code=404, detail="Pending request not found")
        
    # Apply modifications if admin changed anything before approving
    if action.kName is not None: edit_req.kName = action.kName
    if action.eName is not None: edit_req.eName = action.eName
    if action.gender is not None: edit_req.gender = action.gender
    if action.dob is not None: edit_req.dob = action.dob
    if action.is_foreigner is not None: edit_req.is_foreigner = action.is_foreigner
    if action.student_phone is not None: edit_req.student_phone = action.student_phone
    if action.province is not None: edit_req.province = action.province
    if action.district is not None: edit_req.district = action.district
    if action.commune is not None: edit_req.commune = action.commune
    if action.village is not None: edit_req.village = action.village
    if action.previousSchool is not None: edit_req.previousSchool = action.previousSchool
    if action.student_noted is not None: edit_req.student_noted = action.student_noted
    if action.branch is not None: edit_req.branch = action.branch
    
    # Generate UPDATE query for students table
    updates = []
    params = {"student_id": edit_req.student_id}
    
    if edit_req.kName is not None: updates.append("kName = :kName"); params["kName"] = edit_req.kName
    if edit_req.eName is not None: updates.append("eName = :eName"); params["eName"] = edit_req.eName
    if edit_req.gender is not None: updates.append("gender = :gender"); params["gender"] = edit_req.gender
    if edit_req.dob is not None: updates.append("dob = :dob"); params["dob"] = edit_req.dob
    if edit_req.is_foreigner is not None: updates.append("is_foreigner = :is_foreigner"); params["is_foreigner"] = edit_req.is_foreigner
    if edit_req.student_phone is not None: updates.append("student_phone = :student_phone"); params["student_phone"] = edit_req.student_phone
    if edit_req.province is not None: updates.append("province = :province"); params["province"] = edit_req.province
    if edit_req.district is not None: updates.append("district = :district"); params["district"] = edit_req.district
    if edit_req.commune is not None: updates.append("commune = :commune"); params["commune"] = edit_req.commune
    if edit_req.village is not None: updates.append("village = :village"); params["village"] = edit_req.village
    if edit_req.previousSchool is not None: updates.append("previousSchool = :previousSchool"); params["previousSchool"] = edit_req.previousSchool
    if edit_req.student_noted is not None: updates.append("student_noted = :student_noted"); params["student_noted"] = edit_req.student_noted
    if edit_req.branch is not None: updates.append("branch = :branch"); params["branch"] = edit_req.branch

    # Stage the approved avatar onto the student's resource so it persists in the
    # SAME commit as the field changes. The replaced file is deleted only after
    # that commit succeeds (so a failed commit never orphans the live photo).
    old_avatar_to_delete = None
    if edit_req.avatar:
        from ...models.user_resource import UserResource
        resource = db.query(UserResource).filter(
            UserResource.user_id == edit_req.student_id,
            UserResource.user_type == 'student'
        ).first()
        if resource is None:
            resource = UserResource(user_id=edit_req.student_id, user_type='student', status=1)
            db.add(resource)
        if resource.avatar and resource.avatar != edit_req.avatar:
            old_avatar_to_delete = resource.avatar
        resource.avatar = edit_req.avatar

    if updates:
        updates.append("updated_at = NOW()")
        set_clause = ", ".join(updates)
        update_query = text(f"UPDATE students SET {set_clause} WHERE id = :student_id")

        try:
            db.execute(update_query, params)
            edit_req.status = 'approved'
            edit_req.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error applying profile edit: {e}")
            raise HTTPException(status_code=500, detail="Failed to apply update")

    else:
        edit_req.status = 'approved'
        edit_req.updated_at = datetime.utcnow()
        db.commit()

    # Old avatar file removed only after the new one is safely committed.
    if old_avatar_to_delete:
        try:
            from ...models.settings import SystemSettings
            from ...services.storage_service import StorageService
            StorageService.delete_file(old_avatar_to_delete, db.query(SystemSettings).first())
        except Exception as e:
            logger.warning(f"Failed to delete old avatar {old_avatar_to_delete}: {e}")

    # Send push notification to the requester in background
    admin_name = current_user.kName or current_user.eName or "Admin"
    background_tasks.add_task(
        _send_profile_edit_reply_bg,
        request_id=edit_req.id,
        student_id=edit_req.student_id,
        requested_by=edit_req.requested_by,
        requested_by_type=edit_req.requested_by_type,
        status='approved',
        admin_name=admin_name
    )
        
    return {"success": True, "message": "Profile edit approved successfully"}


@router.patch('/profile-edits/{request_id}/approve')
async def approve_profile_edit(
    request_id: int,
    action: EditRequestAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Approve a request from Flutter after enforcing active App Admin access."""
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_locked == False,
    ).first()
    if not admin:
        raise HTTPException(
            status_code=403,
            detail="Only active App Admins can approve requests",
        )

    return await _approve_profile_edit_core(
        request_id=request_id,
        action=action,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


async def _reject_profile_edit_core(
    request_id: int,
    action: EditRequestAction,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
):
    """Apply a rejection after the calling surface has authorized the reviewer."""
    edit_req = db.query(StudentProfileEditRequest).filter(StudentProfileEditRequest.id == request_id).first()
    if not edit_req or edit_req.status != 'pending':
        raise HTTPException(status_code=404, detail="Pending request not found")
        
    edit_req.status = 'rejected'
    edit_req.reason = action.reason
    edit_req.updated_at = datetime.utcnow()
    db.commit()

    # Discard the staged avatar file — it was never applied to the student.
    if edit_req.avatar:
        try:
            from ...models.settings import SystemSettings
            from ...services.storage_service import StorageService
            StorageService.delete_file(edit_req.avatar, db.query(SystemSettings).first())
        except Exception as e:
            logger.warning(f"Failed to delete rejected avatar {edit_req.avatar}: {e}")

    # Send push notification to the requester in background
    admin_name = current_user.kName or current_user.eName or "Admin"
    background_tasks.add_task(
        _send_profile_edit_reply_bg,
        request_id=edit_req.id,
        student_id=edit_req.student_id,
        requested_by=edit_req.requested_by,
        requested_by_type=edit_req.requested_by_type,
        status='rejected',
        admin_name=admin_name,
        reason=action.reason
    )
    
    return {"success": True, "message": "Profile edit rejected successfully"}


@router.patch('/profile-edits/{request_id}/reject')
async def reject_profile_edit(
    request_id: int,
    action: EditRequestAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Reject a request from Flutter after enforcing active App Admin access."""
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_locked == False,
    ).first()
    if not admin:
        raise HTTPException(
            status_code=403,
            detail="Only active App Admins can reject requests",
        )

    return await _reject_profile_edit_core(
        request_id=request_id,
        action=action,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pending student registrations (children added by active parents, status = 2)
# ─────────────────────────────────────────────────────────────────────────────

def _require_active_app_admin(db: Session, current_user: User):
    """Raise 403 unless the caller is an active (unlocked) App Admin."""
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == current_user.id,
        AppAdmin.is_locked == False
    ).first()
    if not admin:
        raise HTTPException(status_code=403, detail="Only active App Admins can manage student registrations")
    return admin


@router.get('/pending-students')
async def get_pending_students(
    submitted_by_parent: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List children awaiting approval (status=2) that were added by parents (submitted_by_parent=1)
    or by admin/system (submitted_by_parent=0). Includes a `days_left` countdown until the 7-day auto-delete."""
    from ...core.pending_student_cleanup import GRACE_DAYS

    _require_active_app_admin(db, current_user)

    if submitted_by_parent == 1:
        query = """
        SELECT s.id, s.kName, s.eName, s.gender, s.dob, s.is_foreigner,
               s.student_phone, s.province, s.district, s.commune, s.village,
               s.previousSchool, s.branch, s.created_at, s.myparents,
               ur.avatar,
               p.fatherName, p.motherName, p.fatherPhone, p.motherPhone, p.username,
               b.branch_name
        FROM students s
        JOIN parents p
          ON p.id = CAST(NULLIF(TRIM(s.myparents), '') AS UNSIGNED)
        LEFT JOIN users_resource ur
          ON ur.user_id = s.id AND ur.user_type = 'student'
        LEFT JOIN branch b
          ON b.id = CAST(NULLIF(TRIM(s.branch), '') AS UNSIGNED)
        WHERE s.status = 2 AND s.submitted_by_parent = 1 AND COALESCE(p.status, 0) = 1
        ORDER BY s.created_at DESC, s.id DESC
        """
    else:
        query = """
        SELECT s.id, s.kName, s.eName, s.gender, s.dob, s.is_foreigner,
               s.student_phone, s.province, s.district, s.commune, s.village,
               s.previousSchool, s.branch, s.created_at, s.myparents,
               ur.avatar,
               p.fatherName, p.motherName, p.fatherPhone, p.motherPhone, p.username,
               b.branch_name
        FROM students s
        LEFT JOIN parents p
          ON p.id = CAST(NULLIF(TRIM(s.myparents), '') AS UNSIGNED)
        LEFT JOIN users_resource ur
          ON ur.user_id = s.id AND ur.user_type = 'student'
        LEFT JOIN branch b
          ON b.id = CAST(NULLIF(TRIM(s.branch), '') AS UNSIGNED)
        WHERE s.status = 2 AND s.submitted_by_parent = 0
        ORDER BY s.created_at DESC, s.id DESC
        """

    rows = db.execute(text(query)).fetchall()

    now = datetime.now()
    result = []
    for r in rows:
        created_at = r[13]
        days_left = None
        created_iso = None
        if created_at is not None:
            try:
                created_iso = created_at.isoformat()
                if submitted_by_parent == 1:
                    age_days = (now - created_at).days
                    days_left = max(0, GRACE_DAYS - age_days)
            except Exception:
                pass

        address = ", ".join([
            str(x).strip() for x in [r[10], r[9], r[8], r[7]]  # village, commune, district, province
            if x is not None and str(x).strip()
        ])

        result.append({
            "id": r[0],
            "kName": r[1],
            "eName": r[2],
            "gender": r[3],
            "dob": r[4].isoformat() if r[4] else None,
            "is_foreigner": r[5],
            "student_phone": r[6],
            "address": address or None,
            "previousSchool": r[11],
            "branch_name": r[21],
            "avatar": r[15],
            "parent_name": (r[16] or r[17] or r[20] or "Unknown"),
            "parent_phone": (r[18] or r[19]),
            "created_at": created_iso,
            "days_left": days_left,
        })

    return {"students": result, "grace_days": GRACE_DAYS}


def _notify_parent_pending_decision_bg(
    student_id,
    parent_id,
    child_name,
    decision,
    admin_name,
    reason=None,
):
    """Push to the parent when their submitted child is approved/rejected."""
    from ...core.database import SessionLocal
    from ...services import notification_service as _ns
    db = SessionLocal()
    try:
        if not parent_id:
            return
        tokens = _ns.get_parent_user_device_tokens(db, int(parent_id))
        if decision == 'approved':
            title = "Student Approved"
            body = f"{child_name} has been approved by {admin_name}."
        else:
            title = "Student Rejected"
            body = f"{child_name}'s registration was rejected by {admin_name}."
            if reason:
                body += f" Reason: {reason}"
        _ns.send_notification(
            device_tokens=tokens,
            title=title,
            body=body,
            data={
                "type": "pending_student_reply",
                "student_id": str(student_id),
                "decision": decision,
                "notification_key": f"pending_student_reply:{student_id}:{decision}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=[{"id": int(parent_id), "user_type": "parent"}],
            redirect_route="my_children",
            redirect_args={"student_id": student_id},
        )
    except Exception as e:
        logger.error(f"Error notifying parent of pending-student decision: {e}")
    finally:
        db.close()


@router.post('/pending-students/{student_id}/approve')
async def approve_pending_student(
    student_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Approve a pending child registration (status 2 -> 1)."""
    _require_active_app_admin(db, current_user)

    row = db.execute(
        text("SELECT status, submitted_by_parent, kName, eName, TRIM(myparents) "
             "FROM students WHERE id = :sid"),
        {"sid": student_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    if int(row[0] or 0) != 2:
        raise HTTPException(status_code=400, detail="Student is not pending approval")

    child_name = (row[2] or row[3] or f"Student #{student_id}")
    parent_id = row[4] if (row[4] and str(row[4]).strip().isdigit()) else None

    try:
        db.execute(
            text("UPDATE students SET status = 1, updated_at = NOW() WHERE id = :sid"),
            {"sid": student_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to approve pending student {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve student")

    try:
        from ...services.query_cache import invalidate_cache
        invalidate_cache("students_list")
    except Exception:
        pass

    admin_name = current_user.kName or current_user.eName or "Admin"
    if int(row[1] or 0) == 1 and parent_id:
        background_tasks.add_task(
            _notify_parent_pending_decision_bg,
            student_id,
            parent_id,
            child_name,
            "approved",
            admin_name,
        )

    return {"success": True, "message": "Student approved successfully"}


@router.post('/pending-students/{student_id}/reject')
async def reject_pending_student(
    student_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Reject a pending child registration: delete the record + avatar file
    (same teardown as the 7-day auto-cleanup)."""
    _require_active_app_admin(db, current_user)

    row = db.execute(
        text("SELECT status, submitted_by_parent, kName, eName, TRIM(myparents) "
             "FROM students WHERE id = :sid"),
        {"sid": student_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    if int(row[0] or 0) != 2:
        raise HTTPException(status_code=400, detail="Student is not pending approval")

    # Capture details BEFORE deletion so we can still notify the parent.
    child_name = (row[2] or row[3] or f"Student #{student_id}")
    parent_id = row[4] if (row[4] and str(row[4]).strip().isdigit()) else None

    try:
        from ...core.pending_student_cleanup import delete_pending_student
        delete_pending_student(db, student_id)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reject pending student {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject student")

    admin_name = current_user.kName or current_user.eName or "Admin"
    if int(row[1] or 0) == 1 and parent_id:
        background_tasks.add_task(
            _notify_parent_pending_decision_bg,
            student_id,
            parent_id,
            child_name,
            "rejected",
            admin_name,
        )

    return {"success": True, "message": "Student registration rejected and removed"}


# ─────────────────────────────────────────────────────────────────────────────
# Parents not on the app — so admins can contact them to install it.
# A parent is "not on the app" when they have no active device_tokens row.
# ─────────────────────────────────────────────────────────────────────────────
@router.get('/parents-without-app')
async def get_parents_without_app(
    only_active: bool = Query(True, description="Only parents who have at least one ACTIVE (enrolled) student"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List active parents who have NO active device token (i.e. not reachable by
    push — likely haven't installed / logged into the app), with their contacts
    and linked children, so an admin can follow up.

    By default ([only_active]=True) only parents with at least one currently
    enrolled (status=1) student are returned, and only their active children are
    listed. Pass only_active=false to include every such parent / all children.
    """
    _require_active_app_admin(db, current_user)

    # Restrict to parents with an enrolled child when only_active.
    active_parent_clause = ""
    if only_active:
        active_parent_clause = """
          AND EXISTS (
            SELECT 1 FROM students s2
            WHERE CAST(NULLIF(TRIM(s2.myparents), '') AS UNSIGNED) = p.id
              AND s2.status = 1
          )"""

    rows = db.execute(text(
        f"""
        SELECT p.id, p.username,
               p.fatherName, p.fatherPhone,
               p.motherName, p.motherPhone,
               p.gName, p.gPhone, p.gIsThe
        FROM parents p
        WHERE COALESCE(p.status, 1) = 1
          AND NOT EXISTS (
            SELECT 1 FROM device_tokens dt
            WHERE dt.user_id = p.id
              AND dt.user_type = 'parent'
              AND (dt.is_active = 1 OR dt.is_active = TRUE)
          )
          {active_parent_clause}
        ORDER BY p.id DESC
        """
    )).fetchall()

    if not rows:
        return {"parents": [], "total": 0}

    # Children for all these parents in one query (grouped by parent id).
    # Always exclude status=2 (pending) — those are managed in the New Students screen.
    parent_ids = [r[0] for r in rows]
    placeholders = ",".join(str(i) for i in parent_ids)
    child_status_clause = "AND status = 1" if only_active else "AND status != 2"
    child_map: dict = {}
    try:
        crows = db.execute(text(
            f"""
            SELECT id, kName, eName,
                   CAST(NULLIF(TRIM(myparents), '') AS UNSIGNED) AS pid
            FROM students
            WHERE CAST(NULLIF(TRIM(myparents), '') AS UNSIGNED) IN ({placeholders})
              {child_status_clause}
            ORDER BY id ASC
            """
        )).fetchall()
        for c in crows:
            child_map.setdefault(c[3], []).append({
                "id": c[0],
                "name": (c[1] or c[2] or f"#{c[0]}"),
            })
    except Exception as e:
        logger.warning(f"Failed to load children for parents-without-app: {e}")

    result = []
    for r in rows:
        pid = r[0]
        contacts = []
        if r[3] and str(r[3]).strip():
            contacts.append({"relation": "Father", "name": r[2], "phone": str(r[3]).strip()})
        if r[5] and str(r[5]).strip():
            contacts.append({"relation": "Mother", "name": r[4], "phone": str(r[5]).strip()})
        if r[7] and str(r[7]).strip():
            contacts.append({"relation": (r[8] or "Guardian"), "name": r[6], "phone": str(r[7]).strip()})
        result.append({
            "id": pid,
            "username": r[1],
            "name": (r[2] or r[4] or r[6] or f"Parent #{pid}"),
            "contacts": contacts,
            "children": child_map.get(pid, []),
        })

    return {"parents": result, "total": len(result)}


# ─────────────────────────────────────────────────────────────────────────────
# Parents overview — search + filter by app status (on/off/all).
# Each parent carries a `has_app` flag (active device token present).
# ─────────────────────────────────────────────────────────────────────────────
@router.get('/parents')
async def get_parents_overview(
    app_status: str = Query('all', description="all | on | off (on = has the app)"),
    only_active: bool = Query(True, description="Only parents with at least one ACTIVE (enrolled) student"),
    search: Optional[str] = Query(None, description="Match parent name/phone/username or student name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Active parents with their app status, contacts and children. Filterable by
    app status and a free-text search; off-app parents are listed first."""
    _require_active_app_admin(db, current_user)

    app_status = (app_status or 'all').lower()
    if app_status not in ('all', 'on', 'off'):
        app_status = 'all'

    has_app_expr = (
        "EXISTS (SELECT 1 FROM device_tokens dt WHERE dt.user_id = p.id "
        "AND dt.user_type = 'parent' AND (dt.is_active = 1 OR dt.is_active = TRUE))"
    )

    where = ["COALESCE(p.status, 1) = 1"]
    params: dict = {}

    if only_active:
        where.append(
            "EXISTS (SELECT 1 FROM students s2 "
            "WHERE CAST(NULLIF(TRIM(s2.myparents), '') AS UNSIGNED) = p.id AND s2.status = 1)"
        )

    if app_status == 'on':
        where.append(has_app_expr)
    elif app_status == 'off':
        where.append("NOT " + has_app_expr)

    if search and search.strip():
        params['q'] = f"%{search.strip()}%"
        where.append(
            "(p.fatherName LIKE :q OR p.motherName LIKE :q OR p.gName LIKE :q "
            "OR p.fatherPhone LIKE :q OR p.motherPhone LIKE :q OR p.gPhone LIKE :q "
            "OR p.username LIKE :q OR EXISTS (SELECT 1 FROM students s3 "
            "WHERE CAST(NULLIF(TRIM(s3.myparents), '') AS UNSIGNED) = p.id "
            "AND (s3.kName LIKE :q OR s3.eName LIKE :q)))"
        )

    where_sql = " AND ".join(where)
    rows = db.execute(text(
        f"""
        SELECT p.id, p.username,
               p.fatherName, p.fatherPhone,
               p.motherName, p.motherPhone,
               p.gName, p.gPhone, p.gIsThe,
               {has_app_expr} AS has_app
        FROM parents p
        WHERE {where_sql}
        ORDER BY has_app ASC, p.id DESC
        LIMIT 500
        """
    ), params).fetchall()

    if not rows:
        return {"parents": [], "total": 0}

    parent_ids = [r[0] for r in rows]
    placeholders = ",".join(str(i) for i in parent_ids)
    child_status_clause = "AND status = 1" if only_active else "AND status != 2"
    child_map: dict = {}
    try:
        crows = db.execute(text(
            f"""
            SELECT id, kName, eName,
                   CAST(NULLIF(TRIM(myparents), '') AS UNSIGNED) AS pid
            FROM students
            WHERE CAST(NULLIF(TRIM(myparents), '') AS UNSIGNED) IN ({placeholders})
              {child_status_clause}
            ORDER BY id ASC
            """
        )).fetchall()
        for c in crows:
            child_map.setdefault(c[3], []).append({
                "id": c[0],
                "name": (c[1] or c[2] or f"#{c[0]}"),
            })
    except Exception as e:
        logger.warning(f"Failed to load children for parents overview: {e}")

    result = []
    for r in rows:
        pid = r[0]
        contacts = []
        if r[3] and str(r[3]).strip():
            contacts.append({"relation": "Father", "name": r[2], "phone": str(r[3]).strip()})
        if r[5] and str(r[5]).strip():
            contacts.append({"relation": "Mother", "name": r[4], "phone": str(r[5]).strip()})
        if r[7] and str(r[7]).strip():
            contacts.append({"relation": (r[8] or "Guardian"), "name": r[6], "phone": str(r[7]).strip()})
        result.append({
            "id": pid,
            "username": r[1],
            "name": (r[2] or r[4] or r[6] or f"Parent #{pid}"),
            "has_app": bool(int(r[9] or 0)),
            "contacts": contacts,
            "children": child_map.get(pid, []),
        })

    return {"parents": result, "total": len(result)}
