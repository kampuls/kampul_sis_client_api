"""
Admin Users Management API.

Provides listing and basic admin controls for users:
- GET /admin/users       (with full JOINs: branch, department, position, avatar)
- PUT /admin/users/{user_id}
- POST /admin/users/{user_id}/logout
"""

from typing import Optional, Any
import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel

from ...core import get_db
from ...models import User, DeviceToken, UserHomeAppPermission
from ...services.notification_service import send_notification
from ...auth import get_current_active_user
from ...services.utils import get_password_hash
import secrets


class NotifyUpdateAppRequest(BaseModel):
    message: Optional[str] = None


class ApproveStaffRegistrationRequest(BaseModel):
    apply_default_locks: bool = False


router = APIRouter()
logger = logging.getLogger(__name__)

_STAFF_DEVICE_TYPES = ("teacher", "employee", "admin", "app_admin")
_DEFAULT_REGISTRATION_LOCKS = {
    "marking",
    "exam_result",
    "classes",
    "teachers",
    "students",
    "reports",
    "attendance",
}


def _ensure_admin(current_user: Any) -> None:
    """Ensure current user is an admin (role == 1)."""
    role_val = getattr(current_user, "role", None)
    try:
        if int(role_val) != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin only",
            )
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )


def _format_date(val):
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _locked_features_map(db: Session, user_ids: list[int]) -> dict[int, list[str]]:
    if not user_ids:
        return {}
    rows = (
        db.query(UserHomeAppPermission.user_id, UserHomeAppPermission.feature_id)
        .filter(
            UserHomeAppPermission.user_id.in_(user_ids),
            UserHomeAppPermission.is_allowed == False,
        )
        .all()
    )
    out: dict[int, list[str]] = {}
    for uid, feature_id in rows:
        out.setdefault(uid, []).append(feature_id)
    return out


def _device_token_payloads(rows) -> list[dict[str, Any]]:
    """Preserve metadata used by the shared physical-device deduper."""
    return [
        {
            "id": row.id,
            "token": row.device_token,
            "device_type": row.device_type or "unknown",
            "user_id": row.user_id,
            "user_type": row.user_type or "teacher",
            "device_name": row.device_name,
            "last_used_at": row.last_used_at,
        }
        for row in rows
        if row.device_token
    ]


def _active_staff_device_tokens(
    db: Session,
    user_ids: list[int],
) -> list[DeviceToken]:
    """Active staff installations, excluding colliding parent/student IDs."""
    if not user_ids:
        return []
    return (
        db.query(DeviceToken)
        .filter(
            DeviceToken.user_id.in_(user_ids),
            DeviceToken.user_type.in_(_STAFF_DEVICE_TYPES),
            DeviceToken.is_active == True,  # noqa: E712
        )
        .order_by(
            DeviceToken.user_id.asc(),
            func.coalesce(
                DeviceToken.last_used_at,
                DeviceToken.updated_at,
                DeviceToken.created_at,
            ).desc(),
            DeviceToken.id.desc(),
        )
        .all()
    )


def _app_device_payload(row: DeviceToken) -> dict[str, Any]:
    last_seen = row.last_used_at or row.updated_at or row.created_at
    return {
        "device_type": row.device_type or "unknown",
        "device_name": row.device_name or "Unknown device",
        "app_version": row.app_version,
        "last_seen_at": (
            last_seen.isoformat() if hasattr(last_seen, "isoformat") else None
        ),
    }


def _notify_home_permission_updated(db: Session, user_id: int) -> None:
    """Best-effort realtime push so user can refresh home permissions immediately."""
    try:
        device_tokens = _active_staff_device_tokens(db, [user_id])
        if not device_tokens:
            return
        token_payloads = _device_token_payloads(device_tokens)
        send_notification(
            device_tokens=token_payloads,
            title="Permissions updated",
            body="Your home feature access was updated.",
            data={
                "type": "home_permission_updated",
                "user_id": str(user_id),
            },
            android_show_system_notification=False,
            db=None,
            user_ids=None,
        )
    except Exception as e:
        logger.warning(
            f"Failed to send home_permission_updated notification for user {user_id}: {e}"
        )


@router.get("/admin/users")
def list_admin_users(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    status: Optional[int] = Query(
        None,
        description="User status (0=inactive, 1=active, 2=pending registration)",
    ),
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
):
    """
    Admin: list users with optional filters.
    JOINs branch, department, position, and users_resource so the Flutter app
    receives full text names (not just IDs).

    Returns JSON:
    {
      "items": [ { enriched user fields } ],
      "total": 123
    }
    """
    _ensure_admin(current_user)

    # ── Build WHERE conditions ─────────────────────────────────────────────────
    where_conditions: list[str] = []
    params: dict = {}

    if status is not None:
        # Statuses represent distinct lifecycle states. In particular, an
        # inactive staff account (0) is not a pending registration (2).
        where_conditions.append("u.status = :status")
        params["status"] = status
    # No default status filter for admin — show all by default

    if branch_id is not None:
        where_conditions.append("u.workplace = :branch_id")
        params["branch_id"] = branch_id

    if department_id is not None:
        where_conditions.append("u.departmentId = :department_id")
        params["department_id"] = department_id

    if search:
        like = f"%{search}%"
        where_conditions.append(
            "(u.eName LIKE :search OR u.kName LIKE :search OR u.username LIKE :search "
            "OR u.phone LIKE :search OR u.email LIKE :search "
            "OR d.department LIKE :search OR d.translate LIKE :search "
            "OR p.position LIKE :search OR p.translate LIKE :search)"
        )
        params["search"] = like

    where_clause = ("WHERE " + " AND ".join(where_conditions)) if where_conditions else ""

    # ── SELECT with JOINs (matches teachers.py pattern) ───────────────────────
    select_sql = """
        SELECT
            u.id,
            u.eName,
            u.kName,
            u.gender,
            u.dob,
            u.status,
            u.role,
            u.created_at,
            u.workplace           AS branch_id,
            b.branch_name,
            u.departmentId,
            d.id                  AS dept_id,
            d.department          AS dept_name,
            d.translate           AS dept_translate,
            d.code                AS dept_code,
            u.positionId,
            p.id                  AS pos_id,
            p.position            AS pos_name,
            p.translate           AS pos_translate,
            u.email,
            u.phone,
            u.username,
            COALESCE(ur_t.avatar, ur_e.avatar) AS avatar,
            (
                SELECT COUNT(*)
                FROM device_tokens dt
                WHERE dt.user_id = u.id
                  AND dt.user_type IN ('teacher', 'employee', 'admin', 'app_admin')
                  AND dt.is_active = 1
            ) AS device_count,
            (
                SELECT dt.app_version
                FROM device_tokens dt
                WHERE dt.user_id = u.id
                  AND dt.user_type IN ('teacher', 'employee', 'admin', 'app_admin')
                  AND dt.is_active = 1
                ORDER BY COALESCE(dt.last_used_at, dt.updated_at, dt.created_at) DESC,
                         dt.id DESC
                LIMIT 1
            ) AS latest_app_version,
            (
                SELECT dt.device_type
                FROM device_tokens dt
                WHERE dt.user_id = u.id
                  AND dt.user_type IN ('teacher', 'employee', 'admin', 'app_admin')
                  AND dt.is_active = 1
                ORDER BY COALESCE(dt.last_used_at, dt.updated_at, dt.created_at) DESC,
                         dt.id DESC
                LIMIT 1
            ) AS latest_device_type,
            (
                SELECT dt.device_name
                FROM device_tokens dt
                WHERE dt.user_id = u.id
                  AND dt.user_type IN ('teacher', 'employee', 'admin', 'app_admin')
                  AND dt.is_active = 1
                ORDER BY COALESCE(dt.last_used_at, dt.updated_at, dt.created_at) DESC,
                         dt.id DESC
                LIMIT 1
            ) AS latest_device_name,
            (
                SELECT COALESCE(dt.last_used_at, dt.updated_at, dt.created_at)
                FROM device_tokens dt
                WHERE dt.user_id = u.id
                  AND dt.user_type IN ('teacher', 'employee', 'admin', 'app_admin')
                  AND dt.is_active = 1
                ORDER BY COALESCE(dt.last_used_at, dt.updated_at, dt.created_at) DESC,
                         dt.id DESC
                LIMIT 1
            ) AS latest_device_last_seen_at,
            u.startWork
        FROM users u
        LEFT JOIN branch b         ON u.workplace    = b.id
        LEFT JOIN department d     ON u.departmentId = d.id
        LEFT JOIN position p       ON u.positionId   = p.id
        LEFT JOIN users_resource ur_t ON u.id = ur_t.user_id AND ur_t.user_type = 'teacher'
        LEFT JOIN users_resource ur_e ON u.id = ur_e.user_id AND ur_e.user_type = 'employee'
    """

    count_sql = f"""
        SELECT COUNT(DISTINCT u.id)
        FROM users u
        LEFT JOIN department d ON u.departmentId = d.id
        LEFT JOIN position p   ON u.positionId   = p.id
        {where_clause}
    """

    # ── Total count ────────────────────────────────────────────────────────────
    try:
        total = db.execute(text(count_sql), params).scalar() or 0
    except Exception as e:
        logger.error(f"Admin users count error: {e}")
        total = 0

    # ── Paginated rows ─────────────────────────────────────────────────────────
    offset = (page - 1) * limit
    paged_params = {**params, "limit": limit, "offset": offset}
    data_sql = f"{select_sql} {where_clause} ORDER BY u.id DESC LIMIT :limit OFFSET :offset"

    try:
        rows = db.execute(text(data_sql), paged_params).fetchall()
    except Exception as e:
        logger.error(f"Admin users query error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # ── Serialize ──────────────────────────────────────────────────────────────
    user_ids = [r[0] for r in rows if r and r[0] is not None]
    locked_features_by_user = _locked_features_map(db, user_ids)
    app_devices_by_user: dict[int, list[dict[str, Any]]] = {}
    for device in _active_staff_device_tokens(db, user_ids):
        app_devices_by_user.setdefault(int(device.user_id), []).append(
            _app_device_payload(device)
        )
    items = []
    for row in rows:
        # Column indices match SELECT order above
        (
            uid, eName, kName, gender, dob, usr_status, role, created_at,
            branch_id_val, branch_name,
            dept_id_raw, dept_id, dept_name, dept_translate, dept_code,
            pos_id_raw, pos_id, pos_name, pos_translate,
            email, phone, username, avatar, device_count, latest_app_version,
            latest_device_type, latest_device_name, latest_device_last_seen_at,
            start_work,
        ) = row

        # Calculate age from dob
        age = None
        if dob:
            try:
                from datetime import date
                today = date.today()
                dob_date = dob if hasattr(dob, "year") else date.fromisoformat(str(dob))
                age = (
                    today.year - dob_date.year
                    - ((today.month, today.day) < (dob_date.month, dob_date.day))
                )
            except Exception:
                pass

        items.append({
            "id": uid,
            "eName": eName or "",
            "kName": kName or "",
            "fullName": f"{eName or ''} {kName or ''}".strip(),
            "first_name": eName or "",
            "last_name": kName or "",
            "gender": gender,
            "dob": _format_date(dob),
            "age": age,
            "status": usr_status,
            "is_active": usr_status == 1,
            "role": role,
            "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at) if created_at else None,
            "email": email,
            "phone": phone,
            "username": username,
            "avatar": avatar,
            "device_count": device_count,
            "has_app_session": (device_count or 0) > 0,
            "app_version": latest_app_version,
            "device_type": latest_device_type,
            "device_name": latest_device_name,
            "device_last_seen_at": _format_date(latest_device_last_seen_at),
            "app_devices": app_devices_by_user.get(int(uid), []),
            "locked_features": locked_features_by_user.get(uid, []),
            # Branch
            "workplace": branch_id_val,
            "branch_id": branch_id_val,
            "branch_name": branch_name,
            # Department — both ID and text names
            "departmentId": dept_id_raw,
            "department_id": dept_id,
            "department": dept_name,           # text label used by Teacher.fromJson
            "dept_name": dept_name,
            "dept_translate": dept_translate,
            "dept_code": dept_code,
            "department_info": {
                "id": dept_id,
                "department": dept_name,
                "translate": dept_translate,
                "code": dept_code,
            } if dept_id is not None else None,
            # Position — both ID and text names
            "positionId": pos_id_raw,
            "position_id": pos_id,
            "position": pos_name,              # text label used by Teacher.fromJson
            "pos_translate": pos_translate,
            "position_info": {
                "id": pos_id,
                "position": pos_name,
                "translate": pos_translate,
            } if pos_id is not None else None,
            # Work start date — used for work anniversary duration display
            "startWork": _format_date(start_work),
            "hire_date": _format_date(start_work),
        })

    return {"items": items, "total": total}


@router.get("/admin/users/{user_id}/registration-review")
def get_admin_user_registration_review(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """Return the complete submitted profile for a pending staff request."""
    _ensure_admin(current_user)

    row = (
        db.execute(
            text(
                """
                SELECT
                    u.id,
                    u.uniqueId,
                    u.username,
                    u.kName,
                    u.eName,
                    u.height,
                    u.gender,
                    u.dob,
                    u.nationality,
                    u.religion,
                    u.province,
                    u.district,
                    u.commune,
                    u.village,
                    u.email,
                    u.phone,
                    u.telegramId,
                    u.pProvince,
                    u.pDistrict,
                    u.pCommune,
                    u.pVillage,
                    u.identityNumber,
                    u.identityRegDate,
                    u.identityEndDate,
                    u.identityRegPlace,
                    u.fatherName,
                    u.motherName,
                    u.departmentId,
                    u.positionId,
                    u.startWork,
                    u.endWork,
                    u.education,
                    u.workplace,
                    u.status,
                    u.role,
                    u.isForeigner,
                    u.baseSalary AS salary,
                    u.bankAccountNumber,
                    u.bankAccountName,
                    u.bankName,
                    u.nssfNumber,
                    u.isNssf,
                    u.isResident,
                    u.hasSpouse,
                    u.numberOfDependents,
                    u.created_at,
                    u.updated_at,
                    b.branch_name,
                    d.department AS dept_name,
                    d.translate AS dept_translate,
                    d.code AS dept_code,
                    p.position AS pos_name,
                    p.translate AS pos_translate,
                    COALESCE(ur_t.avatar, ur_e.avatar) AS avatar
                FROM users u
                LEFT JOIN branch b ON b.id = u.workplace
                LEFT JOIN department d ON d.id = u.departmentId
                LEFT JOIN position p ON p.id = u.positionId
                LEFT JOIN users_resource ur_t
                    ON ur_t.user_id = u.id AND ur_t.user_type = 'teacher'
                LEFT JOIN users_resource ur_e
                    ON ur_e.user_id = u.id AND ur_e.user_type = 'employee'
                WHERE u.id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff registration not found",
        )

    values = dict(row)
    if int(values.get("status") or 0) != 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This staff account is not awaiting registration approval",
        )

    values.update(
        {
            "first_name": values.get("eName") or "",
            "last_name": values.get("kName") or "",
            "is_active": False,
            "hire_date": _format_date(values.get("startWork")),
            "created_at": _format_date(values.get("created_at")),
            "updated_at": _format_date(values.get("updated_at")),
            "dob": _format_date(values.get("dob")),
            "identityRegDate": _format_date(values.get("identityRegDate")),
            "identityEndDate": _format_date(values.get("identityEndDate")),
        }
    )
    return values


@router.post("/admin/users/{user_id}/approve-registration")
def approve_admin_staff_registration(
    user_id: int,
    payload: ApproveStaffRegistrationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """Atomically activate a reviewed staff registration (status 2 -> 1)."""
    _ensure_admin(current_user)

    target = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff registration not found",
        )

    current_status = int(getattr(target, "status", 0) or 0)
    if current_status == 1:
        return {
            "success": True,
            "user_id": user_id,
            "status": 1,
            "already_approved": True,
        }
    if current_status != 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This staff registration is no longer awaiting approval",
        )

    locked_features: list[str] = []
    try:
        target.status = 1
        if payload.apply_default_locks:
            locked_features = sorted(_DEFAULT_REGISTRATION_LOCKS)
            db.query(UserHomeAppPermission).filter(
                UserHomeAppPermission.user_id == user_id
            ).delete()
            for feature_id in locked_features:
                db.add(
                    UserHomeAppPermission(
                        user_id=user_id,
                        feature_id=feature_id,
                        is_allowed=False,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise

    from ...services.registration_notification_service import (
        notify_staff_registration_approved,
    )

    background_tasks.add_task(notify_staff_registration_approved, user_id)
    return {
        "success": True,
        "user_id": user_id,
        "status": 1,
        "already_approved": False,
        "locked_features": locked_features,
    }


@router.put("/admin/users/{user_id}")
def update_admin_user(
    user_id: int,
    payload: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Admin: update basic user fields.
    Accepts partial payload (e.g. {"status": 0, "workplace": 2, "departmentId": 3}).
    """
    _ensure_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    previous_status = int(getattr(user, "status", 0) or 0)
    allowed_fields = {"status", "workplace", "departmentId", "role"}
    locked_features_payload = payload.get("locked_features")
    for field, value in payload.items():
        if field not in allowed_fields:
            continue
        if hasattr(user, field):
            setattr(user, field, value)

    if locked_features_payload is not None:
        if not isinstance(locked_features_payload, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="locked_features must be an array of feature ids",
            )
        normalized_locked = {
            str(item).strip() for item in locked_features_payload if str(item).strip()
        }
        db.query(UserHomeAppPermission).filter(
            UserHomeAppPermission.user_id == user_id
        ).delete()
        for feature_id in normalized_locked:
            db.add(
                UserHomeAppPermission(
                    user_id=user_id,
                    feature_id=feature_id,
                    is_allowed=False,
                )
            )

    db.commit()
    if locked_features_payload is not None:
        _notify_home_permission_updated(db, user_id)
    db.refresh(user)

    if previous_status == 2 and int(getattr(user, "status", 0) or 0) == 1:
        from ...services.registration_notification_service import (
            notify_staff_registration_approved,
        )

        background_tasks.add_task(notify_staff_registration_approved, user_id)

    return {
        "id": user.id,
        "username": user.username,
        "status": user.status,
        "workplace": user.workplace,
        "departmentId": user.departmentId,
        "role": user.role,
        "locked_features": sorted(
            [
                r.feature_id
                for r in db.query(UserHomeAppPermission)
                .filter(
                    UserHomeAppPermission.user_id == user.id,
                    UserHomeAppPermission.is_allowed == False,
                )
                .all()
            ]
        ),
    }


@router.get("/admin/users/{user_id}/home-app-permissions")
def get_user_home_app_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    _ensure_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    rows = (
        db.query(UserHomeAppPermission)
        .filter(UserHomeAppPermission.user_id == user_id)
        .all()
    )
    locked = sorted([r.feature_id for r in rows if not r.is_allowed])
    allowed = sorted([r.feature_id for r in rows if r.is_allowed])
    return {
        "user_id": user_id,
        "locked_features": locked,
        "allowed_features": allowed,
    }


@router.put("/admin/users/{user_id}/home-app-permissions")
def set_user_home_app_permissions(
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    _ensure_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if "locked_features" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="locked_features is required",
        )
    locked_features_payload = payload.get("locked_features")
    if not isinstance(locked_features_payload, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="locked_features must be an array of feature ids",
        )

    normalized_locked = {
        str(item).strip() for item in locked_features_payload if str(item).strip()
    }
    db.query(UserHomeAppPermission).filter(
        UserHomeAppPermission.user_id == user_id
    ).delete()
    for feature_id in normalized_locked:
        db.add(
            UserHomeAppPermission(
                user_id=user_id,
                feature_id=feature_id,
                is_allowed=False,
            )
        )
    db.commit()
    _notify_home_permission_updated(db, user_id)

    return {
        "user_id": user_id,
        "locked_features": sorted(normalized_locked),
    }


@router.post("/admin/users/{user_id}/logout")
async def admin_logout_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Admin: force logout a user.
    - Increments the user's token_version so all existing JWTs are invalidated.
    - Deletes all device tokens for that user so clients are effectively signed out.
    """
    _ensure_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        # Bump token_version so any existing JWTs become invalid
        current_version = getattr(user, "token_version", 1) or 1
        user.token_version = current_version + 1

        # Collect active device tokens BEFORE deleting them (for realtime push)
        device_tokens = _active_staff_device_tokens(db, [user_id])

        # Remove only this staff account's tokens. Parent/student tables use
        # independent numeric IDs and can legitimately have the same value.
        db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.user_type.in_(_STAFF_DEVICE_TYPES),
        ).delete(synchronize_session=False)

        db.commit()
    except Exception:
        db.rollback()
        raise

    # After DB changes are committed, send realtime force-logout push
    try:
        if device_tokens:
            # Prepare token payloads for notification_service
            token_payloads = _device_token_payloads(device_tokens)

            await asyncio.to_thread(
                send_notification,
                device_tokens=token_payloads,
                title="Session Ended",
                body="You have been signed out by an administrator.",
                data={
                    "type": "force_logout",
                    "reason": "admin_logout",
                    "user_id": str(user_id),
                },
                color="#F44336",
                icon=None,
                actions=None,
                vibrate=True,
                android_show_system_notification=True,
                db=db,
                user_ids=[{"id": user_id, "user_type": "teacher"}],
                is_deletable=True,
                redirect_route="login",
                redirect_args=None,
            )
    except Exception as e:
        logger.error(f"Failed to send force_logout push for user {user_id}: {e}")

    return {"success": True}


@router.post("/admin/users/{user_id}/reset-password-next-login")
async def admin_reset_password_next_login(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Admin: reset a user's password to a secure temporary value.
    - Generates a random temporary password.
    - Hashes and stores it on the user.
    - Bumps token_version and deletes device tokens to force re-login.
    - Returns the temporary password so the admin can share it securely.
    """
    _ensure_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Generate a reasonably strong, user-typable temporary password
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    temp_password = "".join(secrets.choice(alphabet) for _ in range(10))

    try:
        # Set new hashed password
        user.password = get_password_hash(temp_password)

        # Invalidate all existing tokens
        current_version = getattr(user, "token_version", 1) or 1
        user.token_version = current_version + 1

        # Collect active device tokens BEFORE deleting them so we can push logout
        device_tokens = _active_staff_device_tokens(db, [user_id])

        # Delete only this staff account's device rows.
        db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.user_type.in_(_STAFF_DEVICE_TYPES),
        ).delete(synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reset password for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password",
        )

    # After commit, send realtime force-logout push so app exits immediately
    try:
        if device_tokens:
            token_payloads = _device_token_payloads(device_tokens)

            await asyncio.to_thread(
                send_notification,
                device_tokens=token_payloads,
                title="Password Reset",
                body="Your session has ended because your password was reset.",
                data={
                    "type": "force_logout",
                    "reason": "password_reset",
                    "user_id": str(user_id),
                },
                color="#0EA5E9",
                icon=None,
                actions=None,
                vibrate=True,
                android_show_system_notification=True,
                db=db,
                user_ids=[{"id": user_id, "user_type": "teacher"}],
                is_deletable=True,
                redirect_route="login",
                redirect_args=None,
            )
    except Exception as e:
        logger.error(
            f"Failed to send force_logout push after password reset for user {user_id}: {e}"
        )

    return {"success": True, "temporary_password": temp_password}


@router.post("/admin/users/{user_id}/notify-update-app")
def admin_notify_update_app(
    user_id: int,
    payload: NotifyUpdateAppRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Admin: send an in-app notification to a single user
    asking them to update the App to the latest version.

    Uses the user's latest known app_version (if any) and
    active device tokens.
    """
    _ensure_admin(current_user)

    # Rows are ordered newest-first, so version and phone metadata always come
    # from the same installation instead of unrelated aggregate subqueries.
    device_tokens = _active_staff_device_tokens(db, [user_id])
    latest_app_version = (
        str(device_tokens[0].app_version or "") if device_tokens else ""
    )

    if not device_tokens:
        # No active app sessions, but still return success so UI
        # doesn't treat this as an error.
        return {
            "success": False,
            "detail": "User has no active app sessions / device tokens.",
        }

    # Build message
    message = payload.message or (
        "Please update the App to the latest version from the store. "
        + (
            f"Your current version is v{latest_app_version}."
            if latest_app_version
            else "A newer version is now available."
        )
    )

    token_payloads = _device_token_payloads(device_tokens)

    ok = send_notification(
        device_tokens=token_payloads,
        title="Update available",
        body=message,
        data={
            "type": "app_update",
            "user_id": str(user_id),
            "current_version": latest_app_version or "",
        },
        color="#0EA5E9",
        icon=None,
        actions=None,
        vibrate=True,
        android_show_system_notification=True,
        db=db,
        user_ids=[{"id": user_id, "user_type": "teacher"}],
        is_deletable=True,
        redirect_route="home",
        redirect_args=None,
    )

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send update notification",
        )

    return {"success": True}
