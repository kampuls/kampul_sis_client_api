"""Pure billing rules shared by the finance API and reminder worker."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def coverage_end(start: date, months: int) -> date:
    """Inclusive end, preserving the original calendar anchor at month end."""
    if months < 1:
        raise ValueError('Billing months must be positive')
    absolute = start.year * 12 + start.month - 1 + months
    year, month = divmod(absolute, 12)
    month += 1
    anniversary = date(year, month, min(start.day, monthrange(year, month)[1]))
    return anniversary - timedelta(days=1)


def service_status(end: date, today: date, grace: int, monthly: bool, continuation: str):
    if continuation == 'one_off':
        return 'One-off'
    if today > end + timedelta(days=grace):
        return 'Expired'
    if today > end:
        return 'In grace'
    if today == end:
        return 'Due today'
    if (end - today).days <= (3 if monthly else 15):
        return 'Upcoming'
    return 'Active'


def reminder_offset(end: date, today: date, months: int, grace: int):
    offset = (today - end).days
    return offset if offset in ((-3, 0, grace) if months == 1 else (-15, -7, 0, grace)) else None


def pending_milestone(end: date, today: date, months: int, grace: int):
    """Catch up the latest milestone for three days, without sending stale stages."""
    offset = (today - end).days
    stages = (-3, 0, grace) if months == 1 else (-15, -7, 0, grace)
    due = [stage for stage in stages if stage <= offset]
    latest = max(due) if due else None
    return latest if latest is not None and offset - latest <= 3 else None


def split_coverage(start, end, years):
    """Require every covered day to belong to exactly one selected academic year."""
    result, cursor = [], start
    valid_years = [(i, date.fromisoformat(str(a)[:10]), date.fromisoformat(str(b)[:10]))
                   for i,a,b in years if a is not None and b is not None]
    for year_id, year_start, year_end in sorted(valid_years, key=lambda y: y[1]):
        left, right = max(start, year_start), min(end, year_end)
        if left > right:
            continue
        if left != cursor:
            raise ValueError('Academic years must cover the period without gaps or overlaps')
        result.append((year_id, left, right))
        cursor = right + timedelta(days=1)
    if cursor != end + timedelta(days=1):
        raise ValueError('Set up the next academic year before recording cross-year coverage')
    return result
