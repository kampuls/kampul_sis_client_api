"""Per-subject grading composition and subject-attendance endpoints."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ...auth import get_current_active_user
from ...core import get_db
from ...models import User
from ...services.subject_grading import (
    attendance_earned_points,
    build_final_mark_candidates,
    normalize_attendance_period,
    validate_components,
)
from ...utils.academic_year import is_historical_academic_year


router = APIRouter()

PRESETS = [
    {
        "id": "attendance_homework_test",
        "name": "Attendance + Homework + Test",
        "components": [
            {"name": "Attendance", "weight_percent": 10, "source_type": "subject_attendance"},
            {"name": "Homework", "weight_percent": 10, "source_type": "manual"},
            {"name": "Test", "weight_percent": 80, "source_type": "manual"},
        ],
    },
    {
        "id": "attendance_activity_exam",
        "name": "Attendance + Activities + Exam",
        "components": [
            {"name": "Attendance", "weight_percent": 10, "source_type": "subject_attendance"},
            {"name": "Class activities", "weight_percent": 20, "source_type": "manual"},
            {"name": "Exam", "weight_percent": 70, "source_type": "manual"},
        ],
    },
    {
        "id": "coursework_midterm_final",
        "name": "Coursework + Midterm + Final",
        "components": [
            {"name": "Coursework", "weight_percent": 40, "source_type": "manual"},
            {"name": "Midterm", "weight_percent": 20, "source_type": "manual"},
            {"name": "Final test", "weight_percent": 40, "source_type": "manual"},
        ],
    },
    {
        "id": "final_only",
        "name": "Final test only",
        "components": [
            {"name": "Final test", "weight_percent": 100, "source_type": "manual"},
        ],
    },
]


def _user_id(current_user) -> int:
    value = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    if value is None:
        raise HTTPException(status_code=401, detail="Authenticated user id missing")
    return int(value)


def _grade_type_key(value: Optional[int]) -> int:
    return int(value or 0)


def _default_attendance_period(db: Session, marks_system_id: int) -> tuple[date, date]:
    """Default attendance to the full month containing the exam open date."""
    value = db.execute(
        text("SELECT for_month FROM marks_system WHERE id = :marks_system_id"),
        {"marks_system_id": marks_system_id},
    ).scalar()
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        value = datetime.now(pytz.timezone("Asia/Phnom_Penh")).date()
    return normalize_attendance_period(None, None, default_date=value)


def _attendance_period_payload(start_date: date, end_date: date) -> Dict[str, str]:
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def _assert_subject_context(
    db: Session,
    context: Dict[str, Any],
    *,
    student_id: Optional[int] = None,
    marks_system_id: Optional[int] = None,
) -> None:
    """Validate that the subject and optional student/exam belong to the class."""
    student_join = "JOIN learning l ON l.gradeid = g.id" if student_id is not None else ""
    student_clause = """
        AND l.studentid = :student_id
        AND l.academicid = :academic_id
        AND l.programid = :program_id
        AND l.shiftid = :shift_id
        AND COALESCE(l.grade_type_id, 0) = :grade_type_id
    """ if student_id is not None else ""
    exam_join = "JOIN marks_system ms ON ms.id = :marks_system_id" if marks_system_id is not None else ""
    exam_clause = """
        AND ms.academic_id = :academic_id
        AND ms.program_id = :program_id
        AND (ms.grade_group_id = g.group_id OR ms.grade_group_id IS NULL)
    """ if marks_system_id is not None else ""
    row = db.execute(
        text(f"""
            SELECT 1
            FROM grade g
            JOIN subjects_group sg
              ON sg.grade_group_id = g.group_id
             AND sg.academic_id = :academic_id
             AND sg.program_id = :program_id
             AND sg.subject_id = :subject_id
            {student_join}
            {exam_join}
            WHERE g.id = :grade_id
              AND g.program_id = :program_id
              {student_clause}
              {exam_clause}
            LIMIT 1
        """),
        {
            **context,
            "student_id": student_id,
            "marks_system_id": marks_system_id,
        },
    ).fetchone()
    if not row:
        detail = (
            "Student is not enrolled in this subject class"
            if student_id is not None
            else "Subject or exam is not configured for this class"
        )
        raise HTTPException(status_code=422, detail=detail)


def _student_rows(db: Session, plan: Dict[str, Any]):
    grade_type_id = int(plan["grade_type_id"] or 0)
    historical = 1 if is_historical_academic_year(db, int(plan["academic_id"])) else 0
    grade_type_clause = (
        "l.grade_type_id = :grade_type_id"
        if grade_type_id
        else "l.grade_type_id IS NULL"
    )
    rows = db.execute(
        text(f"""
            SELECT DISTINCT s.id, s.kName, s.eName, s.gender,
                   COALESCE(ur.avatar, '') AS avatar
            FROM learning l
            JOIN students s ON s.id = l.studentid
            LEFT JOIN (
                SELECT user_id, MIN(avatar) AS avatar
                FROM users_resource
                WHERE user_type = 'student' AND avatar IS NOT NULL AND avatar != ''
                GROUP BY user_id
            ) ur ON ur.user_id = s.id
            WHERE l.academicid = :academic_id
              AND l.programid = :program_id
              AND l.gradeid = :grade_id
              AND l.shiftid = :shift_id
              AND {grade_type_clause}
              AND (s.status = 1 OR :historical = 1)
            ORDER BY s.kName, s.eName
        """),
        {
            "academic_id": int(plan["academic_id"]),
            "program_id": int(plan["program_id"]),
            "grade_id": int(plan["grade_id"]),
            "shift_id": int(plan["shift_id"]),
            "grade_type_id": grade_type_id,
            "historical": historical,
        },
    ).fetchall()
    return rows


def _plan_row(db: Session, plan_id: int) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT id, academic_id, program_id, grade_id, grade_type_id,
                   shift_id, subject_id, marks_system_id,
                   attendance_start_date, attendance_end_date
            FROM subject_grade_plans WHERE id = :plan_id
        """),
        {"plan_id": plan_id},
    ).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Subject grading plan not found")
    return dict(row)


def _components(db: Session, plan_id: int) -> List[Dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, name, weight_percent, source_type, sort_order
            FROM subject_grade_components
            WHERE plan_id = :plan_id
            ORDER BY sort_order, id
        """),
        {"plan_id": plan_id},
    ).mappings().fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "weight_percent": float(row["weight_percent"]),
            "source_type": row["source_type"],
            "sort_order": int(row["sort_order"]),
        }
        for row in rows
    ]


def _attendance_summary(db: Session, plan: Dict[str, Any]) -> Dict[int, Dict[str, int]]:
    total_days = int(
        db.execute(
            text("""
                SELECT COUNT(DISTINCT attendance_date)
                FROM subject_attendance
                WHERE academic_id = :academic_id AND program_id = :program_id
                  AND grade_id = :grade_id AND grade_type_id = :grade_type_id
                  AND shift_id = :shift_id AND subject_id = :subject_id
                  AND attendance_date BETWEEN :attendance_start_date
                                          AND :attendance_end_date
            """),
            plan,
        ).scalar()
        or 0
    )
    rows = db.execute(
        text("""
            SELECT student_id,
                   SUM(CASE WHEN status IN ('IsPresent', 'IsLate') THEN 1 ELSE 0 END)
                       AS attended_days
            FROM subject_attendance
            WHERE academic_id = :academic_id AND program_id = :program_id
              AND grade_id = :grade_id AND grade_type_id = :grade_type_id
              AND shift_id = :shift_id AND subject_id = :subject_id
              AND attendance_date BETWEEN :attendance_start_date
                                      AND :attendance_end_date
            GROUP BY student_id
        """),
        plan,
    ).fetchall()
    summary = {int(row[0]): {"attended_days": int(row[1] or 0), "total_study_days": total_days} for row in rows}
    summary[-1] = {"attended_days": 0, "total_study_days": total_days}
    return summary


def _final_mark_summary(db: Session, plan: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """Return the latest canonical final mark for each student in this context."""
    rows = db.execute(
        text("""
            SELECT mi.student_id, mi.marks, mi.updated_at
            FROM marks_input mi
            JOIN (
                SELECT student_id, MAX(id) AS latest_id
                FROM marks_input
                WHERE academic_id = :academic_id AND program_id = :program_id
                  AND grade_id = :grade_id AND subject_id = :subject_id
                  AND marks_system_id = :marks_system_id
                GROUP BY student_id
            ) latest ON latest.latest_id = mi.id
        """),
        plan,
    ).fetchall()
    return {
        int(row[0]): {
            "mark": float(row[1]),
            "updated_at": row[2].isoformat() if row[2] else None,
        }
        for row in rows
        if row[1] is not None
    }


def _plan_payload(db: Session, plan: Dict[str, Any]) -> Dict[str, Any]:
    plan_id = int(plan["id"])
    components = _components(db, plan_id)
    component_ids = [item["id"] for item in components]
    score_map: Dict[tuple[int, int], float] = {}
    if component_ids:
        score_query = text("""
                SELECT component_id, student_id, earned_points
                FROM subject_grade_scores
                WHERE component_id IN :component_ids
            """).bindparams(bindparam("component_ids", expanding=True))
        rows = db.execute(score_query, {"component_ids": component_ids}).fetchall()
        score_map = {(int(row[0]), int(row[1])): float(row[2]) for row in rows}

    attendance = _attendance_summary(db, plan)
    final_marks = _final_mark_summary(db, plan)
    total_days = attendance[-1]["total_study_days"]
    students = []
    for row in _student_rows(db, plan):
        student_id = int(row[0])
        current_final = final_marks.get(student_id)
        component_scores = []
        total = Decimal("0")
        is_ready = True
        for component in components:
            earned: Optional[float]
            if component["source_type"] == "subject_attendance":
                attended = attendance.get(student_id, attendance[-1])["attended_days"]
                if total_days:
                    earned = float(attendance_earned_points(component["weight_percent"], attended, total_days))
                else:
                    earned = None
                    is_ready = False
            else:
                earned = score_map.get((component["id"], student_id))
                if earned is None:
                    is_ready = False
            if earned is not None:
                total += Decimal(str(earned))
            component_scores.append(
                {
                    "component_id": component["id"],
                    "earned_points": earned,
                    "attended_days": attendance.get(student_id, attendance[-1])["attended_days"]
                    if component["source_type"] == "subject_attendance"
                    else None,
                    "total_study_days": total_days
                    if component["source_type"] == "subject_attendance"
                    else None,
                }
            )
        students.append(
            {
                "id": student_id,
                "kName": row[1] or "",
                "eName": row[2] or "",
                "gender": row[3] or "",
                "avatar": row[4] or None,
                "component_scores": component_scores,
                "total_earned_points": float(total.quantize(Decimal("0.01"))),
                "is_ready": is_ready,
                "has_final_mark": current_final is not None,
                "final_mark": current_final["mark"] if current_final else None,
                "final_mark_updated_at": current_final["updated_at"]
                if current_final
                else None,
            }
        )
    return {
        "id": plan_id,
        "academic_id": int(plan["academic_id"]),
        "program_id": int(plan["program_id"]),
        "grade_id": int(plan["grade_id"]),
        "grade_type_id": int(plan["grade_type_id"]) or None,
        "shift_id": int(plan["shift_id"]),
        "subject_id": int(plan["subject_id"]),
        "marks_system_id": int(plan["marks_system_id"]),
        "attendance_start_date": plan["attendance_start_date"].isoformat(),
        "attendance_end_date": plan["attendance_end_date"].isoformat(),
        "components": components,
        "students": students,
        "subject_study_days": total_days,
    }


class GradeComponentInput(BaseModel):
    id: Optional[int] = None
    name: str = Field(min_length=1, max_length=120)
    weight_percent: Decimal
    source_type: str = "manual"


class GradePlanInput(BaseModel):
    academic_id: int
    program_id: int
    grade_id: int
    grade_type_id: Optional[int] = None
    shift_id: int
    subject_id: int
    marks_system_id: int
    attendance_start_date: Optional[date] = None
    attendance_end_date: Optional[date] = None
    components: List[GradeComponentInput]


class GradeScoreInput(BaseModel):
    component_id: int
    student_id: int
    earned_points: Optional[Decimal] = None


class GradeScoresInput(BaseModel):
    plan_id: int
    scores: List[GradeScoreInput]


class ApplyGradePlanInput(BaseModel):
    plan_id: int
    student_ids: Optional[List[int]] = None
    lock_passcode: Optional[str] = None


class SubjectAttendanceInput(BaseModel):
    student_id: int
    attendance_date: date
    status: Optional[str] = None
    academic_id: int
    program_id: int
    grade_id: int
    grade_type_id: Optional[int] = None
    shift_id: int
    subject_id: int
    note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        allowed = {"IsPresent", "IsLate", "IsPermission", "IsAbsent", None}
        if value not in allowed:
            raise ValueError("Invalid attendance status")
        return value


@router.get("/marks/composition")
def get_grade_plan(
    academic_id: int = Query(...),
    program_id: int = Query(...),
    grade_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    shift_id: int = Query(...),
    subject_id: int = Query(...),
    marks_system_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    params = {
        "academic_id": academic_id,
        "program_id": program_id,
        "grade_id": grade_id,
        "grade_type_id": _grade_type_key(grade_type_id),
        "shift_id": shift_id,
        "subject_id": subject_id,
        "marks_system_id": marks_system_id,
    }
    row = db.execute(
        text("""
            SELECT id, academic_id, program_id, grade_id, grade_type_id,
                   shift_id, subject_id, marks_system_id,
                   attendance_start_date, attendance_end_date
            FROM subject_grade_plans
            WHERE academic_id = :academic_id AND program_id = :program_id
              AND grade_id = :grade_id AND grade_type_id = :grade_type_id
              AND shift_id = :shift_id AND subject_id = :subject_id
              AND marks_system_id = :marks_system_id
        """),
        params,
    ).mappings().fetchone()
    default_start, default_end = _default_attendance_period(db, marks_system_id)
    return {
        "success": True,
        "plan": _plan_payload(db, dict(row)) if row else None,
        "presets": PRESETS,
        "default_attendance_period": _attendance_period_payload(
            default_start, default_end
        ),
    }


@router.put("/marks/composition")
def save_grade_plan(
    request: GradePlanInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        components = validate_components([item.model_dump() for item in request.components])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    default_start, default_end = _default_attendance_period(
        db, request.marks_system_id
    )
    try:
        attendance_start_date, attendance_end_date = normalize_attendance_period(
            request.attendance_start_date,
            request.attendance_end_date,
            default_date=default_start,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user_id = _user_id(current_user)
    params = request.model_dump(exclude={"components"})
    params["grade_type_id"] = _grade_type_key(request.grade_type_id)
    params["attendance_start_date"] = attendance_start_date
    params["attendance_end_date"] = attendance_end_date
    _assert_subject_context(
        db,
        params,
        marks_system_id=request.marks_system_id,
    )
    params.update({"created_by": user_id, "updated_by": user_id})
    try:
        existing = db.execute(
            text("""
                SELECT id FROM subject_grade_plans
                WHERE academic_id = :academic_id AND program_id = :program_id
                  AND grade_id = :grade_id AND grade_type_id = :grade_type_id
                  AND shift_id = :shift_id AND subject_id = :subject_id
                  AND marks_system_id = :marks_system_id
            """),
            params,
        ).fetchone()
        if existing:
            plan_id = int(existing[0])
            db.execute(
                text("""
                    UPDATE subject_grade_plans
                    SET attendance_start_date = :attendance_start_date,
                        attendance_end_date = :attendance_end_date,
                        updated_by = :updated_by, updated_at = NOW()
                    WHERE id = :plan_id
                """),
                {
                    "attendance_start_date": attendance_start_date,
                    "attendance_end_date": attendance_end_date,
                    "updated_by": user_id,
                    "plan_id": plan_id,
                },
            )
        else:
            db.execute(
                text("""
                    INSERT INTO subject_grade_plans (
                        academic_id, program_id, grade_id, grade_type_id, shift_id,
                        subject_id, marks_system_id, attendance_start_date,
                        attendance_end_date, created_by, updated_by
                    ) VALUES (
                        :academic_id, :program_id, :grade_id, :grade_type_id, :shift_id,
                        :subject_id, :marks_system_id, :attendance_start_date,
                        :attendance_end_date, :created_by, :updated_by
                    )
                """),
                params,
            )
            plan_id = int(db.execute(text("SELECT LAST_INSERT_ID()" )).scalar())

        existing_ids = {
            int(row[0])
            for row in db.execute(
                text("SELECT id FROM subject_grade_components WHERE plan_id = :plan_id"),
                {"plan_id": plan_id},
            ).fetchall()
        }
        kept_ids = set()
        for component in components:
            component_id = component.get("id")
            values = {
                "plan_id": plan_id,
                "name": component["name"],
                "weight_percent": component["weight_percent"],
                "source_type": component["source_type"],
                "sort_order": component["sort_order"],
            }
            if component_id is not None and int(component_id) in existing_ids:
                values["component_id"] = int(component_id)
                db.execute(
                    text("""
                        UPDATE subject_grade_components
                        SET name = :name, weight_percent = :weight_percent,
                            source_type = :source_type, sort_order = :sort_order,
                            updated_at = NOW()
                        WHERE id = :component_id AND plan_id = :plan_id
                    """),
                    values,
                )
                kept_ids.add(int(component_id))
            else:
                db.execute(
                    text("""
                        INSERT INTO subject_grade_components (
                            plan_id, name, weight_percent, source_type, sort_order
                        ) VALUES (
                            :plan_id, :name, :weight_percent, :source_type, :sort_order
                        )
                    """),
                    values,
                )
                kept_ids.add(int(db.execute(text("SELECT LAST_INSERT_ID()" )).scalar()))
        for component_id in existing_ids - kept_ids:
            db.execute(
                text("DELETE FROM subject_grade_components WHERE id = :component_id AND plan_id = :plan_id"),
                {"component_id": component_id, "plan_id": plan_id},
            )
        # Automatic attendance values are derived, never retained as stale
        # manual score rows when a teacher changes a component's source.
        db.execute(
            text("""
                DELETE s FROM subject_grade_scores s
                JOIN subject_grade_components c ON c.id = s.component_id
                WHERE c.plan_id = :plan_id
                  AND c.source_type = 'subject_attendance'
            """),
            {"plan_id": plan_id},
        )
        db.commit()
        plan = _plan_row(db, plan_id)
        return {
            "success": True,
            "plan": _plan_payload(db, plan),
            "presets": PRESETS,
            "default_attendance_period": _attendance_period_payload(
                default_start, default_end
            ),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save grading plan: {exc}") from exc


@router.post("/marks/composition/scores")
def save_component_scores(
    request: GradeScoresInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    plan = _plan_row(db, request.plan_id)
    components = {item["id"]: item for item in _components(db, request.plan_id)}
    student_ids = {int(row[0]) for row in _student_rows(db, plan)}
    user_id = _user_id(current_user)
    try:
        for score in request.scores:
            component = components.get(score.component_id)
            if not component or component["source_type"] != "manual":
                raise HTTPException(status_code=422, detail="Only manual components can be edited")
            if score.student_id not in student_ids:
                raise HTTPException(status_code=422, detail="Student is not enrolled in this class")
            if score.earned_points is None:
                db.execute(
                    text("DELETE FROM subject_grade_scores WHERE component_id = :component_id AND student_id = :student_id"),
                    score.model_dump(exclude={"earned_points"}),
                )
                continue
            if score.earned_points < 0 or score.earned_points > Decimal(str(component["weight_percent"])):
                raise HTTPException(
                    status_code=422,
                    detail=f"{component['name']} must be between 0 and {component['weight_percent']}",
                )
            db.execute(
                text("""
                    INSERT INTO subject_grade_scores (
                        component_id, student_id, earned_points, updated_by
                    ) VALUES (
                        :component_id, :student_id, :earned_points, :updated_by
                    ) ON DUPLICATE KEY UPDATE
                        earned_points = VALUES(earned_points),
                        updated_by = VALUES(updated_by), updated_at = NOW()
                """),
                {
                    "component_id": score.component_id,
                    "student_id": score.student_id,
                    "earned_points": score.earned_points,
                    "updated_by": user_id,
                },
            )
        db.commit()
        return {"success": True, "plan": _plan_payload(db, plan)}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save component scores: {exc}") from exc


@router.post("/marks/composition/apply")
def apply_grade_plan(
    request: ApplyGradePlanInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    plan = _plan_row(db, request.plan_id)
    payload = _plan_payload(db, plan)
    try:
        validate_components(payload["components"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    grade_group = db.execute(
        text("SELECT group_id FROM grade WHERE id = :grade_id"),
        {"grade_id": plan["grade_id"]},
    ).fetchone()
    if not grade_group:
        raise HTTPException(status_code=404, detail="Grade not found")
    full_mark_row = db.execute(
        text("""
            SELECT full_marks FROM subjects_group
            WHERE academic_id = :academic_id AND program_id = :program_id
              AND grade_group_id = :grade_group_id AND subject_id = :subject_id
            LIMIT 1
        """),
        {**plan, "grade_group_id": int(grade_group[0])},
    ).fetchone()
    if not full_mark_row:
        raise HTTPException(status_code=404, detail="Subject full mark is not configured")

    candidates = build_final_mark_candidates(
        payload["students"],
        full_mark_row[0],
        set(request.student_ids or []),
    )
    if candidates["unknown_student_ids"]:
        raise HTTPException(
            status_code=422,
            detail="One or more selected students are not enrolled in this class",
        )
    marks = candidates["marks"]
    if not marks:
        raise HTTPException(
            status_code=422,
            detail=(
                "No completed student scores to apply. Use the student's Final "
                "button to publish an individual partial score."
            ),
        )

    # Reuse the canonical mark writer so locks, exam windows, audit logs, and
    # monthly/semester/yearly calculation cascades remain exactly consistent.
    from .marks import save_marks

    result = save_marks(
        {
            "program_id": plan["program_id"],
            "grade_id": plan["grade_id"],
            "grade_type_id": int(plan["grade_type_id"]) or None,
            "academic_id": plan["academic_id"],
            "marks_system_id": plan["marks_system_id"],
            "subject_id": plan["subject_id"],
            "marks": marks,
            "lock_passcode": request.lock_passcode,
        },
        db=db,
        current_user=current_user,
    )
    result["applied_from_composition"] = True
    result["full_mark"] = float(full_mark_row[0])
    result["applied_student_ids"] = [item["student_id"] for item in marks]
    result["partial_student_ids"] = candidates["partial_student_ids"]
    result["skipped_incomplete_student_ids"] = candidates["skipped_student_ids"]
    return result


@router.get("/attendance/subject/students")
def get_subject_attendance_students(
    attendance_date: date = Query(...),
    academic_id: int = Query(...),
    program_id: int = Query(...),
    grade_id: int = Query(...),
    grade_type_id: Optional[int] = Query(None),
    shift_id: int = Query(...),
    subject_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    plan = {
        "academic_id": academic_id,
        "program_id": program_id,
        "grade_id": grade_id,
        "grade_type_id": _grade_type_key(grade_type_id),
        "shift_id": shift_id,
        "subject_id": subject_id,
    }
    statuses = {
        int(row[0]): (row[1], row[2])
        for row in db.execute(
            text("""
                SELECT student_id, status, note FROM subject_attendance
                WHERE attendance_date = :attendance_date
                  AND academic_id = :academic_id AND program_id = :program_id
                  AND grade_id = :grade_id AND grade_type_id = :grade_type_id
                  AND shift_id = :shift_id AND subject_id = :subject_id
            """),
            {**plan, "attendance_date": attendance_date},
        ).fetchall()
    }
    students = []
    for row in _student_rows(db, plan):
        attendance = statuses.get(int(row[0]), (None, None))
        students.append(
            {
                "id": int(row[0]),
                "kName": row[1] or "",
                "eName": row[2] or "",
                "gender": row[3] or "",
                "academicid": academic_id,
                "avatar": row[4] or None,
                "attendance_status": attendance[0],
                "attendance_note": attendance[1],
                "created_by_type": "teacher" if attendance[0] else None,
                "parent_info": None,
            }
        )
    return students


@router.post("/attendance/subject/record")
def record_subject_attendance(
    request: SubjectAttendanceInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from .attendance import _current_user_is_super_admin

    cambodia_today = datetime.now(pytz.timezone("Asia/Phnom_Penh")).date()
    if not _current_user_is_super_admin(db, _user_id(current_user)):
        if request.attendance_date > cambodia_today:
            raise HTTPException(status_code=400, detail="Cannot mark attendance for future dates")
        if request.attendance_date < cambodia_today - timedelta(days=6):
            raise HTTPException(status_code=400, detail="Cannot mark attendance older than 7 days")

    params = request.model_dump()
    params["grade_type_id"] = _grade_type_key(request.grade_type_id)
    params["user_id"] = _user_id(current_user)
    _assert_subject_context(
        db,
        params,
        student_id=request.student_id,
    )
    try:
        if request.status is None:
            db.execute(
                text("""
                    DELETE FROM subject_attendance
                    WHERE student_id = :student_id AND attendance_date = :attendance_date
                      AND academic_id = :academic_id AND program_id = :program_id
                      AND grade_id = :grade_id AND grade_type_id = :grade_type_id
                      AND shift_id = :shift_id AND subject_id = :subject_id
                """),
                params,
            )
            message = "Subject attendance removed successfully"
        else:
            note = (request.note or "").strip() or None
            if request.status not in {"IsPermission", "IsAbsent"}:
                note = None
            params["note"] = note
            db.execute(
                text("""
                    INSERT INTO subject_attendance (
                        student_id, attendance_date, status, academic_id,
                        program_id, grade_id, grade_type_id, shift_id, subject_id,
                        note, teacher_id, created_by, updated_by
                    ) VALUES (
                        :student_id, :attendance_date, :status, :academic_id,
                        :program_id, :grade_id, :grade_type_id, :shift_id, :subject_id,
                        :note, :user_id, :user_id, :user_id
                    ) ON DUPLICATE KEY UPDATE
                        status = VALUES(status), note = VALUES(note),
                        teacher_id = VALUES(teacher_id), updated_by = VALUES(updated_by),
                        updated_at = NOW()
                """),
                params,
            )
            message = "Subject attendance recorded successfully"
        db.commit()
        return {"success": True, "message": message}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record subject attendance: {exc}",
        ) from exc
