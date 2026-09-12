"""Single source of truth for employee attendance participation access."""

from dataclasses import dataclass
from threading import Lock
from typing import Dict, Iterable, Optional, Set

from sqlalchemy.orm import Session

from ..models.attendance_processing_rule import AttendanceProcessingRule
from ..models.user import User


DISABLED_MESSAGE = (
    "Attendance is not required for your account. "
    "You can still open the QR and Time tabs and use leave requests, history, "
    "and approvals. Check-in, attendance reports, ranking, and attendance "
    "notifications are unavailable. "
    "Please contact an administrator if you think this is a mistake."
)

_ensured_bind_ids: Set[int] = set()
_ensure_lock = Lock()


@dataclass(frozen=True)
class AttendanceProcessingAccess:
    enabled: bool
    user_enabled: bool
    department_enabled: bool
    disabled_by: Optional[str]
    message: str

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "user_enabled": self.user_enabled,
            "department_enabled": self.department_enabled,
            "disabled_by": self.disabled_by,
            "message": self.message,
        }


def ensure_attendance_processing_rules_table(db: Session) -> None:
    """Create the small policy table when a deployment has not run migration yet."""
    bind = db.get_bind()
    bind_id = id(bind)
    if bind_id in _ensured_bind_ids:
        return
    with _ensure_lock:
        if bind_id in _ensured_bind_ids:
            return
        AttendanceProcessingRule.__table__.create(bind=bind, checkfirst=True)
        _ensured_bind_ids.add(bind_id)


def _rule_values(
    db: Session,
    *,
    user_ids: Iterable[int] = (),
    department_ids: Iterable[int] = (),
) -> Dict[tuple[str, int], bool]:
    ensure_attendance_processing_rules_table(db)
    user_set = {int(value) for value in user_ids if value is not None}
    department_set = {int(value) for value in department_ids if value is not None}
    if not user_set and not department_set:
        return {}

    query = db.query(AttendanceProcessingRule)
    filters = []
    if user_set:
        filters.append(
            (AttendanceProcessingRule.scope_type == "user")
            & AttendanceProcessingRule.scope_id.in_(user_set)
        )
    if department_set:
        filters.append(
            (AttendanceProcessingRule.scope_type == "department")
            & AttendanceProcessingRule.scope_id.in_(department_set)
        )
    if len(filters) == 2:
        query = query.filter(filters[0] | filters[1])
    else:
        query = query.filter(filters[0])
    return {
        (str(row.scope_type), int(row.scope_id)): bool(row.is_enabled)
        for row in query.all()
    }


def get_attendance_processing_access(
    db: Session,
    user: User,
    *,
    rule_values: Optional[Dict[tuple[str, int], bool]] = None,
) -> AttendanceProcessingAccess:
    user_id = int(user.id)
    department_id = getattr(user, "departmentId", None)
    rules = rule_values
    if rules is None:
        rules = _rule_values(
            db,
            user_ids=[user_id],
            department_ids=[department_id] if department_id is not None else [],
        )
    user_enabled = rules.get(("user", user_id), True)
    department_enabled = (
        rules.get(("department", int(department_id)), True)
        if department_id is not None
        else True
    )
    enabled = bool(user_enabled and department_enabled)
    disabled_by = None
    if not department_enabled:
        disabled_by = "department"
    elif not user_enabled:
        disabled_by = "employee"
    return AttendanceProcessingAccess(
        enabled=enabled,
        user_enabled=bool(user_enabled),
        department_enabled=bool(department_enabled),
        disabled_by=disabled_by,
        message=(
            "Attendance processing is enabled for your account."
            if enabled
            else DISABLED_MESSAGE
        ),
    )


def enabled_user_ids(db: Session, users: Iterable[User]) -> Set[int]:
    user_list = list(users)
    rules = _rule_values(
        db,
        user_ids=[int(user.id) for user in user_list],
        department_ids=[
            int(user.departmentId)
            for user in user_list
            if getattr(user, "departmentId", None) is not None
        ],
    )
    return {
        int(user.id)
        for user in user_list
        if get_attendance_processing_access(db, user, rule_values=rules).enabled
    }


def filter_enabled_users(db: Session, users: Iterable[User]) -> list[User]:
    user_list = list(users)
    allowed = enabled_user_ids(db, user_list)
    return [user for user in user_list if int(user.id) in allowed]


def attendance_processing_rules_revision(db: Session) -> tuple[int, str]:
    """Small cache signature so policy changes invalidate every API worker."""
    ensure_attendance_processing_rules_table(db)
    rows = (
        db.query(
            AttendanceProcessingRule.scope_type,
            AttendanceProcessingRule.scope_id,
            AttendanceProcessingRule.is_enabled,
        )
        .order_by(
            AttendanceProcessingRule.scope_type,
            AttendanceProcessingRule.scope_id,
        )
        .all()
    )
    signature = "|".join(
        f"{scope}:{int(scope_id)}:{1 if enabled else 0}"
        for scope, scope_id, enabled in rows
    )
    return len(rows), signature


def set_attendance_processing_rule(
    db: Session,
    *,
    scope_type: str,
    scope_id: int,
    enabled: bool,
    updated_by: Optional[int],
) -> None:
    ensure_attendance_processing_rules_table(db)
    if scope_type not in {"user", "department"}:
        raise ValueError("Invalid attendance processing rule scope")
    row = (
        db.query(AttendanceProcessingRule)
        .filter(
            AttendanceProcessingRule.scope_type == scope_type,
            AttendanceProcessingRule.scope_id == int(scope_id),
        )
        .first()
    )
    if row is None:
        row = AttendanceProcessingRule(
            scope_type=scope_type,
            scope_id=int(scope_id),
        )
        db.add(row)
    row.is_enabled = bool(enabled)
    row.updated_by = int(updated_by) if updated_by is not None else None
