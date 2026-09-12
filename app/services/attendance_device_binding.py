"""Server-enforced primary phone binding for employee attendance.

The client supplies an opaque app-scoped phone identifier. The raw value is
never persisted or returned; only its SHA-256 digest is stored.
All mutation helpers expect the caller to hold the employee ``users`` row lock
so first-use registration and attendance recording commit atomically.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.attendance_primary_device import (
    AttendancePrimaryDevice,
    AttendancePrimaryDeviceEvent,
)


ATTENDANCE_DEVICE_CHANGE_DAYS = 30
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_VALID_PLATFORMS = {"android", "ios"}


class AttendanceDeviceIdentityError(ValueError):
    pass


@dataclass(frozen=True)
class AttendanceDeviceIdentity:
    raw_id: str
    name: str
    platform: str

    @property
    def id_hash(self) -> str:
        return hash_attendance_device_id(self.raw_id)


class AttendancePrimaryDeviceMismatch(Exception):
    def __init__(self, binding: AttendancePrimaryDevice):
        super().__init__("Use your primary phone to take attendance.")
        self.binding = binding


class AttendanceDeviceChangeLocked(Exception):
    def __init__(self, binding: AttendancePrimaryDevice, now: datetime):
        super().__init__("The primary attendance phone cannot be changed yet.")
        self.binding = binding
        self.remaining_seconds = max(
            0,
            int((binding.change_available_at - now).total_seconds()),
        )


def utc_now_naive() -> datetime:
    """UTC clock represented as naive DATETIME for MySQL/SQLite portability."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def as_utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Return a JSON-safe UTC timestamp for HTTP exception details."""

    utc_value = as_utc(value)
    return utc_value.isoformat() if utc_value is not None else None


def normalize_attendance_device_identity(
    raw_id: object,
    name: object,
    platform: object,
) -> AttendanceDeviceIdentity:
    device_id = str(raw_id or "").strip()
    if not _DEVICE_ID_RE.fullmatch(device_id):
        raise AttendanceDeviceIdentityError(
            "The official app could not provide a valid attendance device identity."
        )

    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform not in _VALID_PLATFORMS:
        raise AttendanceDeviceIdentityError(
            "Attendance is supported only from the official Android or iOS app."
        )

    normalized_name = " ".join(str(name or "").strip().split())[:255]
    if not normalized_name:
        normalized_name = (
            "Android phone" if normalized_platform == "android" else "iPhone"
        )

    return AttendanceDeviceIdentity(
        raw_id=device_id,
        name=normalized_name,
        platform=normalized_platform,
    )


def hash_attendance_device_id(raw_id: str) -> str:
    # Persist a fixed-size one-way fingerprint instead of the raw client value.
    # It remains stable independently of JWT-key rotation.
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


def get_primary_attendance_device(
    db: Session,
    user_id: int,
) -> Optional[AttendancePrimaryDevice]:
    return (
        db.query(AttendancePrimaryDevice)
        .filter(AttendancePrimaryDevice.user_id == int(user_id))
        .first()
    )


def _add_event(
    db: Session,
    *,
    user_id: int,
    action: str,
    actor_user_id: Optional[int] = None,
    previous_device_name: Optional[str] = None,
    new_device_name: Optional[str] = None,
    reason: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    db.add(
        AttendancePrimaryDeviceEvent(
            user_id=int(user_id),
            action=action,
            actor_user_id=actor_user_id,
            previous_device_name=previous_device_name,
            new_device_name=new_device_name,
            reason=reason,
            detail_json=(
                json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
                if detail
                else None
            ),
        )
    )


def binding_status(
    binding: Optional[AttendancePrimaryDevice],
    identity: AttendanceDeviceIdentity,
    *,
    now: Optional[datetime] = None,
) -> dict:
    current = now or utc_now_naive()
    if binding is None:
        return {
            "has_primary_device": False,
            "is_current_device_primary": False,
            "can_change": False,
            "remaining_seconds": 0,
            "primary_device_name": None,
            "platform": None,
            "registered_at": None,
            "change_available_at": None,
            "current_device_name": identity.name,
        }

    remaining_seconds = max(
        0,
        int((binding.change_available_at - current).total_seconds()),
    )
    return {
        "has_primary_device": True,
        "is_current_device_primary": binding.device_id_hash == identity.id_hash,
        "can_change": remaining_seconds == 0,
        "remaining_seconds": remaining_seconds,
        "primary_device_name": binding.device_name,
        "platform": binding.platform,
        "registered_at": as_utc(binding.registered_at),
        "change_available_at": as_utc(binding.change_available_at),
        "current_device_name": identity.name,
    }


def ensure_existing_primary_matches(
    db: Session,
    *,
    user_id: int,
    identity: AttendanceDeviceIdentity,
    previous_identity: Optional[AttendanceDeviceIdentity] = None,
) -> Optional[AttendancePrimaryDevice]:
    """Reject another phone or stage a proof-based installation-ID migration.

    The optional previous identity is a secret already held by the calling app.
    Migration is allowed only when its digest exactly matches the saved primary
    binding. A device model/name match is deliberately never sufficient.
    """

    binding = get_primary_attendance_device(db, user_id)
    if binding is None:
        return None
    if binding.device_id_hash == identity.id_hash:
        return binding
    if (
        previous_identity is not None
        and previous_identity.id_hash == binding.device_id_hash
        and previous_identity.platform == identity.platform
    ):
        previous_name = binding.device_name
        binding.device_id_hash = identity.id_hash
        binding.device_name = identity.name
        binding.platform = identity.platform
        _add_event(
            db,
            user_id=int(user_id),
            action="installation_id_migrated",
            actor_user_id=int(user_id),
            previous_device_name=previous_name,
            new_device_name=identity.name,
            detail={
                "platform": identity.platform,
                "reason": "verified_previous_installation_id",
            },
        )
        return binding
    raise AttendancePrimaryDeviceMismatch(binding)


def refresh_matching_primary_device_metadata(
    binding: Optional[AttendancePrimaryDevice],
    identity: AttendanceDeviceIdentity,
) -> bool:
    """Refresh display metadata without changing which installation is primary."""

    if binding is None or binding.device_id_hash != identity.id_hash:
        return False
    changed = (
        binding.device_name != identity.name
        or binding.platform != identity.platform
    )
    if changed:
        binding.device_name = identity.name
        binding.platform = identity.platform
    return changed


def ensure_or_register_primary_for_attendance(
    db: Session,
    *,
    user_id: int,
    identity: AttendanceDeviceIdentity,
    previous_identity: Optional[AttendanceDeviceIdentity] = None,
    now: Optional[datetime] = None,
) -> AttendancePrimaryDevice:
    """Re-check under the employee row lock and stage first-use registration."""

    current = now or utc_now_naive()
    binding = get_primary_attendance_device(db, user_id)
    if binding is not None:
        binding = ensure_existing_primary_matches(
            db,
            user_id=user_id,
            identity=identity,
            previous_identity=previous_identity,
        )
        assert binding is not None
        # Keep the saved name useful if the OS/library later resolves a more
        # specific commercial model for the same installation.
        refresh_matching_primary_device_metadata(binding, identity)
        return binding

    binding = AttendancePrimaryDevice(
        user_id=int(user_id),
        device_id_hash=identity.id_hash,
        device_name=identity.name,
        platform=identity.platform,
        registered_at=current,
        last_changed_at=current,
        change_available_at=current
        + timedelta(days=ATTENDANCE_DEVICE_CHANGE_DAYS),
    )
    db.add(binding)
    _add_event(
        db,
        user_id=int(user_id),
        action="auto_registered",
        actor_user_id=int(user_id),
        new_device_name=identity.name,
        detail={"platform": identity.platform},
    )
    return binding


def change_primary_attendance_device(
    db: Session,
    *,
    user_id: int,
    identity: AttendanceDeviceIdentity,
    now: Optional[datetime] = None,
) -> dict:
    """Change to the calling phone after the 30-day server cooldown."""

    current = now or utc_now_naive()
    binding = get_primary_attendance_device(db, user_id)
    if binding is None:
        # Reset deliberately leaves the account unbound.  Registration occurs
        # only with the next successful attendance mutation.
        return binding_status(None, identity, now=current)

    if binding.device_id_hash == identity.id_hash:
        return binding_status(binding, identity, now=current)

    if binding.change_available_at > current:
        raise AttendanceDeviceChangeLocked(binding, current)

    previous_name = binding.device_name
    binding.device_id_hash = identity.id_hash
    binding.device_name = identity.name
    binding.platform = identity.platform
    binding.registered_at = current
    binding.last_changed_at = current
    binding.change_available_at = current + timedelta(
        days=ATTENDANCE_DEVICE_CHANGE_DAYS
    )
    _add_event(
        db,
        user_id=int(user_id),
        action="employee_changed",
        actor_user_id=int(user_id),
        previous_device_name=previous_name,
        new_device_name=identity.name,
        detail={"platform": identity.platform},
    )
    return binding_status(binding, identity, now=current)


def reset_primary_attendance_device(
    db: Session,
    *,
    user_id: int,
    actor_user_id: int,
    reason: str,
) -> bool:
    binding = get_primary_attendance_device(db, user_id)
    previous_name = binding.device_name if binding is not None else None
    if binding is not None:
        db.delete(binding)
    _add_event(
        db,
        user_id=int(user_id),
        action="admin_reset",
        actor_user_id=int(actor_user_id),
        previous_device_name=previous_name,
        reason=reason,
    )
    return binding is not None


def mismatch_detail(binding: AttendancePrimaryDevice) -> dict:
    current = utc_now_naive()
    primary_device_name = str(binding.device_name or "Primary phone").strip()
    return {
        "code": "attendance_primary_device_mismatch",
        "message": (
            "This device is not allowed for attendance. "
            "Please use your primary attendance phone: "
            f"{primary_device_name}."
        ),
        "primary_device_name": primary_device_name,
        "registered_at": as_utc_iso(binding.registered_at),
        "change_available_at": as_utc_iso(binding.change_available_at),
        "remaining_seconds": max(
            0,
            int((binding.change_available_at - current).total_seconds()),
        ),
    }


def change_locked_detail(error: AttendanceDeviceChangeLocked) -> dict:
    return {
        "code": "attendance_device_change_locked",
        "message": "You can change your primary attendance phone after the 30-day waiting period.",
        "primary_device_name": error.binding.device_name,
        "change_available_at": as_utc_iso(error.binding.change_available_at),
        "remaining_seconds": error.remaining_seconds,
    }
