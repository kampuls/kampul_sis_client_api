"""
Leave ↔ Attendance integration helpers.

Approved leave is joined at READ time (reports, check-in guard, reminders).
No synthetic attendance_records rows are created for leave — a record on a
date is what marks a user "present" in the report math, so synthetic rows
would corrupt it, and cancellations would need cleanup.
"""

from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def get_approved_leave_map(
    db: Session,
    user_ids: Iterable[int],
    start_date: date,
    end_date: date,
) -> Dict[int, Dict[date, Dict[str, Any]]]:
    """
    Approved leave per user per date in one query.

    Returns {user_id: {date: {"fraction": float (0..1],
                              "full_day": bool,
                              "session_indexes": set[int]  # empty when full_day,
                              "leave_type": str}}}
    Multiple approved requests touching the same date are merged (fraction
    capped at 1.0, session sets unioned, any full day wins).
    """
    ids = sorted({int(u) for u in user_ids if u})
    result: Dict[int, Dict[date, Dict[str, Any]]] = {}
    if not ids:
        return result
    try:
        stmt = text(
            """
            SELECT lr.user_id, lrd.leave_date, lrd.scope, lrd.session_indexes,
                   lrd.day_cost, lt.name
            FROM leave_request_days lrd
            JOIN leave_requests lr ON lr.id = lrd.leave_request_id
            LEFT JOIN leave_types lt ON lt.id = lr.leave_type_id
            WHERE lr.status = 'approved'
              AND lr.user_id IN :uids
              AND lrd.leave_date BETWEEN :start_date AND :end_date
            """
        ).bindparams(bindparam("uids", expanding=True))
        rows = db.execute(
            stmt, {"uids": ids, "start_date": start_date, "end_date": end_date}
        ).fetchall()
    except Exception:
        # Tables may not exist yet on a fresh deployment — behave as "no leave".
        return result

    import json

    for row in rows:
        uid = int(row[0])
        leave_date = row[1]
        scope = str(row[2] or "full_day")
        raw_indexes = row[3]
        day_cost = float(row[4] or 0)
        leave_type = str(row[5] or "Leave")

        indexes: Set[int] = set()
        if raw_indexes:
            try:
                parsed = raw_indexes if isinstance(raw_indexes, list) else json.loads(raw_indexes)
                indexes = {int(i) for i in (parsed or [])}
            except Exception:
                indexes = set()

        per_user = result.setdefault(uid, {})
        entry = per_user.get(leave_date)
        if entry is None:
            per_user[leave_date] = {
                "fraction": min(1.0, day_cost if day_cost > 0 else 1.0),
                "full_day": scope == "full_day",
                "session_indexes": set() if scope == "full_day" else indexes,
                "leave_type": leave_type,
            }
        else:
            entry["fraction"] = min(1.0, entry["fraction"] + day_cost)
            if scope == "full_day":
                entry["full_day"] = True
                entry["session_indexes"] = set()
            elif not entry["full_day"]:
                entry["session_indexes"] |= indexes
    return result


def leave_map_to_json(per_date_map: Dict[date, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Serialize one user's {date: entry} map for API responses
    (ISO date keys, session_indexes as a sorted list)."""
    return {
        d.isoformat(): {
            "fraction": entry["fraction"],
            "full_day": entry["full_day"],
            "session_indexes": sorted(entry["session_indexes"] or set()),
            "leave_type": entry["leave_type"],
        }
        for d, entry in per_date_map.items()
    }


def leave_covers_session(leave_entry: Optional[Dict[str, Any]], session_index: int) -> bool:
    """True when the given 1-based session is covered by approved leave."""
    if not leave_entry:
        return False
    if leave_entry.get("full_day"):
        return True
    return int(session_index) in (leave_entry.get("session_indexes") or set())


def uncovered_sessions(
    leave_entry: Optional[Dict[str, Any]], sessions_total: int
) -> List[int]:
    """1-based session indexes NOT covered by leave (all when no leave)."""
    return [
        i
        for i in range(1, max(0, int(sessions_total)) + 1)
        if not leave_covers_session(leave_entry, i)
    ]
