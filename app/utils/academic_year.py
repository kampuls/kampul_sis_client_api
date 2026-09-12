"""
Canonical academic-year resolution shared by every API module.

The whole project follows one rule:

    current year = academic.status = 1
                 -> settings.academicid
                 -> newest academic.id
                 -> 1 (last resort, logged)

A year is HISTORICAL when it is neither the status=1 year nor the
settings.academicid year. Historical roster queries must relax the
`students.status = 1` filter, otherwise past years look empty because
their students have since been deactivated.
"""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _parse_academic_value(value) -> int | None:
    """settings.academicid can be int, str, or a space-separated string
    like "2 1" (take the first). Returns None when unparseable."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        raw = str(value).strip()
        if " " in raw:
            parts = raw.split()
            return int(parts[0]) if parts else None
        return int(raw)
    except (ValueError, TypeError):
        return None


def get_current_academic_id(db: Session) -> int:
    """Resolve the school's CURRENT academic year id (canonical rule)."""
    # 1. Active year flagged in the academic table
    try:
        row = db.execute(
            text("SELECT id FROM academic WHERE status = 1 LIMIT 1")
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception as e:
        logger.warning(f"get_current_academic_id: academic-table check failed: {e}")

    # 2. settings.academicid
    try:
        row = db.execute(
            text("SELECT academicid FROM settings LIMIT 1")
        ).fetchone()
        if row:
            parsed = _parse_academic_value(row[0])
            if parsed is not None:
                return parsed
    except Exception as e:
        error_str = str(e)
        if "1146" in error_str and "settings" in error_str:
            pass  # settings table missing in some deployments
        else:
            logger.warning(f"get_current_academic_id: settings check failed: {e}")

    # 3. Newest year on record
    try:
        row = db.execute(
            text("SELECT id FROM academic ORDER BY id DESC LIMIT 1")
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception as e:
        logger.warning(f"get_current_academic_id: newest-year check failed: {e}")

    logger.warning("get_current_academic_id: all methods failed, defaulting to 1")
    return 1


def is_historical_academic_year(db: Session, academic_id) -> bool:
    """
    True when the requested academic year is NOT the school's current year.

    The current year is either the one flagged active in `academic`
    (status = 1) or the one configured in `settings.academicid`. For any
    other (historical) year the `students.status = 1` filter must be
    relaxed, otherwise past-year classes/rosters look empty because those
    students have since been deactivated.
    """
    try:
        row = db.execute(
            text("SELECT id FROM academic WHERE status = 1 LIMIT 1")
        ).fetchone()
        if row and row[0] is not None and int(row[0]) == int(academic_id):
            return False
    except Exception as e:
        logger.warning(f"historical-year check (academic table) failed: {e}")
    try:
        row = db.execute(
            text("SELECT academicid FROM settings LIMIT 1")
        ).fetchone()
        if row:
            parsed = _parse_academic_value(row[0])
            if parsed is not None and parsed == int(academic_id):
                return False
    except Exception as e:
        logger.warning(f"historical-year check (settings table) failed: {e}")
    return True
