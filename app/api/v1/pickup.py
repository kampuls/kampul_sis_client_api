"""
Child Pickup API — parents summon their children, admin manages a queue with sound playback.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
import base64
import json
import math
import os
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging

from ...core import get_db
from ...auth import get_current_active_user
from ...models import User
from ...services.storage_service import StorageService
from .websocket import broadcast_to_room, broadcast_to_user

router = APIRouter()
logger = logging.getLogger(__name__)

_STALE_PICKUP_AGE = timedelta(hours=3)
_STALE_CLEANUP_INTERVAL = timedelta(minutes=1)
_stale_cleanup_last_by_academic: Dict[int, datetime] = {}


def _is_parent_principal(current_user: Any) -> bool:
    return bool(getattr(current_user, "is_parent", False)) or str(
        getattr(current_user, "role", "")
    ).lower() == "parent"


def _require_pickup_parent(current_user: Any) -> None:
    if not _is_parent_principal(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Parent access required",
        )


def _require_pickup_staff(current_user: Any) -> None:
    """Reject parent principals from hall-management and configuration routes."""
    if _is_parent_principal(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required",
        )
    try:
        int(getattr(current_user, "role"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required",
        )


def _body_academic_id(body: dict) -> int:
    try:
        academic_id = int(body.get("academic_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="academic_id required")
    if academic_id <= 0:
        raise HTTPException(status_code=400, detail="academic_id must be positive")
    return academic_id


def _strict_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise HTTPException(status_code=400, detail=f"{field_name} must be a boolean")


def _expire_stale_pickup_requests(
    db: Session,
    academic_id: int,
    now: Optional[datetime] = None,
) -> None:
    """Best-effort cleanup, throttled so read polling does not become write load."""
    current = now or datetime.utcnow()
    last = _stale_cleanup_last_by_academic.get(int(academic_id))
    if last is not None and current - last < _STALE_CLEANUP_INTERVAL:
        return

    _stale_cleanup_last_by_academic[int(academic_id)] = current
    try:
        db.execute(
            text("""
                UPDATE pickup_requests
                SET status = 'cancelled', completed_at = :now
                WHERE academic_id = :aid
                  AND status IN ('pending', 'processing')
                  AND requested_at < :limit
            """),
            {
                "aid": int(academic_id),
                "now": current,
                "limit": current - _STALE_PICKUP_AGE,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _stale_cleanup_last_by_academic.pop(int(academic_id), None)
        logger.warning("Pickup stale-request cleanup failed: %s", exc)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters (WGS84 sphere)."""
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c


def _parent_owned_student_ids(db: Session, parent_id: int) -> set:
    row = db.execute(
        text("SELECT myChilds FROM parents WHERE id = :pid"),
        {"pid": parent_id},
    ).fetchone()
    if not row or not row[0]:
        return set()
    out: set = set()
    for part in str(row[0]).split(","):
        p = part.strip()
        if p.isdigit():
            out.add(int(p))
    return out


def _parse_extra_branch_ids(raw) -> List[int]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw if str(x).strip().isdigit()]
    try:
        data = json.loads(str(raw).strip())
        if isinstance(data, list):
            return [int(x) for x in data if str(x).strip().isdigit()]
    except Exception:
        pass
    return []


def _student_allowed_branch_ids(branch_val, extra_raw) -> List[int]:
    ids: List[int] = []
    if branch_val is not None:
        try:
            b = int(branch_val)
            if b > 0:
                ids.append(b)
        except (TypeError, ValueError):
            pass
    for x in _parse_extra_branch_ids(extra_raw):
        if x not in ids:
            ids.append(x)
    return ids


def _branch_geofence_entries(db: Session, branch_ids: List[int]) -> List[tuple]:
    """(branch_id, lat, lon, radius_m) for branches that require a location check."""
    if not branch_ids:
        return []
    ph = ",".join([f":b{i}" for i in range(len(branch_ids))])
    params = {f"b{i}": bid for i, bid in enumerate(branch_ids)}
    rows = db.execute(
        text(
            f"""
            SELECT id, map_latitude, map_longitude, pickup_radius_meters
            FROM branch
            WHERE id IN ({ph})
            """
        ),
        params,
    ).fetchall()
    active: List[tuple] = []
    for r in rows:
        bid, mlat, mlon, rad = r[0], r[1], r[2], r[3]
        try:
            radius = float(rad) if rad is not None else None
        except (TypeError, ValueError):
            radius = None
        if radius is None or radius <= 0:
            continue
        try:
            flat = float(mlat) if mlat is not None else None
            flon = float(mlon) if mlon is not None else None
        except (TypeError, ValueError):
            flat, flon = None, None
        if flat is None or flon is None:
            continue
        try:
            active.append((int(bid), flat, flon, radius))
        except (TypeError, ValueError):
            continue
    return active


def _branch_geofences_for_pickup(db: Session, branch_ids: List[int]) -> List[tuple]:
    """Return list of (lat, lon, radius_m) for branches that require a location check."""
    return [(lat, lon, rad) for (_, lat, lon, rad) in _branch_geofence_entries(db, branch_ids)]


def _resolve_pickup_branch_id(
    db: Session,
    allowed_branch_ids: List[int],
    home_branch_id: Optional[int],
    latitude: Optional[float],
    longitude: Optional[float],
) -> int:
    """
    Branch this pickup is attributed to: innermost geofence match (closest center among hits),
    else student's home branch, else first allowed branch.
    """
    def _fallback() -> int:
        try:
            if home_branch_id is not None and int(home_branch_id) > 0:
                return int(home_branch_id)
        except (TypeError, ValueError):
            pass
        if allowed_branch_ids:
            return int(allowed_branch_ids[0])
        return 0

    entries = _branch_geofence_entries(db, allowed_branch_ids)
    if not entries:
        return _fallback()

    if latitude is None or longitude is None:
        return _fallback()
    try:
        plat, plon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return _fallback()

    matches: List[tuple] = []
    for bid, flat, flon, radius in entries:
        try:
            d = _haversine_meters(plat, plon, float(flat), float(flon))
            if d <= float(radius):
                matches.append((int(bid), d))
        except (TypeError, ValueError):
            continue
    if not matches:
        return _fallback()
    matches.sort(key=lambda x: x[1])
    return int(matches[0][0])


def _validate_parent_in_pickup_zone(
    db: Session,
    allowed_branch_ids: List[int],
    latitude: Optional[float],
    longitude: Optional[float],
) -> None:
    """
    If any allowed branch has pickup_radius_meters + map coords, parent lat/lng is required
    and must fall inside at least one such radius.
    """
    active = _branch_geofences_for_pickup(db, allowed_branch_ids)
    if not active:
        return
    if latitude is None or longitude is None:
        raise HTTPException(status_code=400, detail="LOCATION_REQUIRED")
    try:
        plat, plon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="LOCATION_REQUIRED")
    for flat, flon, radius in active:
        if _haversine_meters(plat, plon, flat, flon) <= radius:
            return
    raise HTTPException(status_code=403, detail="OUTSIDE_PICKUP_ZONE")


def _within_pickup_zone_optional(
    db: Session,
    allowed_branch_ids: List[int],
    latitude: Optional[float],
    longitude: Optional[float],
) -> Optional[bool]:
    """None if no geofence or coords missing; True/False otherwise."""
    active = _branch_geofences_for_pickup(db, allowed_branch_ids)
    if not active:
        return None
    if latitude is None or longitude is None:
        return None
    try:
        plat, plon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    for flat, flon, radius in active:
        if _haversine_meters(plat, plon, flat, flon) <= radius:
            return True
    return False


def _json_safe_student_image(val) -> str:
    """Return the API-managed student image URL/path."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, memoryview):
        val = val.tobytes()
    if isinstance(val, bytes):
        raise ValueError("Binary student media must be migrated to a resource URL")
    return ""


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _get_settings(db: Session, academic_id: int) -> dict:
    """Return pickup settings for academic year, creating defaults if absent."""
    row = db.execute(
        text(
            "SELECT repeat_count, cooldown_seconds, calling_enabled FROM pickup_settings WHERE academic_id = :aid"
        ),
        {"aid": academic_id},
    ).fetchone()
    if row:
        ce_raw = row[2]
        if ce_raw is None:
            calling_on = False
        else:
            try:
                calling_on = bool(int(ce_raw))
            except (TypeError, ValueError):
                calling_on = bool(ce_raw)
        return {
            "repeat_count": row[0],
            "cooldown_seconds": row[1],
            "calling_enabled": calling_on,
        }
    # Auto-insert defaults
    db.execute(
        text("""
            INSERT INTO pickup_settings (academic_id, repeat_count, cooldown_seconds, calling_enabled, updated_at)
            VALUES (:aid, 3, 300, 0, NOW())
        """),
        {"aid": academic_id},
    )
    db.commit()
    return {"repeat_count": 3, "cooldown_seconds": 300, "calling_enabled": False}


def _pickup_calling_by_branch(db: Session, academic_id: int) -> Dict[int, bool]:
    """branch_id -> staff hall-calling on for that campus."""
    rows = db.execute(
        text(
            """
            SELECT branch_id, calling_enabled FROM pickup_branch_calling
            WHERE academic_id = :aid
            """
        ),
        {"aid": academic_id},
    ).fetchall()
    out: Dict[int, bool] = {}
    for bid_raw, ce_raw in rows:
        try:
            bid = int(bid_raw)
        except (TypeError, ValueError):
            continue
        try:
            on = bool(int(ce_raw)) if ce_raw is not None else False
        except (TypeError, ValueError):
            on = bool(ce_raw)
        out[bid] = on
    return out


def _sync_legacy_global_calling_flag(db: Session, academic_id: int) -> None:
    """pickup_settings.calling_enabled = 1 iff any branch has hall calling on."""
    row = db.execute(
        text(
            """
            SELECT COALESCE(MAX(calling_enabled), 0) FROM pickup_branch_calling
            WHERE academic_id = :aid
            """
        ),
        {"aid": academic_id},
    ).fetchone()
    flag = 0
    if row and row[0] is not None:
        try:
            flag = 1 if int(row[0]) > 0 else 0
        except (TypeError, ValueError):
            flag = 1 if bool(row[0]) else 0
    db.execute(
        text(
            """
            UPDATE pickup_settings SET calling_enabled = :ce, updated_at = NOW()
            WHERE academic_id = :aid
            """
        ),
        {"aid": academic_id, "ce": flag},
    )


def _queue_item(row) -> dict:
    return {
        "id": row[0],
        "student_id": row[1],
        "student_name_kh": row[2] or "",
        "student_name_en": row[3] or "",
        "student_image": _json_safe_student_image(row[4]),
        "parent_id": row[5],
        "parent_name": row[6] or "",
        "status": row[7],
        "repeat_count": row[8],
        "current_repeat": row[9],
        "requested_at": row[10].isoformat() if row[10] else None,
        "processing_started_at": row[11].isoformat() if row[11] else None,
        "pickup_audio_url": row[12] if len(row) > 12 else None,
        "pickup_branch_id": int(row[13])
        if len(row) > 13 and row[13] is not None
        else None,
    }


QUEUE_SELECT = """
    SELECT 
        pr.id, pr.student_id,
        s.kName, s.eName, s.image,
        pr.parent_id,
        COALESCE(p.fatherName, p.motherName, '') as parent_name,
        pr.status, pr.repeat_count, pr.current_repeat,
        pr.requested_at, pr.processing_started_at,
        s.pickup_audio_url,
        pr.pickup_branch_id
    FROM pickup_requests pr
    JOIN students s ON pr.student_id = s.id
    LEFT JOIN parents p ON pr.parent_id = p.id
"""

# ─────────────────────────────────────────────
# PARENT ENDPOINTS
# ─────────────────────────────────────────────

@router.post("/request")
async def create_pickup_request(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Parent submits a pickup request for one of their children.
    Body: { student_id: int, academic_id: int, latitude?: float, longitude?: float }
    When any allowed branch has pickup_radius_meters + map coordinates, lat/lng are required.
    """
    _require_pickup_parent(current_user)
    try:
        student_id = int(body.get("student_id"))
        academic_id = int(body.get("academic_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="student_id and academic_id are required")
    if student_id <= 0 or academic_id <= 0:
        raise HTTPException(status_code=400, detail="student_id and academic_id must be positive")

    parent_id = current_user.id
    now = datetime.utcnow()

    lat = body.get("latitude")
    lng = body.get("longitude")

    # 0. Must be parent's child (parents.id matches app user id for parent accounts)
    owned = _parent_owned_student_ids(db, parent_id)
    if int(student_id) not in owned:
        raise HTTPException(status_code=403, detail="NOT_YOUR_CHILD")

    # 1. Check student exists + branch rules
    student = db.execute(
        text(
            """
            SELECT id, kName, eName, image, branch, pickup_extra_branch_ids
            FROM students WHERE id = :sid
            """
        ),
        {"sid": student_id},
    ).fetchone()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    allowed_branches = _student_allowed_branch_ids(student[4], student[5])
    _validate_parent_in_pickup_zone(db, allowed_branches, lat, lng)

    try:
        home_b = int(student[4]) if student[4] is not None and str(student[4]).strip() != "" else None
    except (TypeError, ValueError):
        home_b = None
    pickup_branch_id = _resolve_pickup_branch_id(db, allowed_branches, home_b, lat, lng)
    if pickup_branch_id <= 0:
        pickup_branch_id = home_b or (allowed_branches[0] if allowed_branches else 0)
    if pickup_branch_id <= 0:
        raise HTTPException(status_code=400, detail="Could not resolve pickup branch")

    # 2. Check cooldown — parent cannot re-request while cooldown is active
    cooldown_row = db.execute(
        text("""
            SELECT cooldown_until FROM pickup_requests
            WHERE parent_id = :pid AND student_id = :sid
            ORDER BY id DESC LIMIT 1
        """),
        {"pid": parent_id, "sid": student_id}
    ).fetchone()
    if cooldown_row and cooldown_row[0] and cooldown_row[0] > now:
        remaining = int((cooldown_row[0] - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"COOLDOWN:{remaining}"  # frontend parses remaining seconds
        )

    # 3. Get settings to determine repeat_count & cooldown (may commit if defaults inserted)
    settings = _get_settings(db, academic_id)

    # 4. Serialize concurrent requests for the same student (multi-parent / double-tap).
    # Run AFTER settings so an internal commit does not release our lock before insert.
    # Lock an existing row, not only a possibly-empty active-request result.
    # This serializes simultaneous double taps across API workers reliably.
    db.execute(
        text("SELECT id FROM students WHERE id = :sid FOR UPDATE"),
        {"sid": student_id},
    ).fetchone()
    active = db.execute(
        text("""
            SELECT id FROM pickup_requests
            WHERE student_id = :sid AND status IN ('pending', 'processing')
            LIMIT 1
        """),
        {"sid": student_id},
    ).fetchone()
    if active:
        db.rollback()
        raise HTTPException(status_code=409, detail="ALREADY_IN_QUEUE")

    # 5. Calculate cooldown_until
    cooldown_until = now + timedelta(seconds=settings["cooldown_seconds"])

    # 6. Insert request
    db.execute(
        text("""
            INSERT INTO pickup_requests
                (student_id, parent_id, academic_id, pickup_branch_id, status, repeat_count, current_repeat,
                 requested_at, cooldown_until)
            VALUES
                (:sid, :pid, :aid, :pbid, 'pending', :rc, 0, :now, :cu)
        """),
        {
            "sid": student_id,
            "pid": parent_id,
            "aid": academic_id,
            "pbid": pickup_branch_id,
            "rc": settings["repeat_count"],
            "now": now,
            "cu": cooldown_until,
        }
    )
    db.commit()

    new_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    # 7. Broadcast to admin room + all parents watching pickup for this academic year
    await broadcast_to_room(f"pickup_admin_{academic_id}", {
        "type": "pickup_new_request",
        "payload": {
            "request_id": new_id,
            "student_id": student_id,
            "student_name_kh": student[1] or "",
            "student_name_en": student[2] or "",
            "student_image": _json_safe_student_image(student[3]),
        }
    })
    await broadcast_to_room(f"pickup_parents_{academic_id}", {
        "type": "pickup_queue_changed",
        "payload": {"academic_id": academic_id},
    })

    return {
        "success": True,
        "request_id": new_id,
        "message": "Pickup request submitted",
        "cooldown_until": cooldown_until.isoformat()
    }


@router.get("/my-requests")
async def get_my_requests(
    academic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Parent: get their own active/recent requests."""
    _require_pickup_parent(current_user)
    rows = db.execute(
        text(QUEUE_SELECT + """
            WHERE pr.parent_id = :pid AND pr.academic_id = :aid
            AND pr.status IN ('pending', 'processing')
            ORDER BY pr.requested_at DESC
        """),
        {"pid": current_user.id, "aid": academic_id}
    ).fetchall()
    return {"requests": [_queue_item(r) for r in rows]}


@router.get("/my-children-status")
async def get_children_status(
    academic_id: int,
    student_ids: str,  # comma-separated e.g. "1,2,3"
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Parent: pickup status per child, global queue length, and queue place (1-based).
    Optional latitude/longitude: returns within_pickup_zone when branch geofences are configured.
    """
    _require_pickup_parent(current_user)
    now = datetime.utcnow()
    
    _expire_stale_pickup_requests(db, academic_id, now)

    calling_map = _pickup_calling_by_branch(db, academic_id)
    ids = [int(x) for x in student_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return {
            "queue_length": 0,
            "statuses": {},
            "calling_enabled": False,
            "calling_by_branch": {str(k): v for k, v in calling_map.items()},
        }

    parent_id = current_user.id
    owned = _parent_owned_student_ids(db, parent_id)
    ids = [i for i in ids if i in owned]
    if not ids:
        return {
            "queue_length": 0,
            "statuses": {},
            "calling_enabled": False,
            "calling_by_branch": {str(k): v for k, v in calling_map.items()},
        }

    count_rows = db.execute(
        text(
            """
            SELECT pickup_branch_id, COUNT(*) AS c FROM pickup_requests
            WHERE academic_id = :aid AND status IN ('pending', 'processing')
            GROUP BY pickup_branch_id
            """
        ),
        {"aid": academic_id},
    ).fetchall()
    ql_by_branch: Dict[int, int] = {}
    queue_length = 0
    for bid, c in count_rows:
        cnt = int(c or 0)
        queue_length += cnt
        if bid is not None:
            try:
                ql_by_branch[int(bid)] = cnt
            except (TypeError, ValueError):
                pass

    # Student branch info for geofence preview
    st_placeholders = ",".join([f":st{i}" for i in range(len(ids))])
    st_params = {f"st{i}": v for i, v in enumerate(ids)}
    brow = db.execute(
        text(
            f"""
            SELECT id, branch, pickup_extra_branch_ids FROM students
            WHERE id IN ({st_placeholders})
            """
        ),
        st_params,
    ).fetchall()
    branch_by_student = {r[0]: _student_allowed_branch_ids(r[1], r[2]) for r in brow}
    home_by_student: Dict[int, Optional[int]] = {}
    for r in brow:
        hb: Optional[int] = None
        try:
            if r[1] is not None and str(r[1]).strip() != "":
                hb = int(r[1])
        except (TypeError, ValueError):
            hb = None
        home_by_student[r[0]] = hb

    placeholders = ",".join([f":s{i}" for i in range(len(ids))])
    params = {f"s{i}": v for i, v in enumerate(ids)}
    params.update({"aid": academic_id, "now": now})

    rows = db.execute(
        text(
            f"""
            SELECT 
                pr.student_id,
                pr.status,
                pr.cooldown_until,
                pr.pickup_branch_id,
                (
                    SELECT COUNT(*) FROM pickup_requests pr2
                    WHERE pr2.academic_id = :aid
                    AND pr2.status IN ('pending', 'processing')
                    AND pr2.pickup_branch_id <=> pr.pickup_branch_id
                    AND (
                        pr2.requested_at < pr.requested_at
                        OR (pr2.requested_at = pr.requested_at AND pr2.id < pr.id)
                    )
                ) + 1 AS queue_place,
                pr.id AS request_id,
                pr.requested_at
            FROM pickup_requests pr
            WHERE pr.student_id IN ({placeholders})
            AND pr.academic_id = :aid
            AND (pr.status IN ('pending','processing') OR pr.cooldown_until > :now)
            ORDER BY pr.id DESC
            """
        ),
        params,
    ).fetchall()

    status_map: Dict[str, Any] = {}
    for sid in ids:
        ab = branch_by_student.get(sid, [])
        geofence_on = len(_branch_geofences_for_pickup(db, ab)) > 0
        wz = _within_pickup_zone_optional(db, ab, latitude, longitude)
        preview_bid = _resolve_pickup_branch_id(db, ab, home_by_student.get(sid), latitude, longitude)
        q_len = ql_by_branch.get(preview_bid, 0) if preview_bid > 0 else queue_length
        status_map[str(sid)] = {
            "student_id": sid,
            "status": "available",
            "cooldown_until": None,
            "queue_position": None,
            "queue_place": None,
            "queue_length": q_len,
            "within_pickup_zone": wz,
            "pickup_geofence_enabled": geofence_on,
            "preview_pickup_branch_id": preview_bid if preview_bid > 0 else None,
            "request_id": None,
            "requested_at": None,
        }

    latest_by_sid: Dict[int, Any] = {}
    for r in rows:
        sid = r[0]
        if sid not in latest_by_sid:
            latest_by_sid[sid] = r

    for sid, r in latest_by_sid.items():
        key = str(sid)
        if key not in status_map:
            continue
        existing = status_map[key]
        st = r[1]
        cooldown_until = r[2]
        req_branch = r[3]
        qplace = int(r[4]) if r[4] is not None else None
        request_id = r[5]
        requested_at = r[6]
        
        cu_iso = (
            cooldown_until.isoformat() if cooldown_until and cooldown_until > now else None
        )
        req_at_iso = requested_at.isoformat() if requested_at else None
        try:
            rb = int(req_branch) if req_branch is not None else None
        except (TypeError, ValueError):
            rb = None
        if rb is not None and rb > 0:
            existing["queue_length"] = ql_by_branch.get(rb, 0)
            existing["pickup_branch_id"] = rb
        if st in ("pending", "processing"):
            existing["status"] = st
            existing["queue_place"] = qplace
            existing["queue_position"] = qplace
            existing["request_id"] = request_id
            existing["requested_at"] = req_at_iso
            if cu_iso:
                existing["cooldown_until"] = cu_iso
        elif cooldown_until and cooldown_until > now:
            existing["status"] = "cooldown"
            existing["cooldown_until"] = cu_iso
        elif cu_iso:
            existing["cooldown_until"] = cu_iso

    for st in status_map.values():
        eff = st.get("pickup_branch_id")
        if eff is None:
            eff = st.get("preview_pickup_branch_id")
        bid_e: Optional[int] = None
        if eff is not None:
            try:
                bid_e = int(eff)
            except (TypeError, ValueError):
                bid_e = None
        st["hall_calling_active"] = bool(
            bid_e is not None
            and bid_e > 0
            and calling_map.get(bid_e, False)
        )

    any_branch_calling_for_children = any(
        bool(st.get("hall_calling_active")) for st in status_map.values()
    )

    return {
        "queue_length": queue_length,
        "statuses": status_map,
        "calling_enabled": any_branch_calling_for_children,
        "calling_by_branch": {str(k): v for k, v in calling_map.items()},
    }


# ─────────────────────────────────────────────
# ADMIN ENDPOINTS
# ─────────────────────────────────────────────

@router.get("/queue")
async def get_pickup_queue(
    academic_id: int,
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin: get active queue for an academic year, optionally filtered by pickup branch."""
    _require_pickup_staff(current_user)
    _expire_stale_pickup_requests(db, academic_id)

    sql = (
        QUEUE_SELECT
        + """
            WHERE pr.academic_id = :aid AND pr.status IN ('pending', 'processing')
        """
    )
    params: Dict[str, Any] = {"aid": academic_id}
    if branch_id is not None:
        sql += " AND pr.pickup_branch_id = :bid "
        params["bid"] = int(branch_id)
    sql += " ORDER BY pr.requested_at ASC"
    rows = db.execute(text(sql), params).fetchall()
    return {"queue": [_queue_item(r) for r in rows]}


@router.get("/queue/history")
async def get_pickup_history(
    academic_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin: get completed/cancelled requests (recent history)."""
    _require_pickup_staff(current_user)
    rows = db.execute(
        text(QUEUE_SELECT + """
            WHERE pr.academic_id = :aid AND pr.status IN ('completed', 'cancelled')
            ORDER BY pr.completed_at DESC
            LIMIT :lim
        """),
        {"aid": academic_id, "lim": limit}
    ).fetchall()
    return {"history": [_queue_item(r) for r in rows]}


@router.put("/queue/{request_id}/next-repeat")
async def advance_repeat(
    request_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Admin: increment current_repeat for a request.
    If current_repeat >= repeat_count, auto-complete.
    Body: { academic_id: int, expected_current_repeat?: int }
    """
    _require_pickup_staff(current_user)
    academic_id = _body_academic_id(body)
    expected_current_repeat = body.get("expected_current_repeat")
    if expected_current_repeat is not None:
        try:
            expected_current_repeat = int(expected_current_repeat)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="expected_current_repeat must be an integer",
            )
    row = db.execute(
        text("""
            SELECT id, repeat_count, current_repeat, status, student_id,
                   parent_id, academic_id
            FROM pickup_requests
            WHERE id = :id
            FOR UPDATE
        """),
        {"id": request_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if int(row[6]) != academic_id:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request academic year mismatch")

    # A response can be lost after commit. When the client retries the same
    # completed playback, return the committed result instead of counting it
    # twice. Older clients that omit the expectation keep legacy behavior.
    if expected_current_repeat is not None and int(row[2]) != expected_current_repeat:
        db.rollback()
        if row[3] == "cancelled":
            raise HTTPException(status_code=409, detail="Request was cancelled")
        return {
            "success": True,
            "completed": row[3] == "completed",
            "current_repeat": int(row[2]),
            "already_advanced": True,
        }
    if row[3] not in ("pending", "processing"):
        db.rollback()
        raise HTTPException(status_code=400, detail="Request is not active")

    new_repeat = row[2] + 1
    now = datetime.utcnow()

    if new_repeat >= row[1]:
        # Auto-complete
        db.execute(
            text("""
                UPDATE pickup_requests
                SET current_repeat = :nr, status = 'completed', completed_at = :now
                WHERE id = :id
            """),
            {"nr": new_repeat, "now": now, "id": request_id}
        )
        db.commit()
        # Notify parent
        if row[5]:
            await broadcast_to_user(row[5], {
                "type": "pickup_status_updated",
                "payload": {"request_id": request_id, "status": "completed", "student_id": row[4]}
            })
        # Broadcast updated queue to admin room
        await _broadcast_queue(db, academic_id)
        return {"success": True, "completed": True, "current_repeat": new_repeat}
    else:
        # Update repeat counter, mark as processing
        db.execute(
            text("""
                UPDATE pickup_requests
                SET current_repeat = :nr, status = 'processing',
                    processing_started_at = COALESCE(processing_started_at, :now)
                WHERE id = :id
            """),
            {"nr": new_repeat, "now": now, "id": request_id}
        )
        db.commit()
        
        # Notify parent that it is now processing (if first repeat)
        if new_repeat == 1 and row[5]:
            await broadcast_to_user(row[5], {
                "type": "pickup_status_updated",
                "payload": {"request_id": request_id, "status": "processing", "student_id": row[4]}
            })
            
        # Also broadcast the queue change
        await _broadcast_queue(db, academic_id)

        return {"success": True, "completed": False, "current_repeat": new_repeat}


@router.put("/queue/{request_id}/complete")
async def complete_request(
    request_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin: manually mark a request as completed."""
    _require_pickup_staff(current_user)
    academic_id = _body_academic_id(body)
    row = db.execute(
        text("""
            SELECT id, parent_id, student_id, academic_id, status
            FROM pickup_requests WHERE id = :id FOR UPDATE
        """),
        {"id": request_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if int(row[3]) != academic_id:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request academic year mismatch")
    if row[4] == "completed":
        db.rollback()
        return {"success": True, "already_completed": True}
    if row[4] == "cancelled":
        db.rollback()
        raise HTTPException(status_code=409, detail="Request was cancelled")

    now = datetime.utcnow()
    db.execute(
        text("""
            UPDATE pickup_requests
            SET status = 'completed', completed_at = :now
            WHERE id = :id
        """),
        {"now": now, "id": request_id}
    )
    db.commit()

    # Notify parent
    if row[1]:
        await broadcast_to_user(row[1], {
            "type": "pickup_status_updated",
            "payload": {"request_id": request_id, "status": "completed", "student_id": row[2]}
        })
    await _broadcast_queue(db, academic_id)

    return {"success": True}


@router.put("/queue/{request_id}/cancel")
async def cancel_request(
    request_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin or parent: cancel a pickup request."""
    academic_id = _body_academic_id(body)
    row = db.execute(
        text("""
            SELECT id, parent_id, student_id, academic_id, status
            FROM pickup_requests WHERE id = :id FOR UPDATE
        """),
        {"id": request_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if int(row[3]) != academic_id:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request academic year mismatch")
    if _is_parent_principal(current_user):
        if int(row[1]) != int(current_user.id):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own pickup request",
            )
    else:
        _require_pickup_staff(current_user)
    if row[4] == "cancelled":
        db.rollback()
        return {"success": True, "already_cancelled": True}
    if row[4] == "completed":
        db.rollback()
        raise HTTPException(status_code=409, detail="Request is already completed")

    now = datetime.utcnow()
    db.execute(
        text("""
            UPDATE pickup_requests
            SET status = 'cancelled', completed_at = :now
            WHERE id = :id
        """),
        {"now": now, "id": request_id}
    )
    db.commit()

    if row[1]:
        await broadcast_to_user(row[1], {
            "type": "pickup_status_updated",
            "payload": {"request_id": request_id, "status": "cancelled", "student_id": row[2]}
        })
    await _broadcast_queue(db, academic_id)

    return {"success": True}


# ─────────────────────────────────────────────
# SETTINGS ENDPOINTS (Admin)
# ─────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    academic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    _require_pickup_staff(current_user)
    return _get_settings(db, academic_id)


@router.put("/settings")
async def update_settings(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin: update pickup settings."""
    _require_pickup_staff(current_user)
    academic_id = _body_academic_id(body)
    try:
        repeat_count = int(body.get("repeat_count", 3))
        cooldown_seconds = int(body.get("cooldown_seconds", 300))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="repeat_count and cooldown_seconds must be integers",
        )
    if not 1 <= repeat_count <= 10:
        raise HTTPException(status_code=400, detail="repeat_count must be between 1 and 10")
    if not 60 <= cooldown_seconds <= 1800:
        raise HTTPException(
            status_code=400,
            detail="cooldown_seconds must be between 60 and 1800",
        )

    if "calling_enabled" in body:
        ce = 1 if _strict_bool(body.get("calling_enabled"), "calling_enabled") else 0
        db.execute(
            text("""
                INSERT INTO pickup_settings (academic_id, repeat_count, cooldown_seconds, calling_enabled, updated_at)
                VALUES (:aid, :rc, :cs, :ce, NOW())
                ON DUPLICATE KEY UPDATE repeat_count = :rc, cooldown_seconds = :cs,
                    calling_enabled = :ce, updated_at = NOW()
            """),
            {"aid": academic_id, "rc": repeat_count, "cs": cooldown_seconds, "ce": ce},
        )
    else:
        db.execute(
            text("""
                INSERT INTO pickup_settings (academic_id, repeat_count, cooldown_seconds, calling_enabled, updated_at)
                VALUES (:aid, :rc, :cs, 0, NOW())
                ON DUPLICATE KEY UPDATE repeat_count = :rc, cooldown_seconds = :cs, updated_at = NOW()
            """),
            {"aid": academic_id, "rc": repeat_count, "cs": cooldown_seconds},
        )
    db.commit()
    snap = _get_settings(db, int(academic_id))
    return {
        "success": True,
        "repeat_count": snap["repeat_count"],
        "cooldown_seconds": snap["cooldown_seconds"],
        "calling_enabled": snap["calling_enabled"],
    }


@router.put("/calling-active")
async def set_pickup_calling_active(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Admin: turn pickup hall announcements on/off for one campus (branch_id).
    Parents see hall_calling_active in my-children-status for their pickup branch only.
    """
    _require_pickup_staff(current_user)
    academic_id = body.get("academic_id")
    if academic_id is None:
        raise HTTPException(status_code=400, detail="academic_id required")
    branch_id = body.get("branch_id")
    if branch_id is None:
        raise HTTPException(status_code=400, detail="branch_id required")
    try:
        bid = int(branch_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="branch_id must be an integer")
    if bid <= 0:
        raise HTTPException(status_code=400, detail="branch_id must be positive")

    if "active" not in body:
        raise HTTPException(status_code=400, detail="active required (boolean)")
    flag = 1 if _strict_bool(body.get("active"), "active") else 0
    # Ensure pickup_settings row exists (repeat/cooldown defaults)
    _get_settings(db, int(academic_id))
    db.execute(
        text(
            """
            INSERT INTO pickup_branch_calling
                (academic_id, branch_id, calling_enabled, updated_at)
            VALUES
                (:aid, :bid, :ce, NOW())
            ON DUPLICATE KEY UPDATE
                calling_enabled = VALUES(calling_enabled),
                updated_at = NOW()
            """
        ),
        {"aid": int(academic_id), "bid": bid, "ce": flag},
    )
    _sync_legacy_global_calling_flag(db, int(academic_id))
    db.commit()
    await broadcast_to_room(
        f"pickup_parents_{int(academic_id)}",
        {"type": "pickup_queue_changed", "payload": {"academic_id": int(academic_id)}},
    )
    await broadcast_to_room(
        f"pickup_admin_{int(academic_id)}",
        {"type": "pickup_queue_updated", "payload": {"academic_id": int(academic_id)}},
    )
    snap = _pickup_calling_by_branch(db, int(academic_id))
    return {
        "success": True,
        "calling_enabled": bool(flag),
        "branch_id": bid,
        "calling_by_branch": {str(k): v for k, v in snap.items()},
    }


# ─────────────────────────────────────────────
# STUDENT CUSTOM AUDIO ENDPOINTS (Admin)
# ─────────────────────────────────────────────

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/m4a",
    "audio/vnd.wav", "audio/wav", "audio/x-wav", "audio/aac", "audio/ogg",
    "application/octet-stream",  # some mobile clients send this for recorded files
}
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".aac", ".ogg")
MAX_AUDIO_SIZE = 5 * 1024 * 1024  # 5 MB

import io
import logging

def _trim_silence_from_bytes(file_bytes: bytes, ext: str) -> bytes:
    """Trim leading and trailing silence from an audio byte stream."""
    try:
        fmt = ext.lower().replace(".", "")
        if fmt == "m4a": fmt = "mp4"
        
        from pydub import AudioSegment  # type: ignore
        from pydub.silence import detect_nonsilent  # type: ignore
        
        audio = AudioSegment.from_file(io.BytesIO(file_bytes), format=fmt)
        
        # Detect non-silent parts (silence roughly below average volume - 16dB)
        ranges = detect_nonsilent(audio, min_silence_len=200, silence_thresh=audio.dBFS - 16)
        
        if ranges:
            start = max(0, ranges[0][0] - 100)  # pad start 100ms
            end = min(len(audio), ranges[-1][1] + 100) # pad end 100ms
            
            # Use trimmed version if it's meaningfully shorter
            if end - start < len(audio):
                trimmed = audio[start:end]
                out_buf = io.BytesIO()
                trimmed.export(out_buf, format=fmt)
                return out_buf.getvalue()
    except Exception as e:
        logging.getLogger(__name__).warning("Audio silence trimming failed: %s", str(e))
        
    return file_bytes

@router.post("/students/{student_id}/audio")
async def upload_student_audio(
    student_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin: Upload a custom pickup audio announcement for a student."""
    _require_pickup_staff(current_user)
    fname = (file.filename or "").strip()
    raw_ct = file.content_type or ""
    ct = raw_ct.split(";")[0].strip().lower() if raw_ct else ""
    ext_lower = os.path.splitext(fname)[1].lower()
    ok_type = ct in ALLOWED_AUDIO_TYPES
    ok_ext = fname.lower().endswith(AUDIO_EXTENSIONS)
    # octet-stream only allowed when filename has a known audio extension
    if ct == "application/octet-stream" and not ok_ext:
        ok_type = False
    if not ok_type and not ok_ext:
        logger.warning(f"Audio upload rejected: content_type={raw_ct!r} filename={fname!r}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only MP3, M4A, WAV, AAC, OGG are allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 5 MB.",
        )

    ext = os.path.splitext(fname)[1]
    if not ext:
        ext = ".m4a"

    # Trim silence before saving
    contents = _trim_silence_from_bytes(contents, ext)

    unique_filename = f"pickup_audio_{student_id}_{uuid.uuid4().hex[:8]}{ext}"

    reported_ct = (file.content_type or "").split(";")[0].strip()
    if not reported_ct or reported_ct.lower() == "application/octet-stream":
        upload_ct = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
        }.get((ext or ".m4a").lower(), "audio/m4a")
    else:
        upload_ct = reported_ct

    audio_url = StorageService.upload_file(
        file_data=contents,
        folder="audio",
        filename=unique_filename,
        content_type=upload_ct,
    )

    if not audio_url:
        raise HTTPException(status_code=500, detail="Failed to upload audio")

    # Get old audio to delete
    student_row = db.execute(
        text("SELECT pickup_audio_url FROM students WHERE id = :sid"),
        {"sid": student_id}
    ).fetchone()

    if not student_row:
        raise HTTPException(status_code=404, detail="Student not found")

    old_audio = student_row[0]

    db.execute(
        text("UPDATE students SET pickup_audio_url = :url WHERE id = :sid"),
        {"url": audio_url, "sid": student_id}
    )
    db.commit()

    if old_audio:
        from ...models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        try:
            if not StorageService.delete_file(old_audio, settings):
                logger.warning(
                    "Pickup audio storage delete returned False for %s",
                    old_audio,
                )
        except Exception as e:
            logger.warning(f"Failed to delete old pickup audio {old_audio}: {e}")

    return {"success": True, "pickup_audio_url": audio_url}


@router.delete("/students/{student_id}/audio")
async def delete_student_audio(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Admin: Remove custom pickup audio announcement for a student."""
    _require_pickup_staff(current_user)
    student_row = db.execute(
        text("SELECT pickup_audio_url FROM students WHERE id = :sid"),
        {"sid": student_id}
    ).fetchone()

    if not student_row:
        raise HTTPException(status_code=404, detail="Student not found")

    old_audio = student_row[0]
    if old_audio:
        db.execute(
            text("UPDATE students SET pickup_audio_url = NULL WHERE id = :sid"),
            {"sid": student_id}
        )
        db.commit()

        from ...models.settings import SystemSettings
        settings = db.query(SystemSettings).first()
        try:
            if not StorageService.delete_file(old_audio, settings):
                logger.warning(
                    "Pickup audio storage delete returned False for %s",
                    old_audio,
                )
        except Exception as e:
            logger.warning(f"Failed to delete old pickup audio {old_audio}: {e}")

    return {"success": True}


# ─────────────────────────────────────────────
# BRANCH / STUDENT PICKUP RULES (Admin)
# ─────────────────────────────────────────────


@router.put("/branches/{branch_id}/pickup-radius")
async def set_branch_pickup_radius(
    branch_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Set optional pickup geofence radius (meters) for a branch.
    Uses branch.map_latitude / map_longitude as the center. Pass null to disable.
    """
    _require_pickup_staff(current_user)
    if "pickup_radius_meters" not in body:
        raise HTTPException(
            status_code=400,
            detail="pickup_radius_meters required (number or null to clear)",
        )
    meters = body.get("pickup_radius_meters")
    if meters is not None:
        try:
            meters = float(meters)
            if meters < 0:
                raise ValueError("negative")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="pickup_radius_meters invalid")

    row = db.execute(
        text("SELECT id FROM branch WHERE id = :bid"),
        {"bid": branch_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Branch not found")

    db.execute(
        text("UPDATE branch SET pickup_radius_meters = :m WHERE id = :bid"),
        {"m": meters, "bid": branch_id},
    )
    db.commit()
    return {"success": True, "branch_id": branch_id, "pickup_radius_meters": meters}


@router.get("/students/{student_id}/pickup-extra-branches")
async def get_student_pickup_extra_branches(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return home branch and extra pickup branch IDs for a student."""
    _require_pickup_staff(current_user)
    r = db.execute(
        text(
            "SELECT branch, pickup_extra_branch_ids FROM students WHERE id = :sid"
        ),
        {"sid": student_id},
    ).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Student not found")
    home_raw, extra_raw = r[0], r[1]
    try:
        home_id = int(home_raw) if home_raw is not None and str(home_raw).strip() != "" else None
    except (TypeError, ValueError):
        home_id = None
    extra_ids = _parse_extra_branch_ids(extra_raw)
    return {
        "student_id": student_id,
        "home_branch_id": home_id,
        "extra_branch_ids": extra_ids,
    }


@router.put("/students/{student_id}/pickup-extra-branches")
async def set_student_pickup_extra_branches(
    student_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Extra branch IDs where this student may be picked up (JSON array), in addition to students.branch.
    Example body: { \"extra_branch_ids\": [2, 3] }
    """
    _require_pickup_staff(current_user)
    raw = body.get("extra_branch_ids")
    if raw is None:
        raise HTTPException(status_code=400, detail="extra_branch_ids required")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="extra_branch_ids must be a list")
    ids: List[int] = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="extra_branch_ids must be integers")
    payload = json.dumps(ids) if ids else None

    r = db.execute(
        text("SELECT id FROM students WHERE id = :sid"),
        {"sid": student_id},
    ).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Student not found")

    db.execute(
        text("UPDATE students SET pickup_extra_branch_ids = :j WHERE id = :sid"),
        {"j": payload, "sid": student_id},
    )
    db.commit()
    return {"success": True, "student_id": student_id, "extra_branch_ids": ids}


# ─────────────────────────────────────────────
# INTERNAL HELPER
# ─────────────────────────────────────────────

async def _broadcast_queue(db: Session, academic_id: int):
    """Signal a queue change; clients fetch their own branch-scoped snapshot."""
    await broadcast_to_room(f"pickup_admin_{academic_id}", {
        "type": "pickup_queue_updated",
        "payload": {"academic_id": academic_id}
    })
    await broadcast_to_room(f"pickup_parents_{academic_id}", {
        "type": "pickup_queue_changed",
        "payload": {"academic_id": academic_id},
    })
