"""Detect accounts whose phone number is shared with another account.

A phone number is how users sign in via Telegram OTP, Firebase SMS and the
Telegram contact flow. When the same number sits on two accounts *of the same
kind* the system genuinely cannot tell who is knocking, and before this guard it
simply took whichever row the database returned first — so the same person could
land in a different account on different days.

Scope deliberately excludes the staff+parent pair: a teacher whose own child
attends the school legitimately appears in both tables, and the role button on
the login screen resolves that case. Only same-table duplicates are a data error
worth locking.

Detection compares *canonical* numbers on both sides. Matching a variation list
against the other row's stored string only works in one direction — ``096555444``
does not appear in the variations of ``+855 96 555 444`` — which would lock one
of the two duplicates and let the other straight in.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models import Parent, User
from ..utils.phone import canonical_phone

logger = logging.getLogger(__name__)

# Machine-readable marker the Flutter app branches on to show the locked dialog.
PHONE_CONFLICT_CODE = "phone_linked_to_multiple_accounts"

# The index is rebuilt from a full (but tiny) scan of the two phone columns.
# /me runs on every app launch, so the result is memoised per worker. Staleness
# is bounded by this TTL, and administrators who edit a phone should call
# invalidate_cache() so the fix takes effect immediately rather than in a minute.
_CACHE_TTL_SECONDS = 60

_lock = threading.Lock()
_cache: Dict[str, object] = {"built_at": 0.0, "index": {}}


@dataclass
class PhoneConflict:
    """One phone number claimed by more than one account of the same kind."""

    phone: str
    account_type: str  # "teacher" | "parent"
    account_ids: List[int] = field(default_factory=list)

    def as_payload(self) -> Dict[str, object]:
        """Shape returned to the app.

        Deliberately does not name the other accounts — the caller is not
        entitled to know who else holds the number.
        """
        return {
            "code": PHONE_CONFLICT_CODE,
            "phone": self.phone,
            "account_type": self.account_type,
            "account_count": len(self.account_ids),
            "message": (
                "This phone number is registered on more than one account, so we "
                "cannot tell which one is yours. Please contact the school "
                "administrator to have it corrected."
            ),
        }


def _scan(db: Session) -> List[PhoneConflict]:
    """One pass over both phone columns, grouped by canonical number."""
    conflicts: List[PhoneConflict] = []

    staff: Dict[str, Dict[str, object]] = {}
    for user_id, phone in db.query(User.id, User.phone).all():
        key = canonical_phone(phone)
        if not key:
            continue
        entry = staff.setdefault(key, {"phone": phone, "ids": []})
        entry["ids"].append(user_id)  # type: ignore[union-attr]

    parents: Dict[str, Dict[str, object]] = {}
    for parent_id, father, mother, guardian in db.query(
        Parent.id, Parent.fatherPhone, Parent.motherPhone, Parent.gPhone
    ).all():
        # One account holding the same number in two of its own columns is not a
        # conflict, so collapse within the row before counting.
        by_key = {}
        for value in (father, mother, guardian):
            key = canonical_phone(value)
            if key and key not in by_key:
                by_key[key] = value
        for key, value in by_key.items():
            entry = parents.setdefault(key, {"phone": value, "ids": []})
            entry["ids"].append(parent_id)  # type: ignore[union-attr]

    for account_type, grouped in (("teacher", staff), ("parent", parents)):
        for entry in grouped.values():
            ids = entry["ids"]  # type: ignore[index]
            if len(ids) > 1:  # type: ignore[arg-type]
                conflicts.append(
                    PhoneConflict(
                        phone=str(entry["phone"]),  # type: ignore[index]
                        account_type=account_type,
                        account_ids=sorted(ids),  # type: ignore[arg-type]
                    )
                )

    conflicts.sort(key=lambda c: (c.account_type, c.phone))
    return conflicts


def _index(db: Session, force: bool = False) -> Dict[Tuple[str, int], PhoneConflict]:
    """Cached map of (account_type, account_id) -> the conflict locking it."""
    now = time.monotonic()
    with _lock:
        fresh = (now - float(_cache["built_at"])) < _CACHE_TTL_SECONDS  # type: ignore[arg-type]
        if not force and fresh:
            return _cache["index"]  # type: ignore[return-value]

    try:
        conflicts = _scan(db)
    except Exception as e:
        # A detection failure must never lock people out of the app.
        logger.error("Phone conflict scan failed: %s", e)
        with _lock:
            return _cache["index"]  # type: ignore[return-value]

    built: Dict[Tuple[str, int], PhoneConflict] = {}
    for conflict in conflicts:
        for account_id in conflict.account_ids:
            built[(conflict.account_type, account_id)] = conflict

    with _lock:
        _cache["built_at"] = now
        _cache["index"] = built
    if built:
        logger.warning(
            "Phone conflicts: %d number(s) shared, %d account(s) locked",
            len(conflicts),
            len(built),
        )
    return built


def lock_is_enabled(db: Session) -> bool:
    """Whether to hard-lock affected accounts out of the app.

    An administrator can flip this from the app while working through the
    duplicates, so the database value wins. NULL there means it was never set
    and the environment default applies. Any failure falls back to the
    environment rather than guessing, because guessing "true" would lock people
    out of the app on the strength of a database hiccup.
    """
    from ..core import settings as env_settings

    try:
        from ..models.settings import SystemSettings

        row = db.query(SystemSettings.phone_conflict_lock_enabled).filter(
            SystemSettings.id == 1
        ).first()
        if row is not None and row[0] is not None:
            return bool(row[0])
    except Exception as e:
        logger.debug("Could not read the lock setting, using the env default: %s", e)
    return bool(getattr(env_settings, "phone_conflict_lock_enabled", False))


def set_lock_enabled(db: Session, enabled: bool) -> bool:
    """Persist the toggle. Returns the value now in effect."""
    from ..models.settings import SystemSettings

    row = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if row is None:
        raise ValueError("System settings row is missing")
    row.phone_conflict_lock_enabled = bool(enabled)
    db.commit()
    logger.warning("Phone-conflict lock set to %s by an administrator", enabled)
    return bool(enabled)


def accounts_on_app(db: Session, account_type: str, ids: List[int]) -> Dict[int, bool]:
    """Which of these accounts have the app installed (an active device token).

    An account that is not on the app is not inconvenienced by any of this yet,
    so the office can deprioritise it.
    """
    if not ids:
        return {}
    types = ("teacher", "employee") if account_type == "teacher" else (account_type,)
    try:
        from ..models.device import DeviceToken

        rows = (
            db.query(DeviceToken.user_id)
            .filter(
                DeviceToken.user_id.in_(ids),
                DeviceToken.user_type.in_(types),
                DeviceToken.is_active == True,  # noqa: E712
            )
            .distinct()
            .all()
        )
        on_app = {int(r[0]) for r in rows}
    except Exception as e:
        logger.debug("Could not read device tokens: %s", e)
        on_app = set()
    return {int(i): (int(i) in on_app) for i in ids}


def invalidate_cache() -> None:
    """Force the next check to rescan — call after any phone number is edited."""
    with _lock:
        _cache["built_at"] = 0.0


def find_conflict_for_account(
    db: Session, account_id: int, account_type: str
) -> Optional[PhoneConflict]:
    """Return the conflict locking this account, or None when it is clean.

    ``account_type`` is "teacher" (a ``users`` row) or "parent" (a ``parents``
    row). Students are not covered: they cannot sign in by phone.
    """
    if account_type not in ("teacher", "parent") or not account_id:
        return None
    return _index(db).get((account_type, int(account_id)))


def list_all_conflicts(db: Session) -> List[PhoneConflict]:
    """Every same-type duplicate in the database, for the admin worklist."""
    index = _index(db, force=True)
    seen, out = set(), []
    for conflict in index.values():
        marker = (conflict.account_type, tuple(conflict.account_ids))
        if marker not in seen:
            seen.add(marker)
            out.append(conflict)
    out.sort(key=lambda c: (c.account_type, c.phone))
    return out
