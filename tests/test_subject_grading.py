from datetime import date
from decimal import Decimal

import pytest

from app.services.subject_grading import (
    attendance_earned_points,
    build_final_mark_candidates,
    final_subject_mark,
    month_bounds,
    normalize_attendance_period,
    validate_components,
)


def test_subject_split_must_total_exactly_one_hundred():
    components = validate_components(
        [
            {"name": "Attendance", "weight_percent": 10, "source_type": "subject_attendance"},
            {"name": "Homework", "weight_percent": 10, "source_type": "manual"},
            {"name": "Test", "weight_percent": 80, "source_type": "manual"},
        ]
    )
    assert sum(item["weight_percent"] for item in components) == Decimal("100.00")

    with pytest.raises(ValueError, match="exactly 100"):
        validate_components(
            [
                {"name": "Homework", "weight_percent": 10, "source_type": "manual"},
                {"name": "Test", "weight_percent": 80, "source_type": "manual"},
            ]
        )


def test_subject_split_allows_only_one_automatic_attendance_component():
    with pytest.raises(ValueError, match="only one attendance"):
        validate_components(
            [
                {"name": "Attendance A", "weight_percent": 10, "source_type": "subject_attendance"},
                {"name": "Attendance B", "weight_percent": 10, "source_type": "subject_attendance"},
                {"name": "Test", "weight_percent": 80, "source_type": "manual"},
            ]
        )


def test_attendance_points_use_subject_days_studied():
    assert attendance_earned_points(10, attended_days=8, total_study_days=10) == Decimal("8.00")
    assert attendance_earned_points(10, attended_days=20, total_study_days=10) == Decimal("10.00")
    with pytest.raises(ValueError, match="No subject attendance"):
        attendance_earned_points(10, attended_days=0, total_study_days=0)


def test_composed_percentage_scales_to_subject_full_mark():
    assert final_subject_mark(85, 100) == Decimal("85.00")
    assert final_subject_mark(85, 50) == Decimal("42.50")


def test_attendance_period_defaults_to_full_exam_month():
    assert month_bounds(date(2026, 8, 24)) == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )
    assert normalize_attendance_period(
        None,
        None,
        default_date=date(2024, 2, 10),
    ) == (date(2024, 2, 1), date(2024, 2, 29))


def test_custom_attendance_period_requires_valid_start_and_end():
    with pytest.raises(ValueError, match="both a start and end"):
        normalize_attendance_period(
            date(2026, 8, 1),
            None,
            default_date=date(2026, 8, 24),
        )
    with pytest.raises(ValueError, match="on or before"):
        normalize_attendance_period(
            date(2026, 8, 31),
            date(2026, 8, 1),
            default_date=date(2026, 8, 24),
        )


def test_class_apply_skips_incomplete_students_without_publishing_zeroes():
    result = build_final_mark_candidates(
        [
            {"id": 1, "total_earned_points": 10, "is_ready": False},
            {"id": 2, "total_earned_points": 75, "is_ready": True},
        ],
        full_mark=50,
    )
    assert result["marks"] == [{"student_id": 2, "mark": 37.5}]
    assert result["skipped_student_ids"] == [1]
    assert result["partial_student_ids"] == []


def test_individual_apply_can_publish_and_later_update_a_partial_total():
    students = [
        {"id": 1, "total_earned_points": 10, "is_ready": False},
        {"id": 2, "total_earned_points": 75, "is_ready": True},
    ]
    partial = build_final_mark_candidates(students, 100, {1})
    assert partial["marks"] == [{"student_id": 1, "mark": 10.0}]
    assert partial["partial_student_ids"] == [1]

    students[0]["total_earned_points"] = 85
    students[0]["is_ready"] = True
    updated = build_final_mark_candidates(students, 100, {1})
    assert updated["marks"] == [{"student_id": 1, "mark": 85.0}]
    assert updated["partial_student_ids"] == []


def test_individual_apply_rejects_unknown_student_ids():
    result = build_final_mark_candidates(
        [{"id": 1, "total_earned_points": 10, "is_ready": False}],
        100,
        {99},
    )
    assert result["marks"] == []
    assert result["unknown_student_ids"] == [99]
