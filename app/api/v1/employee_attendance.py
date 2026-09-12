"""
Employee Attendance API endpoints for employee check-in/out and attendance management.
Includes GPS validation, mock location detection, and comprehensive attendance tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from starlette import status
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_, func, bindparam
from typing import List, Optional, Tuple, Dict, Callable, Any
from datetime import date, datetime, time, timedelta, timezone
from collections import defaultdict
import asyncio
import math
import logging
import json
import ipaddress
from enum import Enum
from pydantic import BaseModel

from ...core import get_db
from ...core.config import settings as app_settings
from ...auth import get_current_active_employee
from ...models import (
    User,
    Branch,
    Department,
    AttendanceAudiencePreset,
    AttendanceAuditLog,
    AttendancePrimaryDevice,
    AttendancePrimaryDeviceEvent,
    AppAdmin,
    WorkLocation,
)
from ...schemas.employee_attendance import (
    WorkLocationResponse,
    WorkLocationUpsertRequest,
    AttendanceRecordResponse,
    CheckInOutRequest,
    CheckInOutResponse,
    AttendanceReportResponse,
    SalaryHistoryResponse,
    SalaryDeductionResponse,
    SalaryBonusResponse,
    SystemSettingsResponse,
    UpdateSystemSettingsRequest,
    UserScheduleListResponse,
    UserScheduleInfo,
    UpdateUserAllowedBranchesRequest,
    AdminUserReportSummary,
    AdminGlobalReportResponse,
    DailySessionDetails,
    DailyAttendanceBreakdown,
    AdminUserDetailedReportResponse,
    MonthlyTrend,
    AdminTrendReportResponse,
    CheckInSecurityEventItem,
    CheckInSecurityEventListResponse,
    ClientSecurityEventReportRequest,
    AttendanceProblemReportRequest,
    ManualAttendanceSession,
    ManualAttendanceBulkRequest,
    ScheduleExceptionCreate,
    ScheduleExceptionUpdate,
    ScheduleExceptionItem,
    ScheduleExceptionListResponse,
    AttendanceDeviceIdentityRequest,
    AttendanceDeviceAdminResetRequest,
)
from ...models.attendance_model import (
    AttendanceSystemSettings,
    AttendanceSchedule,
    AttendanceUserAssignment,
    AttendanceScheduleException,
    AttendanceScheduleExceptionEnrollment,
)
from ...models.telegram_attendance_settings import (
    TelegramAttendanceSettings,
    TelegramBranchNotificationRoute,
)
from ...models.check_in_security_event import CheckInSecurityEvent
from ...services.check_in_security import (
    enforce_attendance_support_report_rate_limit,
    enforce_checkin_rate_limit,
    observe_successful_check_in,
    record_checkin_security_event,
)
from ...services.telegram_notification_service import TelegramNotificationService
from ...services.telegram_branch_routing import (
    normalize_branch_routing_mode,
    resolve_attendance_notification_chat_id,
)
from ...services.telegram_leave_routing import (
    normalize_leave_routing_mode,
)
from ...services.attendance_schedule_exception_service import (
    ensure_schedule_exceptions_table,
    available_self_enrollment_exceptions,
    enroll_in_schedule_exception_for_attendance,
    get_schedule_exception_enrollment,
    get_effective_day_attendance,
    get_effective_day_attendance_with_exception,
    sessions_for_user_date,
    match_exception_from_rows,
    get_weekly_day_attendance,
    representative_user_for_exception_scope,
    resolve_enrolled_schedule_exception,
    resolve_schedule_exception,
    schedule_exception_occurs_on,
    schedule_exception_occurs_in_range,
    schedule_exception_recurrence_type,
    PRESET_SESSIONS,
    VALID_RECURRENCE_TYPES,
    _parse_exception_sessions,
)
from ...schemas.telegram_attendance import (
    TelegramAttendanceSettingsResponse,
    TelegramAttendanceSettingsUpdate,
    TelegramTestMessageRequest,
)
from ...services.leave_integration_service import (
    get_approved_leave_map,
    leave_covers_session,
    leave_map_to_json,
    uncovered_sessions,
)
from ...services.attendance_processing_access_service import (
    _rule_values,
    attendance_processing_rules_revision,
    ensure_attendance_processing_rules_table,
    filter_enabled_users,
    get_attendance_processing_access,
    set_attendance_processing_rule,
)
from ...services.attendance_session_windows import (
    is_late_check_out,
    is_session_check_in_open,
    open_check_out_is_available,
    resolve_automatic_attendance_target,
    resolve_explicit_attendance_target,
)
from ...services.attendance_session_transition import (
    calculate_session_transition_wait,
)
from ...services.attendance_gps_compatibility import (
    requires_enhanced_gps_evidence,
)
from ...services.attendance_gps_freshness import (
    gps_age_seconds,
    incorrect_device_time_error_detail,
    is_current_gps_age,
    is_device_time_incorrect,
    stale_gps_error_detail,
)
from ...services.attendance_device_compatibility import (
    requires_attendance_device_identity,
)
from ...services.attendance_mutation_replay import (
    is_recent_auto_checkin_replay,
)
from ...services.attendance_request_policy import (
    is_attendance_branch_authorized,
    validate_attendance_request_context,
)
from ...services.attendance_device_binding import (
    AttendanceDeviceChangeLocked,
    AttendanceDeviceIdentity,
    AttendanceDeviceIdentityError,
    AttendancePrimaryDeviceMismatch,
    as_utc,
    binding_status,
    change_locked_detail,
    change_primary_attendance_device,
    ensure_existing_primary_matches,
    ensure_or_register_primary_for_attendance,
    get_primary_attendance_device,
    mismatch_detail,
    normalize_attendance_device_identity,
    refresh_matching_primary_device_metadata,
    reset_primary_attendance_device,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Cambodia timezone (UTC+7) – used for all attendance time calculations
CAMBODIA_TZ = timezone(timedelta(hours=7))

# In-memory cache for ranking (Facebook/Redis-style, TTL 5 min)
_RANKING_CACHE = {}
_RANKING_CACHE_TTL = 300  # seconds
_RANKING_CACHE_SCHEMA_VERSION = 6  # v6: approved leave excluded from due points

DEFAULT_ATTENDANCE_SCHEDULE_NAME = "Default Attendance Configuration"

# Early clock-in is always a finite window (admin 0–240 minutes). Legacy NULL
# in DB is treated as the maximum (4 hours), not unlimited.
EARLY_CLOCK_IN_MAX_MINUTES = 240


class AttendanceProcessingRuleUpdate(BaseModel):
    enabled: bool


class AttendanceAudiencePresetCreate(BaseModel):
    name: str
    preset_type: str
    branch_id: Optional[int] = None
    department_id: Optional[int] = None
    is_foreigner: Optional[int] = None
    employee_ids: Optional[List[int]] = None


def _ensure_attendance_audience_presets_table(db: Session) -> None:
    AttendanceAudiencePreset.__table__.create(bind=db.get_bind(), checkfirst=True)


def _attendance_audience_employee_ids(
    preset: AttendanceAudiencePreset,
) -> List[int]:
    raw = preset.employee_ids_json
    if not raw:
        return []
    try:
        values = json.loads(str(raw))
    except Exception:
        return []
    if not isinstance(values, list):
        return []
    return sorted(
        {
            int(value)
            for value in values
            if str(value).strip().lstrip("-").isdigit() and int(value) > 0
        }
    )


def _require_attendance_processing(db: Session, user: User) -> None:
    access = get_attendance_processing_access(db, user)
    if not access.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "attendance_processing_disabled",
                **access.as_dict(),
            },
        )


def _is_attendance_admin(db: Session, user: User) -> bool:
    """Return whether the current database user may administer attendance.

    Role 2 is a regular teacher in this application, so it must never be used
    as an attendance-admin shortcut.  Explicit, unlocked App Admins retain
    delegated access even when their ordinary user role is not role 1.
    """
    if int(getattr(user, "role_id", 0) or 0) == 1:
        return True
    return (
        db.query(AppAdmin.id)
        .filter(
            AppAdmin.user_id == int(user.id),
            AppAdmin.is_locked == False,  # noqa: E712
        )
        .first()
        is not None
    )


def _require_attendance_admin(db: Session, user: User) -> None:
    if not _is_attendance_admin(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attendance administrator access required",
        )


def _can_delete_check_in_security_events(db: Session, user: User) -> bool:
    """Security audit deletion is reserved for active App Super Admins."""

    return (
        db.query(AppAdmin.id)
        .filter(
            AppAdmin.user_id == int(user.id),
            AppAdmin.is_super_admin.in_([True, 1]),
            AppAdmin.is_locked.in_([False, 0]),
        )
        .first()
        is not None
    )


def _require_check_in_security_event_delete_permission(
    db: Session,
    user: User,
) -> None:
    if not _can_delete_check_in_security_events(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an active App Super Admin can delete check-in security logs",
        )


def _can_reset_attendance_devices(db: Session, user: User) -> bool:
    admin = db.query(AppAdmin).filter(
        AppAdmin.user_id == int(user.id),
        AppAdmin.is_locked == False,  # noqa: E712
    ).first()
    return bool(
        admin
        and (
            bool(admin.is_super_admin)
            or bool(getattr(admin, "can_reset_attendance_devices", False))
        )
    )


def _require_attendance_device_reset_permission(db: Session, user: User) -> None:
    if not _can_reset_attendance_devices(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attendance primary-phone reset permission required",
        )


def _lock_employee_row(db: Session, user_id: int) -> None:
    if db.get_bind().dialect.name in {"mysql", "mariadb", "postgresql"}:
        db.execute(
            text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"),
            {"user_id": int(user_id)},
        ).fetchone()


def _attendance_device_identity_or_upgrade(
    *,
    device_id: object,
    device_name: object,
    platform: object,
) -> AttendanceDeviceIdentity:
    try:
        return normalize_attendance_device_identity(
            device_id,
            device_name,
            platform,
        )
    except AttendanceDeviceIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            detail={
                "code": "attendance_device_identity_required",
                "message": (
                    "Please update and reopen the official PAMAIS app before "
                    "taking attendance."
                ),
            },
        ) from exc


def _attendance_device_identity_for_check_in(
    request: CheckInOutRequest,
    http_request: Request,
) -> Optional[AttendanceDeviceIdentity]:
    """Resolve identity while keeping recognized pre-1.2.8 apps operational."""

    supplied_values = (
        request.attendance_device_id,
        request.attendance_device_name,
        request.attendance_device_platform,
    )
    if any(str(value or "").strip() for value in supplied_values):
        # Partial or malformed identity from a modern client must fail closed.
        return _attendance_device_identity_or_upgrade(
            device_id=request.attendance_device_id,
            device_name=request.attendance_device_name,
            platform=request.attendance_device_platform,
        )

    if requires_attendance_device_identity(
        http_request.headers.get("X-App-Version"),
        http_request.headers.get("User-Agent"),
        allow_legacy_compatibility=(
            app_settings.allow_legacy_attendance_device_compat
        ),
    ):
        return _attendance_device_identity_or_upgrade(
            device_id=None,
            device_name=None,
            platform=None,
        )

    return None


def _attendance_previous_device_identity_or_upgrade(
    *,
    previous_device_id: object,
    device_name: object,
    platform: object,
) -> Optional[AttendanceDeviceIdentity]:
    if not str(previous_device_id or "").strip():
        return None
    return _attendance_device_identity_or_upgrade(
        device_id=previous_device_id,
        device_name=device_name,
        platform=platform,
    )


def _normalize_early_clock_in_mins(value: object) -> int:
    if value is None:
        return EARLY_CLOCK_IN_MAX_MINUTES
    try:
        v = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return EARLY_CLOCK_IN_MAX_MINUTES
    return max(0, min(v, EARLY_CLOCK_IN_MAX_MINUTES))


def _coerce_per_session_early_clock_in_list(raw: object) -> Optional[List[int]]:
    """Optional JSON list: per-session early clock-in minutes (each 0..240)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, (list, tuple)):
        return None
    out: List[int] = []
    for item in raw[:12]:
        out.append(_normalize_early_clock_in_mins(item))
    return out or None


def _early_clock_in_mins_for_session_index(
    session_index: int,
    *,
    global_mins: int,
    per_session_mins: Optional[List[int]],
) -> int:
    if per_session_mins is not None and 0 <= session_index < len(per_session_mins):
        return int(per_session_mins[session_index])
    return int(global_mins)


def _session_checkin_window_open_minutes(
    session_index: int,
    start_m: int,
    *,
    expected_sessions: List[Dict[str, Any]],
    time_to_minutes: Callable[[str], Optional[int]],
    global_early_mins: int,
    per_session_mins: Optional[List[int]],
) -> int:
    """
    Earliest minute-of-day when check-in may count toward this session.

    Prevents abusing a long early buffer on session 2 to check in during the
    gap after session 1 (e.g. lunch): window cannot open before the previous
    session's scheduled end.
    """
    early_i = _early_clock_in_mins_for_session_index(
        session_index,
        global_mins=global_early_mins,
        per_session_mins=per_session_mins,
    )
    open_m = start_m - early_i
    if session_index <= 0:
        return open_m
    prev_end = time_to_minutes(expected_sessions[session_index - 1].get("end", ""))
    if prev_end is None:
        return open_m
    return max(open_m, prev_end)


def _snapshot_time_value(value: object) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            parsed = datetime.strptime(raw.upper(), fmt)
            return f"{parsed.hour:02d}:{parsed.minute:02d}"
        except Exception:
            pass
    parts = raw.split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1][:2]):02d}"
        except Exception:
            return raw[:8]
    return raw[:8]


def _hhmm_to_minutes(value: object) -> Optional[int]:
    """Convert a normalized schedule time to minutes after midnight."""
    normalized = _snapshot_time_value(value)
    if not normalized:
        return None
    try:
        hours, minutes = normalized.split(":", 1)
        return int(hours) * 60 + int(minutes[:2])
    except (TypeError, ValueError):
        return None


def _coerce_schedule_effective_date(raw: object, *, minimum: Optional[date] = None) -> date:
    parsed: date
    if raw is None or raw == "":
        parsed = datetime.now(CAMBODIA_TZ).date()
    elif isinstance(raw, datetime):
        parsed = raw.date()
    elif isinstance(raw, date):
        parsed = raw
    else:
        parsed = date.fromisoformat(str(raw).strip()[:10])
    if minimum is not None and parsed < minimum:
        return minimum
    return parsed


def _minimum_schedule_version_date() -> date:
    """Get today's date in Cambodia timezone."""
    return datetime.now(CAMBODIA_TZ).date()


def _get_cambodia_current_date() -> date:
    """Get current date in Cambodia timezone for database operations."""
    return datetime.now(CAMBODIA_TZ).date()


def _user_employment_start_date(user: object) -> Optional[date]:
    """Parse the legacy VARCHAR users.startWork field into a report boundary."""
    raw = getattr(user, "startWork", None)
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    value = str(raw or "").strip().split(" ")[0].split("T")[0]
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _version_schedule_assignments(
    db: Session,
    *,
    old_schedule_id: int,
    new_schedule_id: int,
    effective_date: date,
    assigned_by: Optional[int],
) -> Tuple[int, int]:
    """
    Move explicit user assignments from an old schedule row to a new schedule
    version from effective_date onward. Old assignment history ends the day
    before the new version starts so reports for earlier dates keep resolving
    the old schedule.
    """
    previous_end_date = effective_date - timedelta(days=1)
    active_assignments = (
        db.query(AttendanceUserAssignment)
        .filter(
            AttendanceUserAssignment.schedule_id == old_schedule_id,
            AttendanceUserAssignment.end_date.is_(None),
        )
        .all()
    )

    closed = 0
    created_or_updated = 0
    for assignment in active_assignments:
        assignment.end_date = previous_end_date
        assignment.updated_at = func.now()
        closed += 1

        existing_new_pair = (
            db.query(AttendanceUserAssignment)
            .filter(
                AttendanceUserAssignment.user_id == assignment.user_id,
                AttendanceUserAssignment.schedule_id == new_schedule_id,
            )
            .first()
        )
        if existing_new_pair:
            existing_new_pair.start_date = effective_date
            existing_new_pair.end_date = None
            existing_new_pair.assigned_by = assigned_by
            existing_new_pair.updated_at = func.now()
        else:
            db.add(
                AttendanceUserAssignment(
                    user_id=assignment.user_id,
                    schedule_id=new_schedule_id,
                    assigned_by=assigned_by,
                    start_date=effective_date,
                    end_date=None,
                    created_at=func.now(),
                )
            )
        created_or_updated += 1

    return closed, created_or_updated


def _settings_updated_at_as_date(ua: object) -> Optional[date]:
    """ORM may return datetime or date (e.g. if a date was stored); never call .date() on date."""
    if ua is None:
        return None
    if isinstance(ua, datetime):
        return ua.date()
    if isinstance(ua, date):
        return ua
    return None


def _coerce_minutes_list(val) -> list:
    if not val:
        return []
    if isinstance(val, str):
        try:
            import json
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [int(x) for x in parsed if str(x).isdigit()]
        except Exception:
            return [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
    if isinstance(val, list):
        return [int(x) for x in val if str(x).isdigit()]
    return []


def _system_settings_to_response(settings: AttendanceSystemSettings) -> SystemSettingsResponse:
    """ORM row → API response (early clock-in always 0..240 minutes, never null)."""
    ua = getattr(settings, "updated_at", None)
    updated_date = _settings_updated_at_as_date(ua)
    return SystemSettingsResponse(
        id=settings.id,
        require_location=bool(settings.require_location),
        block_mock_location=bool(settings.block_mock_location),
        block_developer_options=bool(settings.block_developer_options),
        allowed_ip_ranges=settings.allowed_ip_ranges,
        allow_early_clock_in_mins=_normalize_early_clock_in_mins(
            settings.allow_early_clock_in_mins
        ),
        per_session_early_clock_in_mins=_coerce_per_session_early_clock_in_list(
            getattr(settings, "per_session_early_clock_in_mins", None)
        ),
        allow_late_clock_out_mins=settings.allow_late_clock_out_mins,
        min_minutes_before_checkout=int(
            30
            if getattr(settings, "min_minutes_before_checkout", None) is None
            else getattr(settings, "min_minutes_before_checkout")
        ),
        session_transition_wait_mins=max(
            0,
            min(
                60,
                int(
                    10
                    if getattr(settings, "session_transition_wait_mins", None) is None
                    else getattr(settings, "session_transition_wait_mins")
                ),
            ),
        ),
        allow_early_leave_mins=int(
            0
            if getattr(settings, "allow_early_leave_mins", None) is None
            else getattr(settings, "allow_early_leave_mins")
        ),
        allow_makeup_missing_sessions=bool(
            getattr(settings, "allow_makeup_missing_sessions", False)
        ),
        late_grace_minutes=int(
            15
            if getattr(settings, "late_grace_minutes", None) is None
            else getattr(settings, "late_grace_minutes")
        ),
        notify_enable_before=bool(
            True
            if getattr(settings, "notify_enable_before", None) is None
            else getattr(settings, "notify_enable_before")
        ),
        notify_minutes_before=_coerce_minutes_list(
            getattr(settings, "notify_minutes_before", None) or [10, 5]
        ),
        notify_enable_after=bool(
            True
            if getattr(settings, "notify_enable_after", None) is None
            else getattr(settings, "notify_enable_after")
        ),
        notify_minutes_after=_coerce_minutes_list(
            getattr(settings, "notify_minutes_after", None) or [10, 30]
        ),
        notify_enable_before_checkout=bool(
            True
            if getattr(settings, "notify_enable_before_checkout", None) is None
            else getattr(settings, "notify_enable_before_checkout")
        ),
        notify_minutes_before_checkout=_coerce_minutes_list(
            getattr(settings, "notify_minutes_before_checkout", None) or [0]
        ),
        notify_enable_after_checkout=bool(
            True
            if getattr(settings, "notify_enable_after_checkout", None) is None
            else getattr(settings, "notify_enable_after_checkout")
        ),
        notify_minutes_after_checkout=_coerce_minutes_list(
            getattr(settings, "notify_minutes_after_checkout", None) or [5]
        ),
        updated_at=updated_date,
    )


def _build_default_weekly_config() -> dict:
    # Sensible fallback: weekdays active, weekends off.
    return {
        "monday": {"active": True, "sessions": [{"start": "07:00", "end": "17:00"}]},
        "tuesday": {"active": True, "sessions": [{"start": "07:00", "end": "17:00"}]},
        "wednesday": {"active": True, "sessions": [{"start": "07:00", "end": "17:00"}]},
        "thursday": {"active": True, "sessions": [{"start": "07:00", "end": "17:00"}]},
        "friday": {"active": True, "sessions": [{"start": "07:00", "end": "17:00"}]},
        "saturday": {"active": False, "sessions": []},
        "sunday": {"active": False, "sessions": []},
    }


def _ensure_default_flag_column(db: Session) -> None:
    """
    Ensure attendance_schedules has is_default column.
    Safe no-op when column already exists.
    """
    try:
        db.execute(text("SELECT is_default FROM attendance_schedules LIMIT 1"))
        return
    except Exception:
        pass

    # MySQL/MariaDB
    try:
        db.execute(
            text(
                """
                ALTER TABLE attendance_schedules
                ADD COLUMN is_default TINYINT(1) NOT NULL DEFAULT 0
                """
            )
        )
        db.commit()
        return
    except Exception:
        db.rollback()

    # SQLite fallback
    try:
        db.execute(
            text(
                """
                ALTER TABLE attendance_schedules
                ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def _default_schedule_query(db: Session):
    return db.query(AttendanceSchedule).filter(
        AttendanceSchedule.user_id.is_(None),
        AttendanceSchedule.department_id.is_(None),
        AttendanceSchedule.branch_id.is_(None),
    )


def _get_default_fallback_schedule(db: Session) -> Optional[AttendanceSchedule]:
    _ensure_default_flag_column(db)
    explicit_default = db.query(AttendanceSchedule).filter(
        AttendanceSchedule.user_id.is_(None),
        AttendanceSchedule.department_id.is_(None),
        AttendanceSchedule.branch_id.is_(None),
        AttendanceSchedule.is_active == 1,
        text("is_default = 1"),
    ).order_by(AttendanceSchedule.id.asc()).first()
    if explicit_default:
        return explicit_default
    return _default_schedule_query(db).filter(
        AttendanceSchedule.is_active == 1,
    ).order_by(AttendanceSchedule.id.asc()).first()


def _ensure_default_fallback_schedule(db: Session) -> AttendanceSchedule:
    _ensure_default_flag_column(db)
    default_schedule = _get_default_fallback_schedule(db)
    if default_schedule:
        # Keep fallback always usable.
        if not default_schedule.weekly_config:
            default_schedule.weekly_config = _build_default_weekly_config()
        if default_schedule.effective_date is None:
            default_schedule.effective_date = date.today()
        default_schedule.is_active = 1
        db.execute(text("UPDATE attendance_schedules SET is_default = 0"))
        db.execute(
            text("UPDATE attendance_schedules SET is_default = 1 WHERE id = :id"),
            {"id": default_schedule.id},
        )
        return default_schedule

    first_schedule = db.query(AttendanceSchedule).order_by(AttendanceSchedule.id.asc()).first()
    if first_schedule:
        # Promote first schedule to default fallback when no global exists.
        first_schedule.branch_id = None
        first_schedule.department_id = None
        first_schedule.user_id = None
        first_schedule.is_active = 1
        if not first_schedule.weekly_config:
            first_schedule.weekly_config = _build_default_weekly_config()
        if first_schedule.effective_date is None:
            first_schedule.effective_date = date.today()
        db.execute(text("UPDATE attendance_schedules SET is_default = 0"))
        db.execute(
            text("UPDATE attendance_schedules SET is_default = 1 WHERE id = :id"),
            {"id": first_schedule.id},
        )
        return first_schedule

    # Bootstrap: no schedule exists yet, create the app default fallback.
    default_schedule = AttendanceSchedule(
        name=DEFAULT_ATTENDANCE_SCHEDULE_NAME,
        type="standard",
        branch_id=None,
        department_id=None,
        user_id=None,
        weekly_config=_build_default_weekly_config(),
        is_active=1,
        effective_date=date.today(),
    )
    db.add(default_schedule)
    db.flush()
    db.execute(text("UPDATE attendance_schedules SET is_default = 0"))
    db.execute(
        text("UPDATE attendance_schedules SET is_default = 1 WHERE id = :id"),
        {"id": default_schedule.id},
    )
    return default_schedule


# Helper: Resolve Effective Schedule
def _resolve_effective_schedule_from_candidates(
    user: User,
    candidates: List[AttendanceSchedule],
    assignment: Optional[AttendanceUserAssignment],
    default_global_id: Optional[int] = None,
) -> Tuple[Optional[AttendanceSchedule], Optional[str]]:
    """
    Pure resolution using preloaded candidates + optional assignment row.
    Returns (schedule, source) where source is assignment|user|department|branch|global.
    """
    if assignment:
        assigned_schedule = next(
            (
                s
                for s in candidates
                if s.id == int(assignment.schedule_id)  # type: ignore
            ),
            None,
        )
        if assigned_schedule:
            return assigned_schedule, "assignment"

    for s in candidates:
        if s.user_id == user.id:  # type: ignore
            return s, "user"

    if user.departmentId:  # type: ignore
        for s in candidates:
            if s.department_id == user.departmentId:  # type: ignore
                return s, "department"

    if user.workplace:  # type: ignore
        for s in candidates:
            if s.branch_id == user.workplace:  # type: ignore
                return s, "branch"

    global_candidates = [
        s
        for s in candidates
        if s.user_id is None and s.department_id is None and s.branch_id is None
    ]
    if default_global_id is not None:
        explicit_default = next(
            (s for s in global_candidates if int(s.id) == int(default_global_id)),  # type: ignore[arg-type]
            None,
        )
        if explicit_default:
            return explicit_default, "global"
    if global_candidates:
        # Candidates are ordered newest effective date first. This lets schedule
        # versions resolve correctly for historical report dates.
        return global_candidates[0], "global"

    return None, None


def _group_active_users_by_effective_schedule(
    db: Session,
    target_date: date,
) -> Dict[int, List[Tuple[User, str]]]:
    """Resolve active users once and group them by effective schedule."""
    default_schedule = _get_default_fallback_schedule(db)
    candidates = (
        db.query(AttendanceSchedule)
        .filter(
            AttendanceSchedule.is_active == 1,
            AttendanceSchedule.effective_date <= target_date,
        )
        .order_by(
            AttendanceSchedule.effective_date.desc(),
            AttendanceSchedule.id.desc(),
        )
        .all()
    )
    users = db.query(User).filter(User.status == 1).all()  # type: ignore
    active_user_ids = [int(user.id) for user in users]  # type: ignore

    assignment_by_user: Dict[int, AttendanceUserAssignment] = {}
    if active_user_ids:
        assignment_rows = (
            db.query(AttendanceUserAssignment)
            .filter(
                AttendanceUserAssignment.user_id.in_(active_user_ids),
                AttendanceUserAssignment.start_date <= target_date,
                or_(
                    AttendanceUserAssignment.end_date.is_(None),
                    AttendanceUserAssignment.end_date >= target_date,
                ),
            )
            .order_by(
                AttendanceUserAssignment.user_id,
                AttendanceUserAssignment.start_date.desc(),
                AttendanceUserAssignment.id.desc(),
            )
            .all()
        )
        for assignment in assignment_rows:
            user_id = int(assignment.user_id)  # type: ignore
            if user_id not in assignment_by_user:
                assignment_by_user[user_id] = assignment

    grouped_users: Dict[int, List[Tuple[User, str]]] = defaultdict(list)
    default_global_id = (
        int(default_schedule.id) if default_schedule is not None else None  # type: ignore[arg-type]
    )
    for user in users:
        effective_schedule, source = _resolve_effective_schedule_from_candidates(
            user,
            candidates,
            assignment_by_user.get(int(user.id)),  # type: ignore[arg-type]
            default_global_id=default_global_id,
        )
        if effective_schedule is None:
            continue
        grouped_users[int(effective_schedule.id)].append(  # type: ignore[arg-type]
            (user, source or "global")
        )
    return grouped_users


def get_effective_schedule(
    db: Session, user: User, target_date: Optional[date] = None
) -> Optional[AttendanceSchedule]:
    """
    Resolve the applicable schedule for a user based on hierarchy:
    1. Direct User Assignment
    2. Department Assignment
    3. Branch Assignment
    4. Global Default (All null)
    """
    if target_date is None:
        target_date = date.today()

    candidates = (
        db.query(AttendanceSchedule)
        .filter(
            AttendanceSchedule.is_active == 1,
            AttendanceSchedule.effective_date <= target_date,
        )
        .order_by(AttendanceSchedule.effective_date.desc(), AttendanceSchedule.id.desc())
        .all()
    )

    assignment = (
        db.query(AttendanceUserAssignment)
        .filter(
            AttendanceUserAssignment.user_id == user.id,
            AttendanceUserAssignment.start_date <= target_date,
            or_(
                AttendanceUserAssignment.end_date.is_(None),
                AttendanceUserAssignment.end_date >= target_date,
            ),
        )
        .order_by(
            AttendanceUserAssignment.start_date.desc(),
            AttendanceUserAssignment.id.desc(),
        )
        .first()
    )

    default_schedule = _get_default_fallback_schedule(db)
    schedule, _ = _resolve_effective_schedule_from_candidates(
        user,
        candidates,
        assignment,
        default_global_id=(int(default_schedule.id) if default_schedule else None),  # type: ignore[arg-type]
    )
    return schedule


def _user_for_schedule_context(db: Session, user_id: int) -> User:
    """Load user fields needed for schedule + exception scope resolution."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None:
        return user
    return User(id=user_id)  # type: ignore[arg-type]


def _compute_user_attendance_totals(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    holidays_dict: dict,
    attended_dates: set,
    limit_today: bool = True,
    leave_by_date: Optional[dict] = None,
    db_user: Optional[User] = None,
    day_info_resolver: Optional[Callable[[User, date], dict]] = None,
    attendance_event_counts: Optional[Dict[date, int]] = None,
    attendance_session_event_counts: Optional[Dict[date, Dict[int, int]]] = None,
    include_date: Optional[Callable[[date], bool]] = None,
) -> tuple:
    """
    Single source of truth for expected / present / absent / leave per user in a date range.
    - Only counts dates where the resolved user/department/branch/global schedule is active.
    - Only counts days up to today (future dates in the range are ignored).
    Historical dates resolve the full hierarchy; a later direct assignment does
    not erase an earlier department/branch/global schedule.
    - leave_by_date: per-date approved-leave entries from get_approved_leave_map()[user_id];
      leave fractions are excluded from absent (asked permission ≠ absent) and cap the
      present contribution of a day at (1 − fraction).
    Returns (expected_days, present_days, absent_days, leave_days).
    """
    # Use Cambodia local date so attendance windows align with local schedules
    today = datetime.now(CAMBODIA_TZ).date()

    # We MUST fetch the full user profile (with workplace and departmentId)
    # to accurately map their Branch or Department level schedule
    db_user = db_user or _user_for_schedule_context(db, user_id)
    if db_user.id is None:
        return (0, 0, 0, 0.0)

    expected_days = 0
    present_days = 0.0
    leave_days = 0.0
    employment_start = _user_employment_start_date(db_user)
    current_date = start_date
    while current_date <= end_date:
        if include_date is not None and not include_date(current_date):
            current_date += timedelta(days=1)
            continue
        if employment_start and current_date < employment_start:
            current_date += timedelta(days=1)
            continue
        if limit_today and current_date > today:
            current_date += timedelta(days=1)
            continue
        is_holiday = current_date in holidays_dict
        is_active_day = False
        if not is_holiday:
            day_info = (
                day_info_resolver(db_user, current_date)
                if day_info_resolver
                else get_effective_day_attendance(db, db_user, current_date)
            )
            is_active_day = bool(day_info.get("is_active_day"))
        if is_active_day:
            expected_days += 1
            leave_entry = (leave_by_date or {}).get(current_date)
            leave_fraction = min(1.0, float(leave_entry["fraction"])) if leave_entry else 0.0
            leave_days += leave_fraction
            remaining_work_fraction = max(0.0, 1.0 - leave_fraction)
            if attendance_session_event_counts is not None:
                expected_sessions = len(day_info.get("sessions") or [])
                expected_events = max(1, expected_sessions * 2)
                events_by_session = attendance_session_event_counts.get(
                    current_date, {}
                )
                actual_events = int(events_by_session.get(0, 0))
                for session_index in range(1, expected_sessions + 1):
                    if leave_covers_session(leave_entry, session_index):
                        continue
                    actual_events += min(
                        2, max(0, int(events_by_session.get(session_index, 0)))
                    )
                event_fraction = min(1.0, actual_events / expected_events)
                present_days += min(remaining_work_fraction, event_fraction)
            elif attendance_event_counts is not None:
                # A complete attendance day earns one fraction. Each expected
                # session has two required events (check-in + check-out), so a
                # missing session/scan becomes a fractional absence instead of
                # incorrectly counting the entire day as present.
                expected_sessions = len(day_info.get("sessions") or [])
                expected_events = max(1, expected_sessions * 2)
                actual_events = max(0, int(attendance_event_counts.get(current_date, 0)))
                event_fraction = min(1.0, actual_events / expected_events)
                present_days += min(remaining_work_fraction, event_fraction)
            elif current_date in attended_dates:
                # Compatibility for callers not yet supplying event counts.
                present_days += remaining_work_fraction
        current_date += timedelta(days=1)
    present_days = round(present_days, 2)
    leave_days = round(leave_days, 2)
    absent_days = max(0.0, round(expected_days - present_days - leave_days, 2))
    return (expected_days, present_days, absent_days, leave_days)


def _approved_leave_days_for_dates(
    leave_by_date: Optional[dict],
    included_dates: set[date],
) -> float:
    """Total approved leave for the requested report period.

    Unlike attendance-rate math, this intentionally includes approved future
    dates inside the selected range so the report's Leave metric agrees with
    the leave request list for that same period.
    """
    total = 0.0
    for leave_date, entry in (leave_by_date or {}).items():
        if leave_date not in included_dates:
            continue
        try:
            fraction = float(entry.get("fraction", 0.0))
        except (TypeError, ValueError, AttributeError):
            fraction = 0.0
        total += min(1.0, max(0.0, fraction))
    return round(total, 2)


def _build_report_schedule_context(
    db: Session,
    users: List[User],
    start_date: date,
    end_date: date,
) -> Callable[[User, date], dict]:
    """Preload schedule data once for report calculations.

    The previous report path queried schedules, assignments and exceptions for
    every employee on every date. This request-scoped resolver keeps the same
    hierarchy while doing the database work in a few bulk queries.
    """
    user_ids = [int(user.id) for user in users if user.id is not None]
    schedules = (
        db.query(AttendanceSchedule)
        .filter(
            AttendanceSchedule.is_active == 1,
            AttendanceSchedule.effective_date <= end_date,
        )
        .order_by(
            AttendanceSchedule.effective_date.desc(),
            AttendanceSchedule.id.desc(),
        )
        .all()
    )
    assignments = []
    if user_ids:
        assignments = (
            db.query(AttendanceUserAssignment)
            .filter(
                AttendanceUserAssignment.user_id.in_(user_ids),
                AttendanceUserAssignment.start_date <= end_date,
                or_(
                    AttendanceUserAssignment.end_date.is_(None),
                    AttendanceUserAssignment.end_date >= start_date,
                ),
            )
            .order_by(
                AttendanceUserAssignment.start_date.desc(),
                AttendanceUserAssignment.id.desc(),
            )
            .all()
        )
    assignments_by_user: Dict[int, list] = defaultdict(list)
    for assignment in assignments:
        uid = int(assignment.user_id)
        assignments_by_user[uid].append(assignment)

    ensure_schedule_exceptions_table(db)
    exceptions = (
        db.query(AttendanceScheduleException)
        .filter(
            AttendanceScheduleException.exception_date <= end_date,
            or_(
                AttendanceScheduleException.end_date.is_(None),
                AttendanceScheduleException.end_date >= start_date,
            ),
        )
        .all()
    )
    enrollment_rows = (
        db.query(AttendanceScheduleExceptionEnrollment)
        .filter(
            AttendanceScheduleExceptionEnrollment.user_id.in_(user_ids),
            AttendanceScheduleExceptionEnrollment.occurrence_date >= start_date,
            AttendanceScheduleExceptionEnrollment.occurrence_date <= end_date,
        )
        .all()
        if user_ids
        else []
    )
    enrollment_by_user_date = {
        (int(row.user_id), row.occurrence_date): int(row.exception_id)
        for row in enrollment_rows
    }
    default_schedule = _get_default_fallback_schedule(db)
    default_global_id = (
        int(default_schedule.id) if default_schedule and default_schedule.id else None
    )

    def resolve(user: User, target_date: date) -> dict:
        applicable_schedules = [
            schedule
            for schedule in schedules
            if schedule.effective_date <= target_date
        ]
        assignment = next(
            (
                row
                for row in assignments_by_user.get(int(user.id), [])
                if row.start_date <= target_date
                and (row.end_date is None or row.end_date >= target_date)
            ),
            None,
        )
        schedule, _ = _resolve_effective_schedule_from_candidates(
            user,
            applicable_schedules,
            assignment,
            default_global_id=default_global_id,
        )
        exception = match_exception_from_rows(
            exceptions,
            user,
            target_date,
            enrolled_exception_id=enrollment_by_user_date.get(
                (int(user.id), target_date)
            ),
        )
        return get_effective_day_attendance_with_exception(
            user,
            target_date,
            schedule=schedule,
            exception=exception,
        )

    return resolve


def _build_day_sessions_map(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    db_user: Optional[User] = None,
    day_info_resolver: Optional[Callable[[User, date], dict]] = None,
) -> Dict[str, dict]:
    """
    Effective sessions per date (weekly template with schedule exceptions
    applied), so clients can render history days without re-deriving the
    schedule — weekend/special-day exceptions and historical schedule versions
    are invisible to the current weekly template the app holds. Schedule,
    assignment and exception rows are preloaded once, so long ranges remain
    accurate without issuing database queries inside the date loop.
    """
    db_user = db_user or _user_for_schedule_context(db, user_id)
    if db_user.id is None:
        return {}
    day_info_resolver = day_info_resolver or _build_report_schedule_context(
        db, [db_user], start_date, end_date
    )

    day_sessions: Dict[str, dict] = {}
    employment_start = _user_employment_start_date(db_user)
    current = start_date
    while current <= end_date:
        if employment_start and current < employment_start:
            info = {
                "sessions": [],
                "is_active_day": False,
                "source": "before_employment",
                "exception_reason": None,
            }
        else:
            info = day_info_resolver(db_user, current)
        day_sessions[current.isoformat()] = {
            "sessions": info.get("sessions") or [],
            "is_active_day": bool(info.get("is_active_day")),
            "source": info.get("source"),
            "exception_reason": info.get("exception_reason"),
        }
        current += timedelta(days=1)
    return day_sessions


def _time_str_to_minutes(value: object) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            parsed = datetime.strptime(raw.upper(), fmt)
            return parsed.hour * 60 + parsed.minute
        except Exception:
            pass
    parts = raw.split(":")
    if len(parts) >= 2:
        try:
            return int(parts[0]) * 60 + int(parts[1][:2])
        except Exception:
            return None
    return None


def _sessions_from_day_config(day_config: object) -> List[Dict[str, Any]]:
    if not isinstance(day_config, dict):
        return []
    sessions = day_config.get("sessions")
    if isinstance(sessions, list):
        cleaned: List[Dict[str, Any]] = []
        for session in sessions:
            if not isinstance(session, dict):
                continue
            start = session.get("start") or session.get("start_time")
            end = session.get("end") or session.get("end_time")
            if _time_str_to_minutes(start) is None or _time_str_to_minutes(end) is None:
                continue
            cleaned.append({"start": start, "end": end})
        if cleaned:
            return cleaned

    if day_config.get("mode") == "half_day":
        return [{"start": "08:00", "end": "12:00"}]
    if day_config.get("active", True) and day_config.get("mode") != "not_working":
        return [{"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}]
    return []


def _compute_user_expected_points_so_far(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    holidays_dict: dict,
) -> float:
    """
    Ranking/star denominator up to the current moment.

    Past active days count as 100 points. Today is counted by due attendance
    events only: a session check-in becomes expected at session start, and
    check-out becomes expected at session end. Future sessions do not reduce
    star/rank before they are due.
    """
    now = datetime.now(CAMBODIA_TZ)
    today = now.date()
    now_minutes = now.hour * 60 + now.minute

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return 0.0

    day_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
    day_map_full = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}

    expected_points = 0.0
    employment_start = _user_employment_start_date(db_user)
    current_date = start_date
    while current_date <= end_date:
        if employment_start and current_date < employment_start:
            current_date += timedelta(days=1)
            continue
        if current_date > today:
            break
        if current_date in holidays_dict:
            current_date += timedelta(days=1)
            continue

        day_info = get_effective_day_attendance(db, db_user, current_date)
        if not day_info.get("is_active_day"):
            current_date += timedelta(days=1)
            continue

        sessions = day_info.get("sessions") or []
        if not sessions:
            current_date += timedelta(days=1)
            continue

        if current_date < today:
            expected_points += 100.0
        else:
            event_value = 100.0 / (len(sessions) * 2)
            for session in sessions:
                start_m = _time_str_to_minutes(session.get("start"))
                end_m = _time_str_to_minutes(session.get("end"))
                if start_m is not None and now_minutes >= start_m:
                    expected_points += event_value
                if end_m is not None and now_minutes >= end_m:
                    expected_points += event_value

        current_date += timedelta(days=1)

    return expected_points


def _late_minutes_for_check_in(
    db: Session,
    user_id: int,
    attendance_date: date,
    check_in_datetime: datetime,
    grace_minutes: int = 15,
    scheduled_start: Optional[str] = None,
    scheduled_end: Optional[str] = None,
) -> float:
    """
    Return late minutes for a single check-in (schedule expected start vs actual).
    Matches detailed report logic: if (actual - expected) > grace_minutes, return that difference in minutes.
    """
    def _to_minutes(hhmm: str) -> Optional[int]:
        try:
            parts = str(hhmm).strip().split(":")
            if len(parts) < 2:
                return None
            return int(parts[0]) * 60 + int(parts[1][:2])
        except Exception:
            return None

    if scheduled_start:
        expected_start_str = scheduled_start
        expected_end_str = scheduled_end
    else:
        dummy_user = _user_for_schedule_context(db, user_id)
        candidate_sessions = sessions_for_user_date(db, dummy_user, attendance_date)
        if not candidate_sessions:
            return 0.0

        actual_minutes = check_in_datetime.hour * 60 + check_in_datetime.minute
        selected_session = None
        best_diff = None
        for sess in candidate_sessions:
            s_start = _to_minutes(sess.get("start", ""))
            s_end = _to_minutes(sess.get("end", ""))
            if s_start is None or s_end is None:
                continue
            # Normal in-window match (supports early-entry buffer).
            if (s_start - 30) <= actual_minutes <= s_end:
                selected_session = sess
                break
            # Fallback: closest start time when outside all windows.
            diff = abs(actual_minutes - s_start)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                selected_session = sess

        if not selected_session:
            return 0.0
        expected_start_str = selected_session.get("start", "08:00")
        expected_end_str = selected_session.get("end", "12:00")

    parts = str(expected_start_str).strip().split(":")
    if len(parts) < 2:
        return 0.0
    try:
        expected_h = int(parts[0])
        expected_m = int(parts[1])
    except (ValueError, TypeError):
        return 0.0
    expected_dt = datetime(
        attendance_date.year, attendance_date.month, attendance_date.day,
        expected_h, expected_m, 0, 0,
    )
    end_parts = str(expected_end_str or "").strip().split(":")
    if len(end_parts) >= 2:
        try:
            end_h = int(end_parts[0])
            end_m = int(end_parts[1])
            expected_end_dt = datetime(
                attendance_date.year,
                attendance_date.month,
                attendance_date.day,
                end_h,
                end_m,
                0,
                0,
            )
            if expected_end_dt < expected_dt:
                expected_end_dt = expected_dt
        except (ValueError, TypeError):
            expected_end_dt = expected_dt
    else:
        expected_end_dt = expected_dt
    # If DB returned timezone-aware check_in, make expected_dt comparable (naive comparison if both naive)
    if getattr(check_in_datetime, "tzinfo", None) is not None and check_in_datetime.tzinfo is not None:
        expected_dt = expected_dt.replace(tzinfo=check_in_datetime.tzinfo)
        expected_end_dt = expected_end_dt.replace(tzinfo=check_in_datetime.tzinfo)
    # Clamp late computation to session range only (start -> end), even when
    # makeup attendance is completed outside working hours.
    bounded_actual_dt = check_in_datetime
    if bounded_actual_dt > expected_end_dt:
        bounded_actual_dt = expected_end_dt
    diff_seconds = (bounded_actual_dt - expected_dt).total_seconds()
    diff_mins = diff_seconds / 60.0
    if diff_mins <= grace_minutes:
        return 0.0
    return diff_mins - grace_minutes


def _early_leave_minutes_for_check_out(
    db: Session,
    user_id: int,
    attendance_date: date,
    check_out_datetime: datetime,
    allow_early_leave_mins: int = 0,
    scheduled_start: Optional[str] = None,
    scheduled_end: Optional[str] = None,
) -> float:
    """
    Return early-leave minutes for a single check-out using the stored schedule
    snapshot. If the row has no scheduled_end snapshot, fall back to the
    effective schedule for that attendance date.
    """
    def _to_minutes(hhmm: str) -> Optional[int]:
        try:
            parts = str(hhmm).strip().split(":")
            if len(parts) < 2:
                return None
            return int(parts[0]) * 60 + int(parts[1][:2])
        except Exception:
            return None

    if not scheduled_end:
        dummy_user = _user_for_schedule_context(db, user_id)
        candidate_sessions = sessions_for_user_date(db, dummy_user, attendance_date)
        if not candidate_sessions:
            return 0.0

        selected_session = None
        if scheduled_start:
            for sess in candidate_sessions:
                if str(sess.get("start", "")).strip() == str(scheduled_start).strip():
                    selected_session = sess
                    break
        if selected_session is None:
            actual_minutes = check_out_datetime.hour * 60 + check_out_datetime.minute
            best_diff = None
            for sess in candidate_sessions:
                s_end = _to_minutes(sess.get("end", ""))
                if s_end is None:
                    continue
                diff = abs(actual_minutes - s_end)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    selected_session = sess

        if not selected_session:
            return 0.0
        scheduled_end = selected_session.get("end")

    parts = str(scheduled_end).strip().split(":")
    if len(parts) < 2:
        return 0.0
    try:
        expected_h = int(parts[0])
        expected_m = int(parts[1])
    except (ValueError, TypeError):
        return 0.0

    expected_dt = datetime(
        attendance_date.year,
        attendance_date.month,
        attendance_date.day,
        expected_h,
        expected_m,
        0,
        0,
    )
    if getattr(check_out_datetime, "tzinfo", None) is not None and check_out_datetime.tzinfo is not None:
        expected_dt = expected_dt.replace(tzinfo=check_out_datetime.tzinfo)

    diff_mins = (expected_dt - check_out_datetime).total_seconds() / 60.0
    if diff_mins <= allow_early_leave_mins:
        return 0.0
    return diff_mins - allow_early_leave_mins


def _compute_user_late_hours_in_range(
    db: Session,
    user_ids: set,
    start_date: date,
    end_date: date,
    grace_minutes: int = 15,
    include_session: Optional[Callable[[int, date, int], bool]] = None,
) -> Tuple[dict, dict]:
    """
    For each user_id in user_ids, compute total late minutes in [start_date, end_date]
    from actual check-ins vs schedule expected start. Returns
    (user_id -> late_hours, user_id -> distinct late dates).
    """
    if not user_ids:
        return {}, {}
    records_query = text("""
        SELECT user_id, attendance_date, check_in_time, scheduled_start,
               scheduled_end, snapshot_late_grace_minutes,
               COALESCE(session_index, 0)
        FROM attendance_records
        WHERE attendance_date BETWEEN :start_date AND :end_date
          AND check_in_time IS NOT NULL
          AND user_id IN :user_ids
    """).bindparams(bindparam("user_ids", expanding=True))
    rows = db.execute(records_query, {
        "start_date": start_date,
        "end_date": end_date,
        "user_ids": list(user_ids),
    }).fetchall()
    user_records = defaultdict(list)
    for row in rows:
        u_id = int(row[0])
        if u_id not in user_ids:
            continue
        d = row[1]
        if hasattr(d, "date"):
            d = d.date()
        elif d is not None:
            d = date.fromisoformat(str(d).strip()[:10])
        else:
            continue
        check_in = row[2]
        if check_in is None:
            continue
        user_records[u_id].append((d, check_in, row[3], row[4], row[5], int(row[6] or 0)))
    user_late_hours = {}
    user_late_days = {}
    for u_id in user_ids:
        total_late_mins = 0.0
        late_dates = set()
        for (d, check_in, scheduled_start, scheduled_end, snapshot_grace, session_index) in user_records.get(u_id, []):
            if include_session is not None and not include_session(
                u_id, d, session_index
            ):
                continue
            rule_grace = int(snapshot_grace) if snapshot_grace is not None else grace_minutes
            late_mins = _late_minutes_for_check_in(
                db,
                u_id,
                d,
                check_in,
                rule_grace,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
            )
            total_late_mins += late_mins
            if late_mins > 0:
                late_dates.add(d)
        user_late_hours[u_id] = round(total_late_mins / 60.0, 2)
        user_late_days[u_id] = len(late_dates)
    return user_late_hours, user_late_days


def _compute_user_early_leave_hours_in_range(
    db: Session,
    user_ids: set,
    start_date: date,
    end_date: date,
    allow_early_leave_mins: int = 0,
    include_session: Optional[Callable[[int, date, int], bool]] = None,
) -> Tuple[dict, dict]:
    """
    For each user_id in user_ids, compute total early-leave minutes in range
    from actual check-outs vs the stored scheduled_end snapshot. Returns
    (user_id -> early-leave hours, user_id -> distinct early-leave dates).
    """
    if not user_ids:
        return {}, {}
    records_query = text("""
        SELECT user_id, attendance_date, check_out_time, scheduled_start, scheduled_end,
               snapshot_allow_early_leave_mins, COALESCE(session_index, 0)
        FROM attendance_records
        WHERE attendance_date BETWEEN :start_date AND :end_date
          AND check_out_time IS NOT NULL
          AND user_id IN :user_ids
    """).bindparams(bindparam("user_ids", expanding=True))
    rows = db.execute(records_query, {
        "start_date": start_date,
        "end_date": end_date,
        "user_ids": list(user_ids),
    }).fetchall()
    user_records = defaultdict(list)
    for row in rows:
        u_id = int(row[0])
        if u_id not in user_ids:
            continue
        d = row[1]
        if hasattr(d, "date"):
            d = d.date()
        elif d is not None:
            d = date.fromisoformat(str(d).strip()[:10])
        else:
            continue
        check_out = row[2]
        if check_out is None:
            continue
        user_records[u_id].append((d, check_out, row[3], row[4], row[5], int(row[6] or 0)))

    user_early_leave_hours = {}
    user_early_leave_days = {}
    for u_id in user_ids:
        total_early_mins = 0.0
        early_leave_dates = set()
        for (d, check_out, scheduled_start, scheduled_end, snapshot_allow, session_index) in user_records.get(u_id, []):
            if include_session is not None and not include_session(
                u_id, d, session_index
            ):
                continue
            rule_allow = (
                int(snapshot_allow)
                if snapshot_allow is not None
                else allow_early_leave_mins
            )
            early_mins = _early_leave_minutes_for_check_out(
                db,
                u_id,
                d,
                check_out,
                rule_allow,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
            )
            total_early_mins += early_mins
            if early_mins > 0:
                early_leave_dates.add(d)
        user_early_leave_hours[u_id] = round(total_early_mins / 60.0, 2)
        user_early_leave_days[u_id] = len(early_leave_dates)
    return user_early_leave_hours, user_early_leave_days


@router.get("/me/schedule")
async def get_my_effective_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get the single effective schedule for the current user based on:
    User > Department > Branch > Global hierarchy.
    """
    _require_attendance_processing(db, current_user)
    schedule = get_effective_schedule(db, current_user)
    if not schedule:
        # Return a fallback or empty response if absolutely no config exists
        return {"type": "not_configured"}
        
    return {
        "id": schedule.id,
        "name": schedule.name,
        "type": schedule.type,
        "weekly_config": schedule.weekly_config,
        "source": "user" if schedule.user_id else  # type: ignore
                  ("department" if schedule.department_id else  # type: ignore
                  ("branch" if schedule.branch_id else "global"))  # type: ignore
    }




def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates in meters using Haversine formula."""
    R = 6371000  # Earth's radius in meters

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) * math.sin(delta_lat / 2) + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) * math.sin(delta_lon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def _is_client_ip_allowed(client_ip: Optional[str], allowed_ip_ranges: Optional[str]) -> bool:
    """
    Validate client IP against comma-separated allowlist entries.
    Supports exact IPv4/IPv6 and CIDR ranges (e.g. 192.168.1.0/24).
    Empty allowlist means allow all.
    """
    if not allowed_ip_ranges or not allowed_ip_ranges.strip():
        return True
    if not client_ip:
        return False

    try:
        ip_obj = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return False

    entries = [entry.strip() for entry in allowed_ip_ranges.split(",") if entry.strip()]
    if not entries:
        return True

    for entry in entries:
        try:
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                if ip_obj in network:
                    return True
            else:
                if ip_obj == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            # Ignore malformed entries and continue checking the rest.
            continue

    return False


def _has_attendance_location_anomaly(
    db: Session,
    user_id: int,
    latitude: Optional[float],
    longitude: Optional[float],
) -> bool:
    if latitude is None or longitude is None:
        return False

    now_local = datetime.now(CAMBODIA_TZ).replace(tzinfo=None)

    # 1) Impossible travel / velocity spike against the user's latest recorded GPS point
    latest_point_query = text(
        """
        SELECT
            COALESCE(check_out_time, check_in_time) AS event_time,
            COALESCE(check_out_latitude, check_in_latitude) AS event_lat,
            COALESCE(check_out_longitude, check_in_longitude) AS event_lon
        FROM attendance_records
        WHERE user_id = :user_id
          AND COALESCE(check_out_time, check_in_time) IS NOT NULL
          AND COALESCE(check_out_latitude, check_in_latitude) IS NOT NULL
          AND COALESCE(check_out_longitude, check_in_longitude) IS NOT NULL
        ORDER BY COALESCE(check_out_time, check_in_time) DESC
        LIMIT 1
        """
    )
    latest_row = db.execute(latest_point_query, {"user_id": user_id}).fetchone()
    if latest_row:
        last_time = latest_row[0]
        last_lat = float(latest_row[1])
        last_lon = float(latest_row[2])
        if isinstance(last_time, datetime):
            elapsed_seconds = (now_local - last_time).total_seconds()
            if elapsed_seconds > 0:
                distance_m = calculate_distance(last_lat, last_lon, float(latitude), float(longitude))
                speed_mps = distance_m / elapsed_seconds
                # > 300 km/h between consecutive attendance points is highly suspicious.
                if speed_mps > 83.33:
                    return True
                # Very short interval + large jump is also suspicious.
                if elapsed_seconds < 120 and distance_m > 5000:
                    return True

    # Do not block repeated identical coordinates. Phones can legitimately
    # report the same fused-GPS point at a fixed workplace, especially indoors.
    # Freshness, accuracy, geofence, device binding, and impossible-travel
    # checks are stronger signals and avoid false blocks for reliable users.
    return False


@router.get("/processing-access/me")
async def get_my_attendance_processing_access(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Lightweight status used by QR, Time, and attendance screens."""
    return get_attendance_processing_access(db, current_user).as_dict()


@router.get("/admin/processing-access")
async def list_attendance_processing_access(
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Admin list for department and employee attendance participation rules."""
    _require_attendance_admin(db, current_user)
    ensure_attendance_processing_rules_table(db)

    users_query = db.query(User).filter(User.status == 1)  # type: ignore
    if branch_id is not None:
        users_query = users_query.filter(User.workplace == branch_id)
    if department_id is not None:
        users_query = users_query.filter(User.departmentId == department_id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        users_query = users_query.filter(
            or_(
                User.eName.like(term),
                User.kName.like(term),
                User.username.like(term),
                User.uniqueId.like(term),
            )
        )
    total = users_query.count()
    users = (
        users_query.order_by(User.eName, User.kName, User.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    department_rows = db.execute(
        text("SELECT id, department, COALESCE(code, '') FROM department ORDER BY department")
    ).fetchall()
    department_names = {int(row[0]): str(row[1] or "") for row in department_rows}
    branch_rows = db.execute(
        text("SELECT id, branch_name FROM branch ORDER BY branch_name")
    ).fetchall()
    branch_names = {int(row[0]): str(row[1] or "") for row in branch_rows}

    user_ids = [int(user.id) for user in users]
    avatar_by_user: Dict[int, str] = {}
    if user_ids:
        avatar_rows = db.execute(
            text("""
                SELECT user_id, MIN(avatar)
                FROM users_resource
                WHERE user_id IN :user_ids
                  AND avatar IS NOT NULL AND avatar != ''
                  AND user_type IN ('employee', 'teacher')
                GROUP BY user_id
            """).bindparams(bindparam("user_ids", expanding=True)),
            {"user_ids": user_ids},
        ).fetchall()
        avatar_by_user = {int(row[0]): str(row[1]) for row in avatar_rows}

    all_active_users = db.query(User).filter(User.status == 1).all()  # type: ignore
    rules = _rule_values(
        db,
        user_ids=[int(user.id) for user in all_active_users],
        department_ids=[
            int(user.departmentId)
            for user in all_active_users
            if getattr(user, "departmentId", None) is not None
        ],
    )
    department_totals: Dict[int, int] = defaultdict(int)
    department_disabled: Dict[int, int] = defaultdict(int)
    for user in all_active_users:
        dept_id = getattr(user, "departmentId", None)
        if dept_id is None:
            continue
        dept_id = int(dept_id)
        department_totals[dept_id] += 1
        if not get_attendance_processing_access(db, user, rule_values=rules).enabled:
            department_disabled[dept_id] += 1

    employees = []
    for user in users:
        access = get_attendance_processing_access(db, user, rule_values=rules)
        dept_id = getattr(user, "departmentId", None)
        branch = getattr(user, "workplace", None)
        employees.append(
            {
                "user_id": int(user.id),
                "employee_id": str(getattr(user, "uniqueId", "") or ""),
                "name": str(user.eName or user.kName or user.username),
                "khmer_name": str(user.kName or ""),
                "department_id": int(dept_id) if dept_id is not None else None,
                "department_name": department_names.get(int(dept_id), "") if dept_id is not None else "",
                "branch_id": int(branch) if branch is not None else None,
                "branch_name": branch_names.get(int(branch), "") if branch is not None else "",
                "avatar": avatar_by_user.get(int(user.id), ""),
                "enabled": access.enabled,
                "user_enabled": access.user_enabled,
                "department_enabled": access.department_enabled,
                "disabled_by": access.disabled_by,
            }
        )

    departments = [
        {
            "department_id": int(row[0]),
            "name": str(row[1] or ""),
            "code": str(row[2] or ""),
            "enabled": rules.get(("department", int(row[0])), True),
            "employee_count": department_totals.get(int(row[0]), 0),
            "disabled_employee_count": department_disabled.get(int(row[0]), 0),
        }
        for row in department_rows
    ]
    branches = [
        {"branch_id": int(row[0]), "name": str(row[1] or "")}
        for row in branch_rows
    ]
    return {
        "departments": departments,
        "employees": employees,
        "branches": branches,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/admin/processing-access/department/{department_id}")
async def update_department_attendance_processing_access(
    department_id: int,
    payload: AttendanceProcessingRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    exists = db.execute(
        text("SELECT 1 FROM department WHERE id = :id LIMIT 1"),
        {"id": department_id},
    ).scalar()
    if not exists:
        raise HTTPException(status_code=404, detail="Department not found")
    set_attendance_processing_rule(
        db,
        scope_type="department",
        scope_id=department_id,
        enabled=payload.enabled,
        updated_by=int(current_user.id),
    )
    db.commit()
    _RANKING_CACHE.clear()
    return {"success": True, "enabled": payload.enabled}


@router.patch("/admin/processing-access/user/{user_id}")
async def update_user_attendance_processing_access(
    user_id: int,
    payload: AttendanceProcessingRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    user = db.query(User).filter(User.id == user_id, User.status == 1).first()  # type: ignore
    if user is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    set_attendance_processing_rule(
        db,
        scope_type="user",
        scope_id=user_id,
        enabled=payload.enabled,
        updated_by=int(current_user.id),
    )
    db.commit()
    _RANKING_CACHE.clear()
    access = get_attendance_processing_access(db, user)
    return {"success": True, **access.as_dict()}


@router.get("/locations", response_model=List[WorkLocationResponse])
async def get_work_locations(
    branch_id: Optional[int] = Query(None, description="Filter by branch"),
    show_all: bool = Query(False, description="Show all locations ignoring user branch"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get work locations for GPS validation.

    Exact workplace coordinates are security-sensitive.  Attendance admins
    may inspect every location; employees only receive global locations plus
    locations for their primary/explicitly allowed branches.
    """
    is_admin = _is_attendance_admin(db, current_user)
    if show_all and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attendance administrator access is required to view all work locations",
        )

    # Administrators need inactive rows in the management screen so switching a
    # location off never makes it look deleted. Employee GPS validation still
    # receives active locations only.
    query = db.query(WorkLocation)
    if not (is_admin and show_all):
        query = query.filter(WorkLocation.is_active == True)  # noqa: E712
    if is_admin:
        if not show_all and branch_id is not None:
            query = query.filter(
                or_(WorkLocation.branch_id == branch_id, WorkLocation.branch_id.is_(None))
            )
    else:
        authorized_branch_ids = {
            int(value)
            for value in [getattr(current_user, "workplace", None)]
            if value is not None
        }
        allowed_rows = db.execute(
            text(
                "SELECT branch_id FROM attendance__allowed_branches "
                "WHERE user_id = :user_id"
            ),
            {"user_id": int(current_user.id)},
        ).fetchall()
        authorized_branch_ids.update(int(row[0]) for row in allowed_rows if row[0] is not None)

        if branch_id is not None and int(branch_id) not in authorized_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this branch's work locations",
            )
        if branch_id is not None:
            authorized_branch_ids = {int(branch_id)}

        branch_filter = WorkLocation.branch_id.is_(None)
        if authorized_branch_ids:
            branch_filter = or_(
                branch_filter,
                WorkLocation.branch_id.in_(sorted(authorized_branch_ids)),
            )
        query = query.filter(branch_filter)

    return [
        {
            "id": int(location.id),
            "name": str(location.name),
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
            "radius_meters": float(location.radius_meters or 100.0),
            "branch_id": location.branch_id,
            "is_active": bool(location.is_active),
        }
        for location in query.order_by(WorkLocation.name).all()
    ]


@router.post("/primary-device/status")
async def get_my_primary_attendance_device_status(
    request: AttendanceDeviceIdentityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    identity = _attendance_device_identity_or_upgrade(
        device_id=request.attendance_device_id,
        device_name=request.attendance_device_name,
        platform=request.attendance_device_platform,
    )
    previous_identity = _attendance_previous_device_identity_or_upgrade(
        previous_device_id=request.attendance_device_previous_id,
        device_name=request.attendance_device_name,
        platform=request.attendance_device_platform,
    )
    _lock_employee_row(db, int(current_user.id))
    try:
        binding = ensure_existing_primary_matches(
            db,
            user_id=int(current_user.id),
            identity=identity,
            previous_identity=previous_identity,
        )
    except AttendancePrimaryDeviceMismatch:
        binding = get_primary_attendance_device(db, int(current_user.id))
    if refresh_matching_primary_device_metadata(binding, identity):
        db.commit()
    elif db.new or db.dirty:
        db.commit()
    return binding_status(binding, identity)


@router.post("/primary-device/change")
async def change_my_primary_attendance_device(
    request: AttendanceDeviceIdentityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    identity = _attendance_device_identity_or_upgrade(
        device_id=request.attendance_device_id,
        device_name=request.attendance_device_name,
        platform=request.attendance_device_platform,
    )
    previous_identity = _attendance_previous_device_identity_or_upgrade(
        previous_device_id=request.attendance_device_previous_id,
        device_name=request.attendance_device_name,
        platform=request.attendance_device_platform,
    )
    try:
        _lock_employee_row(db, int(current_user.id))
        try:
            ensure_existing_primary_matches(
                db,
                user_id=int(current_user.id),
                identity=identity,
                previous_identity=previous_identity,
            )
        except AttendancePrimaryDeviceMismatch:
            # This is a genuinely different installation. Continue into the
            # normal 30-day change policy rather than treating it as a server
            # error.
            pass
        result = change_primary_attendance_device(
            db,
            user_id=int(current_user.id),
            identity=identity,
        )
        db.commit()
        return result
    except AttendanceDeviceChangeLocked as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=change_locked_detail(exc),
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception(
            "Could not change primary attendance device for user %s",
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The primary attendance phone could not be changed",
        )


@router.get("/admin/primary-devices/capability")
async def get_attendance_device_admin_capability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    return {
        "can_reset_attendance_devices": _can_reset_attendance_devices(
            db,
            current_user,
        )
    }


@router.get("/admin/primary-devices")
async def list_employee_primary_attendance_devices(
    search: Optional[str] = Query(None, max_length=100),
    branch_id: Optional[int] = Query(None, ge=1),
    department_id: Optional[int] = Query(None, ge=1),
    is_foreigner: Optional[int] = Query(None, ge=1, le=2),
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_device_reset_permission(db, current_user)
    query = db.query(User, AttendancePrimaryDevice).outerjoin(
        AttendancePrimaryDevice,
        AttendancePrimaryDevice.user_id == User.id,
    ).filter(User.status == 1)
    if branch_id is not None:
        query = query.filter(User.workplace == branch_id)
    if department_id is not None:
        query = query.filter(User.departmentId == department_id)
    if is_foreigner is not None:
        query = query.filter(User.isForeigner == is_foreigner)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        query = query.filter(
            or_(
                User.username.ilike(pattern),
                User.eName.ilike(pattern),
                User.kName.ilike(pattern),
            )
        )
    total = query.count()
    rows = query.order_by(
        func.coalesce(User.eName, User.kName, User.username),
        User.id,
    ).offset((page - 1) * limit).limit(limit).all()

    users = [user for user, _ in rows]
    user_ids = [int(user.id) for user in users]
    branch_ids = {int(user.workplace) for user in users if user.workplace}
    department_ids = {
        int(user.departmentId) for user in users if user.departmentId
    }
    branch_name_by_id = {
        int(branch.id): str(branch.branch_name)
        for branch in (
            db.query(Branch).filter(Branch.id.in_(branch_ids)).all()
            if branch_ids
            else []
        )
    }
    department_name_by_id = {
        int(department.id): str(department.department)
        for department in (
            db.query(Department)
            .filter(Department.id.in_(department_ids))
            .all()
            if department_ids
            else []
        )
    }
    avatar_by_user: Dict[int, str] = {}
    if user_ids:
        avatar_stmt = text(
            """
            SELECT ur.user_id, ur.avatar
            FROM users_resource ur
            WHERE ur.user_id IN :uids
              AND ur.user_type IN ('employee', 'teacher')
              AND ur.avatar IS NOT NULL
              AND ur.avatar != ''
            ORDER BY ur.user_id, ur.id DESC
            """
        ).bindparams(bindparam("uids", expanding=True))
        for avatar_row in db.execute(
            avatar_stmt,
            {"uids": user_ids},
        ).fetchall():
            user_id = int(avatar_row[0])
            if user_id not in avatar_by_user:
                avatar_by_user[user_id] = str(avatar_row[1])

    return {
        "can_reset": True,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total else 0,
        "items": [
            {
                "user_id": int(user.id),
                "username": user.username,
                "employee_name": user.eName or user.kName or user.username,
                "khmer_name": user.kName,
                "avatar": avatar_by_user.get(int(user.id)),
                "branch_id": int(user.workplace) if user.workplace else None,
                "branch_name": branch_name_by_id.get(int(user.workplace))
                if user.workplace
                else None,
                "department_id": int(user.departmentId)
                if user.departmentId
                else None,
                "department_name": department_name_by_id.get(
                    int(user.departmentId)
                )
                if user.departmentId
                else None,
                "is_foreigner": int(user.isForeigner),
                "has_primary_device": binding is not None,
                "primary_device_name": binding.device_name if binding else None,
                "platform": binding.platform if binding else None,
                "registered_at": as_utc(binding.registered_at) if binding else None,
                "change_available_at": (
                    as_utc(binding.change_available_at) if binding else None
                ),
            }
            for user, binding in rows
        ],
    }


@router.get("/admin/primary-devices/{user_id}/events")
async def list_employee_primary_attendance_device_events(
    user_id: int,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_device_reset_permission(db, current_user)
    events = (
        db.query(AttendancePrimaryDeviceEvent)
        .filter(AttendancePrimaryDeviceEvent.user_id == int(user_id))
        .order_by(
            AttendancePrimaryDeviceEvent.created_at.desc(),
            AttendancePrimaryDeviceEvent.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "id": int(event.id),
            "action": event.action,
            "actor_user_id": event.actor_user_id,
            "previous_device_name": event.previous_device_name,
            "new_device_name": event.new_device_name,
            "reason": event.reason,
            "created_at": as_utc(event.created_at),
        }
        for event in events
    ]


@router.post("/admin/primary-devices/{user_id}/reset")
async def reset_employee_primary_attendance_device(
    user_id: int,
    request: AttendanceDeviceAdminResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_device_reset_permission(db, current_user)
    target = db.query(User).filter(User.id == int(user_id)).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    try:
        _lock_employee_row(db, int(user_id))
        had_primary = reset_primary_attendance_device(
            db,
            user_id=int(user_id),
            actor_user_id=int(current_user.id),
            reason=request.reason.strip(),
        )
        db.commit()
        return {
            "success": True,
            "had_primary_device": had_primary,
            "message": (
                "Primary attendance phone reset. The next successful check-in "
                "or check-out will register a new primary phone."
            ),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception(
            "Could not reset primary attendance device for user %s",
            user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The primary attendance phone could not be reset",
        )


@router.post("/check-in-out", response_model=CheckInOutResponse)
async def check_in_out(
    request: CheckInOutRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Handle employee check-in or check-out with GPS validation and security checks.
    """
    try:
        user_id = current_user.id
        # Reject before rate limiting, GPS, schedule, holiday, and notification
        # work so excluded employees do not consume attendance resources.
        _require_attendance_processing(db, current_user)
        attendance_device_identity = _attendance_device_identity_for_check_in(
            request,
            http_request,
        )
        attendance_previous_device_identity = (
            _attendance_previous_device_identity_or_upgrade(
                previous_device_id=request.attendance_device_previous_id,
                device_name=request.attendance_device_name,
                platform=request.attendance_device_platform,
            )
            if attendance_device_identity is not None
            else None
        )
        today = datetime.now(CAMBODIA_TZ).date()

        client_ip = await enforce_checkin_rate_limit(http_request, db, int(user_id))
        _checkin_ua = http_request.headers.get("User-Agent")
        checkin_user_agent = (
            _checkin_ua[:500] if _checkin_ua else None
        )

        def log_security_event(
            event_type: str,
            severity: str,
            message: str,
            detail: Optional[Dict[str, Any]] = None,
        ) -> None:
            record_checkin_security_event(
                db,
                user_id=int(user_id),
                client_ip=client_ip,
                event_type=event_type,
                severity=severity,
                message=message,
                detail=detail,
                user_agent=checkin_user_agent,
            )

        def raise_primary_device_mismatch(
            exc: AttendancePrimaryDeviceMismatch,
        ) -> None:
            detail = mismatch_detail(exc.binding)
            log_security_event(
                "attendance_primary_device_mismatch",
                "warning",
                "Attendance was blocked from a phone that is not the employee's primary attendance phone.",
                {
                    "primary_device_name": exc.binding.device_name,
                    # A short digest prefix is safe for diagnostics and lets us
                    # distinguish "same model name, different installation"
                    # without persisting or logging the raw client identifier.
                    "registered_device_fingerprint": str(
                        exc.binding.device_id_hash or ""
                    )[:12],
                    "attempted_device_fingerprint": (
                        attendance_device_identity.id_hash[:12]
                        if attendance_device_identity is not None
                        else None
                    ),
                    "attempted_device_name": (
                        attendance_device_identity.name
                        if attendance_device_identity is not None
                        else "Legacy app"
                    ),
                    "attempted_platform": (
                        attendance_device_identity.platform
                        if attendance_device_identity is not None
                        else None
                    ),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            ) from exc

        # Fast rejection avoids making the wrong phone wait for GPS and schedule
        # processing. The binding is checked again under the employee row lock
        # immediately before the attendance mutation.
        if attendance_device_identity is not None:
            try:
                ensure_existing_primary_matches(
                    db,
                    user_id=int(user_id),
                    identity=attendance_device_identity,
                    previous_identity=attendance_previous_device_identity,
                )
            except AttendancePrimaryDeviceMismatch as exc:
                raise_primary_device_mismatch(exc)
        else:
            logger.info(
                "attendance legacy device compatibility: user_id=%s app_version=%s",
                user_id,
                http_request.headers.get("X-App-Version"),
            )

        holiday_name = db.execute(
            text("SELECT name FROM holidays WHERE date = :today LIMIT 1"),
            {"today": today},
        ).scalar()
        holiday_open_record = db.execute(
            text("""
                SELECT 1 FROM attendance_records
                WHERE user_id = :user_id AND attendance_date = :today
                  AND check_in_time IS NOT NULL AND check_out_time IS NULL
                LIMIT 1
            """),
            {"user_id": user_id, "today": today},
        ).scalar()
        if (
            holiday_name is not None
            and request.action != "check_out"
            and not (request.action == "auto" and holiday_open_record)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Attendance is not required today because it is a holiday"
                    f" ({holiday_name})."
                ),
            )
        
        # 1. Load Global Security Settings
        settings = db.query(AttendanceSystemSettings).first()
        if not settings:
            # Security defaults must be explicit here. SQLAlchemy column
            # defaults are not guaranteed to be populated on an unflushed
            # transient model, which previously made a fresh deployment fail
            # open for GPS/mock-location checks.
            settings = AttendanceSystemSettings(
                require_location=True,
                block_mock_location=True,
                block_developer_options=False,
            )

        require_location = getattr(settings, "require_location", None) is not False
        block_mock_location = (
            getattr(settings, "block_mock_location", None) is not False
        )

        # 2. Security Checks
        if block_mock_location:
            if request.is_mock_location is None:
                log_security_event(
                    "missing_device_security",
                    "warning",
                    "Check-in was blocked because the device security signal was missing.",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Attendance blocked: device security signal is missing. "
                        "Please enable location services and try again."
                    ),
                )
            if request.is_mock_location:
                log_security_event(
                    "mock_location",
                    "critical",
                    "Check-in was blocked because mock or fake GPS was detected.",
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Attendance blocked: mock/fake GPS is detected. "
                        "Please disable mock location tools and try again."
                    ),
                )
        if not _is_client_ip_allowed(client_ip, settings.allowed_ip_ranges):  # type: ignore
            log_security_event(
                "unauthorized_network",
                "critical",
                "Check-in was blocked from a network that is not authorized.",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Attendance blocked: this network is not authorized. "
                    "Please use an approved school network or contact an admin."
                ),
            )
        if _has_attendance_location_anomaly(
            db,
            int(user_id),
            request.latitude,
            request.longitude,
        ):
            log_security_event(
                "location_anomaly",
                "critical",
                "Check-in was blocked because suspicious location movement was detected.",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Attendance blocked: suspicious location movement was detected. "
                    "Please wait and try again from a stable location."
                ),
            )

        # QR/quick-attendance context is client input, never permission. Validate
        # its shape before using it so missing/mismatched fields cannot silently
        # fall back to the employee's primary branch.
        request_context_violation = validate_attendance_request_context(
            qr_type=request.qr_type,
            qr_id=request.qr_id,
            branch_id=request.branch_id,
            app_version=http_request.headers.get("X-App-Version"),
            user_agent=checkin_user_agent,
        )
        if request_context_violation is not None:
            log_security_event(
                request_context_violation.code,
                "warning",
                "Attendance was blocked because the request context was incomplete or inconsistent.",
                {
                    "qr_type": request.qr_type,
                    "qr_id": request.qr_id,
                    "branch_id": request.branch_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": request_context_violation.code,
                    "message": request_context_violation.message,
                },
            )

        # A privileged QR path is allowed only to an attendance administrator.
        is_user_admin = _is_attendance_admin(db, current_user)
        if request.qr_type == "r_attendance" and not is_user_admin:
            log_security_event(
                "forged_privileged_qr",
                "critical",
                "A non-admin attempted to use the privileged attendance QR path.",
                {"qr_type": request.qr_type, "qr_id": request.qr_id},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This attendance QR is restricted to authorized administrators",
            )
        is_admin_override = request.qr_type == "r_attendance" and is_user_admin

        # Resolve the complete branch audience once. Employees may attend at
        # their primary branch and at every branch explicitly granted through
        # attendance__allowed_branches. Quick GPS inference must use this set
        # too, otherwise overlapping workplace radiuses could select a nearer
        # branch the employee is not allowed to use.
        authorized_checkin_branch_ids: set[int] = set()
        if not is_admin_override:
            if getattr(current_user, "workplace", None):
                authorized_checkin_branch_ids.add(int(current_user.workplace))
            allowed_branch_rows = db.execute(
                text(
                    "SELECT branch_id FROM attendance__allowed_branches "
                    "WHERE user_id = :user_id"
                ),
                {"user_id": int(current_user.id)},
            ).fetchall()
            authorized_checkin_branch_ids.update(
                int(row[0])
                for row in allowed_branch_rows
                if row[0] is not None
            )
            if not authorized_checkin_branch_ids:
                log_security_event(
                    "attendance_branch_not_assigned",
                    "warning",
                    "Attendance was blocked because the employee has no assigned or allowed attendance branch.",
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "attendance_branch_not_assigned",
                        "message": (
                            "Attendance is not available because your account has no "
                            "assigned or allowed branch. Please contact an administrator."
                        ),
                    },
                )

        # ------------------------------------------------------------------
        # 2.1 Infer branch from GPS when coming from quick "Taking Attendance"
        # ------------------------------------------------------------------
        inferred_branch_id = None

        if (
            request.qr_type == "t_attendance"
            and not request.branch_id
            and request.latitude is not None
            and request.longitude is not None
        ):
            # Find nearest active work_location within its radius and pick its branch
            locations_query = text(
                """
                SELECT id, latitude, longitude, radius_meters, branch_id
                FROM work_locations
                WHERE is_active = 1
                """
            )
            locations_result = db.execute(locations_query).fetchall()

            closest_loc = None
            closest_distance = None

            for loc_id, lat, lon, radius_m, branch_id in locations_result:
                if lat is None or lon is None:
                    continue
                if (
                    not is_admin_override
                    and branch_id is not None
                    and int(branch_id) not in authorized_checkin_branch_ids
                ):
                    continue
                distance = calculate_distance(
                    float(request.latitude),
                    float(request.longitude),
                    float(lat),
                    float(lon),
                )
                radius = float(radius_m or 100.0)
                if distance <= radius:
                    if closest_distance is None or distance < closest_distance:
                        closest_distance = distance
                        closest_loc = (loc_id, branch_id)

            if closest_loc is None:
                log_security_event(
                    "outside_workplace",
                    "warning",
                    "Check-in was blocked outside all registered workplace GPS ranges.",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Attendance blocked: you are outside all registered workplace "
                        "GPS ranges. Please move inside your assigned branch area."
                    ),
                )

            _, inferred_branch_id = closest_loc
            # Mutate request so all downstream logic uses the inferred branch
            request.branch_id = inferred_branch_id

        # Validate Branch (if scanning specific branch QR or inferred from GPS)
        # Only the explicit administrator override QR bypasses membership.
        # Having an admin role alone must not make ordinary personal attendance
        # branch-unrestricted.
        if not is_admin_override and request.branch_id:
            scanned_branch = int(request.branch_id)
            is_authorized_branch = is_attendance_branch_authorized(
                scanned_branch,
                authorized_checkin_branch_ids,
                is_admin_override=is_admin_override,
            )

            if not is_authorized_branch:
                log_security_event(
                    "unauthorized_branch",
                    "warning",
                    "Check-in was blocked because the employee is not authorized for the selected branch.",
                    {"branch_id": scanned_branch},
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Check-in blocked: your account is not authorized for this "
                        "branch. Please use your assigned/allowed branch location "
                        "or contact an admin to grant access."
                    ),
                )

        if (
            not is_admin_override
            and require_location
            and (request.latitude is None or request.longitude is None)
        ):
            log_security_event(
                "missing_gps",
                "warning",
                "Check-in was blocked because required GPS coordinates were missing.",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Attendance blocked: GPS location is required. "
                    "Please enable location permission and try again."
                ),
            )

        if not is_admin_override and require_location:
            has_enhanced_gps_evidence = (
                request.gps_accuracy_meters is not None
                and request.gps_timestamp is not None
            )
            enhanced_gps_evidence_required = requires_enhanced_gps_evidence(
                http_request.headers.get("X-App-Version"),
                checkin_user_agent,
            )
            if not has_enhanced_gps_evidence:
                if enhanced_gps_evidence_required:
                    log_security_event(
                        "missing_gps_evidence",
                        "warning",
                        "Check-in was blocked because GPS freshness or accuracy evidence was missing.",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Attendance blocked: the official app must provide a fresh, "
                            "accurate GPS reading. Please update the app and try again."
                        ),
                    )

                # Releases through 1.2.6 did not include the two enhanced GPS
                # fields. They still pass mock-location, allowed-network,
                # suspicious-movement, authorized-branch, and workplace
                # geofence validation below.
                logger.info(
                    "attendance legacy GPS compatibility: user_id=%s app_version=%s",
                    user_id,
                    http_request.headers.get("X-App-Version"),
                )

            if has_enhanced_gps_evidence and (
                float(request.gps_accuracy_meters) <= 0
                or float(request.gps_accuracy_meters) > 200
            ):
                log_security_event(
                    "poor_gps_accuracy",
                    "warning",
                    "Check-in was blocked because GPS accuracy was not sufficient.",
                    {"accuracy_meters": float(request.gps_accuracy_meters)},
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Attendance blocked: GPS accuracy must be within 200 meters. "
                        "Move near a window or outdoors and try again."
                    ),
                )

            if has_enhanced_gps_evidence:
                validation_now = datetime.now(timezone.utc)
                device_clock_age_seconds = (
                    gps_age_seconds(
                        request.device_timestamp,
                        now=validation_now,
                    )
                    if request.device_timestamp is not None
                    else None
                )
                if (
                    device_clock_age_seconds is not None
                    and is_device_time_incorrect(device_clock_age_seconds)
                ):
                    log_security_event(
                        "device_time_incorrect",
                        "warning",
                        "Attendance was blocked because the phone clock did not match server time.",
                        {
                            "clock_offset_seconds": round(
                                device_clock_age_seconds,
                                1,
                            ),
                        },
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=incorrect_device_time_error_detail(
                            device_clock_age_seconds,
                            server_time=validation_now,
                        ),
                    )

                reading_age_seconds = gps_age_seconds(
                    request.gps_timestamp,
                    now=validation_now,
                )
                if not is_current_gps_age(reading_age_seconds):
                    log_security_event(
                        "stale_gps",
                        "warning",
                        "Check-in was blocked because the GPS reading was stale or future-dated.",
                        {"gps_age_seconds": round(reading_age_seconds, 1)},
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=stale_gps_error_detail(reading_age_seconds),
                    )

        # 3. Validate GPS Location (if provided or required)
        if (
            not is_admin_override
            and request.latitude is not None
            and request.longitude is not None
        ):
            # Check if user is within allowed work locations
            valid_location = False
            locations_query = text("""
                SELECT latitude, longitude, radius_meters
                FROM work_locations
                WHERE is_active = 1
                AND (branch_id = :branch_id OR branch_id IS NULL)
            """)

            # Validate GPS against the same branch context already authorized above.
            # This must include allowed branches for non-admin users (not only primary workplace).
            # Priority:
            # 1) explicit/inferred request.branch_id (QR branch or quick-attendance inferred branch)
            # 2) fallback to user's workplace when branch_id is missing
            validation_branch_id = request.branch_id or getattr(current_user, 'workplace', None)

            locations_result = db.execute(locations_query, {
                "branch_id": validation_branch_id
            })

            for loc_row in locations_result:
                if loc_row[0] is not None and loc_row[1] is not None:
                    distance = calculate_distance(
                        request.latitude, request.longitude,
                        float(loc_row[0]), float(loc_row[1])
                    )
                    if distance <= (loc_row[2] or 100.0):  # within radius
                        valid_location = True
                        break

            if not valid_location:
                # Check if this date has a schedule exception allowing outside workplace / home attendance
                allows_outside_workplace = False
                effective_exc = None
                try:
                    if request.schedule_exception_id is not None:
                        effective_exc = db.query(AttendanceScheduleException).filter(
                            AttendanceScheduleException.id == int(request.schedule_exception_id)
                        ).first()
                    if effective_exc is None:
                        effective_exc = resolve_schedule_exception(db, current_user, today)
                    if (
                        effective_exc
                        and str(effective_exc.exception_type or "").lower() == "day_off"
                        and bool(getattr(effective_exc, "allow_outside_workplace", 0))
                    ):
                        allows_outside_workplace = True
                except Exception:
                    pass

                if allows_outside_workplace:
                    logger.info(
                        "Attendance outside workplace allowed by schedule exception id=%s for user_id=%s",
                        effective_exc.id if effective_exc else None,
                        user_id,
                    )
                else:
                    log_security_event(
                        "outside_workplace",
                        "warning",
                        "Check-in was blocked outside the employee's authorized workplace GPS range.",
                        {"branch_id": validation_branch_id},
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "Attendance blocked: you are not inside your authorized workplace "
                            "GPS range."
                        ),
                    )
        
        # 4. Schedule Validation (Effective Schedule)
        schedule = get_effective_schedule(db, current_user)
        if schedule:
            # Determine day key (mon, tue, wed...)
            day_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
            day_key = day_map[today.weekday()]
            
            # Check if today is active
            day_config = schedule.weekly_config.get(day_key, {})
            if not day_config.get('active', True):  # type: ignore  # type: ignore
                # Optionally block or allow as Overtime. 
                # For strict control, we block.
                # raise HTTPException(status_code=403, detail=f"Today ({day_key}) is not a working day in your schedule.")
                pass # Proceed for now, allowing OT check-ins by default until requested otherwise.

        # Ensure the opt-in tables exist before acquiring the employee lock;
        # schema setup can commit on a legacy deployment during its first run.
        ensure_schedule_exceptions_table(db)

        # Serialize both schedule selection and attendance mutation for this
        # employee. The selected exception and first check-in are committed as
        # one transaction, including when two phones submit simultaneously.
        if db.get_bind().dialect.name in {"mysql", "mariadb", "postgresql"}:
            db.execute(
                text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"),
                {"user_id": int(user_id)},
            ).fetchone()

        selected_schedule_exception = None
        if request.schedule_exception_id is not None:
            try:
                enroll_in_schedule_exception_for_attendance(
                    db,
                    current_user,
                    today,
                    int(request.schedule_exception_id),
                )
            except ValueError as exc:
                error_code = str(exc)
                messages = {
                    "schedule_exception_selection_locked": (
                        "Your attendance schedule choice for today is already "
                        "locked and cannot be changed."
                    ),
                    "attendance_already_started": (
                        "Attendance has already started today, so a special "
                        "schedule can no longer be selected."
                    ),
                    "schedule_exception_not_available": (
                        "This special schedule is no longer available for your "
                        "account today. Refresh attendance and try again."
                    ),
                }
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": error_code,
                        "message": messages.get(
                            error_code,
                            "The special schedule could not be selected.",
                        ),
                    },
                )
            selected_schedule_exception = resolve_enrolled_schedule_exception(
                db,
                current_user,
                today,
            )
            if (
                selected_schedule_exception is not None
                and str(selected_schedule_exception.exception_type or "")
                .strip()
                .lower()
                == "day_off"
            ):
                # Choosing an optional day off is the complete action: lock the
                # employee's choice without creating an attendance record.
                db.commit()
                return CheckInOutResponse(
                    success=True,
                    message=(
                        "Day off selected. No attendance is required today."
                    ),
                    timestamp=datetime.now(CAMBODIA_TZ),
                    action="day_off",
                )

        # ---------------------------------------------------------
        # 1. Get User's Schedule & Determine Max Sessions
        #    IMPORTANT: Use same effective schedule source as daily-progress.
        # ---------------------------------------------------------
        max_sessions = 2
        day_type = "full"
        expected_sessions = []
        late_grace_minutes = getattr(settings, "late_grace_minutes", 15)
        effective_schedule = None

        try:
            effective_schedule = get_effective_schedule(db, current_user, target_date=today)
            day_info = get_effective_day_attendance(
                db, current_user, today, schedule=effective_schedule
            )
            if not day_info.get("is_active_day"):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Attendance is not available today because it is configured "
                        "as a non-working day."
                    ),
                )

            expected_sessions = list(day_info.get("sessions") or [])
            if expected_sessions:
                max_sessions = len(expected_sessions)
                day_type = day_info.get("day_type") or f"{max_sessions}-Session"
            else:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Attendance is not available today because no working "
                        "sessions are configured."
                    ),
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Failed to securely resolve the effective attendance schedule for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Attendance cannot be verified right now because your schedule "
                    "could not be loaded. No attendance was recorded; please try again."
                ),
            )

        # ---------------------------------------------------------
        # 2. Analyze Existing Records for Today (Session-aware by time)
        # ---------------------------------------------------------
        # Captured under the employee row lock so the response can tell the
        # app—without another network request—that this successful attendance
        # registered the employee's primary phone for the first time.
        primary_device_registered_now = (
            attendance_device_identity is not None
            and get_primary_attendance_device(db, int(user_id)) is None
        )

        records_query = text("""
            SELECT id, check_in_time, check_out_time, session_index
            FROM attendance_records
            WHERE user_id = :user_id AND attendance_date = :today
            ORDER BY check_in_time ASC, id ASC
        """)
        all_records = db.execute(records_query, {
            "user_id": user_id,
            "today": today
        }).fetchall()
        any_open_record = next((r for r in all_records if r[1] is not None and r[2] is None), None)

        allow_early_clock_in_mins = getattr(settings, "allow_early_clock_in_mins", None)
        allow_late_clock_out_mins = getattr(settings, "allow_late_clock_out_mins", None)
        min_minutes_before_checkout = int(30 if getattr(settings, "min_minutes_before_checkout", None) is None else getattr(settings, "min_minutes_before_checkout"))
        session_transition_wait_mins = max(
            0,
            min(
                60,
                int(
                    10
                    if getattr(settings, "session_transition_wait_mins", None) is None
                    else getattr(settings, "session_transition_wait_mins")
                ),
            ),
        )
        allow_early_leave_mins = int(0 if getattr(settings, "allow_early_leave_mins", None) is None else getattr(settings, "allow_early_leave_mins"))
        allow_makeup_missing_sessions = bool(getattr(settings, "allow_makeup_missing_sessions", False))
        early_entry_buffer = _normalize_early_clock_in_mins(allow_early_clock_in_mins)
        late_exit_buffer = allow_late_clock_out_mins if allow_late_clock_out_mins is not None else 0
        per_session_early_list = _coerce_per_session_early_clock_in_list(
            getattr(settings, "per_session_early_clock_in_mins", None)
        )

        def _time_to_minutes(hhmm: str) -> Optional[int]:
            try:
                raw = str(hhmm).strip()
                if not raw:
                    return None

                # 24-hour formats, with optional seconds
                for fmt in ("%H:%M", "%H:%M:%S"):
                    try:
                        parsed = datetime.strptime(raw, fmt)
                        return parsed.hour * 60 + parsed.minute
                    except Exception:
                        pass

                # 12-hour formats with AM/PM (e.g. "7:00 PM")
                for fmt in ("%I:%M %p", "%I:%M:%S %p"):
                    try:
                        parsed = datetime.strptime(raw.upper(), fmt)
                        return parsed.hour * 60 + parsed.minute
                    except Exception:
                        pass

                # Fallback manual parse for strings like "07:00"
                parts = raw.split(":")
                if len(parts) >= 2:
                    h = int(parts[0])
                    m = int(parts[1][:2])
                    return h * 60 + m
                return None
            except Exception:
                return None

        def _find_session_index_for_minutes(actual_minutes: int, include_late_buffer: bool = True) -> int:
            best_idx = -1
            best_start = None
            for i, sess in enumerate(expected_sessions):
                start_m = _time_to_minutes(sess.get("start", ""))
                end_m = _time_to_minutes(sess.get("end", ""))
                if start_m is None or end_m is None:
                    continue
                window_open = _session_checkin_window_open_minutes(
                    i,
                    start_m,
                    expected_sessions=expected_sessions,
                    time_to_minutes=_time_to_minutes,
                    global_early_mins=early_entry_buffer,
                    per_session_mins=per_session_early_list,
                )
                window_close = end_m + (late_exit_buffer if include_late_buffer else 0)
                if window_open <= actual_minutes <= window_close:
                    if actual_minutes >= start_m:
                        if best_start is None or start_m > best_start:
                            best_start = start_m
                            best_idx = i
                    else:
                        if best_start is None or start_m < best_start:
                            best_start = start_m
                            best_idx = i
            return best_idx

        # Debug trace for session window matching
        try:
            window_debug = []
            for i, sess in enumerate(expected_sessions):
                start_m = _time_to_minutes(sess.get("start", ""))
                end_m = _time_to_minutes(sess.get("end", ""))
                if start_m is None or end_m is None:
                    continue
                window_debug.append(
                    {
                        "session": i + 1,
                        "start": sess.get("start"),
                        "end": sess.get("end"),
                        "open_min": _session_checkin_window_open_minutes(
                            i,
                            start_m,
                            expected_sessions=expected_sessions,
                            time_to_minutes=_time_to_minutes,
                            global_early_mins=early_entry_buffer,
                            per_session_mins=per_session_early_list,
                        ),
                        "close_min": end_m + late_exit_buffer,
                    }
                )
            logger.info(
                "check_in_out session windows user=%s now_min=%s windows=%s",
                user_id,
                datetime.now(CAMBODIA_TZ).hour * 60 + datetime.now(CAMBODIA_TZ).minute,
                window_debug,
            )
        except Exception:
            pass

        # Build session states from today's records without requiring extra DB columns.
        session_state = [
            {"has_in": False, "has_out": False, "open_record": None}
            for _ in range(len(expected_sessions))
        ]
        unmatched_records = []
        
        # When makeup is enabled, assign records to sessions based on completion order.
        # Expired open check-ins stay assigned to their original session, but later
        # sessions may still receive their own open check-in.
        if allow_makeup_missing_sessions:
            logger.info(f"MAKEUP MODE: Processing {len(all_records)} records for user {user_id}")
            # Sort records by check-in time (earliest first)
            sorted_records = sorted(all_records, key=lambda r: r[1] if r[1] else datetime.max)

            # Assign each record to the earliest incomplete session
            for rec in sorted_records:
                rec_id, rec_in, rec_out = rec[0], rec[1], rec[2]
                rec_session_idx = rec[3] if len(rec) > 3 else None
                logger.info(f"MAKEUP: Processing record {rec_id} - check_in={rec_in}, check_out={rec_out}")
                placed = False

                preferred_indexes = []
                if rec_session_idx is not None:
                    try:
                        preferred_indexes.append(int(rec_session_idx) - 1)
                    except Exception:
                        pass
                preferred_indexes.extend(
                    i for i in range(len(session_state)) if i not in preferred_indexes
                )

                # Find the recorded session first, then fall back to the
                # earliest session that does not have this record's state yet.
                for s_idx in preferred_indexes:
                    if s_idx < 0 or s_idx >= len(session_state):
                        continue
                    logger.info(f"MAKEUP: Checking session {s_idx} - has_in={session_state[s_idx]['has_in']}, has_out={session_state[s_idx]['has_out']}, open_record={session_state[s_idx]['open_record']}")
                    # If this is a complete record (has both in and out)
                    if rec_in is not None and rec_out is not None:
                        if not session_state[s_idx]["has_in"] and not session_state[s_idx]["has_out"]:
                            session_state[s_idx]["has_in"] = True
                            session_state[s_idx]["has_out"] = True
                            logger.info(f"MAKEUP: Assigned complete record {rec_id} to session {s_idx}")
                            placed = True
                            break
                    # If this is an open check-in (in but no out), bind it to
                    # the next session without a check-in.
                    elif rec_in is not None and rec_out is None:
                        if not session_state[s_idx]["has_in"]:
                            session_state[s_idx]["has_in"] = True
                            session_state[s_idx]["open_record"] = (rec_id, rec_in, rec_out)
                            logger.info(f"MAKEUP: Assigned open check-in {rec_id} to session {s_idx}")
                            placed = True
                            break
                    # If this is a checkout-only record (shouldn't happen, but handle it)
                    elif rec_out is not None and rec_in is None:
                        if session_state[s_idx]["has_in"] and not session_state[s_idx]["has_out"]:
                            session_state[s_idx]["has_out"] = True
                            session_state[s_idx]["open_record"] = None
                            logger.info(f"MAKEUP: Assigned checkout to session {s_idx}")
                            placed = True
                            break

                if not placed:
                    logger.info(f"MAKEUP: Record {rec_id} not placed - added to unmatched")
                    unmatched_records.append((rec_id, rec_in, rec_out))
            
            logger.info(f"MAKEUP: Final session states: {session_state}")
        else:
            # Normal mode: assign records by check-in/out time
            for idx, rec in enumerate(all_records):
                rec_id, rec_in, rec_out = rec[0], rec[1], rec[2]
                rec_session_idx = rec[3] if len(rec) > 3 else None
                s_idx = -1
                if rec_session_idx is not None:
                    try:
                        s_idx = int(rec_session_idx) - 1
                    except Exception:
                        s_idx = -1
                if s_idx < 0 and rec_in is not None:
                    rec_minutes = rec_in.hour * 60 + rec_in.minute
                    s_idx = _find_session_index_for_minutes(rec_minutes, include_late_buffer=False)
                elif s_idx < 0 and rec_out is not None:
                    rec_minutes = rec_out.hour * 60 + rec_out.minute
                    s_idx = _find_session_index_for_minutes(rec_minutes, include_late_buffer=True)
                if s_idx < 0 or s_idx >= len(session_state):
                    unmatched_records.append((rec_id, rec_in, rec_out))
                    continue
                if rec_in is not None:
                    session_state[s_idx]["has_in"] = True
                if rec_out is not None:
                    session_state[s_idx]["has_out"] = True
                if rec_in is not None and rec_out is None:
                    session_state[s_idx]["open_record"] = (rec_id, rec_in, rec_out)

        # Fallback mapping for makeup records recorded outside normal session windows
        # (e.g. completing a missed 07:00-11:00 session at 22:00).
        for rec_id, rec_in, rec_out in unmatched_records:
            if rec_in is not None and rec_out is None:
                # Unmatched open check-in: bind to earliest session without a
                # check-in so an expired earlier open record does not block
                # today's later sessions.
                placed = False

                for i, state in enumerate(session_state):
                    if not state["has_in"]:
                        state["has_in"] = True
                        state["open_record"] = (rec_id, rec_in, rec_out)
                        placed = True
                        break
                if not placed:
                    # Second fallback: only assign if no open check-in exists (makeup mode)
                    for i, state in enumerate(session_state):
                        if not state["has_in"]:
                            # In makeup mode, skip if another session already has open check-in
                            if allow_makeup_missing_sessions:
                                has_any_open = any(s["open_record"] is not None for s in session_state)
                                if has_any_open:
                                    continue
                            state["has_in"] = True
                            state["open_record"] = (rec_id, rec_in, rec_out)
                            break
                continue

            if rec_in is not None and rec_out is not None:
                # Completed pair outside window: assign to earliest incomplete session.
                for i, state in enumerate(session_state):
                    if not state["has_in"] and not state["has_out"]:
                        state["has_in"] = True
                        state["has_out"] = True
                        state["open_record"] = None
                        break

        # Determine active session/action from current (server) Cambodia time.
        now_dt = datetime.now(CAMBODIA_TZ)
        now_minutes = now_dt.hour * 60 + now_dt.minute
        requested_session_idx = (
            int(request.session_index) - 1
            if request.session_index is not None
            else None
        )
        if requested_session_idx is not None and not (
            0 <= requested_session_idx < len(expected_sessions)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Session {request.session_index} is not configured for today. "
                    f"Today has {len(expected_sessions)} attendance session(s)."
                ),
            )
        open_session_idx = -1
        for idx, state in enumerate(session_state):
            if state["open_record"] is not None:
                open_session_idx = idx
                break

        if (
            open_session_idx < 0
            and any_open_record is not None
            and session_state
            and allow_makeup_missing_sessions
        ):
            # Final safety fallback: bind one open record so checkout can proceed
            # only in makeup mode. Normal mode must not let an expired earlier
            # open record block a later session.
            has_any_open = any(state["open_record"] is not None for state in session_state)
            if not has_any_open:
                session_state[0]["open_record"] = (any_open_record[0], any_open_record[1], any_open_record[2])
                session_state[0]["has_in"] = True
                open_session_idx = 0

        def _session_late_cutoff_minutes(session_idx: int) -> Optional[int]:
            if allow_makeup_missing_sessions:
                return None
            if session_idx < 0 or session_idx >= len(expected_sessions):
                return None
            end_m = _time_to_minutes(expected_sessions[session_idx].get("end", ""))
            if end_m is None:
                return None
            return end_m + late_exit_buffer

        def _open_session_is_actionable(session_idx: int) -> bool:
            """How long an unfinished check-out stays completable.

            allow_late_clock_out_mins sets the window past the session's own
            end. Sized generously it reaches into later sessions on purpose:
            with three hours, a session ending 11:15 stays closeable until
            14:15, so an early-afternoon tap finishes the morning rather than
            starting the afternoon and abandoning it.

            Within that window the check-out is always accepted — it is never
            refused with an error — and _is_late_check_out records how late it
            was for the report.
            """
            if session_idx < 0 or session_idx >= len(expected_sessions):
                return False
            return open_check_out_is_available(
                now_minutes=now_minutes,
                session_end_minutes=_time_to_minutes(
                    expected_sessions[session_idx].get("end", "")
                ),
                allow_late_clock_out_minutes=allow_late_clock_out_mins,
            )

        def _is_late_check_out(session_idx: int, at_minutes: int) -> bool:
            """Whether a check-out lands outside its configured window."""
            if session_idx < 0 or session_idx >= len(expected_sessions):
                return False
            end_m = _time_to_minutes(expected_sessions[session_idx].get("end", ""))
            if end_m is None:
                return False
            return is_late_check_out(
                check_out_minutes=at_minutes,
                session_end_minutes=end_m,
                allow_late_clock_out_minutes=late_exit_buffer,
            )

        actionable_open_session_idx = -1
        for idx, state in enumerate(session_state):
            if state["open_record"] is not None and _open_session_is_actionable(idx):
                actionable_open_session_idx = idx
                break

        def _first_available_incomplete_session_idx() -> int:
            for i, state in enumerate(session_state):
                start_m = _time_to_minutes(expected_sessions[i].get("start", ""))
                if start_m is None:
                    continue
                is_incomplete = not (state["has_in"] and state["has_out"])
                if not is_incomplete:
                    continue
                cutoff = _session_late_cutoff_minutes(i)
                if cutoff is not None and now_minutes > cutoff:
                    logger.info(
                        "Makeup: Skipping session %s because its deadline passed",
                        i + 1,
                    )
                    continue
                return i
            return -1

        if request.action == "auto" and actionable_open_session_idx >= 0:
            replay_record = session_state[actionable_open_session_idx][
                "open_record"
            ]
            replay_check_in_time = (
                replay_record[1]
                if replay_record is not None
                and len(replay_record) > 1
                and isinstance(replay_record[1], datetime)
                else None
            )
            if is_recent_auto_checkin_replay(
                requested_action=request.action,
                open_check_in_time=replay_check_in_time,
                now=now_dt,
            ):
                # A lost HTTP response, double tap, or duplicate camera event
                # must not immediately turn a successful check-in into a
                # check-out. Return the already-recorded success unchanged.
                return CheckInOutResponse(
                    success=True,
                    message=(
                        f"Session {actionable_open_session_idx + 1} check-in "
                        "was already recorded successfully"
                    ),
                    timestamp=replay_check_in_time,
                    action="check_in",
                )

        if request.action == "auto":
            # An unfinished check-out always wins: it must be completed before
            # any later session may start, however long it has been open.
            check_in_session_idx = -1
            if actionable_open_session_idx < 0:
                if allow_makeup_missing_sessions:
                    check_in_session_idx = _first_available_incomplete_session_idx()
                    if check_in_session_idx >= 0:
                        logger.info(f"Makeup: Selected session {check_in_session_idx+1} (available incomplete)")
                if check_in_session_idx < 0:
                    check_in_session_idx = _find_session_index_for_minutes(now_minutes, include_late_buffer=False)
            request.action, active_session_idx = resolve_automatic_attendance_target(
                actionable_open_session_index=actionable_open_session_idx,
                check_in_session_index=check_in_session_idx,
            )
        elif request.action == "check_out":
            checkout_session_idx = (
                requested_session_idx
                if requested_session_idx is not None
                else open_session_idx
            )
            checkout_is_actionable = (
                checkout_session_idx >= 0
                and session_state[checkout_session_idx]["open_record"] is not None
                and _open_session_is_actionable(checkout_session_idx)
            )
            current_check_in_session_idx = _find_session_index_for_minutes(
                now_minutes,
                include_late_buffer=False,
            )
            if checkout_session_idx >= 0:
                resolved_action, resolved_session_idx = (
                    resolve_explicit_attendance_target(
                        requested_action="check_out",
                        requested_session_index=checkout_session_idx,
                        requested_session_actionable=checkout_is_actionable,
                        current_check_in_session_index=current_check_in_session_idx,
                    )
                )
            else:
                resolved_action, resolved_session_idx = "check_out", -1

            if resolved_action == "check_in":
                logger.info(
                    "Attendance target rolled forward for user=%s from expired "
                    "Session %s checkout to Session %s check-in",
                    user_id,
                    checkout_session_idx + 1,
                    resolved_session_idx + 1,
                )
                request.action = resolved_action
                active_session_idx = resolved_session_idx
            elif not checkout_is_actionable:
                target_message = (
                    f" for Session {request.session_index}"
                    if request.session_index is not None
                    else ""
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Check-out is not available{target_message} because no "
                        "check-in record is open."
                    ),
                )
            else:
                active_session_idx = checkout_session_idx
        elif request.action == "check_in":
            if actionable_open_session_idx >= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "You are already checked in. Please check out before starting "
                        "a new check-in."
                    ),
                )
            if requested_session_idx is not None:
                active_session_idx = requested_session_idx
                if allow_makeup_missing_sessions:
                    makeup_target_idx = _first_available_incomplete_session_idx()
                    if makeup_target_idx != active_session_idx:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                "Attendance status changed before submission. "
                                "Refresh attendance status and try again."
                            ),
                        )
                else:
                    requested_start_m = _time_to_minutes(
                        expected_sessions[active_session_idx].get("start", "")
                    )
                    requested_end_m = _time_to_minutes(
                        expected_sessions[active_session_idx].get("end", "")
                    )
                    requested_open_m = (
                        _session_checkin_window_open_minutes(
                            active_session_idx,
                            requested_start_m,
                            expected_sessions=expected_sessions,
                            time_to_minutes=_time_to_minutes,
                            global_early_mins=early_entry_buffer,
                            per_session_mins=per_session_early_list,
                        )
                        if requested_start_m is not None
                        else None
                    )
                    requested_session_is_open = (
                        requested_open_m is not None
                        and requested_end_m is not None
                        and is_session_check_in_open(
                            now_minutes=now_minutes,
                            window_open_minutes=requested_open_m,
                            session_end_minutes=requested_end_m,
                        )
                    )
                    current_check_in_session_idx = _find_session_index_for_minutes(
                        now_minutes,
                        include_late_buffer=False,
                    )
                    resolved_action, resolved_session_idx = (
                        resolve_explicit_attendance_target(
                            requested_action="check_in",
                            requested_session_index=active_session_idx,
                            requested_session_actionable=requested_session_is_open,
                            current_check_in_session_index=current_check_in_session_idx,
                        )
                    )
                    if resolved_session_idx != active_session_idx:
                        logger.info(
                            "Attendance target rolled forward for user=%s from "
                            "expired Session %s check-in to Session %s check-in",
                            user_id,
                            active_session_idx + 1,
                            resolved_session_idx + 1,
                        )
                        request.action = resolved_action
                        active_session_idx = resolved_session_idx
                    elif not requested_session_is_open:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"Session {request.session_index} is not open for "
                                "check-in now. Refresh attendance status and try again."
                            ),
                        )
            else:
                active_session_idx = -1
                if allow_makeup_missing_sessions:
                    active_session_idx = _first_available_incomplete_session_idx()
                    if active_session_idx >= 0:
                        logger.info(f"Makeup check-in: Selected session {active_session_idx+1} (available incomplete)")
                if active_session_idx < 0:
                    active_session_idx = _find_session_index_for_minutes(now_minutes, include_late_buffer=False)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid attendance action. Use 'check_in' or 'check_out'."
            )

        if active_session_idx < 0:
            if not expected_sessions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No attendance session is configured for today. "
                        "Please contact an administrator."
                    ),
                )
            
            # Check if there's an open check-out that can still be completed.
            # If its late clock-out allowance already passed, skip it and let
            # the current active session continue instead of blocking.
            if any_open_record is not None:
                # Find which session this open record belongs to
                open_rec_time = any_open_record[1]  # check_in_time
                if open_rec_time:
                    open_rec_minutes = open_rec_time.hour * 60 + open_rec_time.minute
                    # Check if we're still within late clock-out window for that session
                    for i, sess in enumerate(expected_sessions):
                        end_m = _time_to_minutes(sess.get("end", ""))
                        if end_m is None:
                            continue
                        # Check if this session matches the open record time
                        start_m = _time_to_minutes(sess.get("start", ""))
                        if start_m is not None and open_rec_minutes >= start_m:
                            # This is the session with open check-out
                            late_cutoff = end_m + late_exit_buffer
                            if now_minutes <= late_cutoff:
                                # Still within late clock-out window - allow check-out
                                active_session_idx = i
                                request.action = "check_out"
                                logger.info(
                                    f"Allowing late check-out for session {i+1} (within {late_exit_buffer}min buffer)"
                                )
                                break
                            else:
                                mins_over = now_minutes - late_cutoff
                                logger.info(
                                    "Skipping expired open check-out for session %s: %smin over buffer",
                                    i + 1,
                                    mins_over,
                                )
                                continue
            
            # More helpful feedback: next session open vs all sessions ended.
            # Expired sessions are skipped here so Session 1 never-started or
            # expired open checkout cannot block Session 2.
            next_hint = None
            for i, sess in enumerate(expected_sessions):
                start_m = _time_to_minutes(sess.get("start", ""))
                end_m = _time_to_minutes(sess.get("end", ""))
                if start_m is None or end_m is None:
                    continue
                window_open = _session_checkin_window_open_minutes(
                    i,
                    start_m,
                    expected_sessions=expected_sessions,
                    time_to_minutes=_time_to_minutes,
                    global_early_mins=early_entry_buffer,
                    per_session_mins=per_session_early_list,
                )
                if now_minutes > end_m:
                    mins_over = now_minutes - end_m
                    next_hint = (
                        f"Session {i + 1} check-in closed {mins_over} minutes "
                        f"ago (ended at {sess.get('end')})."
                    )
                    continue
                if i < len(session_state):
                    state = session_state[i]
                    if state["has_in"] and state["has_out"]:
                        continue
                    if state["has_in"] and state["open_record"] is None:
                        continue
                if is_session_check_in_open(
                    now_minutes=now_minutes,
                    window_open_minutes=window_open,
                    session_end_minutes=end_m,
                ):
                    next_hint = (
                        f"Session {i + 1} check-in is open "
                        f"(until {sess.get('end')})."
                    )
                    active_session_idx = i
                    request.action = "check_in"
                    break
                elif now_minutes < window_open:
                    mins_until = window_open - now_minutes
                    h_left = mins_until // 60
                    m_left = mins_until % 60
                    if h_left > 0:
                        in_label = f"{h_left}h {m_left}m"
                    else:
                        in_label = f"{m_left}m"
                    next_hint = f"Session {i + 1} check-in opens at {sess.get('start')} (in {in_label})."
                    break
            
            if active_session_idx < 0:
                logger.info(
                    "check_in_out outside-window user=%s now_min=%s message=%s",
                    user_id,
                    now_minutes,
                    next_hint or "All sessions for today have ended. See you tomorrow!",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=next_hint or "All attendance sessions for today are closed. Please try again tomorrow."
                )

        active_session_number = active_session_idx + 1
        active_session = expected_sessions[active_session_idx]
        snapshot_schedule_id = int(effective_schedule.id) if effective_schedule else None  # type: ignore[arg-type]
        snapshot_scheduled_start = _snapshot_time_value(active_session.get("start"))
        snapshot_scheduled_end = _snapshot_time_value(active_session.get("end"))
        active_state = session_state[active_session_idx]
        open_session = active_state["open_record"]

        # ---------------------------------------------------------
        # Approved leave guard — leave-covered sessions are not actionable.
        # ---------------------------------------------------------
        today_leave_entry = (
            get_approved_leave_map(db, [user_id], today, today)
            .get(int(user_id), {})
            .get(today)
        )
        if today_leave_entry is not None:
            if not uncovered_sessions(today_leave_entry, len(expected_sessions)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are on approved leave today. Check-in is not required.",
                )
            if leave_covers_session(today_leave_entry, active_session_number):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Session {active_session_number} is covered by your approved leave. "
                        "Check-in is only needed for your working sessions today."
                    ),
                )

        # ---------------------------------------------------------
        # 3. Handle Action (strict per active session)
        # ---------------------------------------------------------
        if request.action == "auto":
            request.action = "check_out" if open_session else "check_in"

        if request.action == "check_in":
            if active_state["has_in"] and active_state["has_out"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Session {active_session_number} ({active_session.get('start')} – {active_session.get('end')}) is already complete for today."
                )
            if active_state["has_in"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Session {active_session_number} is already checked in. "
                        "Please check out this session first."
                    ),
                )

            # Prevent an employee from checking out one session and immediately
            # checking in to another. The user-row lock above makes this check
            # and the eventual insert atomic across concurrent API workers.
            last_completed_record = None
            last_completed_check_out = None
            last_completed_sort_time = None
            for completed_record in all_records:
                raw_check_out = completed_record[2]
                if raw_check_out is None:
                    continue
                parsed_check_out = raw_check_out
                if not isinstance(parsed_check_out, datetime):
                    try:
                        parsed_check_out = datetime.fromisoformat(
                            str(parsed_check_out).replace("Z", "+00:00")
                        )
                    except (TypeError, ValueError):
                        continue
                sort_time = parsed_check_out
                if sort_time.tzinfo is not None:
                    sort_time = sort_time.astimezone(CAMBODIA_TZ).replace(tzinfo=None)
                if (
                    last_completed_sort_time is None
                    or sort_time > last_completed_sort_time
                ):
                    last_completed_record = completed_record
                    last_completed_check_out = parsed_check_out
                    last_completed_sort_time = sort_time
            transition_now = datetime.now(CAMBODIA_TZ)
            transition_wait = calculate_session_transition_wait(
                last_completed_check_out,
                transition_now,
                session_transition_wait_mins,
            )
            if transition_wait is not None:
                previous_session = None
                if last_completed_record is not None and len(last_completed_record) > 3:
                    try:
                        previous_session = int(last_completed_record[3])
                    except (TypeError, ValueError):
                        previous_session = None
                remaining_minutes = max(
                    1,
                    math.ceil(transition_wait.remaining_seconds / 60),
                )
                transition_detail = {
                    "code": "session_transition_wait",
                    "message": (
                        f"Please wait {remaining_minutes} minute(s) before checking in "
                        f"to Session {active_session_number}. The configured "
                        f"session transition wait is {transition_wait.wait_minutes} minute(s)."
                    ),
                    "wait_minutes": transition_wait.wait_minutes,
                    "remaining_seconds": transition_wait.remaining_seconds,
                    "available_at": transition_wait.available_at.isoformat(),
                    "previous_session": previous_session,
                    "next_session": active_session_number,
                }
                log_security_event(
                    "rapid_session_transition",
                    "warning",
                    "Check-in was blocked during the required wait after a previous session check-out.",
                    transition_detail,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=transition_detail,
                    headers={
                        "Retry-After": str(transition_wait.remaining_seconds),
                    },
                )

            # Determine late status based on active session start (Cambodia time)
            is_late = False
            check_in_dt = datetime.now(CAMBODIA_TZ)
            if "start" in active_session:
                try:
                    start_time_parts = str(active_session["start"]).split(":")
                    expected_hours = int(start_time_parts[0])
                    expected_mins = int(start_time_parts[1])
                    expected_time = check_in_dt.replace(
                        hour=expected_hours,
                        minute=expected_mins,
                        second=0,
                        microsecond=0
                    )
                    limit_time = expected_time + timedelta(minutes=late_grace_minutes)
                    if check_in_dt > limit_time:
                        is_late = True
                except Exception as e:
                    logger.error(f"Error parsing active session start time: {e}")

            new_status = "late" if is_late else "present"
            effective_reason = (request.reason or "").strip() if request.reason else None
            if is_late and not effective_reason:
                effective_reason = (
                    f"Auto note: Late check-in detected by system for "
                    f"Session {active_session_number}. No reason was provided by app."
                )
            base_scan_value = 100.0 / (max_sessions * 2)
            penalty = 5.0 if is_late else 0.0
            scan_value = max(0.0, base_scan_value - penalty)

            if attendance_device_identity is not None:
                try:
                    ensure_or_register_primary_for_attendance(
                        db,
                        user_id=int(user_id),
                        identity=attendance_device_identity,
                        previous_identity=attendance_previous_device_identity,
                    )
                except AttendancePrimaryDeviceMismatch as exc:
                    raise_primary_device_mismatch(exc)

            insert_query = text("""
                INSERT INTO attendance_records
                (user_id, check_in_time, check_in_latitude, check_in_longitude,
                 check_in_branch_id, is_mock_location, device_info, attendance_date, session_index,
                 schedule_id, scheduled_start, scheduled_end, snapshot_late_grace_minutes,
                 snapshot_allow_early_leave_mins, late_reason, status, earned_percentage)
                VALUES (:user_id, :check_in_time, :latitude, :longitude,
                        :branch_id, :is_mock, :device_info, :today, :session_index,
                        :schedule_id, :scheduled_start, :scheduled_end, :late_grace_minutes,
                        :allow_early_leave_mins, :reason, :status, :earned_percentage)
            """)
            db.execute(insert_query, {
                "user_id": user_id,
                "check_in_time": check_in_dt,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "branch_id": request.branch_id,
                "is_mock": request.is_mock_location or False,
                "device_info": (
                    request.attendance_device_name or request.device_info
                ),
                "today": today,
                "session_index": active_session_number,
                "schedule_id": snapshot_schedule_id,
                "scheduled_start": snapshot_scheduled_start,
                "scheduled_end": snapshot_scheduled_end,
                "late_grace_minutes": late_grace_minutes,
                "allow_early_leave_mins": allow_early_leave_mins,
                "reason": effective_reason,
                "status": new_status,
                "earned_percentage": scan_value
            })

            db.commit()
            _RANKING_CACHE.clear()
            await observe_successful_check_in(
                db,
                user_id=int(user_id),
                client_ip=client_ip,
                user_agent=checkin_user_agent,
            )

            try:
                branch_name = None
                if request.branch_id:
                    branch_row = db.execute(text("SELECT branch_name FROM branch WHERE id = :id"), {"id": request.branch_id}).fetchone()
                    if branch_row:
                        branch_name = branch_row[0]

                # Calculate exact late duration after grace for Telegram display.
                late_mins = None
                late_seconds = None
                if is_late and "start" in active_session:
                    try:
                        start_time_parts = str(active_session["start"]).split(":")
                        expected_hours = int(start_time_parts[0])
                        expected_mins = int(start_time_parts[1])
                        expected_time = check_in_dt.replace(
                            hour=expected_hours,
                            minute=expected_mins,
                            second=0,
                            microsecond=0
                        )
                        diff_seconds = (check_in_dt - expected_time).total_seconds()
                        grace_seconds = int(late_grace_minutes) * 60
                        if diff_seconds > grace_seconds:
                            late_seconds = int(math.ceil(diff_seconds - grace_seconds))
                            late_mins = late_seconds // 60
                    except Exception as e:
                        logger.error(f"Error calculating late duration: {e}")

                # Send Telegram notification in background
                background_tasks.add_task(
                    send_attendance_telegram_notification,
                    db,
                    employee_name=current_user.eName or current_user.kName or current_user.username or f"User #{current_user.id}",
                    action_type="check_in",
                    check_time=check_in_dt,
                    status=new_status,
                    late_minutes=late_mins,
                    duration_seconds=late_seconds,
                    location_name=branch_name,
                    branch_id=getattr(current_user, "workplace", None),
                    latitude=request.latitude,
                    longitude=request.longitude,
                    notes=effective_reason,
                )
            except Exception as e:
                logger.error(f"Failed to queue Telegram notification for check-in: {e}")

            return CheckInOutResponse(
                success=True,
                message=f"Session {active_session_number} Check-in Successful",
                timestamp=check_in_dt,
                action="check_in",
                status=new_status,
                primary_device_registered=primary_device_registered_now,
                primary_device_name=(
                    attendance_device_identity.name
                    if primary_device_registered_now
                    else None
                ),
            )

        elif request.action == "check_out":
            if not open_session:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Check-out is not available for Session {active_session_number} "
                        "because no check-in record is open."
                    ),
                )

            # Do not allow check-out before scheduled session start.
            # Example: check-in at 06:30 for 07:00-11:00 is allowed (early clock-in),
            # but check-out must wait until at least 07:00.
            start_m = _time_to_minutes(active_session.get("start", ""))
            if start_m is not None and now_minutes < start_m:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Session {active_session_number} check-out is not allowed before "
                        f"session start time ({active_session.get('start')})."
                    ),
                )

            # Minimum early-leave guard based on schedule start (not check-in time).
            # Checkout unlocks at session_start + 30 minutes.
            min_minutes_from_session_start = max(0, min_minutes_before_checkout)
            if start_m is not None:
                unlock_min = start_m + min_minutes_from_session_start
                if now_minutes < unlock_min:
                    remaining = max(1, unlock_min - now_minutes)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Session {active_session_number} check-out is allowed only "
                            f"{min_minutes_from_session_start} minutes after session start. "
                            f"Please try again in {remaining} minute(s)."
                        ),
                    )

            # Determine early status based on active session end (Cambodia time)
            is_early = False
            check_out_dt = datetime.now(CAMBODIA_TZ)
            if "end" in active_session:
                try:
                    end_time_parts = str(active_session["end"]).split(":")
                    expected_hours = int(end_time_parts[0])
                    expected_mins = int(end_time_parts[1])
                    expected_time = check_out_dt.replace(
                        hour=expected_hours,
                        minute=expected_mins,
                        second=0,
                        microsecond=0
                    )
                    early_cutoff = expected_time - timedelta(minutes=allow_early_leave_mins)
                    if check_out_dt < early_cutoff:
                        is_early = True

                    # A session that was checked into must always remain
                    # closeable. Refusing a late check-out left the record
                    # open forever, and the employee's next tap then opened a
                    # different session instead — losing the earlier one and
                    # recording them hours late for time they had worked.
                    # allow_late_clock_out_mins now classifies the check-out
                    # for the report rather than blocking it.
                    if allow_late_clock_out_mins is not None:
                        late_cutoff = expected_time + timedelta(minutes=allow_late_clock_out_mins)
                        if check_out_dt > late_cutoff:
                            mins_over = int((check_out_dt - late_cutoff).total_seconds() / 60)
                            logger.info(
                                "Late check-out accepted for session %s: %smin past "
                                "the %smin buffer",
                                active_session_number,
                                mins_over,
                                allow_late_clock_out_mins,
                            )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error parsing active session end time: {e}")

            base_scan_value = 100.0 / (max_sessions * 2)
            effective_reason = (request.reason or "").strip() if request.reason else None
            if is_early and not effective_reason:
                effective_reason = (
                    f"Auto note: Early check-out detected by system for "
                    f"Session {active_session_number}. No reason was provided by app."
                )
            penalty = 5.0 if is_early else 0.0
            scan_value = max(0.0, base_scan_value - penalty)

            if attendance_device_identity is not None:
                try:
                    ensure_or_register_primary_for_attendance(
                        db,
                        user_id=int(user_id),
                        identity=attendance_device_identity,
                        previous_identity=attendance_previous_device_identity,
                    )
                except AttendancePrimaryDeviceMismatch as exc:
                    raise_primary_device_mismatch(exc)

            update_query = text("""
                UPDATE attendance_records
                SET check_out_time = :check_out_time,
                    check_out_latitude = :latitude,
                    check_out_longitude = :longitude,
                    check_out_branch_id = :branch_id,
                    work_hours = ROUND(TIMESTAMPDIFF(MINUTE, check_in_time, :check_out_time) / 60.0, 2),
                    leave_early_reason = :reason,
                    session_index = COALESCE(session_index, :session_index),
                    schedule_id = COALESCE(schedule_id, :schedule_id),
                    scheduled_start = COALESCE(scheduled_start, :scheduled_start),
                    scheduled_end = COALESCE(scheduled_end, :scheduled_end),
                    snapshot_late_grace_minutes = COALESCE(snapshot_late_grace_minutes, :late_grace_minutes),
                    snapshot_allow_early_leave_mins = COALESCE(snapshot_allow_early_leave_mins, :allow_early_leave_mins),
                    status = CASE
                        WHEN :is_early THEN 'early_leave'
                        ELSE status
                    END,
                    earned_percentage = earned_percentage + :scan_value,
                    updated_at = NOW()
                WHERE id = :record_id
            """)
            db.execute(update_query, {
                "record_id": open_session[0],
                "check_out_time": check_out_dt,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "branch_id": request.branch_id,
                "session_index": active_session_number,
                "schedule_id": snapshot_schedule_id,
                "scheduled_start": snapshot_scheduled_start,
                "scheduled_end": snapshot_scheduled_end,
                "late_grace_minutes": late_grace_minutes,
                "allow_early_leave_mins": allow_early_leave_mins,
                "reason": effective_reason,
                "is_early": is_early,
                "scan_value": scan_value
            })

            db.commit()
            _RANKING_CACHE.clear()

            try:
                branch_name = None
                if request.branch_id:
                    branch_row = db.execute(text("SELECT branch_name FROM branch WHERE id = :id"), {"id": request.branch_id}).fetchone()
                    if branch_row:
                        branch_name = branch_row[0]

                # Calculate exact early leave duration after allowance for Telegram display.
                early_mins = None
                early_seconds = None
                if is_early and "end" in active_session:
                    try:
                        end_time_parts = str(active_session["end"]).split(":")
                        expected_hours = int(end_time_parts[0])
                        expected_mins = int(end_time_parts[1])
                        expected_time = check_out_dt.replace(
                            hour=expected_hours,
                            minute=expected_mins,
                            second=0,
                            microsecond=0
                        )
                        diff_early_seconds = (expected_time - check_out_dt).total_seconds()
                        allowance_seconds = int(allow_early_leave_mins) * 60
                        if diff_early_seconds > allowance_seconds:
                            early_seconds = int(math.ceil(diff_early_seconds - allowance_seconds))
                            early_mins = early_seconds // 60
                    except Exception as e:
                        logger.error(f"Error calculating early leave duration: {e}")

                # Send Telegram notification in background
                background_tasks.add_task(
                    send_attendance_telegram_notification,
                    db,
                    employee_name=current_user.eName or current_user.kName or current_user.username or f"User #{current_user.id}",
                    action_type="check_out",
                    check_time=check_out_dt,
                    status="early_leave" if is_early else "completed",
                    late_minutes=early_mins,  # Reuse late_minutes parameter for early duration
                    duration_seconds=early_seconds,
                    location_name=branch_name,
                    branch_id=getattr(current_user, "workplace", None),
                    latitude=request.latitude,
                    longitude=request.longitude,
                    notes=effective_reason,
                )
            except Exception as e:
                logger.error(f"Failed to queue Telegram notification for check-out: {e}")

            # Calculate work hours for this session
            check_in_time = open_session[1]
            check_out_time = check_out_dt
            if getattr(check_in_time, "tzinfo", None) is None:
                check_out_time = check_out_time.replace(tzinfo=None)
            else:
                check_out_time = check_out_time.astimezone(check_in_time.tzinfo)
            duration = (check_out_time - check_in_time).total_seconds() / 3600

            return CheckInOutResponse(
                success=True,
                message=f"Session {active_session_number} Check-out Successful",
                timestamp=check_out_dt,
                action="check_out",
                work_hours=round(duration, 2),
                status="early_leave" if is_early else "completed",
                primary_device_registered=primary_device_registered_now,
                primary_device_name=(
                    attendance_device_identity.name
                    if primary_device_registered_now
                    else None
                ),
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid attendance action. Use 'check_in' or 'check_out'."
            )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in check_in_out: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Attendance could not be processed due to a server error. "
                "Please try again in a moment."
            ),
        )


@router.get("/today", response_model=AttendanceRecordResponse)
async def get_today_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get today's attendance record for current user.
    """
    _require_attendance_processing(db, current_user)
    query = text("""
        SELECT id, check_in_time, check_out_time, session_index, schedule_id,
               scheduled_start, scheduled_end, snapshot_late_grace_minutes,
               snapshot_allow_early_leave_mins, work_hours, status, notes,
               late_reason, leave_early_reason
        FROM attendance_records
        WHERE user_id = :user_id AND attendance_date = :today
    """)

    result = db.execute(query, {
        "user_id": current_user.id,
        "today": datetime.now(CAMBODIA_TZ).date(),
    }).fetchone()

    if result:
        return {
            "id": result[0],
            "check_in_time": result[1],
            "check_out_time": result[2],
            "session_index": result[3],
            "schedule_id": result[4],
            "scheduled_start": result[5],
            "scheduled_end": result[6],
            "snapshot_late_grace_minutes": result[7],
            "snapshot_allow_early_leave_mins": result[8],
            "work_hours": float(result[9]) if result[9] else None,
            "status": result[10] or "present",
            "notes": result[11],
            "late_reason": result[12],
            "leave_early_reason": result[13]
        }
    else:
        return {
            "id": None,
            "check_in_time": None,
            "check_out_time": None,
            "session_index": None,
            "schedule_id": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "snapshot_late_grace_minutes": None,
            "snapshot_allow_early_leave_mins": None,
            "work_hours": None,
            "status": "not_checked_in",
            "notes": None,
            "late_reason": None,
            "leave_early_reason": None
        }


@router.get("/report", response_model=AttendanceReportResponse)
async def get_attendance_report(
    start_date: date = Query(..., description="Start date for report"),
    end_date: date = Query(..., description="End date for report"),
    user_id: Optional[int] = Query(None, description="User ID (admin only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get attendance report for a date range.
    """
    # If user_id not specified, use current user's ID
    target_user_id = user_id if user_id else current_user.id

    # Verify permission if accessing other user's data
    if user_id and user_id != current_user.id:
        _require_attendance_admin(db, current_user)
    report_user = (
        current_user
        if int(target_user_id) == int(current_user.id)
        else db.query(User).filter(User.id == target_user_id).first()
    )
    if report_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _require_attendance_processing(db, report_user)

    query = text("""
        SELECT
            attendance_date,
            check_in_time,
            check_out_time,
            session_index,
            schedule_id,
            scheduled_start,
            scheduled_end,
            snapshot_late_grace_minutes,
            snapshot_allow_early_leave_mins,
            work_hours,
            status,
            notes
        FROM attendance_records
        WHERE user_id = :user_id
        AND attendance_date BETWEEN :start_date AND :end_date
        ORDER BY attendance_date
    """)

    result = db.execute(query, {
        "user_id": target_user_id,
        "start_date": start_date,
        "end_date": end_date
    })

    holiday_query = text("SELECT date FROM holidays WHERE date BETWEEN :start_date AND :end_date")
    holiday_rows = db.execute(holiday_query, {"start_date": start_date, "end_date": end_date}).fetchall()
    holidays_set = {row[0] for row in holiday_rows}

    records = []
    total_hours = 0.0
    attended_dates = set()
    attendance_event_counts = defaultdict(int)
    attendance_session_event_counts = defaultdict(lambda: defaultdict(int))

    for row in result:
        record_date = row[0]
        records.append({
            "date": record_date,
            "check_in_time": row[1],
            "check_out_time": row[2],
            "session_index": row[3],
            "schedule_id": row[4],
            "scheduled_start": row[5],
            "scheduled_end": row[6],
            "snapshot_late_grace_minutes": row[7],
            "snapshot_allow_early_leave_mins": row[8],
            "work_hours": float(row[9]) if row[9] else 0.0,
            "status": row[10] or "present",
            "notes": row[11]
        })

        if row[9]:  # Has work hours
            total_hours += float(row[9])
        # Any row for a date means attendance action existed on that date.
        event_count = (1 if row[1] is not None else 0) + (1 if row[2] is not None else 0)
        if event_count > 0:
            attended_dates.add(record_date)
            attendance_event_counts[record_date] += event_count
            attendance_session_event_counts[record_date][int(row[3] or 0)] += (
                event_count
            )

    holidays_dict = {d: True for d in holidays_set}
    leave_map = get_approved_leave_map(db, [target_user_id], start_date, end_date)
    report_user = (
        current_user
        if int(current_user.id) == int(target_user_id)  # type: ignore[arg-type]
        else db.query(User).filter(User.id == target_user_id).first()
    )
    if report_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    report_day_resolver = _build_report_schedule_context(
        db, [report_user], start_date, end_date
    )
    expected_days, present_days, absent_days, leave_days = _compute_user_attendance_totals(
        db=db,
        user_id=target_user_id,
        start_date=start_date,
        end_date=end_date,
        holidays_dict=holidays_dict,
        attended_dates=attended_dates,
        leave_by_date=leave_map.get(target_user_id),
        db_user=report_user,
        day_info_resolver=report_day_resolver,
        attendance_event_counts=dict(attendance_event_counts),
        attendance_session_event_counts={
            report_date: dict(events)
            for report_date, events in attendance_session_event_counts.items()
        },
    )

    return {
        "user_id": target_user_id,
        "start_date": start_date,
        "end_date": end_date,
        "records": records,
        "leave_by_date": leave_map_to_json(leave_map.get(target_user_id, {})),
        "day_sessions": _build_day_sessions_map(
            db,
            target_user_id,
            start_date,
            end_date,
            db_user=report_user,
            day_info_resolver=report_day_resolver,
        ),
        "summary": {
            "total_work_hours": round(total_hours, 2),
            "present_days": present_days,
            "absent_days": absent_days,
            "leave_days": leave_days,
            "total_days": expected_days
        }
    }


@router.get("/salary-history", response_model=List[SalaryHistoryResponse])
async def get_salary_history(
    user_id: Optional[int] = Query(None, description="User ID (admin only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get salary history for a user.
    """
    target_user_id = user_id if user_id else current_user.id
    if int(target_user_id) != int(current_user.id):
        _require_attendance_admin(db, current_user)

    query = text("""
        SELECT id, base_salary, effective_date, end_date, is_active, reason
        FROM salary_history
        WHERE user_id = :user_id
        ORDER BY effective_date DESC
    """)

    result = db.execute(query, {"user_id": target_user_id})

    salary_history = []
    for row in result:
        salary_history.append({
            "id": row[0],
            "base_salary": float(row[1]),
            "effective_date": row[2],
            "end_date": row[3],
            "is_active": bool(row[4]),
            "reason": row[5]
        })

    return salary_history


@router.get("/deductions", response_model=List[SalaryDeductionResponse])
async def get_salary_deductions(
    user_id: Optional[int] = Query(None, description="User ID (admin only)"),
    active_only: bool = Query(True, description="Get only active deductions"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get salary deductions for a user.
    """
    target_user_id = user_id if user_id else current_user.id
    if int(target_user_id) != int(current_user.id):
        _require_attendance_admin(db, current_user)

    query = text("""
        SELECT id, type, amount, description, is_active, effective_date, end_date
        FROM salary_deductions
        WHERE user_id = :user_id
        AND (:active_only = 0 OR is_active = 1)
        ORDER BY effective_date DESC
    """)

    result = db.execute(query, {
        "user_id": target_user_id,
        "active_only": active_only
    })

    deductions = []
    for row in result:
        deductions.append({
            "id": row[0],
            "type": row[1],
            "amount": float(row[2]),
            "description": row[3],
            "is_active": bool(row[4]),
            "effective_date": row[5],
            "end_date": row[6]
        })

    return deductions


@router.get("/bonuses", response_model=List[SalaryBonusResponse])
async def get_salary_bonuses(
    user_id: Optional[int] = Query(None, description="User ID (admin only)"),
    active_only: bool = Query(True, description="Get only active bonuses"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get salary bonuses for a user.
    """
    target_user_id = user_id if user_id else current_user.id
    if int(target_user_id) != int(current_user.id):
        _require_attendance_admin(db, current_user)

    query = text("""
        SELECT id, type, amount, description, is_active, effective_date, end_date
        FROM salary_bonuses
        WHERE user_id = :user_id
        AND (:active_only = 0 OR is_active = 1)
        ORDER BY effective_date DESC
    """)

    result = db.execute(query, {
        "user_id": target_user_id,
        "active_only": active_only
    })

    bonuses = []
    for row in result:
        bonuses.append({
            "id": row[0],
            "type": row[1],
            "amount": float(row[2]),
            "description": row[3],
            "is_active": bool(row[4]),
            "effective_date": row[5],
            "end_date": row[6]
        })

    return bonuses


# Admin Work Locations Management
@router.post("/admin/work-locations")
async def create_work_location(
    location_data: WorkLocationUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Create a new work location (Admin only).
    """
    _require_attendance_admin(db, current_user)
    payload = location_data.model_dump()
    if payload["branch_id"] is not None and not db.query(Branch.id).filter(
        Branch.id == payload["branch_id"]
    ).first():
        raise HTTPException(status_code=404, detail="Branch not found")
    try:
        query = text("""
            INSERT INTO work_locations
            (name, latitude, longitude, radius_meters, branch_id, is_active, created_at, updated_at, created_by, updated_by)
            VALUES (:name, :latitude, :longitude, :radius_meters, :branch_id, :is_active, NOW(), NOW(), :created_by, :updated_by)
        """)

        db.execute(query, {
            "name": payload["name"].strip(),
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
            "radius_meters": payload["radius_meters"],
            "branch_id": payload["branch_id"],
            "is_active": payload["is_active"],
            "created_by": current_user.id,
            "updated_by": current_user.id
        })

        db.commit()
        return {"success": True, "message": "Work location created successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create work location: {str(e)}"
        )


@router.put("/admin/work-locations/{location_id}")
async def update_work_location(
    location_id: int,
    location_data: WorkLocationUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Update a work location (Admin only).
    """
    _require_attendance_admin(db, current_user)
    payload = location_data.model_dump()
    if payload["branch_id"] is not None and not db.query(Branch.id).filter(
        Branch.id == payload["branch_id"]
    ).first():
        raise HTTPException(status_code=404, detail="Branch not found")
    try:
        # First check if the location exists
        check_query = text("SELECT id FROM work_locations WHERE id = :location_id")
        existing = db.execute(check_query, {"location_id": location_id}).fetchone()

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work location not found"
            )

        # Update the location
        update_query = text("""
            UPDATE work_locations
            SET name = :name,
                latitude = :latitude,
                longitude = :longitude,
                radius_meters = :radius_meters,
                branch_id = :branch_id,
                is_active = :is_active,
                updated_at = NOW(),
                updated_by = :updated_by
            WHERE id = :location_id
        """)

        db.execute(update_query, {
            "location_id": location_id,
            "name": payload["name"].strip(),
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
            "radius_meters": payload["radius_meters"],
            "branch_id": payload["branch_id"],
            "is_active": payload["is_active"],
            "updated_by": current_user.id
        })

        db.commit()
        return {"success": True, "message": "Work location updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update work location: {str(e)}"
        )


@router.delete("/admin/work-locations/{location_id}")
async def delete_work_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Delete a work location (Admin only).
    """
    _require_attendance_admin(db, current_user)
    try:
        # Check if exists
        check_query = text("SELECT id FROM work_locations WHERE id = :location_id")
        existing = db.execute(check_query, {"location_id": location_id}).fetchone()

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work location not found"
            )

        # Delete
        delete_query = text("DELETE FROM work_locations WHERE id = :location_id")
        db.execute(delete_query, {"location_id": location_id})
        db.commit()

        return {"success": True, "message": "Work location deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete work location: {str(e)}"
        )


# --------------------------------------------------------------------------------
# Attendance Schedule Management (New)
# --------------------------------------------------------------------------------

@router.get("/admin/schedules")
async def get_attendance_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get all attendance schedules.
    """
    _require_attendance_admin(db, current_user)
    try:
        _ensure_default_flag_column(db)
        default_schedule = _ensure_default_fallback_schedule(db)
        db.commit()
        effective_users_by_schedule = _group_active_users_by_effective_schedule(
            db,
            _get_cambodia_current_date(),
        )

        rows = db.execute(
            text(
                """
                SELECT id, name, type, branch_id, department_id, user_id,
                       weekly_config, is_active, effective_date,
                       COALESCE(is_default, 0) AS is_default
                FROM attendance_schedules
                ORDER BY id DESC
                """
            )
        ).fetchall()
        schedules = []
        for row in rows:
            config = row[6]
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except Exception:
                    config = {}

            schedule_id = int(row[0])
            branch_id = row[3]
            department_id = row[4]
            user_id = row[5]
            history_count = int(
                db.execute(
                    text("SELECT COUNT(*) FROM attendance_records WHERE schedule_id = :sid"),
                    {"sid": schedule_id},
                ).scalar()
                or 0
            )
            assignment_count = (
                db.query(AttendanceUserAssignment)
                .filter(
                    AttendanceUserAssignment.schedule_id == schedule_id,
                    or_(
                        AttendanceUserAssignment.end_date.is_(None),
                        AttendanceUserAssignment.end_date >= date.today(),
                    ),
                )
                .count()
            )
            scoped_user_count = 0
            if user_id is not None:
                scoped_user_count = (
                    db.query(User)
                    .filter(User.id == user_id, User.status == 1)  # type: ignore
                    .count()
                )
            elif department_id is not None:
                scoped_user_count = (
                    db.query(User)
                    .filter(User.departmentId == department_id, User.status == 1)  # type: ignore
                    .count()
                )
            elif branch_id is not None:
                scoped_user_count = (
                    db.query(User)
                    .filter(User.workplace == branch_id, User.status == 1)  # type: ignore
                    .count()
                )
            elif row[9]:
                scoped_user_count = (
                    db.query(User)
                    .filter(User.status == 1)  # type: ignore
                    .count()
                )

            schedules.append({
                "id": schedule_id,
                "name": row[1],
                "type": row[2],
                "branch_id": branch_id,
                "department_id": department_id,
                "user_id": user_id,
                "weekly_config": config,
                "is_active": bool(row[7]),
                "effective_date": row[8].isoformat() if row[8] else None,
                "is_default": bool(row[9]) or (row[0] == default_schedule.id),
                "history_count": history_count,
                "assignment_count": assignment_count,
                "scoped_user_count": scoped_user_count,
                "effective_user_count": len(
                    effective_users_by_schedule.get(schedule_id, [])
                ),
                "is_used": bool(
                    history_count
                    or assignment_count
                    or scoped_user_count
                    or effective_users_by_schedule.get(schedule_id)
                ),
            })

        return {"schedules": schedules}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to fetch schedules: {e}")
        return {"schedules": []}


@router.get("/admin/schedules/{schedule_id}/users")
async def get_attendance_schedule_users(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Return active staff who currently use a schedule.

    The preview uses the same assignment > user > department > branch > global
    precedence as attendance processing and the schedule-list usage count.
    """
    _require_attendance_admin(db, current_user)

    schedule = (
        db.query(AttendanceSchedule)
        .filter(AttendanceSchedule.id == schedule_id)
        .first()
    )
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    preview_date = _get_cambodia_current_date()
    matching_users = _group_active_users_by_effective_schedule(
        db,
        preview_date,
    ).get(schedule_id, [])

    matching_user_ids = [int(user.id) for user, _ in matching_users]  # type: ignore
    branch_ids = {
        int(user.workplace)
        for user, _ in matching_users
        if user.workplace is not None  # type: ignore
    }
    department_ids = {
        int(user.departmentId)
        for user, _ in matching_users
        if user.departmentId is not None  # type: ignore
    }
    branch_names = {
        int(branch.id): str(branch.branch_name)  # type: ignore
        for branch in (
            db.query(Branch).filter(Branch.id.in_(branch_ids)).all()
            if branch_ids
            else []
        )
    }
    department_names = {
        int(department.id): str(department.department)  # type: ignore
        for department in (
            db.query(Department).filter(Department.id.in_(department_ids)).all()
            if department_ids
            else []
        )
    }

    avatar_by_user: Dict[int, str] = {}
    if matching_user_ids:
        avatar_stmt = text(
            """
            SELECT ur.user_id, ur.avatar
            FROM users_resource ur
            WHERE ur.user_id IN :uids
              AND ur.user_type IN ('employee', 'teacher')
              AND ur.avatar IS NOT NULL
              AND ur.avatar != ''
            ORDER BY ur.user_id, ur.id DESC
            """
        ).bindparams(bindparam("uids", expanding=True))
        for row in db.execute(avatar_stmt, {"uids": matching_user_ids}).fetchall():
            user_id = int(row[0])
            if user_id not in avatar_by_user:
                avatar_by_user[user_id] = str(row[1])

    serialized_users = []
    for user, source in matching_users:
        user_id = int(user.id)  # type: ignore
        user_name = (
            f"{user.eName or ''} {user.kName or ''}".strip()
            or str(user.username)  # type: ignore
        )
        serialized_users.append(
            {
                "user_id": user_id,
                "user_name": user_name,
                "avatar": avatar_by_user.get(user_id),
                "branch_id": user.workplace,  # type: ignore
                "branch_name": branch_names.get(int(user.workplace))  # type: ignore[arg-type]
                if user.workplace is not None  # type: ignore
                else None,
                "department_id": user.departmentId,  # type: ignore
                "department_name": department_names.get(int(user.departmentId))  # type: ignore[arg-type]
                if user.departmentId is not None  # type: ignore
                else None,
                "schedule_source": source,
            }
        )
    serialized_users.sort(key=lambda item: item["user_name"].casefold())

    return {
        "schedule_id": schedule_id,
        "schedule_name": schedule.name,
        "preview_date": preview_date.isoformat(),
        "total": len(serialized_users),
        "users": serialized_users,
    }


@router.post("/admin/schedules")
async def create_attendance_schedule(
    schedule_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Create a new attendance schedule.
    """
    _require_attendance_admin(db, current_user)
    try:
        _ensure_default_flag_column(db)
        total_before = db.query(AttendanceSchedule).count()
        config = schedule_data.get("weekly_config", {})
        if not config:
            config = _build_default_weekly_config()

        new_schedule = AttendanceSchedule(
            name=schedule_data["name"],
            type=schedule_data.get("type", "standard"),
            branch_id=schedule_data.get("branch_id"),
            department_id=schedule_data.get("department_id"),
            user_id=schedule_data.get("user_id"),
            weekly_config=config,
            is_active=1 if schedule_data.get("is_active", True) else 0,
            effective_date=schedule_data.get("effective_date", date.today()),
        )
        db.add(new_schedule)
        db.flush()

        # Rule: first created schedule becomes app default fallback.
        if total_before == 0:
            new_schedule.branch_id = None
            new_schedule.department_id = None
            new_schedule.user_id = None
            new_schedule.is_active = 1
            db.execute(text("UPDATE attendance_schedules SET is_default = 0"))
            db.execute(
                text("UPDATE attendance_schedules SET is_default = 1 WHERE id = :id"),
                {"id": new_schedule.id},
            )

        db.commit()
        return {"success": True, "message": "Schedule created successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create schedule: {str(e)}"
        )


@router.put("/admin/schedules/{schedule_id}")
async def update_attendance_schedule(
    schedule_id: int,
    schedule_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Create a new effective version of an attendance schedule.

    Existing schedule rows are left unchanged so historical reports can keep
    resolving old dates against the old schedule definition.
    """
    _require_attendance_admin(db, current_user)
    try:
        _ensure_default_flag_column(db)
        schedule = db.query(AttendanceSchedule).filter(AttendanceSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        default_schedule = _get_default_fallback_schedule(db)
        is_default = default_schedule is not None and default_schedule.id == schedule_id

        config = schedule_data.get("weekly_config", {})
        if not config:
            config = _build_default_weekly_config()

        min_version_date = _minimum_schedule_version_date()
        effective_date = _coerce_schedule_effective_date(
            schedule_data.get("effective_date"),
            minimum=min_version_date,
        )

        if is_default:
            branch_id = None
            department_id = None
            user_id = None
            is_active = 1
        else:
            branch_id = schedule_data.get("branch_id")
            department_id = schedule_data.get("department_id")
            user_id = schedule_data.get("user_id")
            is_active = 1 if schedule_data.get("is_active", True) else 0

        new_schedule = AttendanceSchedule(
            name=schedule_data.get("name") or schedule.name,
            type=schedule_data.get("type", schedule.type or "standard"),
            branch_id=branch_id,
            department_id=department_id,
            user_id=user_id,
            weekly_config=config,
            is_active=is_active,
            effective_date=effective_date,
        )
        db.add(new_schedule)
        db.flush()

        assignments_closed, assignments_created = _version_schedule_assignments(
            db,
            old_schedule_id=int(schedule_id),
            new_schedule_id=int(new_schedule.id),  # type: ignore[arg-type]
            effective_date=effective_date,
            assigned_by=int(current_user.id) if current_user.id is not None else None,  # type: ignore[arg-type]
        )

        if is_default:
            db.execute(text("UPDATE attendance_schedules SET is_default = 0"))
            db.execute(
                text("UPDATE attendance_schedules SET is_default = 1 WHERE id = :id"),
                {"id": new_schedule.id},
            )

        db.commit()
        return {
            "success": True,
            "message": "Schedule version created successfully",
            "schedule_id": int(new_schedule.id),  # type: ignore[arg-type]
            "previous_schedule_id": schedule_id,
            "effective_date": effective_date.isoformat(),
            "minimum_effective_date": min_version_date.isoformat(),
            "versioned": True,
            "assignments_closed": assignments_closed,
            "assignments_created": assignments_created,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schedule: {str(e)}"
        )


@router.patch("/admin/schedules/{schedule_id}/activation")
async def update_attendance_schedule_activation(
    schedule_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Activate or deactivate a schedule without deleting its history."""
    _require_attendance_admin(db, current_user)
    try:
        requested_state = payload.get("is_active")
        if not isinstance(requested_state, bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="is_active must be true or false",
            )

        _ensure_default_flag_column(db)
        schedule = (
            db.query(AttendanceSchedule)
            .filter(AttendanceSchedule.id == schedule_id)
            .first()
        )
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found",
            )

        default_schedule = _get_default_fallback_schedule(db)
        is_default = (
            default_schedule is not None
            and int(default_schedule.id) == int(schedule_id)  # type: ignore[arg-type]
        )
        if not requested_state and is_default:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "The default fallback schedule cannot be deactivated. "
                    "Set another schedule as default first."
                ),
            )

        schedule.is_active = 1 if requested_state else 0
        db.commit()
        return {
            "success": True,
            "schedule_id": schedule_id,
            "is_active": requested_state,
            "message": (
                "Schedule activated successfully"
                if requested_state
                else "Schedule deactivated successfully"
            ),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schedule status: {str(e)}",
        )


@router.post("/admin/schedules/{schedule_id}/set-default")
async def set_default_attendance_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Set a specific schedule as the global default fallback.
    """
    _require_attendance_admin(db, current_user)
    try:
        _ensure_default_flag_column(db)
        target = db.query(AttendanceSchedule).filter(AttendanceSchedule.id == schedule_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Schedule not found")

        config = target.weekly_config or _build_default_weekly_config()
        effective_date = _minimum_schedule_version_date()

        # Create a global default version instead of mutating the selected row.
        # The selected row may be a historical branch/department/user schedule.
        new_default = AttendanceSchedule(
            name=target.name,
            type=target.type or "standard",
            branch_id=None,
            department_id=None,
            user_id=None,
            weekly_config=config,
            is_active=1,
            effective_date=effective_date,
        )
        db.add(new_default)
        db.flush()

        db.execute(text("UPDATE attendance_schedules SET is_default = 0"))
        db.execute(
            text("UPDATE attendance_schedules SET is_default = 1 WHERE id = :id"),
            {"id": new_default.id},
        )

        db.commit()
        return {
            "success": True,
            "message": "Default schedule version created successfully",
            "schedule_id": int(new_default.id),  # type: ignore[arg-type]
            "previous_schedule_id": schedule_id,
            "effective_date": effective_date.isoformat(),
            "minimum_effective_date": effective_date.isoformat(),
            "versioned": True,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set default schedule: {str(e)}"
        )


@router.delete("/admin/schedules/{schedule_id}")
async def delete_attendance_schedule(
    schedule_id: int,
    force_remove: bool = Query(False, description="Allow deleting default fallback schedule"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Delete an attendance schedule.
    """
    _require_attendance_admin(db, current_user)
    try:
        schedule = db.query(AttendanceSchedule).filter(AttendanceSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        default_schedule = _get_default_fallback_schedule(db)
        is_default = default_schedule is not None and default_schedule.id == schedule_id
        if is_default and not force_remove:
            raise HTTPException(
                status_code=400,
                detail="Default fallback schedule cannot be deleted. Use force_remove=true if necessary.",
            )

        if not force_remove:
            used_by_records = db.execute(
                text(
                    "SELECT COUNT(*) FROM attendance_records WHERE schedule_id = :sid"
                ),
                {"sid": schedule_id},
            ).scalar() or 0
            used_by_assignments = (
                db.query(AttendanceUserAssignment)
                .filter(AttendanceUserAssignment.schedule_id == schedule_id)
                .count()
            )
            today_local = datetime.now(CAMBODIA_TZ).date()
            is_historical_scope_schedule = bool(
                schedule.effective_date is not None
                and schedule.effective_date < today_local
                and (schedule.branch_id is not None or schedule.department_id is not None or schedule.user_id is not None)
            )
            if used_by_records or used_by_assignments or is_historical_scope_schedule:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "This schedule is used by attendance history or assignments. "
                        "Create/edit a new version instead of deleting it, or use force_remove=true only if you accept historical report changes."
                    ),
                )

        db.delete(schedule)
        db.flush()

        # Always keep a fallback default schedule available.
        _ensure_default_fallback_schedule(db)
        db.commit()
        return {"success": True, "message": "Schedule deleted successfully"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete schedule: {str(e)}"
        )


def _validate_schedule_exception_recurrence(
    recurrence_type: str,
    exception_date: date,
    end_date: Optional[date],
) -> Tuple[str, Optional[date]]:
    normalized = (recurrence_type or "once").strip().lower()
    if normalized not in VALID_RECURRENCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="recurrence_type must be once, date_range, or monthly",
        )
    if normalized == "once":
        return normalized, None
    if normalized == "date_range" and end_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date is required for a date_range override",
        )
    if end_date is not None and end_date < exception_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be before exception_date",
        )
    return normalized, end_date


def _resolve_exception_sessions_payload(
    payload: ScheduleExceptionCreate | ScheduleExceptionUpdate,
    *,
    existing_type: Optional[str] = None,
) -> Tuple[str, Optional[List[Dict[str, str]]]]:
    exc_type = (payload.exception_type or existing_type or "sessions_override").strip().lower()
    if exc_type == "day_off":
        return exc_type, []

    preset = (payload.preset or "").strip().lower() if getattr(payload, "preset", None) else ""
    if preset and preset in PRESET_SESSIONS:
        return exc_type, [dict(s) for s in PRESET_SESSIONS[preset]]

    raw_sessions = payload.sessions
    if raw_sessions:
        sessions = [
            {"start": s.start.strip(), "end": s.end.strip()}
            for s in raw_sessions
            if s.start and s.end
        ]
        if sessions:
            return exc_type, sessions

    if exc_type != "day_off":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sessions or a preset are required for sessions_override",
        )
    return exc_type, []


def _exception_scope_label(row: AttendanceScheduleException) -> str:
    if row.user_id is not None:
        return "user"
    if row.department_id is not None:
        return "department"
    if row.branch_id is not None:
        return "branch"
    if row.is_foreigner is not None:
        return "nationality"
    return "all_staff"


def _nationality_label(value: Optional[int]) -> Optional[str]:
    if value == 1:
        return "Khmer Staff"
    if value == 2:
        return "Foreigner Staff"
    return None


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _bilingual_text_pair(
    english: Optional[str],
    khmer: Optional[str],
    *,
    fallback: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Fill a missing language from the other without machine translation."""
    en = _clean_optional_text(english)
    km = _clean_optional_text(khmer)
    legacy = _clean_optional_text(fallback)
    en = en or km or legacy
    km = km or en or legacy
    return en, km


def _serialize_schedule_exception(
    db: Session,
    row: AttendanceScheduleException,
) -> Dict[str, Any]:
    sessions = _parse_exception_sessions(row.sessions)
    user_name = None
    branch_name = None
    department_name = None
    if row.user_id is not None:
        user = db.query(User).filter(User.id == row.user_id).first()
        if user:
            user_name = str(user.eName or user.kName or user.username or user.id)
    if row.branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == row.branch_id).first()
        if branch:
            branch_name = str(branch.branch_name or branch.id)
    if row.department_id is not None:
        dept = db.query(Department).filter(Department.id == row.department_id).first()
        if dept:
            department_name = str(dept.department_name or dept.id)

    weekly_preview = None
    if row.exception_date is not None:
        rep_user = representative_user_for_exception_scope(
            db,
            user_id=row.user_id,
            branch_id=row.branch_id,
            department_id=row.department_id,
            is_foreigner=row.is_foreigner,
        )
        weekly_preview = get_weekly_day_attendance(db, rep_user, row.exception_date)

    title_en, title_km = _bilingual_text_pair(
        getattr(row, "title_en", None),
        getattr(row, "title_km", None),
        fallback=row.reason,
    )
    reason_en, reason_km = _bilingual_text_pair(
        getattr(row, "reason_en", None),
        getattr(row, "reason_km", None),
        fallback=row.reason,
    )

    return {
        "id": int(row.id),  # type: ignore[arg-type]
        "exception_date": row.exception_date.isoformat() if row.exception_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "recurrence_type": schedule_exception_recurrence_type(row),
        "user_id": row.user_id,
        "branch_id": row.branch_id,
        "department_id": row.department_id,
        "is_foreigner": row.is_foreigner,
        "nationality_label": _nationality_label(row.is_foreigner),
        "exception_type": row.exception_type,
        "sessions": sessions,
        "reason": row.reason,
        "title_en": title_en,
        "title_km": title_km,
        "reason_en": reason_en,
        "reason_km": reason_km,
        "created_by": row.created_by,
        "is_active": bool(row.is_active),
        "self_enrollment_enabled": bool(
            getattr(row, "self_enrollment_enabled", 0)
        ),
        "allow_outside_workplace": bool(
            getattr(row, "allow_outside_workplace", 0)
        ),
        "enrollment_count": (
            db.query(AttendanceScheduleExceptionEnrollment)
            .filter(
                AttendanceScheduleExceptionEnrollment.exception_id == row.id
            )
            .count()
        ),
        "scope_label": _exception_scope_label(row),
        "user_name": user_name,
        "branch_name": branch_name,
        "department_name": department_name,
        "weekly_preview": weekly_preview,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/admin/schedule-exceptions")
async def list_schedule_exceptions(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    user_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    ensure_schedule_exceptions_table(db)

    if start_date is None:
        start_date = date.today().replace(day=1)
    if end_date is None:
        end_date = start_date + timedelta(days=62)

    query = db.query(AttendanceScheduleException).filter(
        AttendanceScheduleException.exception_date <= end_date,
        or_(
            AttendanceScheduleException.end_date.is_(None),
            AttendanceScheduleException.end_date >= start_date,
        ),
    )
    if user_id is not None:
        query = query.filter(AttendanceScheduleException.user_id == user_id)
    if branch_id is not None:
        query = query.filter(AttendanceScheduleException.branch_id == branch_id)
    if department_id is not None:
        query = query.filter(AttendanceScheduleException.department_id == department_id)

    rows = query.order_by(
        AttendanceScheduleException.exception_date.desc(),
        AttendanceScheduleException.id.desc(),
    ).all()
    rows = [
        row
        for row in rows
        if schedule_exception_occurs_in_range(row, start_date, end_date)
    ]

    items = []
    for row in rows:
        item = _serialize_schedule_exception(db, row)
        occurrence = start_date
        while occurrence <= end_date:
            if schedule_exception_occurs_on(row, occurrence):
                item["occurrence_date"] = occurrence.isoformat()
                break
            occurrence += timedelta(days=1)
        items.append(item)
    return {"exceptions": items, "total": len(items)}


@router.get("/admin/schedule-exceptions/preview")
async def preview_schedule_exception(
    target_date: date = Query(..., description="Date to preview"),
    user_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    is_foreigner: Optional[int] = Query(None, description="1=Khmer, 2=Foreigner"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Show normal weekly schedule vs what an exception would replace."""
    _require_attendance_admin(db, current_user)
    ensure_schedule_exceptions_table(db)

    rep_user = representative_user_for_exception_scope(
        db,
        user_id=user_id,
        branch_id=branch_id,
        department_id=department_id,
        is_foreigner=is_foreigner,
    )
    weekly = get_weekly_day_attendance(db, rep_user, target_date)
    existing = resolve_schedule_exception(db, rep_user, target_date)

    scope = "all_staff"
    if user_id is not None:
        scope = "user"
    elif department_id is not None:
        scope = "department"
    elif branch_id is not None:
        scope = "branch"
    elif is_foreigner is not None:
        scope = "nationality"

    day_names = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday",
    ]
    return {
        "date": target_date.isoformat(),
        "day_name": day_names[target_date.weekday()],
        "scope": scope,
        "is_foreigner": is_foreigner,
        "nationality_label": _nationality_label(is_foreigner),
        "normal_weekly": weekly,
        "existing_exception": (
            _serialize_schedule_exception(db, existing) if existing else None
        ),
    }


@router.post("/admin/schedule-exceptions", status_code=status.HTTP_201_CREATED)
async def create_schedule_exception(
    payload: ScheduleExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    ensure_schedule_exceptions_table(db)

    recurrence_type, end_date = _validate_schedule_exception_recurrence(
        payload.recurrence_type,
        payload.exception_date,
        payload.end_date,
    )

    scopes = [payload.user_id, payload.branch_id, payload.department_id]
    if sum(1 for s in scopes if s is not None) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose only one scope: user, branch, department, or all staff",
        )

    exc_type, sessions = _resolve_exception_sessions_payload(payload)
    title_en, title_km = _bilingual_text_pair(
        payload.title_en,
        payload.title_km,
        fallback=payload.reason,
    )
    reason_en, reason_km = _bilingual_text_pair(
        payload.reason_en,
        payload.reason_km,
        fallback=payload.reason,
    )

    row = AttendanceScheduleException(
        exception_date=payload.exception_date,
        end_date=end_date,
        recurrence_type=recurrence_type,
        user_id=payload.user_id,
        branch_id=payload.branch_id,
        department_id=payload.department_id,
        is_foreigner=payload.is_foreigner if payload.user_id is None else None,
        exception_type=exc_type,
        sessions=sessions,
        reason=reason_en or reason_km,
        title_en=title_en,
        title_km=title_km,
        reason_en=reason_en,
        reason_km=reason_km,
        created_by=int(current_user.id),  # type: ignore[arg-type]
        is_active=1 if payload.is_active else 0,
        self_enrollment_enabled=1 if payload.self_enrollment_enabled else 0,
        allow_outside_workplace=1 if payload.allow_outside_workplace else 0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_schedule_exception(db, row)


@router.put("/admin/schedule-exceptions/{exception_id}")
async def update_schedule_exception(
    exception_id: int,
    payload: ScheduleExceptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    ensure_schedule_exceptions_table(db)

    row = db.query(AttendanceScheduleException).filter(
        AttendanceScheduleException.id == exception_id
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")

    if payload.exception_date is not None:
        row.exception_date = payload.exception_date
    update_data = payload.model_dump(exclude_unset=True)
    if "end_date" in update_data:
        row.end_date = payload.end_date
    if {"user_id", "branch_id", "department_id"} & set(update_data.keys()):
        row.user_id = payload.user_id
        row.branch_id = payload.branch_id
        row.department_id = payload.department_id
    scopes = [row.user_id, row.branch_id, row.department_id]
    if sum(1 for scope in scopes if scope is not None) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose only one scope: user, branch, department, or all staff",
        )
    if "is_foreigner" in update_data:
        row.is_foreigner = payload.is_foreigner
    if row.user_id is not None:
        row.is_foreigner = None
    if payload.reason is not None:
        row.reason = payload.reason.strip() or None
    if payload.is_active is not None:
        row.is_active = 1 if payload.is_active else 0
    if payload.self_enrollment_enabled is not None:
        row.self_enrollment_enabled = (
            1 if payload.self_enrollment_enabled else 0
        )
    if payload.allow_outside_workplace is not None:
        row.allow_outside_workplace = (
            1 if payload.allow_outside_workplace else 0
        )

    recurrence_raw = (
        payload.recurrence_type
        if "recurrence_type" in update_data
        else schedule_exception_recurrence_type(row)
    )
    recurrence_type, normalized_end_date = _validate_schedule_exception_recurrence(
        recurrence_raw or "once",
        row.exception_date,
        row.end_date,
    )
    row.recurrence_type = recurrence_type
    row.end_date = normalized_end_date

    if (
        payload.exception_type is not None
        or payload.preset is not None
        or payload.sessions is not None
    ):
        exc_type, sessions = _resolve_exception_sessions_payload(
            payload,
            existing_type=row.exception_type,
        )
        row.exception_type = exc_type
        row.sessions = sessions

    title_fields = {"title_en", "title_km"}
    if title_fields & set(update_data.keys()):
        row.title_en, row.title_km = _bilingual_text_pair(
            payload.title_en,
            payload.title_km,
            fallback=row.reason,
        )
    elif payload.reason is not None and not (
        getattr(row, "title_en", None) or getattr(row, "title_km", None)
    ):
        row.title_en, row.title_km = _bilingual_text_pair(
            None,
            None,
            fallback=row.reason,
        )

    reason_fields = {"reason_en", "reason_km"}
    if reason_fields & set(update_data.keys()):
        row.reason_en, row.reason_km = _bilingual_text_pair(
            payload.reason_en,
            payload.reason_km,
            fallback=payload.reason,
        )
        row.reason = row.reason_en or row.reason_km
    elif payload.reason is not None:
        row.reason_en, row.reason_km = _bilingual_text_pair(
            None,
            None,
            fallback=row.reason,
        )

    enrollment_count = (
        db.query(AttendanceScheduleExceptionEnrollment)
        .filter(
            AttendanceScheduleExceptionEnrollment.exception_id == row.id
        )
        .count()
    )
    schedule_fields = {
        "exception_date",
        "end_date",
        "recurrence_type",
        "user_id",
        "branch_id",
        "department_id",
        "is_foreigner",
        "exception_type",
        "preset",
        "sessions",
    }
    if enrollment_count and schedule_fields & set(update_data.keys()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This exception already has staff attendance enrollments. Its "
                "dates, audience, and sessions are locked for audit accuracy."
            ),
        )

    db.commit()
    db.refresh(row)
    return _serialize_schedule_exception(db, row)


@router.delete("/admin/schedule-exceptions/{exception_id}")
async def delete_schedule_exception(
    exception_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    ensure_schedule_exceptions_table(db)

    row = db.query(AttendanceScheduleException).filter(
        AttendanceScheduleException.id == exception_id
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")

    enrollment_count = (
        db.query(AttendanceScheduleExceptionEnrollment)
        .filter(
            AttendanceScheduleExceptionEnrollment.exception_id == row.id
        )
        .count()
    )
    if enrollment_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This exception has staff attendance enrollments and cannot be "
                "deleted. Deactivate it to close new enrollment."
            ),
        )

    db.delete(row)
    db.commit()
    return {"success": True, "message": "Schedule exception deleted"}


# -----------------------------------------------------------------------------
# Global Security Settings

@router.get("/security-settings")
async def get_security_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get attendance system security settings for mobile app validation.
    This endpoint provides settings that mobile apps use for client-side security checks.
    """
    try:
        settings = db.query(AttendanceSystemSettings).first()
        if not settings:
            # Return default settings if none configured
            return {
                "id": 1,
                "require_location": True,
                "block_mock_location": True,
                "block_developer_options": False,
                "allowed_ip_ranges": None,
                "allow_early_clock_in_mins": EARLY_CLOCK_IN_MAX_MINUTES,
                "per_session_early_clock_in_mins": None,
                "allow_late_clock_out_mins": None,
                "min_minutes_before_checkout": 30,
                "session_transition_wait_mins": 10,
                "allow_early_leave_mins": 0,
                "allow_makeup_missing_sessions": False,
                "updated_at": None,
                "created_at": datetime.now().isoformat()
            }

        return {
            "id": settings.id,
            "require_location": bool(settings.require_location),
            "block_mock_location": bool(settings.block_mock_location),
            "block_developer_options": bool(settings.block_developer_options),
            "allowed_ip_ranges": settings.allowed_ip_ranges,
            "allow_early_clock_in_mins": _normalize_early_clock_in_mins(
                settings.allow_early_clock_in_mins
            ),
            "per_session_early_clock_in_mins": _coerce_per_session_early_clock_in_list(
                getattr(settings, "per_session_early_clock_in_mins", None)
            ),
            "allow_late_clock_out_mins": settings.allow_late_clock_out_mins,
            "min_minutes_before_checkout": int(30 if getattr(settings, "min_minutes_before_checkout", None) is None else getattr(settings, "min_minutes_before_checkout")),
            "session_transition_wait_mins": max(0, min(60, int(10 if getattr(settings, "session_transition_wait_mins", None) is None else getattr(settings, "session_transition_wait_mins")))),
            "allow_early_leave_mins": int(0 if getattr(settings, "allow_early_leave_mins", None) is None else getattr(settings, "allow_early_leave_mins")),
            "allow_makeup_missing_sessions": bool(getattr(settings, "allow_makeup_missing_sessions", False)),
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,  # type: ignore
            "created_at": settings.created_at.isoformat() if settings.created_at else None  # type: ignore
        }

    except Exception as e:
        logger.error(f"Error fetching security settings: {e}")
        # Return safe defaults on error
        return {
            "id": 1,
            "require_location": True,
            "block_mock_location": True,
            "block_developer_options": False,
            "allowed_ip_ranges": None,
            "allow_early_clock_in_mins": EARLY_CLOCK_IN_MAX_MINUTES,
            "per_session_early_clock_in_mins": None,
            "allow_late_clock_out_mins": None,  # NULL = unlimited
            "min_minutes_before_checkout": 30,
            "session_transition_wait_mins": 10,
            "allow_early_leave_mins": 0,
            "allow_makeup_missing_sessions": False,
            "updated_at": None,
            "created_at": datetime.now().isoformat()
        }


# -----------------------------------------------------------------------------

@router.get("/admin/settings", response_model=SystemSettingsResponse)
async def get_system_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get global system security settings.
    Creates default settings if they don't exist.
    """
    _require_attendance_admin(db, current_user)

    settings = db.query(AttendanceSystemSettings).first()
    if not settings:
        # Create with sensible defaults (early clock-in capped at 0–4h via admin UI)
        settings = AttendanceSystemSettings(
            require_location=True,
            block_mock_location=True,
            block_developer_options=False,
            allow_early_clock_in_mins=30,
            per_session_early_clock_in_mins=[60, 30],
            allow_late_clock_out_mins=None,   # NULL = allow all late clock-outs
            min_minutes_before_checkout=30,
            session_transition_wait_mins=10,
            allow_early_leave_mins=0,
            allow_makeup_missing_sessions=False,
            late_grace_minutes=15,  # Default 15 minutes grace period
            notify_enable_before=True,
            notify_minutes_before=[10, 5],
            notify_enable_after=True,
            notify_minutes_after=[10, 30],
            notify_enable_before_checkout=True,
            notify_minutes_before_checkout=[0],
            notify_enable_after_checkout=True,
            notify_minutes_after_checkout=[5]
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return _system_settings_to_response(settings)

@router.put("/admin/settings", response_model=SystemSettingsResponse)
async def update_system_settings(
    request: UpdateSystemSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Update global system security settings.
    """
    _require_attendance_admin(db, current_user)
         
    settings = db.query(AttendanceSystemSettings).first()
    if not settings:
        settings = AttendanceSystemSettings()
        db.add(settings)
    
    # Update only fields explicitly sent (including explicit nulls).
    payload = request.dict(exclude_unset=True)
    for key, value in payload.items():
        if key == "allow_early_leave_mins" and value is None:
            value = 0
        if key == "allow_makeup_missing_sessions" and value is None:
            value = False
        if key == "min_minutes_before_checkout" and value is None:
            value = 30
        if key == "session_transition_wait_mins" and value is None:
            value = 10
        if key == "allow_early_clock_in_mins":
            value = _normalize_early_clock_in_mins(value)
        if key == "per_session_early_clock_in_mins":
            value = _coerce_per_session_early_clock_in_list(value)
        setattr(settings, key, value)

    # Always persist early clock-in within 0..240 (legacy NULL → max).
    settings.allow_early_clock_in_mins = _normalize_early_clock_in_mins(
        settings.allow_early_clock_in_mins
    )

    settings.updated_at = datetime.now(CAMBODIA_TZ)
    db.commit()
    db.refresh(settings)

    return _system_settings_to_response(settings)


@router.get(
    "/admin/check-in-security-events",
    response_model=CheckInSecurityEventListResponse,
)
async def list_check_in_security_events(
    limit: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    start_date: Optional[date] = Query(
        None, description="Inclusive start date (Cambodia calendar day)"
    ),
    end_date: Optional[date] = Query(
        None, description="Inclusive end date (Cambodia calendar day)"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """
    Audit log for check-in rate limits and IP-pattern signals (shared school NAT, multi-IP / VPN).
    Attendance administrators can view.
    Prefer passing start_date/end_date (e.g. current month) to avoid loading the full history.
    """
    _require_attendance_admin(db, current_user)

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date",
        )

    # School operates in Cambodia time (UTC+7); bound the day in that zone.
    cambodia_tz = timezone(timedelta(hours=7))
    q = db.query(CheckInSecurityEvent).order_by(CheckInSecurityEvent.created_at.desc())
    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=cambodia_tz)
        q = q.filter(CheckInSecurityEvent.created_at >= start_dt)
    if end_date:
        end_exclusive = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=cambodia_tz
        )
        q = q.filter(CheckInSecurityEvent.created_at < end_exclusive)
    if severity:
        q = q.filter(CheckInSecurityEvent.severity == severity)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        matching_user_ids = db.query(User.id).filter(
            or_(
                User.username.ilike(pattern),
                User.eName.ilike(pattern),
                User.kName.ilike(pattern),
                User.uniqueId.ilike(pattern),
            )
        )
        search_conditions = [
            CheckInSecurityEvent.event_type.ilike(pattern),
            CheckInSecurityEvent.severity.ilike(pattern),
            CheckInSecurityEvent.message.ilike(pattern),
            CheckInSecurityEvent.client_ip.ilike(pattern),
            CheckInSecurityEvent.detail_json.ilike(pattern),
            CheckInSecurityEvent.user_agent.ilike(pattern),
            CheckInSecurityEvent.user_id.in_(matching_user_ids),
        ]
        if normalized_search.isdigit():
            numeric_search = int(normalized_search)
            search_conditions.extend(
                [
                    CheckInSecurityEvent.id == numeric_search,
                    CheckInSecurityEvent.user_id == numeric_search,
                ]
            )
        q = q.filter(or_(*search_conditions))
    rows = q.limit(limit).all()

    user_ids = {r.user_id for r in rows if r.user_id}
    id_to_username: Dict[int, str] = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            id_to_username[int(u.id)] = str(u.username)

    events: List[CheckInSecurityEventItem] = []
    for r in rows:
        events.append(
            CheckInSecurityEventItem(
                id=int(r.id),
                created_at=r.created_at,
                user_id=r.user_id,
                username=id_to_username.get(r.user_id) if r.user_id else None,
                client_ip=r.client_ip,
                event_type=r.event_type,
                severity=r.severity,
                message=r.message,
                detail_json=r.detail_json,
                user_agent=r.user_agent,
            )
        )
    return CheckInSecurityEventListResponse(
        events=events,
        can_delete=_can_delete_check_in_security_events(db, current_user),
    )


@router.delete("/admin/check-in-security-events/{event_id}")
async def delete_check_in_security_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Permanently delete one security event and retain an admin audit record."""

    _require_check_in_security_event_delete_permission(db, current_user)
    event = (
        db.query(CheckInSecurityEvent)
        .filter(CheckInSecurityEvent.id == int(event_id))
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security event not found",
        )

    audit_detail = (
        f"Deleted check-in security event #{int(event.id)} "
        f"({event.event_type}, user_id={event.user_id})"
    )
    try:
        db.delete(event)
        db.execute(
            text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """),
            {
                "user_id": int(current_user.id),
                "action": "CHECK_IN_SECURITY_EVENT_DELETED",
                "details": audit_detail,
                "timestamp": datetime.utcnow(),
            },
        )
        db.commit()
        return {"success": True, "deleted_count": 1}
    except Exception:
        db.rollback()
        logger.exception(
            "Could not delete check-in security event %s",
            event_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete the security event",
        )


@router.delete("/admin/check-in-security-events")
async def delete_check_in_security_events_in_range(
    start_date: date = Query(
        ..., description="Inclusive start date (Cambodia calendar day)"
    ),
    end_date: date = Query(
        ..., description="Inclusive end date (Cambodia calendar day)"
    ),
    severity: Optional[str] = Query(None, pattern=r"^(info|warning|critical)$"),
    search: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Delete all matching events in an explicit date range with audit trail."""

    _require_check_in_security_event_delete_permission(db, current_user)
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date",
        )

    cambodia_tz = timezone(timedelta(hours=7))
    start_dt = datetime.combine(start_date, time.min, tzinfo=cambodia_tz)
    end_exclusive = datetime.combine(
        end_date + timedelta(days=1),
        time.min,
        tzinfo=cambodia_tz,
    )
    query = db.query(CheckInSecurityEvent).filter(
        CheckInSecurityEvent.created_at >= start_dt,
        CheckInSecurityEvent.created_at < end_exclusive,
    )
    if severity:
        query = query.filter(CheckInSecurityEvent.severity == severity)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        matching_user_ids = db.query(User.id).filter(
            or_(
                User.username.ilike(pattern),
                User.eName.ilike(pattern),
                User.kName.ilike(pattern),
                User.uniqueId.ilike(pattern),
            )
        )
        search_conditions = [
            CheckInSecurityEvent.event_type.ilike(pattern),
            CheckInSecurityEvent.severity.ilike(pattern),
            CheckInSecurityEvent.message.ilike(pattern),
            CheckInSecurityEvent.client_ip.ilike(pattern),
            CheckInSecurityEvent.detail_json.ilike(pattern),
            CheckInSecurityEvent.user_agent.ilike(pattern),
            CheckInSecurityEvent.user_id.in_(matching_user_ids),
        ]
        if normalized_search.isdigit():
            numeric_search = int(normalized_search)
            search_conditions.extend(
                [
                    CheckInSecurityEvent.id == numeric_search,
                    CheckInSecurityEvent.user_id == numeric_search,
                ]
            )
        query = query.filter(or_(*search_conditions))

    try:
        deleted_count = int(query.delete(synchronize_session=False) or 0)
        db.execute(
            text("""
                INSERT INTO admin_logs (user_id, action, details, timestamp)
                VALUES (:user_id, :action, :details, :timestamp)
            """),
            {
                "user_id": int(current_user.id),
                "action": "CHECK_IN_SECURITY_EVENTS_RANGE_DELETED",
                "details": (
                    f"Deleted {deleted_count} check-in security event(s) from "
                    f"{start_date.isoformat()} through {end_date.isoformat()}"
                    + (f" with severity={severity}" if severity else "")
                    + (
                        f" matching search={normalized_search!r}"
                        if normalized_search
                        else ""
                    )
                ),
                "timestamp": datetime.utcnow(),
            },
        )
        db.commit()
        return {"success": True, "deleted_count": deleted_count}
    except Exception:
        db.rollback()
        logger.exception(
            "Could not delete check-in security events from %s through %s",
            start_date,
            end_date,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete security events for the selected period",
        )


@router.post("/security-events/client-report")
async def report_client_security_events(
    request: ClientSecurityEventReportRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Persist attendance security checks that were blocked on the device.

    The request accepts only a small allow-list of event types. Messages and
    severities are chosen by the API so a client cannot inject arbitrary audit
    text. These reports never create or update an attendance record.
    """
    client_ip = await enforce_checkin_rate_limit(
        http_request,
        db,
        int(current_user.id),
    )
    raw_user_agent = http_request.headers.get("User-Agent")
    user_agent = raw_user_agent[:500] if raw_user_agent else None
    definitions: Dict[str, Tuple[str, str]] = {
        "mock_location": (
            "critical",
            "Attendance was blocked on the device because mock or fake GPS was detected.",
        ),
        "poor_gps_accuracy": (
            "warning",
            "Attendance was blocked on the device because GPS accuracy was insufficient.",
        ),
        "location_required": (
            "warning",
            "Attendance was blocked on the device because a location could not be obtained.",
        ),
        "developer_options": (
            "critical",
            "Attendance was blocked on the device because developer or emulator signals were detected.",
        ),
        "compromised_device": (
            "critical",
            "Attendance was blocked on a device that appears rooted or jailbroken.",
        ),
        "debugger_attached": (
            "critical",
            "Attendance was blocked because a debugger was attached to the app.",
        ),
        "vpn_active": (
            "warning",
            "Attendance was blocked on the device because a VPN was active.",
        ),
        "device_verification_unavailable": (
            "critical",
            "Attendance was blocked because device security could not be verified.",
        ),
        "invalid_ip": (
            "critical",
            "Attendance was blocked on the device because the network was not authorized.",
        ),
    }

    for event in request.events:
        event_type = str(event.event_type)
        severity, message = definitions[event_type]
        detail: Optional[Dict[str, Any]] = None
        if event.gps_accuracy_meters is not None:
            detail = {
                "accuracy_meters": round(float(event.gps_accuracy_meters), 2),
                "source": "mobile_preflight",
            }
        else:
            detail = {"source": "mobile_preflight"}
        record_checkin_security_event(
            db,
            user_id=int(current_user.id),
            client_ip=client_ip,
            event_type=event_type,
            severity=severity,
            message=message,
            detail=detail,
            user_agent=user_agent,
        )

    return {"success": True, "accepted": len(request.events)}


@router.post("/support-report")
async def report_attendance_problem(
    report: AttendanceProblemReportRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """Send an employee-requested attendance diagnostic to Telegram.

    The issue and screen are allow-listed. The app never sends coordinates,
    tokens, passwords, or arbitrary Telegram markup through this endpoint.
    """
    client_ip = await enforce_attendance_support_report_rate_limit(
        http_request,
        db,
        int(current_user.id),
    )
    settings = db.query(TelegramAttendanceSettings).first()
    if not settings or not settings.bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attendance support reporting is not configured.",
        )
    support_chat_id = resolve_attendance_notification_chat_id(
        settings,
        db=db,
        branch_id=getattr(current_user, "workplace", None),
    )
    if not support_chat_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attendance support reporting has no Attendance destination.",
        )

    issue_labels: Dict[str, str] = {
        "stale_gps": "Location reading is outdated",
        "device_time_incorrect": "Phone date or time is incorrect",
        "poor_gps_accuracy": "GPS signal is too weak",
        "missing_gps_evidence": "Fresh GPS evidence is missing",
        "location_required": "Location is unavailable",
        "mock_location": "Mock or fake GPS was detected",
        "outside_workplace": "Outside an allowed workplace",
        "unauthorized_branch": "Branch is not allowed",
        "unauthorized_network": "Network is not allowed",
        "location_anomaly": "Unusual location movement",
        "device_security": "Device security could not be verified",
        "developer_options": "Developer or emulator signal detected",
        "compromised_device": "Modified device detected",
        "debugger_attached": "Debugger detected",
        "vpn_active": "VPN detected",
        "schedule": "Attendance schedule problem",
        "server_time": "Official time could not be verified",
        "server_error": "Attendance server error",
        "unknown": "Unclassified attendance problem",
    }
    technical_message = (report.technical_message or "").strip()[:500] or None
    app_version = (http_request.headers.get("X-App-Version") or "").strip()[:50]
    device_type = (http_request.headers.get("X-Device-Type") or "").strip()[:50]
    user_agent = (http_request.headers.get("User-Agent") or "").strip()[:500]

    record_checkin_security_event(
        db,
        user_id=int(current_user.id),
        client_ip=client_ip,
        event_type="employee_problem_report",
        severity="info",
        message=f"Employee reported attendance problem: {report.issue_code}.",
        detail={
            "issue_code": report.issue_code,
            "surface": report.surface,
            "app_version": app_version or None,
            "device_type": device_type or None,
        },
        user_agent=user_agent or None,
    )

    sent = await TelegramNotificationService.send_attendance_problem_report(
        bot_token=settings.bot_token,
        chat_id=support_chat_id,
        employee_name=(
            current_user.eName
            or current_user.kName
            or current_user.username
            or f"User #{current_user.id}"
        ),
        username=str(current_user.username or "unknown"),
        user_id=int(current_user.id),
        issue_label=issue_labels[report.issue_code],
        issue_code=report.issue_code,
        surface=report.surface,
        technical_message=technical_message,
        app_version=app_version or None,
        device_type=device_type or None,
    )
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The attendance problem report could not be delivered.",
        )
    return {"success": True}


def _serialize_attendance_audience_preset(
    db: Session,
    preset: AttendanceAudiencePreset,
    *,
    branch_names: Dict[int, str],
    department_names: Dict[int, str],
) -> Dict[str, Any]:
    employee_ids = _attendance_audience_employee_ids(preset)
    preset_type = str(preset.preset_type)
    query = db.query(func.count(User.id)).filter(User.status == 1)
    if preset_type == "employees":
        resolved_count = (
            int(query.filter(User.id.in_(employee_ids)).scalar() or 0)
            if employee_ids
            else 0
        )
        missing_count = max(0, len(employee_ids) - resolved_count)
    else:
        if preset.branch_id is not None:
            query = query.filter(User.workplace == int(preset.branch_id))
        if preset.department_id is not None:
            query = query.filter(User.departmentId == int(preset.department_id))
        if preset.is_foreigner is not None:
            query = query.filter(User.isForeigner == int(preset.is_foreigner))
        resolved_count = int(query.scalar() or 0)
        missing_count = 0

    return {
        "id": int(preset.id),
        "name": str(preset.name),
        "preset_type": preset_type,
        "branch_id": preset.branch_id,
        "branch_name": (
            branch_names.get(int(preset.branch_id))
            if preset.branch_id is not None
            else None
        ),
        "department_id": preset.department_id,
        "department_name": (
            department_names.get(int(preset.department_id))
            if preset.department_id is not None
            else None
        ),
        "is_foreigner": preset.is_foreigner,
        "employee_ids": employee_ids,
        "saved_count": len(employee_ids),
        "resolved_count": resolved_count,
        "missing_count": missing_count,
        "created_by": int(preset.created_by),
        "created_at": preset.created_at.isoformat() if preset.created_at else None,
        "updated_at": preset.updated_at.isoformat() if preset.updated_at else None,
    }


@router.get("/admin/audience-presets")
async def list_attendance_audience_presets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    _ensure_attendance_audience_presets_table(db)
    presets = (
        db.query(AttendanceAudiencePreset)
        .order_by(
            AttendanceAudiencePreset.updated_at.desc(),
            AttendanceAudiencePreset.id.desc(),
        )
        .all()
    )
    branch_ids = {
        int(row.branch_id) for row in presets if row.branch_id is not None
    }
    department_ids = {
        int(row.department_id)
        for row in presets
        if row.department_id is not None
    }
    branch_names = {
        int(branch.id): str(branch.branch_name)
        for branch in (
            db.query(Branch).filter(Branch.id.in_(branch_ids)).all()
            if branch_ids
            else []
        )
    }
    department_names = {
        int(department.id): str(department.department)
        for department in (
            db.query(Department).filter(Department.id.in_(department_ids)).all()
            if department_ids
            else []
        )
    }
    return {
        "presets": [
            _serialize_attendance_audience_preset(
                db,
                preset,
                branch_names=branch_names,
                department_names=department_names,
            )
            for preset in presets
        ]
    }


@router.post("/admin/audience-presets", status_code=status.HTTP_201_CREATED)
async def create_attendance_audience_preset(
    payload: AttendanceAudiencePresetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    _ensure_attendance_audience_presets_table(db)
    name = payload.name.strip()
    if not name or len(name) > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preset name must contain 1 to 120 characters",
        )
    preset_type = payload.preset_type.strip().lower()
    if preset_type not in {"filters", "employees"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="preset_type must be filters or employees",
        )
    if payload.is_foreigner not in {None, 1, 2}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="is_foreigner must be 1, 2, or null",
        )
    employee_ids = sorted(
        {int(value) for value in (payload.employee_ids or []) if int(value) > 0}
    )
    if len(employee_ids) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A fixed group can contain at most 500 employees",
        )
    if preset_type == "employees" and not employee_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose at least one employee for a fixed group",
        )
    if preset_type == "filters":
        employee_ids = []

    existing = (
        db.query(AttendanceAudiencePreset)
        .filter(
            AttendanceAudiencePreset.created_by == int(current_user.id),
            func.lower(AttendanceAudiencePreset.name) == name.lower(),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an attendance group with this name",
        )

    preset = AttendanceAudiencePreset(
        name=name,
        preset_type=preset_type,
        branch_id=payload.branch_id if preset_type == "filters" else None,
        department_id=(
            payload.department_id if preset_type == "filters" else None
        ),
        is_foreigner=(
            payload.is_foreigner if preset_type == "filters" else None
        ),
        employee_ids_json=json.dumps(employee_ids),
        created_by=int(current_user.id),
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    branch_names: Dict[int, str] = {}
    department_names: Dict[int, str] = {}
    if preset.branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == preset.branch_id).first()
        if branch is not None:
            branch_names[int(branch.id)] = str(branch.branch_name)
    if preset.department_id is not None:
        department = (
            db.query(Department)
            .filter(Department.id == preset.department_id)
            .first()
        )
        if department is not None:
            department_names[int(department.id)] = str(department.department)
    return _serialize_attendance_audience_preset(
        db,
        preset,
        branch_names=branch_names,
        department_names=department_names,
    )


@router.delete("/admin/audience-presets/{preset_id}")
async def delete_attendance_audience_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    _require_attendance_admin(db, current_user)
    _ensure_attendance_audience_presets_table(db)
    preset = (
        db.query(AttendanceAudiencePreset)
        .filter(AttendanceAudiencePreset.id == preset_id)
        .first()
    )
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance group not found",
        )
    db.delete(preset)
    db.commit()
    return {"success": True}


@router.get("/admin/users-schedules", response_model=UserScheduleListResponse)
async def get_users_with_schedules(
    branch_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    is_foreigner: Optional[int] = Query(None, description="1=Khmer, 2=Foreigner"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get paginated list of users with their effective schedule status.
    """
    _require_attendance_admin(db, current_user)
    try:
        # 1. Build Query for Users
        query = db.query(User).filter(User.status == 1)  # type: ignore # active users only

        if branch_id:
            query = query.filter(User.workplace == branch_id)  # type: ignore

        if department_id:
            query = query.filter(User.departmentId == department_id)  # type: ignore

        if is_foreigner is not None:
            query = query.filter(User.isForeigner == is_foreigner)  # type: ignore

        if user_ids:
            parsed_user_ids = sorted(
                {
                    int(value.strip())
                    for value in user_ids.split(",")
                    if value.strip().isdigit() and int(value.strip()) > 0
                }
            )
            if len(parsed_user_ids) > 500:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At most 500 user IDs can be requested",
                )
            if not parsed_user_ids:
                return UserScheduleListResponse(
                    users=[], total=0, page=page, limit=limit, total_pages=0
                )
            query = query.filter(User.id.in_(parsed_user_ids))

        if search:
            search_term = f"%{search}%"
            search_conditions = [
                User.eName.like(search_term),
                User.kName.like(search_term),
                User.username.like(search_term),
                User.email.like(search_term),
            ]
            normalized_search = search.strip()
            if normalized_search.isdigit():
                search_conditions.append(User.id == int(normalized_search))
            query = query.filter(
                or_(*search_conditions)
            )

        # 2. Pagination
        total = query.count()
        users = query.offset((page - 1) * limit).limit(limit).all()

        target_date = date.today()
        default_schedule = _get_default_fallback_schedule(db)
        candidates = (
            db.query(AttendanceSchedule)
            .filter(
                AttendanceSchedule.is_active == 1,
                AttendanceSchedule.effective_date <= target_date,
            )
            .order_by(AttendanceSchedule.effective_date.desc(), AttendanceSchedule.id.desc())
            .all()
        )

        user_ids = [int(u.id) for u in users]  # type: ignore
        assignment_by_user: Dict[int, AttendanceUserAssignment] = {}
        if user_ids:
            assignment_rows = (
                db.query(AttendanceUserAssignment)
                .filter(
                    AttendanceUserAssignment.user_id.in_(user_ids),
                    AttendanceUserAssignment.start_date <= target_date,
                    or_(
                        AttendanceUserAssignment.end_date.is_(None),
                        AttendanceUserAssignment.end_date >= target_date,
                    ),
                )
                .order_by(
                    AttendanceUserAssignment.user_id,
                    AttendanceUserAssignment.start_date.desc(),
                    AttendanceUserAssignment.id.desc(),
                )
                .all()
            )
            for a in assignment_rows:
                uid = int(a.user_id)  # type: ignore
                if uid not in assignment_by_user:
                    assignment_by_user[uid] = a

        workplace_ids = list(
            {int(u.workplace) for u in users if u.workplace}  # type: ignore
        )
        branch_name_by_id: Dict[int, str] = {}
        if workplace_ids:
            for b in db.query(Branch).filter(Branch.id.in_(workplace_ids)).all():
                branch_name_by_id[int(b.id)] = str(b.branch_name)  # type: ignore

        dept_ids = list(
            {int(u.departmentId) for u in users if u.departmentId}  # type: ignore
        )
        dept_name_by_id: Dict[int, str] = {}
        if dept_ids:
            for d in db.query(Department).filter(Department.id.in_(dept_ids)).all():
                dept_name_by_id[int(d.id)] = str(d.department)  # type: ignore

        avatar_by_user: Dict[int, str] = {}
        if user_ids:
            avatar_stmt = text(
                """
                SELECT ur.user_id, ur.avatar
                FROM users_resource ur
                WHERE ur.user_id IN :uids
                  AND ur.user_type IN ('employee', 'teacher')
                  AND ur.avatar IS NOT NULL
                  AND ur.avatar != ''
                ORDER BY ur.user_id, ur.id DESC
                """
            ).bindparams(bindparam("uids", expanding=True))
            avatar_rows = db.execute(avatar_stmt, {"uids": user_ids}).fetchall()
            for row in avatar_rows:
                uid = int(row[0])
                if uid not in avatar_by_user:
                    avatar_by_user[uid] = str(row[1])

        allowed_by_user: Dict[int, List[int]] = defaultdict(list)
        if user_ids:
            ab_stmt = text(
                "SELECT user_id, branch_id FROM attendance__allowed_branches "
                "WHERE user_id IN :uids"
            ).bindparams(bindparam("uids", expanding=True))
            rows = db.execute(ab_stmt, {"uids": user_ids}).fetchall()
            for row in rows:
                allowed_by_user[int(row[0])].append(int(row[1]))

        # 3. Resolve schedule + assemble rows (no per-user schedule table scans)
        user_list = []
        for user in users:
            uid = int(user.id)  # type: ignore
            schedule, source = _resolve_effective_schedule_from_candidates(
                user,
                candidates,
                assignment_by_user.get(uid),
                default_global_id=(int(default_schedule.id) if default_schedule else None),  # type: ignore[arg-type]
            )

            branch_name = None
            if user.workplace:  # type: ignore
                branch_name = branch_name_by_id.get(int(user.workplace))  # type: ignore

            dept_name = None
            if user.departmentId:  # type: ignore
                dept_name = dept_name_by_id.get(int(user.departmentId))  # type: ignore

            allowed_branches = allowed_by_user.get(uid, [])

            info = UserScheduleInfo(
                user_id=uid,
                user_name=f"{user.eName or ''} {user.kName or ''}".strip()
                or str(user.username),  # type: ignore
                avatar=avatar_by_user.get(uid),
                branch_id=user.workplace,  # type: ignore
                branch_name=branch_name,
                department_id=user.departmentId,  # type: ignore
                department_name=dept_name,
                is_active=bool(user.status == 1),
                has_schedule=schedule is not None,
                schedule_name=schedule.name if schedule else None,  # type: ignore
                schedule_type=schedule.type if schedule else None,  # type: ignore
                schedule_source=source,
                schedule_id=schedule.id if schedule else None,  # type: ignore
                schedule_is_default=(
                    bool(default_schedule is not None and schedule is not None and int(schedule.id) == int(default_schedule.id))  # type: ignore[arg-type]
                ),
                schedule_effective_date=schedule.effective_date if schedule else None,  # type: ignore
                allowed_branches=allowed_branches,
            )
            user_list.append(info)

        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return UserScheduleListResponse(
            users=user_list,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users schedules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch users: {str(e)}"
        )


@router.get("/admin/users/{user_id}/schedule")
async def get_user_effective_schedule(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get the effective schedule for a specific user.
    Useful for admins to debug or verify what schedule a user is on.
    """
    _require_attendance_admin(db, current_user)
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    schedule = get_effective_schedule(db, target_user)
    
    if not schedule:
        return {
            "user_id": user_id,
            "user_name": target_user.username,
            "has_schedule": False,
            "message": "No effective schedule found (Global default or missing)"
        }

    today = datetime.now(CAMBODIA_TZ).date()
    source = None
    
    # Check explicit assignment
    if schedule:
        assignment = db.query(AttendanceUserAssignment).filter(
            AttendanceUserAssignment.user_id == user_id,
            AttendanceUserAssignment.schedule_id == schedule.id
        ).first()

        if assignment: source = "assignment"
        elif schedule.user_id == target_user.id: source = "user"  # type: ignore
        elif schedule.department_id: source = "department"  # type: ignore
        elif schedule.branch_id: source = "branch"  # type: ignore
        else: source = "global"

    return {
        "user_id": user_id,
        "user_name": target_user.username,
        "has_schedule": True,
        "schedule": {
            "id": schedule.id,
            "name": schedule.name,
            "type": schedule.type,
            "weekly_config": schedule.weekly_config,
            "source": source
        }
    }


@router.post("/admin/schedules/assign-user")
async def assign_schedule_to_user(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Assign a specific schedule to a user (Overrides defaults).
    Body: {"user_id": int, "schedule_id": int}
    """
    _require_attendance_admin(db, current_user)
    try:
        user_id = int(data.get("user_id"))
        schedule_id = int(data.get("schedule_id"))

        if not user_id or not schedule_id:
            raise HTTPException(status_code=400, detail="Missing user_id or schedule_id")

        # Check if schedule exists
        schedule = db.query(AttendanceSchedule).filter(AttendanceSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        # Get ANY active assignment for this user (regardless of schedule)
        existing_active = db.query(AttendanceUserAssignment).filter(
            AttendanceUserAssignment.user_id == user_id,
            AttendanceUserAssignment.end_date.is_(None)
        ).first()

        # Check if already assigned to THIS specific schedule
        if existing_active and existing_active.schedule_id == schedule_id:
            db.commit()  # Ensure session is clean
            return {
                "success": True,
                "message": "User is already assigned to this schedule",
                "unchanged": True
            }

        action = "assigned"
        
        cambodia_today = _get_cambodia_current_date()
        
        if existing_active:
            # Close currently active assignment
            existing_active.end_date = cambodia_today
            existing_active.updated_at = func.now()
            
            # Check if we can reactivate a historical assignment for the target schedule
            existing_same_pair = db.query(AttendanceUserAssignment).filter(
                AttendanceUserAssignment.user_id == user_id,
                AttendanceUserAssignment.schedule_id == schedule_id,
                AttendanceUserAssignment.end_date.isnot(None)
            ).order_by(AttendanceUserAssignment.end_date.desc()).first()
            
            if existing_same_pair:
                # Reactivate: set end_date to NULL
                existing_same_pair.start_date = cambodia_today
                existing_same_pair.end_date = None
                existing_same_pair.assigned_by = current_user.id
                existing_same_pair.updated_at = func.now()
                action = "reactivated"
            else:
                # Create new assignment
                new_assignment = AttendanceUserAssignment(
                    user_id=user_id,
                    schedule_id=schedule_id,
                    assigned_by=current_user.id,
                    start_date=cambodia_today,
                    end_date=None,
                    created_at=func.now()
                )
                db.add(new_assignment)
        else:
            # No active assignment exists, check for historical
            existing_same_pair = db.query(AttendanceUserAssignment).filter(
                AttendanceUserAssignment.user_id == user_id,
                AttendanceUserAssignment.schedule_id == schedule_id,
                AttendanceUserAssignment.end_date.isnot(None)
            ).order_by(AttendanceUserAssignment.end_date.desc()).first()
            
            if existing_same_pair:
                # Reactivate
                existing_same_pair.start_date = cambodia_today
                existing_same_pair.end_date = None
                existing_same_pair.assigned_by = current_user.id
                existing_same_pair.updated_at = func.now()
                action = "reactivated"
            else:
                # Create new
                new_assignment = AttendanceUserAssignment(
                    user_id=user_id,
                    schedule_id=schedule_id,
                    assigned_by=current_user.id,
                    start_date=cambodia_today,
                    end_date=None,
                    created_at=func.now()
                )
                db.add(new_assignment)

        # Flush to ensure changes are written
        db.flush()
        db.commit()

        return {
            "success": True,
            "message": f"Schedule {action} successfully",
            "action": action,
            "schedule_name": schedule.name,
            "schedule_id": schedule_id,
            "user_id": user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        logger.error(f"Assign schedule error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/schedules/assign-users-bulk")
async def assign_schedule_to_users_bulk(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Assign a specific schedule to MULTIPLE users at once.
    Body: {"user_ids": [1, 2, ...], "schedule_id": int}
    """
    _require_attendance_admin(db, current_user)
    try:
        user_ids = data.get("user_ids")
        schedule_id = data.get("schedule_id")

        if not user_ids or not isinstance(user_ids, list) or not schedule_id:
            raise HTTPException(status_code=400, detail="Missing user_ids list or schedule_id")

        # Check if schedule exists
        schedule = db.query(AttendanceSchedule).filter(AttendanceSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        # Get Cambodia current date once for all users
        cambodia_today = _get_cambodia_current_date()

        # Process each user
        updated_count = 0
        created_count = 0
        unchanged_count = 0

        for uid in user_ids:
            # Check if active assignment exists
            existing_active = db.query(AttendanceUserAssignment).filter(
                AttendanceUserAssignment.user_id == uid,
                AttendanceUserAssignment.end_date.is_(None)
            ).first()

            if existing_active and existing_active.schedule_id == schedule_id:
                unchanged_count += 1
                continue

            if existing_active:
                existing_active.end_date = cambodia_today
                existing_active.updated_at = func.now()
                updated_count += 1

            existing_same_pair = db.query(AttendanceUserAssignment).filter(
                AttendanceUserAssignment.user_id == uid,
                AttendanceUserAssignment.schedule_id == schedule_id,
                AttendanceUserAssignment.end_date.isnot(None)
            ).first()
            if existing_same_pair:
                existing_same_pair.start_date = cambodia_today
                existing_same_pair.end_date = None
                existing_same_pair.assigned_by = current_user.id
                existing_same_pair.updated_at = func.now()
            else:
                new_assignment = AttendanceUserAssignment(
                    user_id=uid,
                    schedule_id=schedule_id,
                    assigned_by=current_user.id,
                    start_date=cambodia_today,
                    end_date=None,
                    created_at=func.now()
                )
                db.add(new_assignment)
                created_count += 1


        db.commit()
        return {
            "success": True,
            "message": f"Assigned schedule to {created_count + updated_count + unchanged_count} users",
            "details": {"created": created_count, "updated": updated_count, "unchanged": unchanged_count}
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/schedules/unassign-user/{user_id}")
async def remove_user_schedule_assignment(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Remove explicit schedule assignment for a user.
    """
    _require_attendance_admin(db, current_user)
    try:
        default_schedule = _get_default_fallback_schedule(db)
        if not default_schedule:
            default_schedule = _ensure_default_fallback_schedule(db)

        active_assignments = db.query(AttendanceUserAssignment).filter(
            AttendanceUserAssignment.user_id == user_id,
            AttendanceUserAssignment.end_date.is_(None)
        ).all()

        if not active_assignments:
            raise HTTPException(status_code=404, detail="No active explicit assignment found for this user")

        # End on previous day so fallback/default applies immediately today.
        end_date_immediate = datetime.now(CAMBODIA_TZ).date() - timedelta(days=1)
        for assignment in active_assignments:
            assignment.end_date = end_date_immediate
            assignment.updated_at = func.now()

        # Explicitly assign default so user always lands on fallback default.
        existing_default_pair = db.query(AttendanceUserAssignment).filter(
            AttendanceUserAssignment.user_id == user_id,
            AttendanceUserAssignment.schedule_id == default_schedule.id,  # type: ignore
        ).first()
        if existing_default_pair:
            existing_default_pair.start_date = datetime.now(CAMBODIA_TZ).date()
            existing_default_pair.end_date = None
            existing_default_pair.assigned_by = current_user.id
            existing_default_pair.updated_at = func.now()
        else:
            db.add(
                AttendanceUserAssignment(
                    user_id=user_id,
                    schedule_id=default_schedule.id,  # type: ignore
                    assigned_by=current_user.id,
                    start_date=datetime.now(CAMBODIA_TZ).date(),
                    end_date=None,
                    created_at=func.now(),
                )
            )
        db.commit()
        return {"success": True, "message": "Assignment removed. User now uses default schedule."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/schedules/unassign-users-bulk")
async def remove_users_schedule_assignment_bulk(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Remove explicit schedule assignment for MULTIPLE users at once.
    Body: {"user_ids": [1, 2, ...]}
    """
    _require_attendance_admin(db, current_user)
    try:
        user_ids = data.get("user_ids")

        if not user_ids or not isinstance(user_ids, list):
            raise HTTPException(status_code=400, detail="Missing user_ids list")

        default_schedule = _get_default_fallback_schedule(db)
        if not default_schedule:
            default_schedule = _ensure_default_fallback_schedule(db)

        deleted_count = 0
        default_applied = 0
        end_date_immediate = datetime.now(CAMBODIA_TZ).date() - timedelta(days=1)
        for uid in user_ids:
            active_assignments = db.query(AttendanceUserAssignment).filter(
                AttendanceUserAssignment.user_id == uid,
                AttendanceUserAssignment.end_date.is_(None)
            ).all()

            if active_assignments:
                for assignment in active_assignments:
                    assignment.end_date = end_date_immediate
                    assignment.updated_at = func.now()
                deleted_count += 1

            existing_default_pair = db.query(AttendanceUserAssignment).filter(
                AttendanceUserAssignment.user_id == uid,
                AttendanceUserAssignment.schedule_id == default_schedule.id,  # type: ignore
            ).first()
            if existing_default_pair:
                existing_default_pair.start_date = datetime.now(CAMBODIA_TZ).date()
                existing_default_pair.end_date = None
                existing_default_pair.assigned_by = current_user.id
                existing_default_pair.updated_at = func.now()
            else:
                db.add(
                    AttendanceUserAssignment(
                        user_id=uid,
                        schedule_id=default_schedule.id,  # type: ignore
                        assigned_by=current_user.id,
                        start_date=datetime.now(CAMBODIA_TZ).date(),
                        end_date=None,
                        created_at=func.now(),
                    )
                )
            default_applied += 1

        db.commit()
        return {
            "success": True, 
            "message": f"Assignments removed for {deleted_count} users and default applied for {default_applied} users.",
            "details": {"deleted": deleted_count, "default_applied": default_applied}
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/users/{user_id}/allowed-branches", response_model=List[int])
async def get_user_allowed_branches(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get the list of extra branches a specific user is authorized to scan at.
    """
    _require_attendance_admin(db, current_user)

    query = text("SELECT branch_id FROM attendance__allowed_branches WHERE user_id = :user_id")
    result = db.execute(query, {"user_id": user_id}).fetchall()
    return [row[0] for row in result]


@router.post("/admin/users/{user_id}/allowed-branches")
async def update_user_allowed_branches(
    user_id: int,
    request_data: UpdateUserAllowedBranchesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Update the list of extra branches a specific user is authorized to scan at.
    """
    _require_attendance_admin(db, current_user)

    try:
        # 1. Clear existing allowed branches for this user
        delete_query = text("DELETE FROM attendance__allowed_branches WHERE user_id = :user_id")
        db.execute(delete_query, {"user_id": user_id})

        # 2. Add new allowed branches
        if request_data.branch_ids:
            insert_query = text("""
                INSERT INTO attendance__allowed_branches (user_id, branch_id)
                VALUES (:user_id, :branch_id)
            """)
            for b_id in request_data.branch_ids:
                db.execute(insert_query, {"user_id": user_id, "branch_id": b_id})
                
        db.commit()
        return {"success": True, "message": "Allowed branches updated successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/allowed-branches-bulk")
async def add_allowed_branches_to_users_bulk(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Add allowed extra branches to MULTIPLE users at once.
    Body: {"user_ids": [1, 2, ...], "branch_ids": [1, 2, ...]}
    Note: This APPENDS to their existing branches (ignores duplicates).
    """
    _require_attendance_admin(db, current_user)

    try:
        user_ids = data.get("user_ids", [])
        branch_ids = data.get("branch_ids", [])

        if not user_ids or not branch_ids or not isinstance(user_ids, list) or not isinstance(branch_ids, list):
            raise HTTPException(status_code=400, detail="Missing or invalid user_ids or branch_ids list")

        added_count = 0
        for uid in user_ids:
            # Get existing branches for user to prevent duplicates
            query = text("SELECT branch_id FROM attendance__allowed_branches WHERE user_id = :user_id")
            result = db.execute(query, {"user_id": uid}).fetchall()
            existing_branches = set(row[0] for row in result)

            insert_query = text("""
                INSERT INTO attendance__allowed_branches (user_id, branch_id)
                VALUES (:user_id, :branch_id)
            """)
            for b_id in branch_ids:
                if b_id not in existing_branches:
                    db.execute(insert_query, {"user_id": uid, "branch_id": b_id})
                    added_count += 1
                
        db.commit()
        return {
            "success": True, 
            "message": f"Successfully added allowed branches ({added_count} new associations).",
            "details": {"added": added_count}
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/unassign-allowed-branches-bulk")
async def remove_allowed_branches_from_users_bulk(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Remove specific allowed branches from MULTIPLE users at once.
    Body: {"user_ids": [1, 2, ...], "branch_ids": [1, 2, ...]}
    If branch_ids is [], it clears ALL allowed branches for those users.
    """
    _require_attendance_admin(db, current_user)

    try:
        user_ids = data.get("user_ids", [])
        branch_ids = data.get("branch_ids", [])

        if not user_ids or not isinstance(user_ids, list):
            raise HTTPException(status_code=400, detail="Missing user_ids list")

        deleted_count = 0
        for uid in user_ids:
            if not branch_ids:
                # Clear all
                del_query = text("DELETE FROM attendance__allowed_branches WHERE user_id = :user_id")
                result = db.execute(del_query, {"user_id": uid})
                deleted_count += result.rowcount
            else:
                # Remove specific branches
                for b_id in branch_ids:
                    del_query = text("DELETE FROM attendance__allowed_branches WHERE user_id = :user_id AND branch_id = :branch_id")
                    result = db.execute(del_query, {"user_id": uid, "branch_id": b_id})
                    deleted_count += result.rowcount
                
        db.commit()
        return {
            "success": True, 
            "message": f"Successfully removed {deleted_count} allowed branch associations.",
            "details": {"deleted": deleted_count}
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/admin/records")
async def get_admin_attendance_records(
    attendance_date: date = Query(..., description="Date to fetch records for (YYYY-MM-DD)"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID (optional)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Admin endpoint: Get all attendance records for a specific date across all branches.
    Returns the most recent activity per record, joined with user info.
    Requires attendance administrator access.
    """
    _require_attendance_admin(db, current_user)

    try:
        params: dict = {"attendance_date": attendance_date.isoformat()}

        branch_filter = ""
        if branch_id:
            branch_filter = "AND u.workplace = :branch_id"
            params["branch_id"] = branch_id

        query = text(f"""
            SELECT
                ar.id, ar.user_id, ar.attendance_date,
                ar.check_in_time, ar.check_out_time,
                ar.status, ar.work_hours, ar.late_reason,
                ar.leave_early_reason, ar.notes,
                ar.session_index, ar.schedule_id, ar.scheduled_start, ar.scheduled_end,
                ar.snapshot_late_grace_minutes, ar.snapshot_allow_early_leave_mins,
                u.eName, u.kName, u.username,
                u.workplace AS branch_id,
                b.branch_name,
                ar.check_in_latitude, ar.check_in_longitude,
                ar.check_out_latitude, ar.check_out_longitude,
                ar.device_info, ar.is_mock_location,
                ar.check_in_branch_id, ar.check_out_branch_id
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            LEFT JOIN branch b ON u.workplace = b.id
            WHERE ar.attendance_date = :attendance_date
            {branch_filter}
            ORDER BY
                GREATEST(
                    COALESCE(ar.check_out_time, '1970-01-01'),
                    COALESCE(ar.check_in_time,  '1970-01-01')
                ) DESC
            LIMIT :limit OFFSET :offset
        """)
        params["limit"] = limit
        params["offset"] = offset

        rows = db.execute(query, params).fetchall()

        # Count total for pagination
        count_query = text(f"""
            SELECT COUNT(*)
            FROM attendance_records ar
            JOIN users u ON ar.user_id = u.id
            WHERE ar.attendance_date = :attendance_date
            {branch_filter}
        """)
        count_params = {"attendance_date": attendance_date.isoformat()}
        if branch_id:
            count_params["branch_id"] = branch_id
        total = db.execute(count_query, count_params).scalar() or 0

        records = []
        for row in rows:
            full_name = ""
            if row[16]:  # eName
                full_name = row[16]
            elif row[17]:  # kName
                full_name = row[17]
            else:
                full_name = row[18] or "Unknown"  # username

            records.append({
                "id": row[0],
                "user_id": row[1],
                "attendance_date": row[2].isoformat() if row[2] else None,
                "check_in_time": row[3].isoformat() if row[3] else None,
                "check_out_time": row[4].isoformat() if row[4] else None,
                "status": row[5] or "present",
                "work_hours": float(row[6]) if row[6] else None,
                "late_reason": row[7],
                "leave_early_reason": row[8],
                "notes": row[9],
                "session_index": row[10],
                "schedule_id": row[11],
                "scheduled_start": row[12],
                "scheduled_end": row[13],
                "snapshot_late_grace_minutes": row[14],
                "snapshot_allow_early_leave_mins": row[15],
                "full_name": full_name,
                "username": row[18],
                "branch_id": row[19],
                "branch_name": row[20],
                "check_in_latitude": float(row[21]) if row[21] else None,
                "check_in_longitude": float(row[22]) if row[22] else None,
                "check_out_latitude": float(row[23]) if row[23] else None,
                "check_out_longitude": float(row[24]) if row[24] else None,
                "device_info": row[25],
                "is_mock_location": bool(row[26]) if row[26] is not None else False,
                "check_in_branch_id": row[27],
                "check_out_branch_id": row[28],
            })

        return {
            "date": attendance_date.isoformat(),
            "records": records,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching admin attendance records: {str(e)}")


@router.get("/admin/report/global", response_model=AdminGlobalReportResponse)
async def get_admin_global_report(
    start_date: date = Query(..., description="Start date for report (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for report (YYYY-MM-DD)"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID (optional)"),
    department_id: Optional[int] = Query(None, description="Filter by department ID (optional)"),
    department_name: Optional[str] = Query(None, description="Filter by department name (optional)"),
    weekdays: Optional[str] = Query(
        None,
        description="Optional comma-separated ISO weekdays (1=Monday, 7=Sunday)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Admin endpoint: Get aggregated attendance report for ALL users within a custom date range.
    Returns metrics like perfect attendance, late counts, and total hours per user.
    """
    _require_attendance_admin(db, current_user)

    try:
        ensure_attendance_processing_rules_table(db)
        selected_weekdays = set(range(1, 8))
        if weekdays is not None:
            try:
                selected_weekdays = {
                    int(value.strip())
                    for value in weekdays.split(",")
                    if value.strip()
                }
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail="weekdays must contain comma-separated numbers from 1 to 7",
                )
            if not selected_weekdays or any(
                value < 1 or value > 7 for value in selected_weekdays
            ):
                raise HTTPException(
                    status_code=422,
                    detail="weekdays must contain at least one value from 1 to 7",
                )

        selected_report_dates = []
        cursor = start_date
        while cursor <= end_date:
            if cursor.isoweekday() in selected_weekdays:
                selected_report_dates.append(cursor)
            cursor += timedelta(days=1)
        selected_report_dates_set = set(selected_report_dates)

        # 1. Start with active users
        params: dict = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        
        branch_filter = ""
        if branch_id:
            branch_filter = "AND u.workplace = :branch_id"
            params["branch_id"] = branch_id
            
        dept_filter = ""
        if department_id:
            dept_filter = "AND u.departmentId = :department_id"
            params["department_id"] = department_id
        elif department_name and department_name.strip():
            dept_filter = "AND LOWER(d.department) = LOWER(:department_name)"
            params["department_name"] = department_name.strip()

        # We first grab all relevant users, then left join their attendance records in that date range.
        # This ensures users with NO attendance still show up with 0s.
        # We also keep departmentId / workplace to allow schedule-based working day calculation.
        attendance_date_filter = ""
        if len(selected_weekdays) < 7:
            attendance_date_filter = "AND ar.attendance_date IN :selected_report_dates"
            params["selected_report_dates"] = selected_report_dates

        query = text(f"""
            SELECT 
                u.id as user_id,                                                     -- 0
                COALESCE(u.eName, u.kName, u.username) as full_name,                -- 1
                COALESCE(d.department, 'Unknown') as department_name,               -- 2
                COALESCE(b.branch_name, 'Unknown') as branch_name,                  -- 3
                COUNT(ar.id) as total_scans,                                        -- 4
                COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) as present_days_raw, -- 5
                COUNT(DISTINCT CASE WHEN ar.status = 'late' THEN ar.attendance_date END) as late_days, -- 6
                COALESCE(SUM(CASE WHEN ar.status = 'absent' AND ar.attendance_date NOT IN (SELECT date FROM holidays) THEN 1 ELSE 0 END), 0) as absent_days_raw, -- 7
                COUNT(DISTINCT CASE WHEN ar.status = 'early_leave' THEN ar.attendance_date END) as early_leave_days, -- 8
                COALESCE(SUM(ar.work_hours), 0.0) as sum_work_hours,                -- 9
                COALESCE(SUM(ar.earned_percentage), 0) as total_earned_percentage,  -- 10
                u.departmentId,                                                     -- 11
                u.workplace,                                                        -- 12
                COALESCE(ur.avatar, '') as avatar,                                  -- 13
                COALESCE(u.gender, '') as gender                                    -- 14
            FROM users u
            LEFT JOIN department d ON u.departmentId = d.id
            LEFT JOIN branch b ON u.workplace = b.id
            LEFT JOIN attendance_records ar 
                ON u.id = ar.user_id 
                AND ar.attendance_date BETWEEN :start_date AND :end_date
                {attendance_date_filter}
            LEFT JOIN (
                SELECT user_id, MIN(avatar) AS avatar
                FROM users_resource
                WHERE avatar IS NOT NULL
                  AND avatar != ''
                  AND user_type IN ('employee', 'teacher')
                GROUP BY user_id
            ) ur ON ur.user_id = u.id
            WHERE u.status = 1
            AND NOT EXISTS (
                SELECT 1
                FROM attendance_processing_rules apr
                WHERE apr.is_enabled = 0
                  AND (
                    (apr.scope_type = 'user' AND apr.scope_id = u.id)
                    OR
                    (apr.scope_type = 'department' AND apr.scope_id = u.departmentId)
                  )
            )
            {branch_filter}
            {dept_filter}
            GROUP BY u.id, full_name, department_name, branch_name, u.departmentId, u.workplace, ur.avatar, u.gender
            ORDER BY department_name, full_name
        """)
        if len(selected_weekdays) < 7:
            query = query.bindparams(
                bindparam("selected_report_dates", expanding=True)
            )

        rows = db.execute(query, params).fetchall()
        user_ids = {int(row[0]) for row in rows}
        users_by_id = {
            int(user.id): user
            for user in db.query(User).filter(User.id.in_(user_ids)).all()
        } if user_ids else {}
        day_info_resolver = _build_report_schedule_context(
            db,
            list(users_by_id.values()),
            start_date,
            end_date,
        )
        grace_minutes = 15
        try:
            settings = db.query(AttendanceSystemSettings).first()
            if settings and getattr(settings, "late_grace_minutes", None) is not None:
                grace_minutes = int(settings.late_grace_minutes)
        except Exception:
            pass
        allow_early_leave_mins = 0
        try:
            settings = db.query(AttendanceSystemSettings).first()
            if settings and getattr(settings, "allow_early_leave_mins", None) is not None:
                allow_early_leave_mins = int(settings.allow_early_leave_mins)
        except Exception:
            pass
        # Preload holidays in range for per-user working-day calculations
        holiday_query = text("""
            SELECT date, name 
            FROM holidays 
            WHERE date BETWEEN :start_date AND :end_date
        """)
        holiday_rows = db.execute(holiday_query, {"start_date": start_date, "end_date": end_date}).fetchall()

        def _norm_date(v):
            """Normalize DB value to date so membership checks work (current_date in set)."""
            if v is None:
                return None
            if isinstance(v, date):
                return v
            if hasattr(v, "date"):
                return v.date()
            s = str(v).strip()[:10]
            return date.fromisoformat(s) if s else None

        holidays_dict = {}
        for row in holiday_rows:
            d = _norm_date(row[0])
            if d is not None:
                holidays_dict[d] = row[1]

        # Per-user set of dates with at least one attendance record (match My Attendance: "has record" = present for that day)
        today_ceiling = datetime.now(CAMBODIA_TZ).date()
        attended_dates_query = text("""
            SELECT user_id, attendance_date, COALESCE(session_index, 0),
                   SUM(CASE WHEN check_in_time IS NOT NULL THEN 1 ELSE 0 END) +
                   SUM(CASE WHEN check_out_time IS NOT NULL THEN 1 ELSE 0 END) AS event_count
            FROM attendance_records
            WHERE attendance_date BETWEEN :start_date AND :end_date
              AND attendance_date <= :today_ceiling
              AND user_id IN :user_ids
            GROUP BY user_id, attendance_date, session_index
        """).bindparams(bindparam("user_ids", expanding=True))
        attended_rows = db.execute(attended_dates_query, {
            "start_date": start_date,
            "end_date": end_date,
            "today_ceiling": today_ceiling,
            "user_ids": list(user_ids),
        }).fetchall()
        user_attended_dates = defaultdict(set)
        user_event_counts = defaultdict(dict)
        user_session_event_counts = defaultdict(lambda: defaultdict(dict))
        for r in attended_rows:
            d = _norm_date(r[1])
            if d is not None:
                user_attended_dates[int(r[0])].add(d)
                event_count = int(r[3] or 0)
                user_event_counts[int(r[0])][d] = (
                    user_event_counts[int(r[0])].get(d, 0) + event_count
                )
                user_session_event_counts[int(r[0])][d][int(r[2] or 0)] = event_count

        # Approved leave (permission) days for everyone in one query — these are
        # excluded from absent and count as excused in the attendance rate.
        all_user_ids = [int(row[0]) for row in rows]
        leave_map_by_user = get_approved_leave_map(db, all_user_ids, start_date, end_date)

        expected_day_cache: Dict[Tuple[int, date], bool] = {}

        def _include_report_session(
            report_user_id: int, report_date: date, session_index: int
        ) -> bool:
            if report_date not in selected_report_dates_set:
                return False
            if report_date in holidays_dict:
                return False
            report_user = users_by_id.get(report_user_id)
            employment_start = _user_employment_start_date(report_user)
            if employment_start and report_date < employment_start:
                return False
            cache_key = (report_user_id, report_date)
            is_expected = expected_day_cache.get(cache_key)
            if is_expected is None:
                is_expected = bool(
                    report_user
                    and day_info_resolver(report_user, report_date).get(
                        "is_active_day"
                    )
                )
                expected_day_cache[cache_key] = is_expected
            if not is_expected:
                return False
            leave_entry = leave_map_by_user.get(report_user_id, {}).get(
                report_date
            )
            if leave_entry and leave_entry.get("full_day"):
                return False
            if session_index > 0 and leave_covers_session(
                leave_entry, session_index
            ):
                return False
            return True

        user_late_hours, user_late_days = _compute_user_late_hours_in_range(
            db,
            user_ids,
            start_date,
            end_date,
            grace_minutes,
            include_session=_include_report_session,
        )
        user_early_leave_hours, user_early_leave_days = (
            _compute_user_early_leave_hours_in_range(
                db,
                user_ids,
                start_date,
                end_date,
                allow_early_leave_mins,
                include_session=_include_report_session,
            )
        )

        user_summaries = []
        global_present_total = 0.0
        global_days_tracked = 0

        for row in rows:
            # row mapping (see SELECT above)
            u_id = int(row[0])
            name = row[1]
            dept = row[2]
            branch = row[3]
            hours = float(row[9] or 0.0)
            avatar = row[13] or None
            gender = row[14] or ''

            # Use same User(id=user_id) as detailed report so get_effective_schedule
            # resolves the same schedule; ensures Individuals list matches detailed screen.
            user_attended_set = user_attended_dates.get(u_id, set())
            # Use same helper as detailed report so list and detail always match.
            expected_working_days, present_days, recalculated_absent, leave_days = _compute_user_attendance_totals(
                db, u_id, start_date, end_date, holidays_dict, user_attended_set,
                leave_by_date=leave_map_by_user.get(u_id),
                db_user=users_by_id.get(u_id),
                day_info_resolver=day_info_resolver,
                attendance_event_counts=user_event_counts.get(u_id, {}),
                attendance_session_event_counts=user_session_event_counts.get(
                    u_id, {}
                ),
                include_date=lambda report_date: report_date
                in selected_report_dates_set,
            )
            total_days = expected_working_days
            approved_leave_days = _approved_leave_days_for_dates(
                leave_map_by_user.get(u_id),
                selected_report_dates_set,
            )
            # Approved leave counts as excused, so it doesn't drag the rate down.
            attendance_rate = (
                round(((present_days + leave_days) / total_days) * 100.0, 1) if total_days > 0 else 0.0
            )
            global_present_total += present_days + leave_days
            global_days_tracked += total_days

            user_summaries.append(
                AdminUserReportSummary(
                    user_id=u_id,
                    user_name=name,
                    department=dept,
                    branch=branch,
                    total_work_hours=round(hours, 2),
                    present_days=float(present_days),
                    absent_days=float(recalculated_absent),
                    late_days=user_late_days.get(u_id, 0),
                    late_hours=user_late_hours.get(u_id, 0.0),
                    early_leave_days=user_early_leave_days.get(u_id, 0),
                    early_leave_hours=user_early_leave_hours.get(u_id, 0.0),
                    leave_days=float(leave_days),
                    approved_leave_days=float(approved_leave_days),
                    attendance_rate=attendance_rate,
                    total_days=float(total_days),
                    avatar=avatar if avatar else None,
                    gender=gender,
                )
            )

        overall_rate = 0.0
        if global_days_tracked > 0:
            overall_rate = (global_present_total / global_days_tracked) * 100.0

        return AdminGlobalReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_users=len(user_summaries),
            overall_attendance_rate=round(overall_rate, 1),
            users=user_summaries
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating global admin report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate global report: {str(e)}"
        )


@router.get("/admin/report/trend", response_model=AdminTrendReportResponse)
async def get_admin_trend_report(
    start_date: date = Query(..., description="Start date for trend data (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for trend data (YYYY-MM-DD)"),
    branch_id: Optional[int] = Query(None, description="Filter by branch ID (optional)"),
    department_name: Optional[str] = Query(None, description="Filter by department name (optional)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Admin endpoint: Get monthly overall attendance trends across the dataset using robust schedule parsing.
    """
    _require_attendance_admin(db, current_user)

    try:
        # 1. Fetch all active users
        users_query = db.query(User).filter(User.status == 1)
        if branch_id is not None:
            users_query = users_query.filter(User.workplace == branch_id)
        if department_name and department_name.strip():
            users_query = users_query.join(
                Department, User.departmentId == Department.id
            ).filter(func.lower(Department.department) == department_name.strip().lower())
        report_users = filter_enabled_users(db, users_query.all())
        user_ids = [int(user.id) for user in report_users]
        day_info_resolver = _build_report_schedule_context(
            db,
            report_users,
            start_date,
            end_date,
        )
        users_by_id = {int(user.id): user for user in report_users}

        def _norm_date(v):
            if v is None: return None
            # Do datetime check FIRST because datetime is a subclass of date
            if isinstance(v, datetime): return v.date()
            if isinstance(v, date): return v
            if hasattr(v, "date"): return v.date()
            s = str(v).strip()[:10]
            return date.fromisoformat(s) if s else None

        # 2. Get holidays over the entire period
        holiday_query = text("SELECT date, name FROM holidays WHERE date BETWEEN :start_date AND :end_date")
        holiday_rows = db.execute(holiday_query, {"start_date": start_date, "end_date": end_date}).fetchall()
        holidays_dict = {}
        for row in holiday_rows:
            d = _norm_date(row[0])
            if d is not None:
                holidays_dict[d] = row[1]

        # 3. Get all attended dates (for fast lookup)
        attended_query = text("""
            SELECT user_id, attendance_date, COALESCE(session_index, 0),
                   SUM(CASE WHEN check_in_time IS NOT NULL THEN 1 ELSE 0 END) +
                   SUM(CASE WHEN check_out_time IS NOT NULL THEN 1 ELSE 0 END) AS event_count
            FROM attendance_records
            WHERE attendance_date BETWEEN :start_date AND :end_date
              AND user_id IN :user_ids
            GROUP BY user_id, attendance_date, session_index
        """).bindparams(bindparam("user_ids", expanding=True))
        attended_rows = db.execute(attended_query, {
            "start_date": start_date,
            "end_date": end_date,
            "user_ids": user_ids,
        }).fetchall()
        user_attended_map = defaultdict(set)
        user_event_counts = defaultdict(dict)
        user_session_event_counts = defaultdict(lambda: defaultdict(dict))
        for row in attended_rows:
            uid = row[0]
            d = _norm_date(row[1])
            if d is not None:
                user_attended_map[uid].add(d)
                event_count = int(row[3] or 0)
                user_event_counts[int(uid)][d] = (
                    user_event_counts[int(uid)].get(d, 0) + event_count
                )
                user_session_event_counts[int(uid)][d][int(row[2] or 0)] = event_count

        # Approved leave counts as excused in the trend rate as well.
        trend_leave_map = get_approved_leave_map(db, list(user_ids), start_date, end_date)

        # Group operations by month
        import calendar

        monthly_trends = []
        current_month_start = start_date.replace(day=1)

        while current_month_start <= end_date:
            month_str = current_month_start.strftime("%Y-%m")
            last_day = calendar.monthrange(current_month_start.year, current_month_start.month)[1]
            month_end = current_month_start.replace(day=last_day)

            # Trim to the requested window if it overlaps
            calc_start = max(start_date, current_month_start)
            calc_end = min(end_date, month_end)

            global_present = 0.0
            global_expected = 0

            for u_id in user_ids:
                expected, present, absent, leave = _compute_user_attendance_totals(
                    db, u_id, calc_start, calc_end, holidays_dict, user_attended_map.get(u_id, set()),
                    leave_by_date=trend_leave_map.get(u_id),
                    db_user=users_by_id.get(int(u_id)),
                    day_info_resolver=day_info_resolver,
                    attendance_event_counts=user_event_counts.get(int(u_id), {}),
                    attendance_session_event_counts=user_session_event_counts.get(
                        int(u_id), {}
                    ),
                )
                global_present += present + leave
                global_expected += expected

            rate = 0.0
            if global_expected > 0:
                rate = (global_present / global_expected) * 100.0
                
            monthly_trends.append(
                MonthlyTrend(
                    month=month_str,
                    attendance_rate=round(rate, 3)
                )
            )
            
            # Move to next month
            if current_month_start.month == 12:
                current_month_start = current_month_start.replace(year=current_month_start.year + 1, month=1)
            else:
                current_month_start = current_month_start.replace(month=current_month_start.month + 1)

        return AdminTrendReportResponse(
            start_date=start_date,
            end_date=end_date,
            trends=monthly_trends
        )

    except Exception as e:
        logger.error(f"Error generating admin trend report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate trend report: {str(e)}"
        )

@router.get("/admin/report/user/{user_id}/detailed", response_model=AdminUserDetailedReportResponse)
async def get_admin_user_detailed_report(
    user_id: int,
    start_date: date = Query(..., description="Start date for report (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for report (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Admin endpoint: Get a day-by-day, session-by-session detailed breakdown for a specific user.
    Maps actual attendance scans against the expected schedule. Identifies missing records.
    """
    _require_attendance_admin(db, current_user)
        
    try:
        # 1. Fetch User Data
        user_query = text("""
            SELECT u.id, COALESCE(u.eName, u.kName, u.username) as name,
                   COALESCE(d.department, 'Unknown') as dept,
                   COALESCE(b.branch_name, 'Unknown') as branch
            FROM users u
            LEFT JOIN department d ON u.departmentId = d.id
            LEFT JOIN branch b ON u.workplace = b.id
            WHERE u.id = :uid
        """)
        target_user = db.query(User).filter(User.id == user_id).first()
        if target_user is None:
            raise HTTPException(status_code=404, detail="User not found")
        target_access = get_attendance_processing_access(db, target_user)
        if not target_access.enabled:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "attendance_processing_disabled",
                    **target_access.as_dict(),
                },
            )
        user_row = db.execute(user_query, {"uid": user_id}).fetchone()
        if not user_row:
             raise HTTPException(status_code=404, detail="User not found")
             
        # 2. Holidays and attended dates (for shared totals)
        holiday_query = text("SELECT date, name FROM holidays WHERE date BETWEEN :start_date AND :end_date")
        holiday_rows = db.execute(holiday_query, {"start_date": start_date, "end_date": end_date}).fetchall()
        holidays_dict = {}
        for row in holiday_rows:
            k = row[0]
            if k is None:
                continue
            if isinstance(k, date):
                pass
            elif hasattr(k, "date"):
                k = k.date()
            else:
                k = date.fromisoformat(str(k).strip()[:10])
            holidays_dict[k] = row[1]
        attended_query = text("""
            SELECT attendance_date, COALESCE(session_index, 0),
                   SUM(CASE WHEN check_in_time IS NOT NULL THEN 1 ELSE 0 END) +
                   SUM(CASE WHEN check_out_time IS NOT NULL THEN 1 ELSE 0 END) AS event_count
            FROM attendance_records
            WHERE user_id = :uid AND attendance_date BETWEEN :start_date AND :end_date
            GROUP BY attendance_date, session_index
        """)
        attended_rows = db.execute(attended_query, {"uid": user_id, "start_date": start_date, "end_date": end_date}).fetchall()
        attended_set = set()
        attendance_event_counts = {}
        attendance_session_event_counts = defaultdict(dict)
        for row in attended_rows:
            d = row[0]
            if d is None:
                continue
            if isinstance(d, date):
                normalized_date = d
            elif hasattr(d, "date"):
                normalized_date = d.date()
            else:
                normalized_date = date.fromisoformat(str(d).strip()[:10])
            event_count = int(row[2] or 0)
            if event_count > 0:
                attended_set.add(normalized_date)
            attendance_event_counts[normalized_date] = (
                attendance_event_counts.get(normalized_date, 0) + event_count
            )
            attendance_session_event_counts[normalized_date][int(row[1] or 0)] = (
                event_count
            )

        current_date = start_date
        days_breakdown = []

        # Reuse system time-window buffers for robust session mapping.
        system_settings = db.query(AttendanceSystemSettings).first()
        allow_early_clock_in_mins = getattr(system_settings, "allow_early_clock_in_mins", None)
        allow_late_clock_out_mins = getattr(system_settings, "allow_late_clock_out_mins", None)
        early_entry_buffer = _normalize_early_clock_in_mins(allow_early_clock_in_mins)
        late_exit_buffer = allow_late_clock_out_mins if allow_late_clock_out_mins is not None else 0
        per_session_early_list = _coerce_per_session_early_clock_in_list(
            getattr(system_settings, "per_session_early_clock_in_mins", None)
        ) if system_settings else None
        
        # We need a full user profile for schedule + exception scope resolution.
        db_user = _user_for_schedule_context(db, user_id)
        detailed_day_resolver = _build_report_schedule_context(
            db, [db_user], start_date, end_date
        )

        # Approved leave per date → sessions show "on_leave" instead of "missing_*".
        detailed_leave_map = get_approved_leave_map(db, [user_id], start_date, end_date).get(user_id, {})
        employment_start = _user_employment_start_date(db_user)

        # Load the employee's entire range once. The previous implementation
        # queried attendance_records inside the calendar-day loop, which made
        # long-range and multi-employee detailed exports issue thousands of
        # small database queries.
        records_query = text("""
            SELECT id, check_in_time, check_out_time, status, work_hours, earned_percentage,
                   late_reason, leave_early_reason, notes, session_index, schedule_id,
                   scheduled_start, scheduled_end, snapshot_late_grace_minutes,
                   snapshot_allow_early_leave_mins, attendance_date
            FROM attendance_records
            WHERE user_id = :uid
              AND attendance_date BETWEEN :start_date AND :end_date
            ORDER BY attendance_date ASC, created_at ASC
        """)
        range_records = db.execute(
            records_query,
            {"uid": user_id, "start_date": start_date, "end_date": end_date},
        ).fetchall()
        actual_records_by_date: Dict[date, list] = defaultdict(list)
        for record in range_records:
            record_date = record[15]
            if isinstance(record_date, datetime):
                record_date = record_date.date()
            elif not isinstance(record_date, date):
                record_date = date.fromisoformat(str(record_date).strip()[:10])
            actual_records_by_date[record_date].append(record)

        while current_date <= end_date:
            is_holiday = current_date in holidays_dict
            holiday_name = holidays_dict.get(current_date, "")
            before_employment = bool(
                employment_start and current_date < employment_start
            )

            # Check Schedule for THIS specific date (includes daily exceptions)
            expected_sessions_raw = [{'start': '08:00', 'end': '12:00'}, {'start': '13:00', 'end': '17:00'}]
            is_active_day = False
            day_type = f"Holiday ({holiday_name})" if is_holiday else "Full Day"

            if not is_holiday and not before_employment:
                day_info = detailed_day_resolver(db_user, current_date)
                is_active_day = bool(day_info.get("is_active_day"))
                expected_sessions_raw = list(day_info.get("sessions") or [])
                if is_active_day:
                    day_type = day_info.get("day_type") or day_type
                    if day_info.get("source") == "exception" and day_info.get("exception_reason"):
                        day_type = f"{day_type} (Exception)"

            if not is_active_day:
                if before_employment:
                    day_type = "Before Employment"
                else:
                    day_type = f"Holiday ({holiday_name})" if is_holiday else "Non-Working Day"
                expected_sessions_raw = []
                
            actual_records = actual_records_by_date.get(current_date, [])

            snapshot_expected_by_index: Dict[int, Dict[str, Any]] = {}
            for rec in actual_records:
                try:
                    rec_idx = int(rec[9]) if rec[9] is not None else 0
                except Exception:
                    rec_idx = 0
                if rec_idx <= 0:
                    continue
                rec_start = rec[11]
                rec_end = rec[12]
                if rec_start or rec_end:
                    snapshot_expected_by_index[rec_idx] = {
                        "start": rec_start,
                        "end": rec_end,
                    }

            if snapshot_expected_by_index and is_active_day:
                max_snapshot_index = max(snapshot_expected_by_index)
                while len(expected_sessions_raw) < max_snapshot_index:
                    expected_sessions_raw.append({})
                for snap_idx, snap_sess in snapshot_expected_by_index.items():
                    slot_idx = snap_idx - 1
                    if 0 <= slot_idx < len(expected_sessions_raw):
                        expected_sessions_raw[slot_idx] = {
                            **(expected_sessions_raw[slot_idx] or {}),
                            **snap_sess,
                        }

            # Map Actuals to Expecteds sequentially
            daily_sessions = []
            daily_work_hours = 0.0
            day_status = "present"
            today_upper = datetime.now(CAMBODIA_TZ).date()

            if is_active_day and len(expected_sessions_raw) > 0:
                # Future days: show as Pending, do not count as absent
                if current_date > today_upper:
                    future_leave_entry = detailed_leave_map.get(current_date)
                    covered_future_sessions = 0
                    for idx, exp_sess in enumerate(expected_sessions_raw):
                        session_status = (
                            "on_leave"
                            if leave_covers_session(future_leave_entry, idx + 1)
                            else "pending"
                        )
                        if session_status == "on_leave":
                            covered_future_sessions += 1
                        daily_sessions.append(DailySessionDetails(
                            session_index=idx + 1,
                            expected_start=exp_sess.get('start'),
                            expected_end=exp_sess.get('end'),
                            actual_check_in=None,
                            actual_check_out=None,
                            status=session_status,
                            work_hours=0.0,
                        ))
                    if covered_future_sessions == len(expected_sessions_raw):
                        day_status = "on_leave"
                    elif covered_future_sessions > 0:
                        day_status = "partial_leave"
                    else:
                        day_status = "pending"
                else:
                    def _time_to_minutes(hhmm: str):
                        try:
                            raw = str(hhmm).strip()
                            if not raw:
                                return None
                            for fmt in ("%H:%M", "%H:%M:%S"):
                                try:
                                    parsed = datetime.strptime(raw, fmt)
                                    return parsed.hour * 60 + parsed.minute
                                except Exception:
                                    pass
                            for fmt in ("%I:%M %p", "%I:%M:%S %p"):
                                try:
                                    parsed = datetime.strptime(raw.upper(), fmt)
                                    return parsed.hour * 60 + parsed.minute
                                except Exception:
                                    pass
                            parts = raw.split(":")
                            if len(parts) >= 2:
                                return int(parts[0]) * 60 + int(parts[1][:2])
                            return None
                        except Exception:
                            return None

                    def _find_session_index_for_minutes(actual_minutes: int, include_late_buffer: bool = True) -> int:
                        best_idx = -1
                        best_start = None
                        for i, sess in enumerate(expected_sessions_raw):
                            start_m = _time_to_minutes(sess.get("start", ""))
                            end_m = _time_to_minutes(sess.get("end", ""))
                            if start_m is None or end_m is None:
                                continue
                            window_open = _session_checkin_window_open_minutes(
                                i,
                                start_m,
                                expected_sessions=expected_sessions_raw,
                                time_to_minutes=_time_to_minutes,
                                global_early_mins=early_entry_buffer,
                                per_session_mins=per_session_early_list,
                            )
                            window_close = end_m + (late_exit_buffer if include_late_buffer else 0)
                            if window_open <= actual_minutes <= window_close:
                                if actual_minutes >= start_m:
                                    if best_start is None or start_m > best_start:
                                        best_start = start_m
                                        best_idx = i
                                else:
                                    if best_start is None or start_m < best_start:
                                        best_start = start_m
                                        best_idx = i
                        return best_idx

                    # Map records to expected sessions by actual time window.
                    # This prevents Session 2 scans from being displayed under Session 1.
                    mapped_sessions = [
                        {
                            "rec": None,
                            "in": None,
                            "out": None,
                            "status": None,
                            "work_hours": 0.0,
                            "late_reason": None,
                            "leave_early_reason": None,
                            "notes": None,
                            "schedule_id": None,
                            "scheduled_start": None,
                            "scheduled_end": None,
                            "snapshot_late_grace_minutes": None,
                            "snapshot_allow_early_leave_mins": None,
                        }
                        for _ in range(len(expected_sessions_raw))
                    ]
                    unmatched_records = []
                    for rec in actual_records:
                        rec_in = rec[1]
                        rec_out = rec[2]
                        rec_session_idx = rec[9]
                        if rec_session_idx is not None:
                            try:
                                s_idx = int(rec_session_idx) - 1
                            except Exception:
                                s_idx = -1
                        elif rec_in is not None:
                            rec_minutes = rec_in.hour * 60 + rec_in.minute
                            s_idx = _find_session_index_for_minutes(rec_minutes, include_late_buffer=False)
                        elif rec_out is not None:
                            rec_minutes = rec_out.hour * 60 + rec_out.minute
                            s_idx = _find_session_index_for_minutes(rec_minutes, include_late_buffer=True)
                        else:
                            continue

                        if s_idx < 0 or s_idx >= len(mapped_sessions):
                            unmatched_records.append(rec)
                            continue

                        slot = mapped_sessions[s_idx]
                        if slot["rec"] is None:
                            slot["rec"] = rec
                            slot["in"] = rec_in
                            slot["out"] = rec_out
                            slot["status"] = rec[3]
                            slot["work_hours"] = float(rec[4]) if rec[4] else 0.0
                            slot["late_reason"] = rec[6]
                            slot["leave_early_reason"] = rec[7]
                            slot["notes"] = rec[8]
                            slot["schedule_id"] = rec[10]
                            slot["scheduled_start"] = rec[11]
                            slot["scheduled_end"] = rec[12]
                            slot["snapshot_late_grace_minutes"] = rec[13]
                            slot["snapshot_allow_early_leave_mins"] = rec[14]
                        else:
                            # Merge partials if same session receives separate in/out rows.
                            if slot["in"] is None and rec_in is not None:
                                slot["in"] = rec_in
                            if slot["out"] is None and rec_out is not None:
                                slot["out"] = rec_out
                            if slot["status"] is None and rec[3] is not None:
                                slot["status"] = rec[3]
                            if not slot["work_hours"] and rec[4]:
                                slot["work_hours"] = float(rec[4])
                            if slot["late_reason"] is None and rec[6]:
                                slot["late_reason"] = rec[6]
                            if slot["leave_early_reason"] is None and rec[7]:
                                slot["leave_early_reason"] = rec[7]
                            if slot["notes"] is None and rec[8]:
                                slot["notes"] = rec[8]
                            if slot["schedule_id"] is None and rec[10] is not None:
                                slot["schedule_id"] = rec[10]
                            if slot["scheduled_start"] is None and rec[11]:
                                slot["scheduled_start"] = rec[11]
                            if slot["scheduled_end"] is None and rec[12]:
                                slot["scheduled_end"] = rec[12]
                            if slot["snapshot_late_grace_minutes"] is None and rec[13] is not None:
                                slot["snapshot_late_grace_minutes"] = rec[13]
                            if slot["snapshot_allow_early_leave_mins"] is None and rec[14] is not None:
                                slot["snapshot_allow_early_leave_mins"] = rec[14]

                    # Fallback assignment for makeup records outside session ranges.
                    for rec in unmatched_records:
                        rec_in = rec[1]
                        rec_out = rec[2]
                        target_idx = -1
                        for i, slot in enumerate(mapped_sessions):
                            if slot["rec"] is None:
                                target_idx = i
                                break
                            if slot["in"] is None and rec_in is not None:
                                target_idx = i
                                break
                            if slot["out"] is None and rec_out is not None:
                                target_idx = i
                                break
                        if target_idx < 0:
                            continue
                        slot = mapped_sessions[target_idx]
                        if slot["rec"] is None:
                            slot["rec"] = rec
                            slot["status"] = rec[3]
                            slot["late_reason"] = rec[6]
                            slot["leave_early_reason"] = rec[7]
                            slot["notes"] = rec[8]
                            slot["schedule_id"] = rec[10]
                            slot["scheduled_start"] = rec[11]
                            slot["scheduled_end"] = rec[12]
                            slot["snapshot_late_grace_minutes"] = rec[13]
                            slot["snapshot_allow_early_leave_mins"] = rec[14]
                        if slot["in"] is None and rec_in is not None:
                            slot["in"] = rec_in
                        if slot["out"] is None and rec_out is not None:
                            slot["out"] = rec_out
                        if not slot["work_hours"] and rec[4]:
                            slot["work_hours"] = float(rec[4])

                    for idx, exp_sess in enumerate(expected_sessions_raw):
                        actual_in = None
                        actual_out = None
                        sess_status = "missing_both"
                        wh = 0.0

                        slot = mapped_sessions[idx]
                        expected_start = slot.get("scheduled_start") or exp_sess.get('start')
                        expected_end = slot.get("scheduled_end") or exp_sess.get('end')
                        actual_in = slot["in"]
                        actual_out = slot["out"]
                        wh = float(slot["work_hours"] or 0.0)
                        session_on_leave = leave_covers_session(
                            detailed_leave_map.get(current_date), idx + 1
                        )

                        # A check-out past scheduled_end + the allowance is
                        # accepted but flagged. `status` describes the
                        # check-in side, so this travels separately.
                        session_late_check_out = False
                        if actual_out is not None:
                            end_reference = (
                                slot.get("scheduled_end") or exp_sess.get("end") or ""
                            )
                            end_minutes = _time_to_minutes(end_reference)
                            if end_minutes is not None:
                                session_late_check_out = is_late_check_out(
                                    check_out_minutes=(
                                        actual_out.hour * 60 + actual_out.minute
                                    ),
                                    session_end_minutes=end_minutes,
                                    allow_late_clock_out_minutes=(
                                        allow_late_clock_out_mins or 0
                                    ),
                                )

                        if actual_in and actual_out:
                            if slot["status"] == "late":
                                sess_status = "late"
                            elif slot["status"] == "early_leave":
                                sess_status = "early_leave"
                            else:
                                sess_status = "on_time"
                        elif actual_in and not actual_out:
                            sess_status = "missing_out"
                        elif not actual_in and actual_out:
                            sess_status = "missing_in"
                        else:
                            sess_status = "missing_both"

                        # Approved leave is a reversible read-time overlay. Keep
                        # the attendance row in the database, but never expose
                        # its times/status/work hours while this session is
                        # covered. Cancelling leave makes it visible again.
                        if session_on_leave:
                            sess_status = "on_leave"
                            actual_in = None
                            actual_out = None
                            wh = 0.0
                            session_late_check_out = False
                        daily_work_hours += wh

                        daily_sessions.append(DailySessionDetails(
                            session_index=idx + 1,
                            expected_start=expected_start,
                            expected_end=expected_end,
                            schedule_id=slot.get("schedule_id"),
                            scheduled_start=slot.get("scheduled_start"),
                            scheduled_end=slot.get("scheduled_end"),
                            snapshot_late_grace_minutes=slot.get("snapshot_late_grace_minutes"),
                            snapshot_allow_early_leave_mins=slot.get("snapshot_allow_early_leave_mins"),
                            actual_check_in=actual_in,
                            actual_check_out=actual_out,
                            status=sess_status,
                            is_late_check_out=session_late_check_out,
                            work_hours=round(wh, 2),
                            late_reason=None if session_on_leave else slot.get("late_reason"),
                            leave_early_reason=None if session_on_leave else slot.get("leave_early_reason"),
                            notes=None if session_on_leave else slot.get("notes"),
                        ))

                    # Derive Overall Daily Status: any check-in or check-out = Present (or Incomplete)
                    has_any_record = any(
                        rec[1] is not None or rec[2] is not None
                        for rec in actual_records
                    )
                    missing_count = sum(1 for s in daily_sessions if "missing" in s.status)
                    on_leave_count = sum(1 for s in daily_sessions if s.status == "on_leave")
                    if on_leave_count == len(daily_sessions) and daily_sessions:
                        # Whole day covered by approved leave — excused, not absent.
                        day_status = "on_leave"
                    elif on_leave_count > 0:
                        day_status = "partial_leave"
                    elif not has_any_record and missing_count + on_leave_count == len(daily_sessions):
                        day_status = "absent"
                    elif has_any_record:
                        day_status = "incomplete" if missing_count > 0 else "present"
                    else:
                        day_status = "absent"
            else:
                # Holidays and schedule days off are never expected/absent, but
                # still expose any extra/manual work instead of hiding it.
                if before_employment:
                    day_status = "not_employed"
                else:
                    day_status = "holiday" if is_holiday else "non_working"
                for fallback_idx, rec in enumerate(actual_records, start=1):
                    actual_in = rec[1]
                    actual_out = rec[2]
                    if actual_in is None and actual_out is None:
                        continue
                    try:
                        session_index = int(rec[9] or fallback_idx)
                    except Exception:
                        session_index = fallback_idx
                    work_hours = float(rec[4] or 0.0)
                    daily_work_hours += work_hours
                    if actual_in is not None and actual_out is not None:
                        session_status = "on_time"
                    elif actual_in is not None:
                        session_status = "missing_out"
                    else:
                        session_status = "missing_in"
                    daily_sessions.append(DailySessionDetails(
                        session_index=session_index,
                        expected_start=rec[11],
                        expected_end=rec[12],
                        schedule_id=rec[10],
                        scheduled_start=rec[11],
                        scheduled_end=rec[12],
                        snapshot_late_grace_minutes=rec[13],
                        snapshot_allow_early_leave_mins=rec[14],
                        actual_check_in=actual_in,
                        actual_check_out=actual_out,
                        status=session_status,
                        work_hours=round(work_hours, 2),
                        late_reason=rec[6],
                        leave_early_reason=rec[7],
                        notes=rec[8],
                    ))
            
            day_leave_entry = detailed_leave_map.get(current_date)
            days_breakdown.append(DailyAttendanceBreakdown(
                date=current_date,
                day_type=day_type,
                expected_sessions_count=len(expected_sessions_raw),
                sessions=daily_sessions,
                daily_status=day_status,
                total_work_hours=round(daily_work_hours, 2),
                leave_fraction=min(1.0, float(day_leave_entry["fraction"])) if day_leave_entry else 0.0,
                leave_type_name=day_leave_entry.get("leave_type") if day_leave_entry else None,
            ))
            
            current_date += timedelta(days=1)

        # Use same helper as global report so list and detail always show same Expected/Absent
        exp, pres, abs_days, leave_days = _compute_user_attendance_totals(
            db, user_id, start_date, end_date, holidays_dict, attended_set,
            leave_by_date=detailed_leave_map,
            db_user=db_user,
            day_info_resolver=detailed_day_resolver,
            attendance_event_counts=attendance_event_counts,
            attendance_session_event_counts=dict(attendance_session_event_counts),
        )
        return AdminUserDetailedReportResponse(
            user_id=user_row[0],
            user_name=user_row[1],
            department=user_row[2],
            branch=user_row[3],
            start_date=start_date,
            end_date=end_date,
            total_expected_days=float(exp),
            total_present_days=float(pres),
            total_absent_days=float(abs_days),
            total_leave_days=float(leave_days),
            days_breakdown=days_breakdown
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating detailed admin report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate detailed report: {str(e)}"
        )


@router.get("/user-records")
async def get_user_attendance_records(
    user_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get attendance records for a specific user (for individual user dashboard).
    Users can only view their own records, admins can view any user's records.
    """
    try:
        # Permission check - users can only view their own records, admins can view any
        if int(current_user.id) != int(user_id):
            _require_attendance_admin(db, current_user)

        records_user = (
            current_user
            if int(current_user.id) == int(user_id)
            else db.query(User).filter(User.id == user_id).first()
        )
        if records_user is None:
            raise HTTPException(status_code=404, detail="User not found")
        _require_attendance_processing(db, records_user)

        import calendar
        month_last_day = calendar.monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end = date(year, month, month_last_day)

        # Get attendance records for the specified user and month/year using raw SQL
        query = text("""
            SELECT id, user_id, attendance_date, check_in_time, check_out_time,
                   check_in_latitude, check_in_longitude, check_out_latitude, check_out_longitude,
                   is_mock_location, device_info,
                   session_index, schedule_id, scheduled_start, scheduled_end,
                   snapshot_late_grace_minutes, snapshot_allow_early_leave_mins,
                   work_hours, status, notes, late_reason, leave_early_reason, created_at, updated_at
            FROM attendance_records
            WHERE user_id = :user_id
            AND attendance_date BETWEEN :month_start AND :month_end
            ORDER BY attendance_date DESC
        """)

        result = db.execute(query, {
            "user_id": user_id,
            "month_start": month_start,
            "month_end": month_end,
        }).fetchall()

        # Convert to dict format
        records_data = []
        for row in result:
            records_data.append({
                'id': row[0],
                'user_id': row[1],
                'attendance_date': row[2].isoformat() if row[2] else None,
                'check_in_time': row[3].isoformat() if row[3] else None,
                'check_out_time': row[4].isoformat() if row[4] else None,
                'check_in_latitude': row[5],
                'check_in_longitude': row[6],
                'check_out_latitude': row[7],
                'check_out_longitude': row[8],
                'is_mock_location': bool(row[9]) if row[9] is not None else False,
                'device_info': row[10],
                'session_index': row[11],
                'schedule_id': row[12],
                'scheduled_start': row[13],
                'scheduled_end': row[14],
                'snapshot_late_grace_minutes': row[15],
                'snapshot_allow_early_leave_mins': row[16],
                'work_hours': float(row[17]) if row[17] else None,
                'status': row[18] or 'present',
                'notes': row[19],
                'late_reason': row[20],
                'leave_early_reason': row[21],
                'created_at': row[22].isoformat() if row[22] else None,
                'updated_at': row[23].isoformat() if row[23] else None,
            })

        # Build assignment/schedule-aware month summary for Report cards.
        summary_user = records_user
        if summary_user is None:
            raise HTTPException(status_code=404, detail="User not found")
        month_day_resolver = _build_report_schedule_context(
            db, [summary_user], month_start, month_end
        )
        holiday_query = text(
            "SELECT date FROM holidays WHERE date BETWEEN :start_date AND :end_date"
        )
        holiday_rows = db.execute(
            holiday_query,
            {"start_date": month_start, "end_date": month_end},
        ).fetchall()
        holidays_dict = {row[0]: True for row in holiday_rows}
        attended_dates = set()
        month_event_counts = defaultdict(int)
        month_session_event_counts = defaultdict(lambda: defaultdict(int))
        for record_row in result:
            report_date = record_row[2]
            if report_date is None:
                continue
            event_count = int(record_row[3] is not None) + int(
                record_row[4] is not None
            )
            if event_count <= 0:
                continue
            attended_dates.add(report_date)
            month_event_counts[report_date] += event_count
            month_session_event_counts[report_date][int(record_row[11] or 0)] += (
                event_count
            )
        month_leave_map = get_approved_leave_map(db, [user_id], month_start, month_end)
        expected_days, present_days, absent_days, leave_days = _compute_user_attendance_totals(
            db=db,
            user_id=user_id,
            start_date=month_start,
            end_date=month_end,
            holidays_dict=holidays_dict,
            attended_dates=attended_dates,
            leave_by_date=month_leave_map.get(user_id),
            db_user=summary_user,
            day_info_resolver=month_day_resolver,
            attendance_event_counts=dict(month_event_counts),
            attendance_session_event_counts={
                report_date: dict(events)
                for report_date, events in month_session_event_counts.items()
            },
        )

        return {
            'user_id': user_id,
            'month': month,
            'year': year,
            'records': records_data,
            'total_records': len(records_data),
            # Per-date approved leave so clients can render "on leave" instead
            # of "missing" for covered sessions.
            'leave_by_date': leave_map_to_json(month_leave_map.get(user_id, {})),
            # Per-date effective sessions (schedule exceptions applied) so the
            # client history matches special weekend/exception schedules.
            'day_sessions': _build_day_sessions_map(
                db,
                user_id,
                month_start,
                month_end,
                db_user=summary_user,
                day_info_resolver=month_day_resolver,
            ),
            'summary': {
                'present_days': round(float(present_days), 2),
                'absent_days': round(float(absent_days), 2),
                'leave_days': round(float(leave_days), 2),
                'total_days': int(expected_days),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching user attendance records: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Bulk schedule resolver — used by /user/ranking to avoid per-user N+1 queries.
# The legacy helpers _compute_user_expected_points_so_far / _compute_user_attendance_totals
# call get_effective_schedule once per user per day, which causes 30+s response
# times when "All Branches + All Departments" returns hundreds of users. The
# helpers below pre-fetch all candidate schedules and assignments once, then
# resolve in pure Python with no DB calls inside the per-user loop.
# ─────────────────────────────────────────────────────────────────────────────
def _build_ranking_compute_context(
    db: Session,
    user_ids: List[int],
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Pre-fetch every row needed to compute ranking metrics for `user_ids` in
    pure Python. Returns a dict with candidates and per-user assignments keyed
    for O(1) lookup in the compute loop.
    """
    if not user_ids:
        return {
            "candidates": [],
            "assignments_by_user": {},
            "default_global_id": None,
            "exceptions": [],
            "leave_by_user": {},
        }

    candidates = (
        db.query(AttendanceSchedule)
        .filter(
            AttendanceSchedule.is_active == 1,
            AttendanceSchedule.effective_date <= end_date,
        )
        .order_by(
            AttendanceSchedule.effective_date.desc(),
            AttendanceSchedule.id.desc(),
        )
        .all()
    )

    assignment_rows = (
        db.query(AttendanceUserAssignment)
        .filter(
            AttendanceUserAssignment.user_id.in_(user_ids),
            AttendanceUserAssignment.start_date <= end_date,
        )
        .order_by(
            AttendanceUserAssignment.start_date.desc(),
            AttendanceUserAssignment.id.desc(),
        )
        .all()
    )
    assignments_by_user: Dict[int, List[AttendanceUserAssignment]] = defaultdict(list)
    for a in assignment_rows:
        assignments_by_user[int(a.user_id)].append(a)  # type: ignore[arg-type]

    default_schedule = _get_default_fallback_schedule(db)
    default_global_id = int(default_schedule.id) if default_schedule else None  # type: ignore[arg-type]

    ensure_schedule_exceptions_table(db)
    exception_rows = (
        db.query(AttendanceScheduleException)
        .filter(
            AttendanceScheduleException.exception_date <= end_date,
            or_(
                AttendanceScheduleException.end_date.is_(None),
                AttendanceScheduleException.end_date >= start_date,
            ),
        )
        .all()
    )
    enrollment_rows = (
        db.query(AttendanceScheduleExceptionEnrollment)
        .filter(
            AttendanceScheduleExceptionEnrollment.user_id.in_(user_ids),
            AttendanceScheduleExceptionEnrollment.occurrence_date >= start_date,
            AttendanceScheduleExceptionEnrollment.occurrence_date <= end_date,
        )
        .all()
    )

    return {
        "candidates": candidates,
        "assignments_by_user": dict(assignments_by_user),
        "default_global_id": default_global_id,
        "exceptions": exception_rows,
        "exception_enrollments": {
            (int(row.user_id), row.occurrence_date): int(row.exception_id)
            for row in enrollment_rows
        },
        # Approved leave per user per date — leave-covered sessions must not
        # count as due attendance events (asked permission ≠ absent).
        "leave_by_user": get_approved_leave_map(db, user_ids, start_date, end_date),
    }


class _RankingUserStub:
    """Lightweight User-shaped object so the resolver helpers work without
    re-querying the users table inside the ranking compute loop."""

    __slots__ = ("id", "departmentId", "workplace", "isForeigner", "startWork")

    def __init__(
        self,
        user_id: int,
        department_id: Optional[int],
        workplace: Optional[int],
        is_foreigner: Optional[int] = None,
        start_work: Optional[str] = None,
    ):
        self.id = user_id
        self.departmentId = department_id
        self.workplace = workplace
        self.isForeigner = is_foreigner
        self.startWork = start_work


def _resolve_schedule_for_user_date_cached(
    user_obj: Any,
    target_date: date,
    candidates: List[AttendanceSchedule],
    user_assignments: List[AttendanceUserAssignment],
    default_global_id: Optional[int],
) -> Optional[AttendanceSchedule]:
    """Pure-Python equivalent of get_effective_schedule(db, user, target_date)
    using pre-fetched candidates + per-user assignments. No DB calls."""
    eligible_candidates = [
        c for c in candidates
        if c.effective_date is not None and c.effective_date <= target_date  # type: ignore[union-attr]
    ]

    active_assignment: Optional[AttendanceUserAssignment] = None
    for a in user_assignments:
        if a.start_date is None or a.start_date > target_date:  # type: ignore[union-attr]
            continue
        if a.end_date is not None and a.end_date < target_date:  # type: ignore[union-attr]
            continue
        active_assignment = a
        break  # already ordered by start_date DESC

    schedule, _ = _resolve_effective_schedule_from_candidates(
        user_obj,
        eligible_candidates,
        active_assignment,
        default_global_id=default_global_id,
    )
    return schedule


def _compute_user_ranking_metrics_cached(
    user_obj: Any,
    start_date: date,
    end_date: date,
    holidays_set: set,
    context: Dict[str, Any],
) -> Tuple[float, int]:
    """
    Compute (expected_points_so_far, total_month_days) for a single user
    using only the pre-fetched `context`. Mirrors the logic of the legacy
    _compute_user_expected_points_so_far + _compute_user_attendance_totals
    (with limit_today=False) but without any DB calls.
    """
    now = datetime.now(CAMBODIA_TZ)
    today = now.date()
    now_minutes = now.hour * 60 + now.minute

    user_id = int(user_obj.id)
    user_assignments = context["assignments_by_user"].get(user_id, [])
    candidates = context["candidates"]
    default_global_id = context["default_global_id"]
    exception_rows = context.get("exceptions") or []
    exception_enrollments = context.get("exception_enrollments") or {}
    leave_by_date = (context.get("leave_by_user") or {}).get(user_id, {})
    employment_start = _user_employment_start_date(user_obj)

    expected_points = 0.0
    total_month_days = 0

    current_date = start_date
    while current_date <= end_date:
        if employment_start and current_date < employment_start:
            current_date += timedelta(days=1)
            continue
        if current_date in holidays_set:
            current_date += timedelta(days=1)
            continue

        schedule = _resolve_schedule_for_user_date_cached(
            user_obj, current_date, candidates, user_assignments, default_global_id,
        )
        exception = match_exception_from_rows(
            exception_rows,
            user_obj,
            current_date,
            enrolled_exception_id=exception_enrollments.get(
                (user_id, current_date)
            ),
        )
        day_info = get_effective_day_attendance_with_exception(
            user_obj,
            current_date,
            schedule=schedule,
            exception=exception,
        )
        if not day_info.get("is_active_day"):
            current_date += timedelta(days=1)
            continue

        sessions = day_info.get("sessions") or []
        if not sessions:
            current_date += timedelta(days=1)
            continue

        # total_month_days = every active day in the full month range
        total_month_days += 1

        # Approved leave reduces due points — leave must not lower star/rank.
        leave_entry = leave_by_date.get(current_date)

        # expected_points_so_far: only past + today (matches legacy logic)
        if current_date < today:
            leave_fraction = min(1.0, float(leave_entry["fraction"])) if leave_entry else 0.0
            expected_points += 100.0 * (1.0 - leave_fraction)
        elif current_date == today:
            event_value = 100.0 / (len(sessions) * 2)
            for s_idx, session in enumerate(sessions, 1):
                if leave_covers_session(leave_entry, s_idx):
                    continue
                start_m = _time_str_to_minutes(session.get("start"))
                end_m = _time_str_to_minutes(session.get("end"))
                if start_m is not None and now_minutes >= start_m:
                    expected_points += event_value
                if end_m is not None and now_minutes >= end_m:
                    expected_points += event_value

        current_date += timedelta(days=1)

    return expected_points, total_month_days


@router.get("/user/ranking")
async def get_user_attendance_ranking(
    branch_id: Optional[int] = Query(None, description="Filter by branch. -1=all, null=user workplace, else specific branch"),
    department_id: Optional[int] = Query(None, description="Filter by department. -1=all, null=user dept, else specific dept"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get user's attendance ranking. Branch and department filters combine (AND logic).
    - branch_id=-1: no branch filter (all branches)
    - branch_id=null: use user's workplace
    - branch_id=N: filter by branch N
    Same for department_id. Both filters apply together (e.g. All Branches + Dept 1).
    """
    import time
    try:
        _require_attendance_processing(db, current_user)
        ensure_attendance_processing_rules_table(db)
        now = datetime.now()
        current_month = now.month
        current_year = now.year

        def _is_all(val):
            return val == -1 or val == "-1" or (isinstance(val, str) and str(val).strip() == "-1")

        # Effective filter values for cache key
        eff_branch = branch_id if branch_id is not None else getattr(current_user, 'workplace', None)
        eff_dept = department_id if department_id is not None else getattr(current_user, 'departmentId', None)
        cache_key = (
            _RANKING_CACHE_SCHEMA_VERSION,
            attendance_processing_rules_revision(db),
            current_month,
            current_year,
            eff_branch,
            eff_dept,
        )

        # Check cache first (fast path)
        if cache_key in _RANKING_CACHE:
            entry = _RANKING_CACHE[cache_key]
            if time.time() - entry['ts'] < _RANKING_CACHE_TTL:
                rankings = entry['rankings']
                current_user_rank = next((r for r in rankings if r.get('is_current_user')), None)
                total = len(rankings)
                page = rankings[offset : offset + limit]
                has_next = offset + limit < total
                return {
                    'ranking_type': 'filtered',
                    'month': current_month,
                    'year': current_year,
                    'total_users': total,
                    'has_next': has_next,
                    'current_user_rank': current_user_rank,
                    'rankings': page
                }
            else:
                del _RANKING_CACHE[cache_key]

        # Check if attendance_records table exists and has data
        try:
            count_query = "SELECT COUNT(*) FROM attendance_records WHERE attendance_date BETWEEN :start_date AND :end_date"
            import calendar as _cal_probe
            _last_day_probe = _cal_probe.monthrange(current_year, current_month)[1]
            _start_probe = date(current_year, current_month, 1)
            _end_probe = date(current_year, current_month, _last_day_probe)
            record_count = db.execute(
                text(count_query),
                {"start_date": _start_probe, "end_date": _end_probe},
            ).scalar()
            logger.debug(
                "Found %s attendance records for %s/%s",
                record_count,
                current_month,
                current_year,
            )
        except Exception as e:
            print(f"Error checking attendance records: {e}")
            # Return empty ranking if no records
            return {
                'ranking_type': 'filtered',
                'month': current_month,
                'year': current_year,
                'total_users': 0,
                'has_next': False,
                'current_user_rank': None,
                'rankings': []
            }

        # Pre-compute month bounds once — used by SQL JOIN and Python compute below.
        import calendar
        last_day_of_month = calendar.monthrange(current_year, current_month)[1]
        start_date = date(current_year, current_month, 1)
        end_date = date(current_year, current_month, last_day_of_month)

        # Build the query (LEFT JOIN branch, users_resource for avatar).
        # NOTE: use BETWEEN so MySQL can use the index on attendance_date.
        # MONTH()/YEAR() wraps the column in a function and forces a full scan.
        base_query = """
            SELECT
                u.id,
                u.username,
                u.eName,
                u.kName,
                u.role,
                u.gender,
                COUNT(ar.id) as scanned_days,
                COALESCE(SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END), 0) as present_days,
                COUNT(DISTINCT CASE WHEN ar.status = 'late' THEN ar.attendance_date END) as late_days,
                COUNT(DISTINCT CASE WHEN ar.status = 'absent' AND ar.attendance_date NOT IN (SELECT date FROM holidays) THEN ar.attendance_date END) as absent_days,
                u.departmentId,
                u.workplace,
                u.isForeigner,
                COALESCE(SUM(ar.earned_percentage), 0) as total_earned_percentage,
                b.branch_name,
                COALESCE(ur_emp.avatar, ur_tea.avatar) as avatar,
                u.startWork
            FROM users u
            LEFT JOIN attendance_records ar ON u.id = ar.user_id
                AND ar.attendance_date BETWEEN :start_date AND :end_date
            LEFT JOIN branch b ON u.workplace = b.id
            LEFT JOIN users_resource ur_emp ON ur_emp.user_id = u.id AND ur_emp.user_type = 'employee'
            LEFT JOIN users_resource ur_tea ON ur_tea.user_id = u.id AND ur_tea.user_type = 'teacher'
            WHERE u.status = 1
              AND NOT EXISTS (
                SELECT 1
                FROM attendance_processing_rules apr
                WHERE apr.is_enabled = 0
                  AND (
                    (apr.scope_type = 'user' AND apr.scope_id = u.id)
                    OR
                    (apr.scope_type = 'department' AND apr.scope_id = u.departmentId)
                  )
              )
        """

        params = {"start_date": start_date, "end_date": end_date}

        # Combine branch + department filters (AND logic)
        # branch_id=-1: no branch filter; null: use user workplace; else: specific branch
        if _is_all(branch_id):
            pass  # All branches - no filter
        elif branch_id is not None:
            base_query += " AND u.workplace = :branch_id"
            params["branch_id"] = int(branch_id) if isinstance(branch_id, str) else branch_id
        else:
            effective_branch = getattr(current_user, 'workplace', None)
            if effective_branch is not None:
                base_query += " AND u.workplace = :branch_id"
                params["branch_id"] = effective_branch

        if _is_all(department_id):
            pass  # All departments - no filter
        elif department_id is not None:
            base_query += " AND u.departmentId = :department_id"
            params["department_id"] = int(department_id) if isinstance(department_id, str) else department_id
        else:
            effective_dept = getattr(current_user, 'departmentId', None)
            if effective_dept is not None:
                base_query += " AND u.departmentId = :department_id"
                params["department_id"] = effective_dept

        base_query += """
            GROUP BY u.id, u.username, u.eName, u.kName, u.role, u.gender, u.departmentId, u.workplace, b.branch_name, ur_emp.avatar, ur_tea.avatar, u.startWork
            ORDER BY present_days DESC, late_days ASC, u.id ASC
        """

        result = db.execute(text(base_query), params).fetchall()

        holiday_query = text("SELECT date, name FROM holidays WHERE date BETWEEN :start_date AND :end_date")
        holiday_rows = db.execute(holiday_query, {"start_date": start_date, "end_date": end_date}).fetchall()
        holidays_dict = {row[0]: row[1] for row in holiday_rows}
        holidays_set = set(holidays_dict.keys())

        # Bulk pre-fetch schedule + assignment data for ALL users in one shot.
        # This eliminates the per-user N+1 (each user used to issue ~60+ queries
        # via _compute_user_expected_points_so_far + _compute_user_attendance_totals,
        # which is what made "All Branches + All Departments" take 30+ seconds).
        all_user_ids = [int(row[0]) for row in result if row[0] is not None]
        ranking_ctx = _build_ranking_compute_context(
            db=db,
            user_ids=all_user_ids,
            start_date=start_date,
            end_date=end_date,
        )

        # Convert to list and add ranking
        rankings = []
        for idx, row in enumerate(result, 1):
            try:
                # Ensure all values are JSON serializable
                user_id = int(row[0]) if row[0] is not None else 0
                username = str(row[1]) if row[1] is not None else ""
                english_name = str(row[2]) if row[2] is not None else ""
                khmer_name = str(row[3]) if row[3] is not None else ""
                role_id = int(row[4]) if row[4] is not None else 0
                dept_id = int(row[10]) if row[10] is not None else None
                workplace_id = int(row[11]) if row[11] is not None else None
                is_foreigner = int(row[12]) if row[12] is not None else None

                # Build a lightweight user stub so the cached resolver can run
                # the same hierarchy (user → department → branch → global) as
                # get_effective_schedule, without re-querying the users table.
                user_stub = _RankingUserStub(
                    user_id=user_id,
                    department_id=dept_id,
                    workplace=workplace_id,
                    is_foreigner=is_foreigner,
                    start_work=str(row[16]) if row[16] else None,
                )

                expected_points_so_far, total_month_days = _compute_user_ranking_metrics_cached(
                    user_obj=user_stub,
                    start_date=start_date,
                    end_date=end_date,
                    holidays_set=holidays_set,
                    context=ranking_ctx,
                )

                late_days = int(row[8] or 0)
                absent_days = int(row[9] or 0)
                total_earned_percentage = float(row[13] or 0.0)
                branch_name = str(row[14]) if row[14] else None
                avatar = str(row[15]) if row[15] else None

                # Dynamically calculate present days based on partial percentage logic
                raw_present_days = round(total_earned_percentage / 100.0, 2)
                present_days = int(raw_present_days) if raw_present_days == int(raw_present_days) else raw_present_days

                # Calculate cumulative attendance metrics using deductive formula.
                # Missing points = due attendance events so far - actually earned.
                deducted_points = max(0.0, expected_points_so_far - total_earned_percentage)

                attendance_percentage = 100.0
                star_rating = 5.0

                if total_month_days > 0:
                    total_month_possible = total_month_days * 100.0
                    penalty_ratio = deducted_points / total_month_possible
                    
                    attendance_percentage = round(100.0 - (penalty_ratio * 100.0), 1)
                    star_rating = round(max(0.0, min(5.0, 5.0 - (penalty_ratio * 5.0))), 1)

                user_data = {
                    'rank': idx,
                    'user_id': user_id,
                    'username': username,
                    'english_name': english_name,
                    'khmer_name': khmer_name,
                    'role_id': role_id,
                    'total_days': total_month_days,
                    'present_days': present_days,
                    'late_days': late_days,
                    'absent_days': absent_days,
                    'attendance_percentage': float(attendance_percentage),
                    'star_rating': float(star_rating),
                    'is_current_user': user_id == current_user.id,
                    'workplace_id': int(row[11]) if row[11] is not None else None,
                    'department_id': int(row[10]) if row[10] is not None else None,
                    'branch_name': branch_name,
                    'avatar': avatar,
                    'gender': str(row[5]) if row[5] else None,
                }
                rankings.append(user_data)
            except Exception as row_error:
                print(f"Error processing row {idx}: {row_error}, row data: {row}")
                continue

        # Sort by star first (highest first), then attendance percentage,
        # then present days, then fewer late days, then user_id for stability.
        rankings.sort(
            key=lambda x: (
                -(float(x.get('star_rating') or 0.0)),
                -(float(x.get('attendance_percentage') or 0.0)),
                -(float(x.get('present_days') or 0.0)),
                float(x.get('late_days') or 0.0),
                int(x.get('user_id') or 0),
            )
        )

        # Re-assign rank after sorting
        for i, r in enumerate(rankings, 1):
            r['rank'] = i

        # Find current user's rank
        current_user_rank = None
        for rank_data in rankings:
            if rank_data['is_current_user']:
                current_user_rank = rank_data
                break

        total = len(rankings)
        page = rankings[offset : offset + limit]
        has_next = offset + limit < total

        # Store in cache for fast subsequent requests
        _RANKING_CACHE[cache_key] = {'rankings': rankings, 'ts': time.time()}

        return {
            'ranking_type': 'filtered',
            'month': current_month,
            'year': current_year,
            'total_users': total,
            'has_next': has_next,
            'current_user_rank': current_user_rank,
            'rankings': page
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching attendance ranking: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# SERVER TIME (Cambodia / UTC+7) — used by mobile app to prevent clock cheating
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/server-time")
async def get_server_time(
    current_user: User = Depends(get_current_active_employee)
):
    """
    Return the authoritative server time in Cambodia timezone (UTC+7 / Asia/Phnom_Penh).
    The mobile app must use this time for session-window checks so users cannot
    manipulate their device clock to bypass attendance restrictions.
    """
    from zoneinfo import ZoneInfo          # Python 3.9+
    cambodia_tz = ZoneInfo("Asia/Phnom_Penh")
    now_cambodia = datetime.now(cambodia_tz)

    return {
        "hour":   now_cambodia.hour,
        "minute": now_cambodia.minute,
        "second": now_cambodia.second,
        "date":   now_cambodia.strftime("%Y-%m-%d"),
        "timezone": "Asia/Phnom_Penh",
        "utc_offset": "+07:00",
        "iso8601": now_cambodia.isoformat(),
    }


@router.get("/user/schedule")
async def get_user_schedule(
    user_id: Optional[int] = Query(None, description="Optional user ID to get schedule for another user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get user's assigned attendance schedule with check-in/check-out times.
    """
    try:
        target_user = current_user
        if user_id is not None:
            target_user = db.query(User).filter(User.id == user_id).first()
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found")
        _require_attendance_processing(db, target_user)

        logger.debug("Schedule request for user_id: %s", target_user.id)

        # First check if required tables exist
        try:
            # Check attendance_schedules table
            db.execute(text("SELECT 1 FROM attendance_schedules LIMIT 1")).fetchone()
        except Exception as e:
            print(f"attendance_schedules table issue: {e}")
            return {
                'has_schedule': False,
                'message': 'ប្រព័ន្ធកាលវិភាគមិនទាន់បានដំឡើង។'
            }

        try:
            # Check attendance_user_assignments table
            db.execute(text("SELECT 1 FROM attendance_user_assignments LIMIT 1")).fetchone()
        except Exception as e:
            print(f"attendance_user_assignments table issue: {e}")
            return {
                'has_schedule': False,
                'message': 'ប្រព័ន្ធកាលវិភាគមិនទាន់បានដំឡើង។'
            }

        schedule = get_effective_schedule(db, target_user, date.today())
        
        if not schedule:
            # Check if user has any assignments at all to give appropriate error message
            try:
                check_assignments_query = """
                    SELECT COUNT(*) as assignment_count
                    FROM attendance_user_assignments
                    WHERE user_id = :user_id
                """
                assignment_count = db.execute(text(check_assignments_query), {"user_id": target_user.id}).scalar()
            except Exception as e:
                print(f"Error checking assignments: {e}")
                assignment_count = 0

            if assignment_count == 0:
                return {
                    'has_schedule': False,
                    'message': 'អ្នកមិនទាន់បានចាត់ចែងកាលវិភាគនៅឡើយទេ។ សូមទាក់ទងអ្នកគ្រប់គ្រងរបស់អ្នក។'
                }

            return {
                'has_schedule': False,
                'message': 'No active schedule assigned'
            }

        schedule_data = {
            'schedule_id': schedule.id,
            'schedule_name': schedule.name,
            'schedule_type': schedule.type,
            'weekly_config': schedule.weekly_config if schedule.weekly_config else {}
        }

        # Parse the weekly config to show daily schedules
        daily_schedules = {}
        weekly_config = schedule_data['weekly_config']

        if isinstance(weekly_config, str):
            import json
            weekly_config = json.loads(weekly_config)

        days_map = {
            'mon': 'Monday', 'tue': 'Tuesday', 'wed': 'Wednesday',
            'thu': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday', 'sun': 'Sunday'
        }

        for day_key, day_name in days_map.items():
            if day_key in weekly_config:
                day_config = weekly_config[day_key]
                if isinstance(day_config, dict):
                    mode = day_config.get('mode', 'full_day')
                    # Determine active status based on mode
                    active = mode != 'not_working'
                    daily_schedules[day_name] = {
                        'active': active,
                        'mode': mode,
                        'sessions': day_config.get('sessions', [])
                    }
                else:
                    daily_schedules[day_name] = {
                        'active': True,
                        'mode': 'full_day',
                        'sessions': []
                    }
            else:
                daily_schedules[day_name] = {
                    'active': False,
                    'mode': 'not_working',
                    'sessions': []
                }

        return {
            'has_schedule': True,
            'schedule_info': schedule_data,
            'daily_schedules': daily_schedules
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching user schedule: {str(e)}")


@router.get("/user/daily-progress")
async def get_user_daily_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee)
):
    """
    Get user's attendance progress for today vs. expected schedule.
    """
    try:
        _require_attendance_processing(db, current_user)
        logger.debug("Daily progress request for user_id: %s", current_user.id)

        from datetime import date, datetime

        now_cambodia = datetime.now(CAMBODIA_TZ)
        today = now_cambodia.date()
        today_str = today.strftime('%Y-%m-%d')

        # Check if attendance_records table exists
        try:
            db.execute(text("SELECT 1 FROM attendance_records LIMIT 1")).fetchone()
        except Exception as e:
            print(f"attendance_records table issue: {e}")
            return {
                'date': today_str,
                'day_of_week': today.strftime('%a').lower(),
                'server_time_minutes': (
                    now_cambodia.hour * 60 + now_cambodia.minute
                ),
                'server_time_iso': now_cambodia.isoformat(),
                'completed_check_ins': 0,
                'completed_check_outs': 0,
                'expected_check_ins': 0,
                'expected_check_outs': 0,
                'progress_percentage': 0.0,
                'is_complete': False,
                'expected_sessions': [],
                'today_records': []
            }

        # Get today's attendance records
        today_records_query = """
            SELECT id, check_in_time, check_out_time, status, session_index,
                   schedule_id, scheduled_start, scheduled_end,
                   snapshot_late_grace_minutes, snapshot_allow_early_leave_mins
            FROM attendance_records
            WHERE user_id = :user_id AND attendance_date = :today
            ORDER BY check_in_time
        """

        today_records = db.execute(text(today_records_query), {
            "user_id": current_user.id,
            "today": today_str
        }).fetchall()

        logger.debug("Found %s records for today", len(today_records))

        enrollment = get_schedule_exception_enrollment(
            db,
            int(current_user.id),
            today,
        )
        selectable_exceptions = (
            []
            if today_records or enrollment is not None
            else available_self_enrollment_exceptions(db, current_user, today)
        )

        def _employee_exception_choice(row: AttendanceScheduleException) -> Dict[str, Any]:
            title_en, title_km = _bilingual_text_pair(
                getattr(row, "title_en", None),
                getattr(row, "title_km", None),
                fallback=row.reason or "Special schedule",
            )
            reason_en, reason_km = _bilingual_text_pair(
                getattr(row, "reason_en", None),
                getattr(row, "reason_km", None),
                fallback=row.reason,
            )
            return {
                "id": int(row.id),
                "exception_type": row.exception_type,
                "title": title_en or title_km or "Special schedule",
                "title_en": title_en,
                "title_km": title_km,
                "reason": row.reason,
                "reason_en": reason_en,
                "reason_km": reason_km,
                "sessions": _parse_exception_sessions(row.sessions),
                "date": today.isoformat(),
            }

        selected_choice = None
        if enrollment is not None:
            selected_row = (
                db.query(AttendanceScheduleException)
                .filter(
                    AttendanceScheduleException.id == enrollment.exception_id
                )
                .first()
            )
            if selected_row is not None:
                selected_choice = _employee_exception_choice(selected_row)

        # Get user's schedule for today (includes daily exceptions)
        day_of_week = today.strftime('%a').lower()  # 'mon', 'tue', etc.
        schedule = get_effective_schedule(db, current_user, today)
        day_info = get_effective_day_attendance(
            db, current_user, today, schedule=schedule
        )
        expected_sessions = list(day_info.get("sessions") or [])
        schedule_exception_payload = None
        if day_info.get("source") == "exception":
            schedule_exception_payload = {
                "id": day_info.get("exception_id"),
                "type": day_info.get("exception_type"),
                "reason": day_info.get("exception_reason"),
                "date": day_info.get("exception_date"),
                "day_type": day_info.get("day_type"),
            }

        logger.debug("Expected sessions for %s: %s", day_of_week, expected_sessions)

        # Get system settings used by check-in/out and session mapping.
        late_grace_minutes = 15  # Default
        allow_early_clock_in_mins_raw: Optional[int] = None
        allow_late_clock_out_mins = 0
        min_minutes_before_checkout = 30
        session_transition_wait_mins = 10
        allow_early_leave_mins = 0
        allow_makeup_missing_sessions = False
        per_session_early_list: Optional[List[int]] = None
        try:
            orm_settings = db.query(AttendanceSystemSettings).first()
            if orm_settings:
                if orm_settings.late_grace_minutes is not None:
                    late_grace_minutes = int(orm_settings.late_grace_minutes)
                allow_early_clock_in_mins_raw = orm_settings.allow_early_clock_in_mins
                if orm_settings.allow_late_clock_out_mins is not None:
                    allow_late_clock_out_mins = int(orm_settings.allow_late_clock_out_mins)
                if orm_settings.min_minutes_before_checkout is not None:
                    min_minutes_before_checkout = int(orm_settings.min_minutes_before_checkout)
                if getattr(orm_settings, "session_transition_wait_mins", None) is not None:
                    session_transition_wait_mins = max(
                        0,
                        min(60, int(orm_settings.session_transition_wait_mins)),
                    )
                if orm_settings.allow_early_leave_mins is not None:
                    allow_early_leave_mins = int(orm_settings.allow_early_leave_mins)
                allow_makeup_missing_sessions = bool(
                    getattr(orm_settings, "allow_makeup_missing_sessions", False)
                )
                per_session_early_list = _coerce_per_session_early_clock_in_list(
                    getattr(orm_settings, "per_session_early_clock_in_mins", None)
                )
        except Exception as e:
            print(f"Error fetching system settings: {e}")

        allow_early_clock_in_mins = _normalize_early_clock_in_mins(
            allow_early_clock_in_mins_raw
        )
        early_entry_buffer = allow_early_clock_in_mins

        def _time_to_minutes(hhmm: str):
            try:
                raw = str(hhmm).strip()
                if not raw:
                    return None
                for fmt in ("%H:%M", "%H:%M:%S"):
                    try:
                        parsed = datetime.strptime(raw, fmt)
                        return parsed.hour * 60 + parsed.minute
                    except Exception:
                        pass
                for fmt in ("%I:%M %p", "%I:%M:%S %p"):
                    try:
                        parsed = datetime.strptime(raw.upper(), fmt)
                        return parsed.hour * 60 + parsed.minute
                    except Exception:
                        pass
                parts = raw.split(":")
                if len(parts) >= 2:
                    return int(parts[0]) * 60 + int(parts[1][:2])
                return None
            except Exception:
                return None

        def _find_session_index_for_minutes(actual_minutes: int, include_late_buffer: bool = True) -> int:
            best_idx = -1
            best_start = None
            for i, sess in enumerate(expected_sessions):
                start_m = _time_to_minutes(sess.get('start', ''))
                end_m = _time_to_minutes(sess.get('end', ''))
                if start_m is None or end_m is None:
                    continue
                window_open = _session_checkin_window_open_minutes(
                    i,
                    start_m,
                    expected_sessions=expected_sessions,
                    time_to_minutes=_time_to_minutes,
                    global_early_mins=early_entry_buffer,
                    per_session_mins=per_session_early_list,
                )
                window_close = end_m + (allow_late_clock_out_mins if include_late_buffer else 0)
                if window_open <= actual_minutes <= window_close:
                    if actual_minutes >= start_m:
                        if best_start is None or start_m > best_start:
                            best_start = start_m
                            best_idx = i
                    else:
                        if best_start is None or start_m < best_start:
                            best_start = start_m
                            best_idx = i
            return best_idx

        session_state = [
            {"has_in": False, "has_out": False, "check_in_time": None, "check_out_time": None}
            for _ in range(len(expected_sessions))
        ]
        unmatched_records = []

        # When makeup is enabled, assign records to sessions based on completion
        # order. More than one session can be partially open when an earlier
        # missed session has passed its checkout deadline and the user continues
        # with a later current session.
        if allow_makeup_missing_sessions:
            # Sort records by check-in time (earliest first)
            sorted_records = sorted(today_records, key=lambda r: r[1] if r[1] else datetime.max)

            for record in sorted_records:
                rec_id = record[0]
                rec_in = record[1]
                rec_out = record[2]
                rec_session_idx = record[4] if len(record) > 4 else None
                placed = False

                preferred_indexes = []
                if rec_session_idx is not None:
                    try:
                        preferred_indexes.append(int(rec_session_idx) - 1)
                    except Exception:
                        pass
                preferred_indexes.extend(
                    i for i in range(len(session_state)) if i not in preferred_indexes
                )

                # Prefer the stored session index, then fall back to earliest
                # available session for legacy rows.
                for s_idx in preferred_indexes:
                    if s_idx < 0 or s_idx >= len(session_state):
                        continue
                    # If this is a complete record (has both in and out)
                    if rec_in is not None and rec_out is not None:
                        if not session_state[s_idx]["has_in"] and not session_state[s_idx]["has_out"]:
                            session_state[s_idx]["has_in"] = True
                            session_state[s_idx]["has_out"] = True
                            session_state[s_idx]["check_in_time"] = session_state[s_idx]["check_in_time"] or rec_in
                            session_state[s_idx]["check_out_time"] = session_state[s_idx]["check_out_time"] or rec_out
                            placed = True
                            break
                    # If this is an open check-in (in but no out), bind it to
                    # the next session that does not have a check-in yet.
                    elif rec_in is not None and rec_out is None:
                        if not session_state[s_idx]["has_in"]:
                            session_state[s_idx]["has_in"] = True
                            session_state[s_idx]["check_in_time"] = rec_in
                            placed = True
                            break
                    # If this is a checkout-only record (shouldn't happen, but handle it)
                    elif rec_out is not None and rec_in is None:
                        if session_state[s_idx]["has_in"] and not session_state[s_idx]["has_out"]:
                            session_state[s_idx]["has_out"] = True
                            session_state[s_idx]["check_out_time"] = rec_out
                            placed = True
                            break
                
                if not placed:
                    unmatched_records.append((rec_id, rec_in, rec_out))
        else:
            # Normal mode: assign records by check-in/out time
            for idx, record in enumerate(today_records):
                rec_id = record[0]
                rec_in = record[1]
                rec_out = record[2]
                rec_session_idx = record[4] if len(record) > 4 else None
                s_idx = -1
                if rec_session_idx is not None:
                    try:
                        s_idx = int(rec_session_idx) - 1
                    except Exception:
                        s_idx = -1
                if s_idx < 0 and rec_in is not None:
                    in_min = rec_in.hour * 60 + rec_in.minute
                    s_idx = _find_session_index_for_minutes(in_min, include_late_buffer=False)
                elif s_idx < 0 and rec_out is not None:
                    out_min = rec_out.hour * 60 + rec_out.minute
                    s_idx = _find_session_index_for_minutes(out_min, include_late_buffer=True)

                if s_idx < 0 or s_idx >= len(session_state):
                    unmatched_records.append((rec_id, rec_in, rec_out))
                    continue

                if rec_in is not None:
                    session_state[s_idx]["has_in"] = True
                    session_state[s_idx]["check_in_time"] = rec_in
                if rec_out is not None:
                    session_state[s_idx]["has_out"] = True
                    session_state[s_idx]["check_out_time"] = rec_out

        # Makeup records can be captured outside session windows (e.g. at night).
        # Fallback-map unmatched records sequentially to incomplete sessions so
        # UI can reliably identify Session 1 vs Session 2 state.
        for _, rec_in, rec_out in unmatched_records:
            if rec_in is not None and rec_out is not None:
                # Completed pair -> assign to earliest not-complete session.
                for i, state in enumerate(session_state):
                    if not state["has_in"] and not state["has_out"]:
                        state["has_in"] = True
                        state["has_out"] = True
                        state["check_in_time"] = state["check_in_time"] or rec_in
                        state["check_out_time"] = state["check_out_time"] or rec_out
                        break
                continue

            if rec_in is not None:
                # Open check-in -> assign to earliest session without check-in.
                for i, state in enumerate(session_state):
                    if not state["has_in"]:
                        state["has_in"] = True
                        state["check_in_time"] = state["check_in_time"] or rec_in
                        break
                continue

            if rec_out is not None:
                # Check-out only record (edge case) -> assign to earliest session
                # that has check-in but no check-out; otherwise next incomplete.
                target_idx = -1
                for i, state in enumerate(session_state):
                    if state["has_in"] and not state["has_out"]:
                        target_idx = i
                        break
                if target_idx < 0:
                    for i, state in enumerate(session_state):
                        if not state["has_out"]:
                            target_idx = i
                            break
                if target_idx >= 0:
                    session_state[target_idx]["has_out"] = True
                    session_state[target_idx]["check_out_time"] = (
                        session_state[target_idx]["check_out_time"] or rec_out
                    )

        # Approved leave today → covered sessions are excused, not missing.
        today_leave_entry = (
            get_approved_leave_map(db, [int(current_user.id)], today, today)
            .get(int(current_user.id), {})
            .get(today)
        )

        session_progress = []
        completed_check_ins = 0
        completed_check_outs = 0
        covered_sessions = 0

        for idx, session in enumerate(expected_sessions, 1):
            state = session_state[idx - 1]
            check_in_completed = state["has_in"]
            check_out_completed = state["has_out"]

            session_on_leave = leave_covers_session(today_leave_entry, idx)
            if session_on_leave:
                covered_sessions += 1
                session_status = 'on_leave'
            elif check_in_completed and check_out_completed:
                completed_check_ins += 1
                completed_check_outs += 1
                session_status = 'completed'
            elif check_in_completed or check_out_completed:
                if check_in_completed:
                    completed_check_ins += 1
                if check_out_completed:
                    completed_check_outs += 1
                session_status = 'partial'
            else:
                session_status = 'pending'

            session_progress.append({
                'session_index': idx,
                'start_time': session['start'],
                'end_time': session['end'],
                # Leave has display/progress precedence. The raw audit record is
                # retained below in today_records and reappears after cancel.
                'check_in_completed': False if session_on_leave else check_in_completed,
                'check_in_time': None if session_on_leave else (
                    state["check_in_time"].isoformat() if state["check_in_time"] else None
                ),
                'check_out_completed': False if session_on_leave else check_out_completed,
                'check_out_time': None if session_on_leave else (
                    state["check_out_time"].isoformat() if state["check_out_time"] else None
                ),
                'on_leave': session_on_leave,
                'status': session_status
            })

        logger.debug("Session progress created: %s sessions", len(session_progress))

        expected_check_ins = max(0, len(expected_sessions) - covered_sessions)
        expected_check_outs = expected_check_ins
        progress_percentage = (
            round((completed_check_ins / expected_check_ins) * 100, 1)
            if expected_check_ins > 0
            else (100.0 if covered_sessions > 0 else 0.0)
        )

        return {
            'date': today_str,
            'day_of_week': day_of_week,
            # Quick Attendance uses this value only for optional prompts. The
            # mutation endpoint remains authoritative, but returning the time
            # with the daily context avoids a second network request and keeps
            # every phone on the same clock.
            'server_time_minutes': now_cambodia.hour * 60 + now_cambodia.minute,
            'server_time_iso': now_cambodia.isoformat(),
            'completed_check_ins': completed_check_ins,
            'completed_check_outs': completed_check_outs,
            'expected_check_ins': expected_check_ins,
            'expected_check_outs': expected_check_outs,
            'progress_percentage': progress_percentage,
            'is_complete': completed_check_ins >= expected_check_ins and completed_check_outs >= expected_check_outs,
            'expected_sessions': expected_sessions,
            'schedule_exception': schedule_exception_payload,
            'schedule_exception_selection': {
                # Lock becomes permanent as soon as the first attendance row is
                # created. An enrollment is also locked even before serialization
                # so retries always preserve the employee's first choice.
                'locked': bool(today_records) or enrollment is not None,
                'selected': selected_choice,
                'available': [
                    _employee_exception_choice(row)
                    for row in selectable_exceptions
                ],
            },
            'leave': (
                {
                    'fraction': today_leave_entry['fraction'],
                    'full_day': today_leave_entry['full_day'],
                    'session_indexes': sorted(today_leave_entry['session_indexes'] or set()),
                    'leave_type': today_leave_entry['leave_type'],
                }
                if today_leave_entry
                else None
            ),
            'session_progress': session_progress,  # New detailed breakdown
            'check_events': session_progress,
            'today_records': [{
                'id': int(r[0]) if r[0] is not None else 0,
                'check_in_time': r[1].isoformat() if r[1] else None,
                'check_out_time': r[2].isoformat() if r[2] else None,
                'status': str(r[3]) if r[3] else 'unknown',
                'session_index': int(r[4]) if len(r) > 4 and r[4] is not None else None,
                'schedule_id': int(r[5]) if len(r) > 5 and r[5] is not None else None,
                'scheduled_start': str(r[6]) if len(r) > 6 and r[6] else None,
                'scheduled_end': str(r[7]) if len(r) > 7 and r[7] else None,
                'snapshot_late_grace_minutes': int(r[8]) if len(r) > 8 and r[8] is not None else None,
                'snapshot_allow_early_leave_mins': int(r[9]) if len(r) > 9 and r[9] is not None else None,
            } for r in today_records],
            'late_grace_minutes': late_grace_minutes,
            'system_settings': {
                'late_grace_minutes': late_grace_minutes,
                'allow_early_clock_in_mins': allow_early_clock_in_mins,
                'per_session_early_clock_in_mins': per_session_early_list,
                'allow_late_clock_out_mins': allow_late_clock_out_mins,
                'min_minutes_before_checkout': min_minutes_before_checkout,
                'session_transition_wait_mins': session_transition_wait_mins,
                'allow_early_leave_mins': allow_early_leave_mins,
                'allow_makeup_missing_sessions': allow_makeup_missing_sessions,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching daily progress: {str(e)}")


# =============================================================================
# Telegram Notification Settings Endpoints
# =============================================================================

def _validate_notification_only_destination(
    db: Session,
    chat_id: Optional[str],
    label: str,
) -> None:
    """Reject known chats that are inactive or assigned as General Groups.

    A missing row remains valid for backwards compatibility with installations
    that saved a chat ID before tracked-chat roles were introduced.
    """
    if not chat_id:
        return
    try:
        row = db.execute(text("""
            SELECT bot_role, is_active
            FROM telegram_tracked_chats
            WHERE chat_id = :chat_id
            LIMIT 1
        """), {"chat_id": str(chat_id)}).fetchone()
    except Exception:
        return
    if row and (not bool(row[1]) or row[0] != "notification_only"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be an active Notification Only group",
        )

@router.get("/admin/telegram-settings", response_model=TelegramAttendanceSettingsResponse)
async def get_telegram_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """
    Get Telegram notification settings for attendance.
    Requires admin privileges.
    """
    try:
        _require_attendance_admin(db, current_user)

        settings = db.query(TelegramAttendanceSettings).first()

        if not settings:
            # Create default settings if not exist
            settings = TelegramAttendanceSettings(enabled=False)
            db.add(settings)
            db.commit()
            db.refresh(settings)

        return settings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Telegram settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load settings: {str(e)}"
        )


@router.post("/admin/telegram-settings", response_model=TelegramAttendanceSettingsResponse)
async def update_telegram_settings(
    settings_update: TelegramAttendanceSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """
    Update Telegram notification settings for attendance.
    Requires admin privileges.
    """
    _require_attendance_admin(db, current_user)

    settings = db.query(TelegramAttendanceSettings).first()

    if not settings:
        settings = TelegramAttendanceSettings()
        db.add(settings)

    # Update fields. Branch routes are child rows and are handled separately
    # after validating every branch and Telegram destination.
    update_data = settings_update.model_dump(exclude_unset=True)
    branch_routes_provided = "branch_routes" in update_data
    branch_routes_data = update_data.pop("branch_routes", [])

    # Validate and normalize bot token if provided.
    if "bot_token" in update_data:
        bot_token = str(update_data["bot_token"] or "").strip()
        if bot_token:
            # Validate the bot token
            validation = await TelegramNotificationService.validate_bot_token(bot_token)
            if not validation.get("valid"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid bot token: {validation.get('error', 'Unknown error')}"
                )
            update_data["bot_token"] = bot_token
        else:
            update_data["bot_token"] = None

    for chat_field in ("chat_id", "leave_chat_id"):
        if chat_field in update_data:
            normalized_chat_id = str(update_data[chat_field] or "").strip()
            update_data[chat_field] = normalized_chat_id or None

    def effective(field: str):
        if field in update_data:
            return update_data[field]
        return getattr(settings, field, None)

    leave_routing_mode = normalize_leave_routing_mode(
        effective("leave_routing_mode")
    )
    # Persist the normalized default when an old database row contains NULL.
    update_data["leave_routing_mode"] = leave_routing_mode
    branch_routing_mode = normalize_branch_routing_mode(
        effective("branch_routing_mode")
    )
    update_data["branch_routing_mode"] = branch_routing_mode

    effective_bot_token = str(effective("bot_token") or "").strip() or None
    attendance_chat_id = str(effective("chat_id") or "").strip() or None
    leave_chat_id = str(effective("leave_chat_id") or "").strip() or None
    attendance_enabled = bool(effective("enabled"))
    leave_requests_enabled = bool(effective("notify_leave_requests"))
    leave_decisions_enabled = bool(effective("notify_leave_decisions"))
    any_leave_enabled = leave_requests_enabled or leave_decisions_enabled

    if (
        leave_routing_mode == "separate"
        and leave_chat_id
        and leave_chat_id == attendance_chat_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose a different Leave group when separate delivery is selected",
        )

    if attendance_enabled:
        if not effective_bot_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bot token is required to enable notifications"
            )
        if not attendance_chat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An Attendance notification group is required to enable notifications"
            )
        _validate_notification_only_destination(
            db, attendance_chat_id, "Attendance destination"
        )

    if any_leave_enabled:
        if not effective_bot_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bot token is required to enable leave notifications",
            )
        effective_leave_target = (
            leave_chat_id
            if leave_routing_mode == "separate"
            else attendance_chat_id
        )
        if not effective_leave_target:
            target_name = (
                "Leave notification group"
                if leave_routing_mode == "separate"
                else "Attendance notification group"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{target_name} is required to enable leave notifications",
            )
        _validate_notification_only_destination(
            db, effective_leave_target, "Leave destination"
        )

    normalized_branch_routes: list[dict[str, Any]] = []
    if branch_routes_provided:
        seen_branch_ids: set[int] = set()
        for raw_route in branch_routes_data:
            branch_id = int(raw_route.get("branch_id") or 0)
            if branch_id in seen_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Branch {branch_id} appears more than once",
                )
            seen_branch_ids.add(branch_id)
            if not db.query(Branch.id).filter(Branch.id == branch_id).first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Branch {branch_id} does not exist",
                )
            attendance_route = str(
                raw_route.get("attendance_chat_id") or ""
            ).strip() or None
            leave_route = str(raw_route.get("leave_chat_id") or "").strip() or None
            if attendance_route:
                _validate_notification_only_destination(
                    db,
                    attendance_route,
                    f"Attendance destination for branch {branch_id}",
                )
            if leave_route:
                _validate_notification_only_destination(
                    db,
                    leave_route,
                    f"Leave destination for branch {branch_id}",
                )
            # Empty rows do not override the global fallback and need not be
            # persisted.
            if attendance_route or leave_route:
                normalized_branch_routes.append(
                    {
                        "branch_id": branch_id,
                        "attendance_chat_id": attendance_route,
                        "leave_chat_id": leave_route,
                    }
                )

    # Apply updates
    for field, value in update_data.items():
        setattr(settings, field, value)

    if branch_routes_provided:
        settings.branch_routes.clear()
        # Delete old rows before inserting replacements so the per-branch
        # unique constraint cannot be hit when a destination is edited.
        db.flush()
        for route in normalized_branch_routes:
            settings.branch_routes.append(
                TelegramBranchNotificationRoute(**route)
            )

    db.commit()
    db.refresh(settings)
    # Ensure response serialization sees the replaced child collection.
    _ = settings.branch_routes

    if settings.bot_token:
        try:
            import httpx
            import os

            webhook_url = (
                os.environ.get("TELEGRAM_WEBHOOK_URL")
                or "https://pamais.duckdns.org/api/v1/telegram/"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{settings.bot_token}/setWebhook",
                    json={
                        "url": webhook_url,
                        "allowed_updates": [
                            "message",
                            "edited_message",
                            "channel_post",
                            "edited_channel_post",
                            "my_chat_member",
                            "chat_member",
                            "callback_query",
                        ],
                    },
                )
                commands_url = (
                    f"https://api.telegram.org/bot{settings.bot_token}/setMyCommands"
                )
                await client.post(
                    commands_url,
                    json={"scope": {"type": "default"}, "commands": []},
                )
                await client.post(
                    commands_url,
                    json={
                        "scope": {"type": "all_private_chats"},
                        "commands": [
                            {
                                "command": "login",
                                "description": "Login to PAMA app",
                            },
                            {
                                "command": "myid",
                                "description": "Get your personal Telegram ID",
                            },
                            {
                                "command": "help",
                                "description": "Show help message",
                            },
                        ],
                    },
                )
        except Exception as e:
            logger.warning(f"Telegram settings saved but webhook auto-setup failed: {e}")

    return settings


@router.post("/admin/telegram-settings/test")
async def test_telegram_notification(
    request: TelegramTestMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """
    Send a test Telegram notification.
    Requires admin privileges and configured settings.
    """
    _require_attendance_admin(db, current_user)

    settings = db.query(TelegramAttendanceSettings).first()

    if not settings or not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram notifications are not enabled"
        )

    if not settings.bot_token or not settings.chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot token and chat ID must be configured"
        )

    # Send test message
    result = await TelegramNotificationService.send_test_message(
        bot_token=settings.bot_token,
        chat_id=settings.chat_id,
    )

    if result.get("success"):
        return {"message": "Test notification sent successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test message: {result.get('error', 'Unknown error')}"
        )


async def send_attendance_telegram_notification(
    db: Session,
    employee_name: str,
    action_type: str,
    check_time: datetime,
    status: Optional[str] = None,
    late_minutes: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    location_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    notes: Optional[str] = None,
):
    """
    Background task to send attendance notification to Telegram.
    Called after successful check-in or check-out.
    """
    try:
        settings = db.query(TelegramAttendanceSettings).first()

        if not settings or not settings.enabled:
            return

        if not settings.bot_token:
            return

        destination_chat_id = resolve_attendance_notification_chat_id(
            settings,
            db=db,
            branch_id=branch_id,
        )
        if not destination_chat_id:
            return

        await TelegramNotificationService.send_attendance_notification(
            bot_token=settings.bot_token,
            chat_id=destination_chat_id,
            employee_name=employee_name,
            action_type=action_type,
            check_time=check_time,
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            notes=notes,
            status=status,  # Pass status (late, early_leave, present, etc.)
            late_minutes=late_minutes,  # Pass late minutes if applicable
            duration_seconds=duration_seconds,
        )
    except Exception as e:
        logger.error(f"Error in Telegram notification background task: {str(e)}")
        # Don't rethrow - this is a background task

@router.post("/admin/manual-attendance/bulk", status_code=status.HTTP_201_CREATED)
def admin_manual_attendance_bulk(
    request: ManualAttendanceBulkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_employee),
):
    """
    Manually insert bulk attendance sessions for a user on a given date.
    This bypasses strict security (mock location, time boundaries) 
    and handles multiple sessions (e.g. Session 1, Session 2) correctly.
    """
    _require_attendance_admin(db, current_user)

    user = (
        db.query(User)
        .filter(User.id == request.user_id, User.status == 1)  # type: ignore
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _require_attendance_processing(db, user)

    branch = db.query(Branch).filter(Branch.id == request.branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    user_primary_branch = int(getattr(user, "workplace", 0) or 0)
    branch_is_allowed = user_primary_branch == int(request.branch_id)
    if not branch_is_allowed:
        branch_is_allowed = bool(
            db.execute(
                text(
                    "SELECT 1 FROM attendance__allowed_branches "
                    "WHERE user_id = :user_id AND branch_id = :branch_id LIMIT 1"
                ),
                {"user_id": int(user.id), "branch_id": int(request.branch_id)},
            ).scalar()
        )
    if not branch_is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The selected branch is not assigned or allowed for this employee. "
                "Grant branch access before recording manual attendance."
            ),
        )

    try:
        att_date = datetime.strptime(request.attendance_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format, use YYYY-MM-DD")

    if att_date > datetime.now(CAMBODIA_TZ).date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Future attendance cannot be recorded",
        )
    holiday_name = db.execute(
        text("SELECT name FROM holidays WHERE date = :attendance_date LIMIT 1"),
        {"attendance_date": att_date},
    ).scalar()
    if holiday_name is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Attendance cannot be recorded on a holiday ({holiday_name})",
        )

    manual_settings = db.query(AttendanceSystemSettings).first()
    manual_schedule = get_effective_schedule(db, user, target_date=att_date)
    day_info = get_effective_day_attendance(
        db, user, att_date, schedule=manual_schedule
    )
    manual_expected_sessions: List[Dict[str, Any]] = list(day_info.get("sessions") or [])
    if not day_info.get("is_active_day") or not manual_expected_sessions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attendance cannot be recorded because this is a non-working day",
        )

    validated_sessions: List[Tuple[int, Any]] = []
    seen_session_indexes: set[int] = set()
    for fallback_session_idx, sess in enumerate(request.sessions, start=1):
        if not sess.check_in_time and not sess.check_out_time:
            continue
        session_idx = int(sess.session_index or fallback_session_idx)
        if session_idx > len(manual_expected_sessions):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_idx} is not configured for this employee on this date",
            )
        if session_idx in seen_session_indexes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_idx} was submitted more than once",
            )
        seen_session_indexes.add(session_idx)
        if sess.check_out_time is not None and sess.check_in_time is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_idx} cannot have a check-out without a check-in",
            )
        for label, value in (
            ("check-in", sess.check_in_time),
            ("check-out", sess.check_out_time),
        ):
            if value is not None and value.date() != att_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Session {session_idx} {label} must be on {att_date.isoformat()}",
                )
        if sess.check_in_time is not None and sess.check_out_time is not None:
            try:
                invalid_order = sess.check_out_time < sess.check_in_time
            except TypeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Session {session_idx} check-in and check-out must use "
                        "the same timezone format"
                    ),
                )
            if invalid_order:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Session {session_idx} check-out cannot be before check-in",
                )
        validated_sessions.append((session_idx, sess))

    if not validated_sessions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid sessions provided",
        )

    if db.get_bind().dialect.name in {"mysql", "mariadb", "postgresql"}:
        db.execute(
            text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"),
            {"user_id": int(request.user_id)},
        ).fetchone()

    # Validation is complete; replacing existing rows is now safe and atomic.
    replaced_count = int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM attendance_records "
                "WHERE user_id = :uid AND attendance_date = :ad"
            ),
            {"uid": request.user_id, "ad": att_date},
        ).scalar()
        or 0
    )
    db.execute(
        text("DELETE FROM attendance_records WHERE user_id = :uid AND attendance_date = :ad"),
        {"uid": request.user_id, "ad": att_date}
    )

    total_inserted = 0
    for session_idx, sess in validated_sessions:
        work_hours = 0.0
        if sess.check_in_time and sess.check_out_time:
            td = sess.check_out_time - sess.check_in_time
            work_hours = td.total_seconds() / 3600.0

        expected_session = (
            manual_expected_sessions[session_idx - 1]
            if session_idx - 1 < len(manual_expected_sessions)
            else {}
        )
        scheduled_start = _snapshot_time_value(
            sess.scheduled_start or expected_session.get("start")
        )
        scheduled_end = _snapshot_time_value(
            sess.scheduled_end or expected_session.get("end")
        )
        late_grace_minutes = int(
            getattr(manual_settings, "late_grace_minutes", 15) or 0
        )
        allow_early_leave_mins = int(
            getattr(manual_settings, "allow_early_leave_mins", 0) or 0
        )
        manual_status = "present"
        if sess.check_in_time is not None:
            check_in_minutes = (
                sess.check_in_time.hour * 60 + sess.check_in_time.minute
            )
            scheduled_start_minutes = _hhmm_to_minutes(scheduled_start)
            if (
                scheduled_start_minutes is not None
                and check_in_minutes > scheduled_start_minutes + late_grace_minutes
            ):
                manual_status = "late"
        if sess.check_out_time is not None:
            check_out_minutes = (
                sess.check_out_time.hour * 60 + sess.check_out_time.minute
            )
            scheduled_end_minutes = _hhmm_to_minutes(scheduled_end)
            if (
                scheduled_end_minutes is not None
                and check_out_minutes
                < scheduled_end_minutes - allow_early_leave_mins
            ):
                manual_status = "early_leave"
        expected_session_count = max(1, len(manual_expected_sessions))
        attendance_event_count = int(sess.check_in_time is not None) + int(
            sess.check_out_time is not None
        )
        earned_percentage = (
            100.0 / (expected_session_count * 2)
        ) * attendance_event_count
        stmt = text("""
            INSERT INTO attendance_records (
                user_id, attendance_date, session_index, schedule_id,
                scheduled_start, scheduled_end, snapshot_late_grace_minutes,
                snapshot_allow_early_leave_mins,
                check_in_time, check_in_latitude, check_in_longitude, check_in_branch_id,
                check_out_time, check_out_latitude, check_out_longitude, check_out_branch_id,
                status, work_hours, earned_percentage, notes, is_mock_location
            ) VALUES (
                :uid, :ad, :session_index, :schedule_id,
                :scheduled_start, :scheduled_end, :late_grace_minutes,
                :allow_early_leave_mins,
                :cit, :cil, :cilo, :cib,
                :cot, :col, :colo, :cob,
                :attendance_status, :wh, :earned_percentage, :no, 0
            )
        """)

        db.execute(stmt, {
            "uid": request.user_id,
            "ad": att_date,
            "session_index": session_idx,
            "schedule_id": int(manual_schedule.id) if manual_schedule else None,  # type: ignore[arg-type]
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
            "late_grace_minutes": late_grace_minutes,
            "allow_early_leave_mins": allow_early_leave_mins,
            "cit": sess.check_in_time,
            "cil": sess.check_in_latitude,
            "cilo": sess.check_in_longitude,
            "cib": request.branch_id if sess.check_in_time else None,
            "cot": sess.check_out_time,
            "col": sess.check_out_latitude,
            "colo": sess.check_out_longitude,
            "cob": request.branch_id if sess.check_out_time else None,
            "attendance_status": manual_status,
            "wh": work_hours,
            "earned_percentage": round(earned_percentage, 2),
            "no": request.note or f"Manual Session {session_idx}"
        })
        total_inserted += 1

    db.add(
        AttendanceAuditLog(
            user_id=int(current_user.id),
            user_name=(
                str(getattr(current_user, "eName", None) or "").strip()
                or str(getattr(current_user, "username", None) or current_user.id)
            ),
            user_role="attendance_admin",
            action_type="REPLACE",
            entity_type="employee_attendance_day",
            entity_id=int(request.user_id),
            old_value=json.dumps(
                {"attendance_date": att_date.isoformat(), "records": replaced_count}
            ),
            new_value=json.dumps(
                {
                    "attendance_date": att_date.isoformat(),
                    "records": total_inserted,
                    "session_indexes": sorted(seen_session_indexes),
                }
            ),
            change_description=(
                f"Manual attendance replaced for employee #{request.user_id} "
                f"on {att_date.isoformat()}"
            ),
            branch_id=int(request.branch_id),
        )
    )
    db.commit()
    return {"message": f"Successfully recorded {total_inserted} manual attendance session(s)"}
