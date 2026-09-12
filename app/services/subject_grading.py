"""Calculation helpers for per-subject grading composition."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping


TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")


def month_bounds(value: date) -> tuple[date, date]:
    """Return the first and last calendar day containing ``value``."""
    start = value.replace(day=1)
    next_month = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, next_month - timedelta(days=1)


def normalize_attendance_period(
    start_date: date | None,
    end_date: date | None,
    *,
    default_date: date,
) -> tuple[date, date]:
    """Validate a selected range or default to ``default_date``'s month."""
    if start_date is None and end_date is None:
        return month_bounds(default_date)
    if start_date is None or end_date is None:
        raise ValueError("Attendance period requires both a start and end date")
    if start_date > end_date:
        raise ValueError("Attendance period start date must be on or before end date")
    return start_date, end_date


def as_decimal(value) -> Decimal:
    """Convert an API/database number to a two-place Decimal safely."""
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def validate_components(components: Iterable[Mapping]) -> list[dict]:
    """Normalize a component list and require a positive, exact 100% split."""
    normalized: list[dict] = []
    attendance_count = 0
    names: set[str] = set()

    for index, component in enumerate(components):
        name = str(component.get("name") or "").strip()
        if not name:
            raise ValueError(f"Component {index + 1} needs a name")
        name_key = name.casefold()
        if name_key in names:
            raise ValueError(f"Component names must be unique: {name}")
        names.add(name_key)

        weight = as_decimal(component.get("weight_percent", 0))
        if weight <= 0 or weight > HUNDRED:
            raise ValueError(f"{name} weight must be greater than 0 and at most 100")

        source_type = str(component.get("source_type") or "manual").strip()
        if source_type not in {"manual", "subject_attendance"}:
            raise ValueError(f"Unsupported component source: {source_type}")
        if source_type == "subject_attendance":
            attendance_count += 1

        normalized.append(
            {
                "id": component.get("id"),
                "name": name,
                "weight_percent": weight,
                "source_type": source_type,
                "sort_order": index,
            }
        )

    if not normalized:
        raise ValueError("Add at least one grading component")
    if len(normalized) > 20:
        raise ValueError("A grading plan can have at most 20 components")
    if attendance_count > 1:
        raise ValueError("A grading plan can contain only one attendance component")

    total = sum((item["weight_percent"] for item in normalized), Decimal("0"))
    if total != HUNDRED:
        raise ValueError(f"Component weights must total exactly 100%, not {total}%")
    return normalized


def attendance_earned_points(
    weight_percent,
    attended_days: int,
    total_study_days: int,
) -> Decimal:
    """Return weighted attendance points based on subject study sessions."""
    if total_study_days <= 0:
        raise ValueError("No subject attendance study days have been recorded")
    attended = max(0, min(int(attended_days), int(total_study_days)))
    points = as_decimal(weight_percent) * Decimal(attended) / Decimal(total_study_days)
    return points.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def final_subject_mark(total_earned_points, full_mark) -> Decimal:
    """Scale a plan's earned points out of 100 to the subject's full mark."""
    earned = as_decimal(total_earned_points)
    if earned < 0 or earned > HUNDRED:
        raise ValueError("Total earned points must be between 0 and 100")
    mark = earned * as_decimal(full_mark) / HUNDRED
    return mark.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def build_final_mark_candidates(
    students: Iterable[Mapping],
    full_mark,
    selected_ids: set[int] | None = None,
) -> dict:
    """Choose safe class-wide marks or explicitly requested partial marks.

    A class-wide apply only publishes students whose component inputs are
    complete. An explicit student selection may publish the current partial
    total, where missing components already contribute zero to that total.
    """
    student_rows = list(students)
    available_ids = {int(student["id"]) for student in student_rows}
    requested_ids = {int(value) for value in (selected_ids or set())}
    explicit_selection = bool(requested_ids)
    marks = []
    partial_student_ids = []
    skipped_student_ids = []

    for student in student_rows:
        student_id = int(student["id"])
        if explicit_selection and student_id not in requested_ids:
            continue
        if not student.get("is_ready"):
            if explicit_selection:
                partial_student_ids.append(student_id)
            else:
                skipped_student_ids.append(student_id)
                continue
        marks.append(
            {
                "student_id": student_id,
                "mark": float(
                    final_subject_mark(student.get("total_earned_points", 0), full_mark)
                ),
            }
        )

    return {
        "marks": marks,
        "partial_student_ids": partial_student_ids,
        "skipped_student_ids": skipped_student_ids,
        "unknown_student_ids": sorted(requested_ids - available_ids),
    }
