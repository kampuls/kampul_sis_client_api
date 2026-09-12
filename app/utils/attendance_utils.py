import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

def safe_decimal(value, default=Decimal('0')):
    """Safely convert value to Decimal."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default

def round_decimal_to_2_places(value: Decimal) -> Decimal:
    """Rounds a Decimal to 2 places."""
    return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

def _to_date(value):
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None

def _get_academic_dates(db_session, academic_id: int):
    # Using raw SQL for flexibility or SQLAlchemy session
    # Expecting db_session to be a SQLAlchemy Session
    from sqlalchemy import text
    try:
        result = db_session.execute(
            text("SELECT academic_start, academic_end FROM academic WHERE id = :id"),
            {"id": academic_id}
        ).fetchone()
        
        if result:
            return _to_date(result[0]), _to_date(result[1])
    except Exception as e:
        logger.error(f"Error getting academic dates: {e}")
    return None, None


def _get_skip_weekend_settings(db_session):
    from sqlalchemy import text
    try:
        result = db_session.execute(text("SELECT skip_sat, skip_sun FROM settings LIMIT 1")).fetchone()
        if result:
            # Handle potential index access if result is tuple/rowproxy
            # Adjust based on DB driver return type, usually tuple or dict-like
            skip_sat = str(result[0] if result[0] is not None else "no").lower() == "yes"
            skip_sun = str(result[1] if result[1] is not None else "no").lower() == "yes"
            return skip_sat, skip_sun
    except Exception as e:
        logger.warning(f"Failed to read settings skip_sat/skip_sun: {e}")
    return False, True


def _get_holidays(db_session, start_date, end_date):
    if not start_date or not end_date:
        return set()
    from sqlalchemy import text
    try:
        result = db_session.execute(
            text("SELECT date FROM holidays WHERE date BETWEEN :start AND :end"),
            {"start": start_date, "end": end_date}
        ).fetchall()
        
        holidays = set()
        for row in result:
            date_value = _to_date(row[0])
            if date_value:
                holidays.add(date_value)
        return holidays
    except Exception as e:
        logger.error(f"Error getting holidays: {e}")
        return set()


def _count_working_days(month_records, start_date, end_date, skip_sat, skip_sun, holidays):
    if not month_records or not start_date or not end_date:
        return 0

    # month_records is list of dicts/objects having 'year' and 'month'
    month_keys = set()
    for m in month_records:
        y = int(m.get('year') or 0)
        mo = int(m.get('month') or 0)
        if y > 0 and mo > 0:
            month_keys.add((y, mo))

    if not month_keys:
        return 0

    min_year, min_month = min(month_keys)
    max_year, max_month = max(month_keys)
    
    # Python datetime.date for range comparison
    range_start = max(start_date, datetime.date(min_year, min_month, 1))
    
    # Logic for last day of max month
    # start of next month - 1 day
    next_month_year = max_year + (1 if max_month == 12 else 0)
    next_month = 1 if max_month == 12 else max_month + 1
    last_day_of_max_month = datetime.date(next_month_year, next_month, 1) - datetime.timedelta(days=1)
    
    range_end = min(end_date, last_day_of_max_month)

    if range_end < range_start:
        return 0

    working_days = 0
    current = range_start
    while current <= range_end:
        if (current.year, current.month) in month_keys:
            weekday = current.weekday() # 0 = Monday, 6 = Sunday
            if skip_sat and weekday == 5:
                current += datetime.timedelta(days=1)
                continue
            if skip_sun and weekday == 6:
                current += datetime.timedelta(days=1)
                continue
            if current in holidays:
                current += datetime.timedelta(days=1)
                continue
            working_days += 1
        current += datetime.timedelta(days=1)
    return working_days


def enrich_attendance_summary(db_session, academic_id: int, month_records: list, attendance_summary: dict) -> dict:
    """
    Adds working days, not marked, and percentage fields to attendance_summary.
    month_records: list of dicts [{'year': 2024, 'month': 1}, ...] representing months to count.
    attendance_summary: dict {'IsPresent': 10, 'IsAbsent': 1, ...}
    """
    if attendance_summary is None:
        attendance_summary = {}

    academic_start, academic_end = _get_academic_dates(db_session, academic_id)
    skip_sat, skip_sun = _get_skip_weekend_settings(db_session)
    holidays = _get_holidays(db_session, academic_start, academic_end)

    working_days = _count_working_days(
        month_records,
        academic_start,
        academic_end,
        skip_sat,
        skip_sun,
        holidays,
    )

    # Sum known statuses
    total_marked = sum(int(v or 0) for k, v in attendance_summary.items() if k in ['IsPresent', 'IsLate', 'IsPermission', 'IsAbsent'])
    not_marked = max(0, working_days - total_marked)

    def pct(value):
        if not working_days:
            return 0.0
        # Use Decimal with ROUND_HALF_UP to 2 decimal places
        pct_value = (Decimal(str(value)) / Decimal(str(working_days))) * Decimal("100")
        pct_rounded = round_decimal_to_2_places(pct_value)
        return float(pct_rounded)

    # Add enriched fields with underscore prefix to avoid collision with raw db columns
    attendance_summary["_working_days"] = working_days
    attendance_summary["_not_marked"] = not_marked
    attendance_summary["_percent_present"] = pct(attendance_summary.get("IsPresent", 0))
    attendance_summary["_percent_late"] = pct(attendance_summary.get("IsLate", 0))
    attendance_summary["_percent_permission"] = pct(attendance_summary.get("IsPermission", 0))
    attendance_summary["_percent_absent"] = pct(attendance_summary.get("IsAbsent", 0))
    attendance_summary["_percent_not_marked"] = pct(not_marked)
    
    return attendance_summary
