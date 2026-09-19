"""
Users API endpoints.
"""

import base64
import logging
import os
import uuid
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import List, Any, Optional
from pathlib import Path

from ...core import get_db

logger = logging.getLogger(__name__)
from ...models import User, Parent
from ...services import phone_conflict
from ...schemas import UserResponse, UserUpdate
from ...auth import get_current_active_user
from ...services.utils import get_password_hash

router = APIRouter()

# Parent table columns that can be updated via PATCH /me
PARENT_UPDATE_FIELDS = {
    "fatherName", "motherName", "fatherPhone", "motherPhone",
    "fatherJob", "motherJob", "pProvince", "pDistrict", "pCommune", "pVillage",
    "pEmail", "pTelegramId", "username", "password",
    "gName", "gPhone", "gIsThe", "gHome", "gStreet", "gGroup",
    "gProvince", "gDistrict", "gCommune", "gVillage",
}


@router.get("/check-username/{username}")
async def check_username_available(
    username: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """Check if username is available. Returns 200 with available=true/false."""
    # Check if it's the current user's own username (works for User and parent adapter)
    if getattr(current_user, "username", None) == username:
        return {"available": True}  # It's available to THIS user (no change)

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return {"available": False}
    existing_parent = db.query(Parent).filter(Parent.username == username).first()
    return {"available": existing_parent is None}


from pydantic import BaseModel


class VerifyPasswordRequest(BaseModel):
    password: str


@router.post("/verify-current-password")
async def verify_current_password(
    body: VerifyPasswordRequest,
    current_user: Any = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Verify current password. Returns {valid: true/false}. Used before allowing password change."""
    password = body.password if body else None
    if not password:
        return {"valid": False}

    from ...services.utils import verify_password

    if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
        parent = db.query(Parent).filter(Parent.id == current_user.id).first()
        if parent is None:
            return {"valid": False}
        stored = parent.password or ""
    else:
        user = db.query(User).filter(User.id == current_user.id).first()
        if user is None:
            return {"valid": False}
        stored = user.password or ""

    return {"valid": verify_password(password, stored)}


def _normalize_phone_for_verify(s: str) -> str:
    """Normalize phone for Firebase token comparison."""
    if not s:
        return ""
    clean = s.replace(" ", "").replace("-", "").replace("+", "")
    if clean.startswith("0"):
        clean = clean[1:]
    if clean.startswith("855"):
        clean = clean[3:]
    return clean.strip()


async def _verify_firebase_token_matches_phone(token: str, phone: str, field_name: str) -> None:
    """Verify Firebase ID token and that it matches the given phone. Raises HTTPException on failure."""
    if not token or not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phone verification required for {field_name}. Please verify the new phone first.",
        )
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification not available.",
        )
    try:
        request = google_requests.Request()
        FIREBASE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
        # run_in_threadpool: blocks on HTTP calls to Google, would freeze all users without it
        decoded = await run_in_threadpool(
            lambda: google_id_token.verify_token(
                token,
                request,
                audience=None,
                certs_url=FIREBASE_CERTS_URL,
            )
        )
        token_phone = decoded.get("phone_number")
        if not token_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token: Phone number not found.",
            )
        token_clean = _normalize_phone_for_verify(token_phone)
        user_clean = _normalize_phone_for_verify(phone)
        if not user_clean.endswith(token_clean) and not token_clean.endswith(user_clean):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Phone verification failed for {field_name}. The verified phone does not match.",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification token.",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Firebase token verification error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phone verification failed.",
        ) from e


@router.patch("/me")
async def update_user_me(
    user_update: UserUpdate,
    current_user: Any = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    x_firebase_id_token_father: Optional[str] = Header(None, alias="X-Firebase-ID-Token-Father"),
    x_firebase_id_token_mother: Optional[str] = Header(None, alias="X-Firebase-ID-Token-Mother"),
    x_firebase_id_token_guardian: Optional[str] = Header(None, alias="X-Firebase-ID-Token-Guardian"),
    x_firebase_id_token: Optional[str] = Header(None, alias="X-Firebase-ID-Token"),
):
    """Update current user profile. Supports both User (teachers) and Parent."""
    try:
        update_data = user_update.model_dump(exclude_unset=True, exclude_none=True)
        
        # Parent flow: update parents table
        if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
            parent = db.query(Parent).filter(Parent.id == current_user.id).first()
            if parent is None:
                raise HTTPException(status_code=404, detail="Parent not found")

            # Require Firebase verification when changing father/mother phone
            new_father = update_data.get("fatherPhone")
            new_mother = update_data.get("motherPhone")
            if new_father is not None and (parent.fatherPhone or "").strip() != (new_father or "").strip():
                await _verify_firebase_token_matches_phone(
                    x_firebase_id_token_father or "",
                    new_father,
                    "Father's phone",
                )
            if new_mother is not None and (parent.motherPhone or "").strip() != (new_mother or "").strip():
                await _verify_firebase_token_matches_phone(
                    x_firebase_id_token_mother or "",
                    new_mother,
                    "Mother's phone",
                )
            new_guardian = update_data.get("gPhone")
            if (
                new_guardian is not None
                and (new_guardian or "").strip()
                and (parent.gPhone or "").strip() != (new_guardian or "").strip()
            ):
                await _verify_firebase_token_matches_phone(
                    x_firebase_id_token_guardian or "",
                    new_guardian,
                    "Guardian's phone",
                )

            for field in PARENT_UPDATE_FIELDS:
                if field not in update_data:
                    continue
                value = update_data[field]
                if field == "password" and value:
                    old_password = update_data.get("old_password")
                    if old_password:
                        from ...services.utils import verify_password
                        if not verify_password(old_password, parent.password or ""):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Current password is incorrect",
                            )
                    value = get_password_hash(value)
                if field == "old_password":
                    continue
                if hasattr(parent, field):
                    try:
                        setattr(parent, field, value)
                    except Exception:
                        pass
            parent.updated_at = date.today()  # type: ignore[assignment]

            # Handle profile image (base64) -> save to uploads/avatars and create/update UserResource
            image_b64 = update_data.get("image")
            if image_b64 and isinstance(image_b64, str):
                try:
                    image_data = base64.b64decode(image_b64)
                    upload_dir = "uploads/avatars"
                    os.makedirs(upload_dir, exist_ok=True)
                    filename = f"parent_{parent.id}_{uuid.uuid4().hex[:8]}.jpg"
                    file_path = os.path.join(upload_dir, filename)
                    with open(file_path, "wb") as f:
                        f.write(image_data)
                    from ...models.user_resource import UserResource
                    existing = db.query(UserResource).filter(
                        UserResource.user_id == parent.id,
                        UserResource.user_type == "parent",
                    ).first()
                    if existing:
                        existing.avatar = file_path  # type: ignore[assignment]
                        db.add(existing)
                    else:
                        user_res = UserResource(
                            user_id=parent.id,
                            user_type="parent",
                            avatar=file_path,
                            status=1,
                        )
                        db.add(user_res)
                except Exception as e:
                    logger.warning("Failed to save parent profile image: %s", e)

            db.commit()
            # A changed phone can create or clear a login lock — rescan on next check.
            phone_conflict.invalidate_cache()
            db.refresh(parent)
            # Return parent as dict (matches /auth/me parent response shape)
            return {
                "id": parent.id,
                "username": parent.username,
                "fatherName": parent.fatherName,
                "motherName": parent.motherName,
                "fatherPhone": parent.fatherPhone,
                "motherPhone": parent.motherPhone,
                "fatherJob": parent.fatherJob,
                "motherJob": parent.motherJob,
                "pProvince": parent.pProvince,
                "pDistrict": parent.pDistrict,
                "pCommune": parent.pCommune,
                "pVillage": parent.pVillage,
                "pEmail": parent.pEmail,
                "pTelegramId": parent.pTelegramId,
                "gName": parent.gName,
                "gPhone": parent.gPhone,
                "gIsThe": parent.gIsThe,
                "gHome": parent.gHome,
                "gStreet": parent.gStreet,
                "gGroup": parent.gGroup,
                "gProvince": parent.gProvince,
                "gDistrict": parent.gDistrict,
                "gCommune": parent.gCommune,
                "gVillage": parent.gVillage,
                "status": parent.status,
                "user_type": "parent",
            }
        
        # User (teacher) flow - require Firebase verification when changing phone
        user = db.query(User).filter(User.id == current_user.id).first()
        if user is not None:
            new_phone = update_data.get("phone")
            if new_phone is not None and (user.phone or "").strip() != (new_phone or "").strip():
                await _verify_firebase_token_matches_phone(
                    x_firebase_id_token or "",
                    new_phone,
                    "Phone",
                )
        readonly_fields = {'id', 'created_at', 'updated_at', 'uniqueId'}
        for field, value in update_data.items():
            if field in readonly_fields:
                continue
            if not hasattr(current_user, field):
                continue
            # Hash password if it's being updated
            if field == 'password':
                if value and len(value) > 0:
                    # Verify old password if provided
                    old_password = update_data.get('old_password')
                    if old_password:
                        # Import verify_password from services
                        from ...services.utils import verify_password
                        if not verify_password(old_password, current_user.password):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Current password is incorrect"
                            )
                    value = get_password_hash(value)
                else:
                    continue
            
            # Skip old_password field from being saved to database
            if field == 'old_password':
                continue
            
            # Handle date string conversion
            if field in ['dob', 'identityRegDate', 'identityEndDate'] and value is not None:
                if isinstance(value, str) and value.strip():
                    from datetime import datetime
                    try:
                        # Try parsing ISO format dates (e.g., "2025-03-07T00:00:00" or "2025-03-07")
                        if 'T' in value:
                            value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                        else:
                            value = datetime.strptime(value, '%Y-%m-%d').date()
                    except (ValueError, AttributeError):
                        continue
                elif not value:
                    continue  # Skip empty date strings
            
            # Handle height conversion (Numeric field)
            if field == 'height' and value is not None:
                try:
                    if isinstance(value, str):
                        value = float(value) if value.strip() else None
                    elif isinstance(value, (int, float)):
                        value = float(value)
                    else:
                        value = None
                except (ValueError, TypeError):
                    continue
            
            # Skip None values for non-nullable fields
            if value is None:
                # Check if field is nullable in the model
                column = getattr(current_user.__class__, field, None)
                if column is not None and hasattr(column, 'property') and hasattr(column.property, 'columns'):
                    col = column.property.columns[0]
                    if not col.nullable:
                        continue
            
            try:
                setattr(current_user, field, value)
            except Exception:
                continue
        
        db.commit()
        # A changed phone can create or clear a login lock — rescan on next check.
        phone_conflict.invalidate_cache()
        db.refresh(current_user)
        try:
            from .websocket import broadcast_to_user
            await broadcast_to_user(current_user.id, {
                "type": "user_updated",
                "payload": {"user_id": current_user.id, "updated_fields": list(update_data.keys())},
            })
        except Exception:
            pass
        # Return dict excluding binary fields to avoid UnicodeDecodeError
        # when serializing bytes (image, signature) to JSON
        resp = UserResponse.model_validate(current_user)
        return resp.model_dump(mode="json", exclude={"image", "signature"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("PATCH /me failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) if str(e) else "Failed to update profile",
        )


@router.get("/me", response_model=UserResponse, response_model_exclude={"image", "signature"})
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return current_user


@router.get("/", response_model=List[UserResponse], response_model_exclude={"image", "signature"})
async def read_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of users (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.get("/birthdays/today", response_model=List[dict])
async def read_todays_birthdays(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of OTHER active users whose birthday is today (Admin, Super Admin, Teacher)."""
    # Parent accounts are not permitted to see this list
    if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    from ...models import UserResource
    from sqlalchemy import extract
    from sqlalchemy.orm import aliased
    from datetime import date, datetime, timezone, timedelta

    # Use Cambodia local time (UTC+7) so the day boundary is correct
    _CAMBODIA_TZ = timezone(timedelta(hours=7))
    today = datetime.now(_CAMBODIA_TZ).date()
    
    URTeacher = aliased(UserResource)
    UREmployee = aliased(UserResource)

    users_with_resource = db.query(User, URTeacher.avatar, UREmployee.avatar).outerjoin(
        URTeacher, (URTeacher.user_id == User.id) & (URTeacher.user_type == 'teacher')
    ).outerjoin(
        UREmployee, (UREmployee.user_id == User.id) & (UREmployee.user_type == 'employee')
    ).filter(
        extract('month', User.dob) == today.month,
        extract('day', User.dob) == today.day,
        User.id != current_user.id,
        User.status == 1
    ).all()
    
    result = []
    for u, teacher_avatar, employee_avatar in users_with_resource:
        avatar = teacher_avatar or employee_avatar
        result.append({
            "id": u.id,
            "username": u.username,
            "eName": u.eName,
            "kName": u.kName,
            "gender": u.gender,
            "dob": u.dob.isoformat() if u.dob else None,
            "avatar": avatar,
        })
    return result

@router.post("/birthdays/{target_user_id}/wish")
async def send_birthday_wish(
    target_user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send a birthday wish push notification to another user."""
    # Parent accounts are not permitted to send wishes
    if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only allow wishes to active users whose birthday is actually today (Cambodia time)
    from datetime import datetime, timezone, timedelta
    _CAMBODIA_TZ = timezone(timedelta(hours=7))
    today = datetime.now(_CAMBODIA_TZ).date()
    if (
        getattr(target_user, "status", None) != 1
        or not target_user.dob
        or target_user.dob.month != today.month
        or target_user.dob.day != today.day
    ):
        raise HTTPException(status_code=400, detail="It is not this user's birthday today")

    from ...services.notification_service import get_teacher_device_tokens
    tokens = get_teacher_device_tokens(db, target_user_id)

    sender_name = current_user.kName or current_user.eName or current_user.username

    title = "Happy Birthday!"
    body = f"{sender_name} has sent you a birthday wish! 🎉"
    
    data = {
        "type": "birthday_wish",
        "sender_id": str(current_user.id),
        "sender_name": sender_name
    }
    
    from ...services.notification_service import send_notification_async
    
    # Store as 'teacher' type in notifications table since all admins/teachers use this
    target_user_info = [{"id": target_user_id, "user_type": "teacher"}]
    
    if tokens or True: # Even if no tokens, save to DB
        await send_notification_async(
            device_tokens=tokens,
            title=title,
            body=body,
            data=data,
            color="#E91E63", # Pink
            icon="ic_cake",
            vibrate=True,
            db=db,
            user_ids=target_user_info,
            is_deletable=True
        )
    
    return {"success": True, "message": "Birthday wish sent!"}



def _parse_start_work(value):
    """Parse a startWork value (date, datetime, or VARCHAR in yyyy-mm-dd / dd/mm/yyyy form) to a date, or None."""
    from datetime import date, datetime
    import re

    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    if isinstance(value, str):
        clean_str = value.strip().split(' ')[0].split('T')[0]
        if clean_str:
            if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', clean_str):
                parts = re.split(r'[-/]', clean_str)
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            elif re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$', clean_str):
                parts = re.split(r'[-/]', clean_str)
                p1, p2, year = int(parts[0]), int(parts[1]), int(parts[2])
                if p1 > 12:
                    return date(year, p2, p1)
                elif p2 > 12:
                    return date(year, p1, p2)
                else:
                    return date(year, p2, p1)
    return None


@router.get("/anniversaries/today", response_model=List[dict])
async def read_todays_anniversaries(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of OTHER active users whose work anniversary is today."""
    if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    from ...models import UserResource
    from sqlalchemy.orm import aliased
    from datetime import date, datetime, timezone, timedelta
    import re

    # Use Cambodia local time (UTC+7) so the day boundary is correct
    _CAMBODIA_TZ = timezone(timedelta(hours=7))
    today = datetime.now(_CAMBODIA_TZ).date()
    
    URTeacher = aliased(UserResource)
    UREmployee = aliased(UserResource)

    # Fetch all active users with startWork, filter safely in Python to handle VARCHAR inconsistencies
    users_with_resource = db.query(User, URTeacher.avatar, UREmployee.avatar).outerjoin(
        URTeacher, (URTeacher.user_id == User.id) & (URTeacher.user_type == 'teacher')
    ).outerjoin(
        UREmployee, (UREmployee.user_id == User.id) & (UREmployee.user_type == 'employee')
    ).filter(
        User.startWork != None,
        User.startWork != '',
        User.id != current_user.id,
        User.status == 1
    ).all()
    
    result = []
    for u, teacher_avatar, employee_avatar in users_with_resource:
        try:
            start_work = None
            if isinstance(u.startWork, str):
                clean_str = u.startWork.strip().split(' ')[0].split('T')[0]
                if clean_str:
                    # Handle yyyy-mm-dd or dd/mm/yyyy
                    if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', clean_str):
                        parts = re.split(r'[-/]', clean_str)
                        start_work = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    elif re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$', clean_str):
                        parts = re.split(r'[-/]', clean_str)
                        p1, p2, year = int(parts[0]), int(parts[1]), int(parts[2])
                        if p1 > 12:
                            start_work = date(year, p2, p1)
                        elif p2 > 12:
                            start_work = date(year, p1, p2)
                        else:
                            start_work = date(year, p2, p1)
            elif isinstance(u.startWork, date) or isinstance(u.startWork, datetime):
                start_work = u.startWork
            
            if start_work and start_work.day == today.day:
                months = (today.year - start_work.year) * 12 + (today.month - start_work.month)
                if months > 0 and months % 3 == 0:
                    avatar = teacher_avatar or employee_avatar
                    result.append({
                        "id": u.id,
                        "username": u.username,
                        "eName": u.eName,
                        "kName": u.kName,
                        "gender": u.gender,
                        "startWork": u.startWork.isoformat() if hasattr(u.startWork, 'isoformat') else str(u.startWork),
                        "avatar": avatar,
                        "months_worked": months
                    })
        except Exception:
            pass
            
    return result

@router.post("/anniversaries/{target_user_id}/wish")
async def send_anniversary_wish(
    target_user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send an anniversary wish push notification to another user."""
    # Parent accounts are not permitted to send wishes
    if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only allow wishes to active users whose work anniversary is actually today (Cambodia time)
    from datetime import datetime, timezone, timedelta
    _CAMBODIA_TZ = timezone(timedelta(hours=7))
    today = datetime.now(_CAMBODIA_TZ).date()
    try:
        start_work = _parse_start_work(target_user.startWork)
    except Exception:
        start_work = None
    months = None
    if start_work and start_work.day == today.day:
        months = (today.year - start_work.year) * 12 + (today.month - start_work.month)
    if getattr(target_user, "status", None) != 1 or months is None or months <= 0 or months % 3 != 0:
        raise HTTPException(status_code=400, detail="It is not this user's work anniversary today")

    from ...services.notification_service import get_teacher_device_tokens
    tokens = get_teacher_device_tokens(db, target_user_id)
    
    sender_name = current_user.kName or current_user.eName or current_user.username
    
    title = "Work Anniversary!"
    body = f"{sender_name} has sent you an anniversary wish! 🎉"
    
    data = {
        "type": "anniversary_wish",
        "sender_id": str(current_user.id),
        "sender_name": sender_name
    }
    
    from ...services.notification_service import send_notification_async
    
    target_user_info = [{"id": target_user_id, "user_type": "teacher"}]
    
    if tokens or True:
        await send_notification_async(
            device_tokens=tokens,
            title=title,
            body=body,
            data=data,
            color="#FFC107", 
            icon="ic_work",
            vibrate=True,
            db=db,
            user_ids=target_user_info,
            is_deletable=True
        )
    
    return {"success": True, "message": "Anniversary wish sent!"}

# Payroll, banking and government-ID fields. UserResponse carries the whole
# employee row, so anyone who could read another user's record could read their
# salary and bank account. Only the person themselves and admins see these.
_PRIVATE_STAFF_FIELDS = (
    "baseSalary",
    "bankAccountNumber",
    "bankAccountName",
    "bankName",
    "nssfNumber",
    "isNssf",
    "isResident",
    "hasSpouse",
    "numberOfDependents",
    "identityNumber",
    "identityRegDate",
    "identityEndDate",
    "identityRegPlace",
)


def _may_see_private_staff_fields(current_user, target_user_id: int) -> bool:
    """Self or admin. Parents are never staff, so they never qualify."""
    if getattr(current_user, "is_parent", False):
        return False
    if getattr(current_user, "user_type", None) == "parent":
        return False
    try:
        if int(getattr(current_user, "id", 0) or 0) == int(target_user_id):
            return True
    except (TypeError, ValueError):
        pass
    return bool(getattr(current_user, "is_admin", False))


def _redact_private_staff_fields(user: User, current_user) -> dict:
    """Serialise a user, blanking payroll/ID fields for everyone else.

    Returns a dict rather than the ORM object so the response keeps exactly the
    same keys — callers that read e.g. `departmentId` keep working, they just
    get null where they used to get somebody's bank account.
    """
    data = UserResponse.model_validate(user).model_dump()
    if not _may_see_private_staff_fields(current_user, user.id):
        for field in _PRIVATE_STAFF_FIELDS:
            data[field] = None
    return data


@router.get("/{user_id}", response_model=UserResponse, response_model_exclude={"image", "signature"})
async def read_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific user by ID.

    Any signed-in account can look up a colleague, which the app relies on, but
    salary, bank details and national-ID numbers are blanked unless you are that
    person or an admin.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return _redact_private_staff_fields(user, current_user)

from fastapi import UploadFile, File

@router.get("/{user_id}/signature")
async def get_user_signature(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a user's signature URL.

    Signatures are used to sign school documents, so this mirrors the upload
    endpoint: your own, or an admin's view. It previously required no
    authentication at all.
    """
    if not _may_see_private_staff_fields(current_user, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted to view this signature",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.signatureImagePath:
        # Assuming the app is accessible at the root URL and /uploads is mounted
        # For a full URL, we would need request object, but returning the path is safer
        return {"signature_url": f"/{user.signatureImagePath}"}
        
    return {"signature_url": None}

@router.post("/{user_id}/signature")
async def upload_user_signature(
    user_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a signature for a user."""
    # Only allow users to update their own signature, or admins can update anyone's
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not permitted to update this signature")
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
        
    # Save the file
    upload_dir = Path("uploads/signatures")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # The extension came straight from the client filename, so an upload could
    # choose its own type — e.g. .html, which /uploads serves as text/html and
    # the browser then executes on the API origin. content_type is client
    # supplied too, so it cannot be trusted to decide this either.
    from ...services.storage_service import StorageService

    safe = StorageService.safe_filename(file.filename, file.content_type)
    ext = os.path.splitext(safe)[1].lstrip(".") or "png"
    filename = f"sig_{user_id}_{int(datetime.now().timestamp())}.{ext}"
    file_path = upload_dir / filename
    
    # Read and save file content
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
        
    # Update user record
    db_path = f"uploads/signatures/{filename}"
    user.signatureImagePath = db_path
    db.commit()
    
    return {"message": "Signature updated successfully", "signature_url": f"/{db_path}"}


@router.get("/portfolio/{identifier}")
async def get_public_employee_portfolio(
    identifier: str,
    db: Session = Depends(get_db)
):
    """
    Public portfolio view for employee/teacher.
    No authentication required, sanitized output only.
    """
    from sqlalchemy import text
    is_num = identifier.isdigit()
    filter_cond = (User.uniqueId == identifier)
    if is_num:
        filter_cond = filter_cond | (User.id == int(identifier))
    elif "-" in identifier:
        parts = identifier.split("-")
        if parts[-1].isdigit():
            filter_cond = filter_cond | (User.id == int(parts[-1]))

    user = db.query(User).filter(filter_cond).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")

    dept_code = "EMP"
    dept_name_km = None
    dept_name_en = None
    if getattr(user, "departmentId", None):
        try:
            d_row = db.execute(
                text("SELECT id, department, translate, code FROM department WHERE id = :id LIMIT 1"),
                {"id": user.departmentId}
            ).mappings().first()
            if d_row:
                dept_code = d_row.get("code") or "EMP"
                dept_name_en = d_row.get("department")
                dept_name_km = d_row.get("translate") or dept_name_en
        except Exception:
            db.rollback()

    pos_name_km = None
    pos_name_en = None
    if getattr(user, "positionId", None):
        try:
            p_row = db.execute(
                text("SELECT id, position, translate FROM position WHERE id = :id LIMIT 1"),
                {"id": user.positionId}
            ).mappings().first()
            if p_row:
                pos_name_en = p_row.get("position")
                pos_name_km = p_row.get("translate") or pos_name_en
        except Exception:
            db.rollback()

    branch_name = None
    if getattr(user, "workplace", None):
        try:
            b_row = db.execute(
                text("SELECT id, branch_name FROM branch WHERE id = :id LIMIT 1"),
                {"id": user.workplace}
            ).mappings().first()
            if b_row:
                branch_name = b_row.get("branch_name")
        except Exception:
            db.rollback()

    # Employee ID code formatting
    user_id_val = getattr(user, "id", 0)
    try:
        emp_code = f"{dept_code}-{int(user_id_val):04d}"
    except Exception:
        emp_code = f"{dept_code}-{user_id_val}"

    # Photo URL fallback to users_resource if user.image is empty
    photo_url = user.image if getattr(user, "image", None) else None
    if not photo_url:
        try:
            res_row = db.execute(
                text("""
                    SELECT avatar FROM users_resource
                    WHERE user_id = :uid AND user_type IN ('employee', 'teacher') AND status = 1
                    ORDER BY id DESC LIMIT 1
                """),
                {"uid": user.id}
            ).fetchone()
            if res_row and res_row[0]:
                photo_url = res_row[0]
        except Exception:
            db.rollback()

    user_status = getattr(user, "status", 1)
    is_active = (user_status == 1)

    return {
        "id": user.id,
        "uniqueId": user.uniqueId or emp_code,
        "employeeId": emp_code,
        "cardNo": emp_code,
        "khmerName": user.kName,
        "latinName": user.eName,
        "positionKhmer": pos_name_km,
        "positionLatin": pos_name_en,
        "departmentKhmer": dept_name_km,
        "departmentLatin": dept_name_en,
        "branchName": branch_name,
        "gender": user.gender,
        "genderLatin": "Female" if user.gender in ["ស្រី", "Female"] else "Male",
        "dob": str(user.dob) if user.dob else None,
        "nationality": user.nationality,
        "religion": user.religion,
        "phone": user.phone,
        "email": user.email,
        "telegram": user.telegramId,
        "address": f"{user.village or ''} {user.commune or ''} {user.district or ''} {user.province or ''}".strip(),
        "pAddress": f"{user.pVillage or ''} {user.pCommune or ''} {user.pDistrict or ''} {user.pProvince or ''}".strip(),
        "identityNumber": user.identityNumber,
        "startWork": str(user.startWork) if user.startWork else None,
        "education": user.education,
        "photoUrl": photo_url,
        "signatureUrl": user.signatureImagePath if getattr(user, "signatureImagePath", None) else None,
        "status": "Active Faculty" if is_active else "Inactive",
        "isVerified": is_active
    }

