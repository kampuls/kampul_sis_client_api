"""
Homeroom teacher comment permission and persistence for student results.

Validation matches kortra_env results (*_monthly_results_flow.py handle_comment_input):
- Maximum 153 characters
- Emojis not allowed
- Comment cannot be empty when saving
"""

import re
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# Same limit as kortra Telegram bot (handle_comment_input)
TEACHER_COMMENT_MAX_LENGTH = 153

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def validate_teacher_comment_text(comment: str) -> str:
    """Normalize and validate comment text; raises HTTPException if invalid."""
    text_comment = (comment or "").strip()
    if not text_comment:
        raise HTTPException(status_code=400, detail="Comment cannot be empty.")
    if _EMOJI_PATTERN.search(text_comment):
        raise HTTPException(
            status_code=400,
            detail="Emojis are not allowed in comments.",
        )
    if len(text_comment) > TEACHER_COMMENT_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Comment too long. Current: {len(text_comment)} characters "
                f"(maximum: {TEACHER_COMMENT_MAX_LENGTH})"
            ),
        )
    return text_comment

def _current_user_id(current_user: Any) -> int:
    uid = getattr(current_user, "id", None)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(uid)


def is_parent_user(current_user: Any) -> bool:
    role = getattr(current_user, "role", None)
    return role == 3


def is_homeroom_teacher_for_class(
    db: Session,
    teacher_user_id: int,
    program_id: int,
    grade_id: int,
    shift_id: int,
    academic_id: int,
    grade_type_id: Optional[int],
) -> bool:
    """True when the logged-in user is the homeroom teacher for this class context."""
    if grade_type_id is None:
        row = db.execute(
            text("""
                SELECT 1
                FROM class_teachers
                WHERE teacher_id = :teacher_id
                  AND program_id = :program_id
                  AND grade_id = :grade_id
                  AND shift_id = :shift_id
                  AND academic_id = :academic_id
                  AND grade_type_id IS NULL
                LIMIT 1
            """),
            {
                "teacher_id": teacher_user_id,
                "program_id": program_id,
                "grade_id": grade_id,
                "shift_id": shift_id,
                "academic_id": academic_id,
            },
        ).fetchone()
    else:
        row = db.execute(
            text("""
                SELECT 1
                FROM class_teachers
                WHERE teacher_id = :teacher_id
                  AND program_id = :program_id
                  AND grade_id = :grade_id
                  AND shift_id = :shift_id
                  AND academic_id = :academic_id
                  AND grade_type_id = :grade_type_id
                LIMIT 1
            """),
            {
                "teacher_id": teacher_user_id,
                "program_id": program_id,
                "grade_id": grade_id,
                "shift_id": shift_id,
                "academic_id": academic_id,
                "grade_type_id": grade_type_id,
            },
        ).fetchone()
    return row is not None


def resolve_exam_type_for_comment(
    db: Session,
    program_id: int,
    grade_id: int,
    academic_id: int,
    marks_system_id: int,
    result_name: Optional[str],
    exam_type: Optional[str],
) -> Tuple[str, str]:
    """Return (exam_type, result_name) used to locate the stored result row."""
    if exam_type and str(exam_type).strip().lower() in (
        "semester",
        "yearly",
        "monthly",
        "input",
    ):
        et = str(exam_type).strip().lower()
        if et == "input":
            et = "monthly"
        rn = (result_name or "").strip()
        if et in ("semester", "yearly") and not rn:
            raise HTTPException(
                status_code=400,
                detail="result_name is required for semester/yearly comments",
            )
        return et, rn

    grade_row = db.execute(
        text("SELECT group_id FROM grade WHERE id = :grade_id"),
        {"grade_id": grade_id},
    ).fetchone()
    if not grade_row:
        raise HTTPException(status_code=404, detail="Grade not found")
    grade_group_id = grade_row[0]

    ecs_row = db.execute(
        text("""
            SELECT exam_type, result_name
            FROM exam_calculate_sign
            WHERE academic_id = :academic_id
              AND program_id = :program_id
              AND grade_group_id = :grade_group_id
              AND marks_system_id = :marks_system_id
            LIMIT 1
        """),
        {
            "academic_id": academic_id,
            "program_id": program_id,
            "grade_group_id": grade_group_id,
            "marks_system_id": marks_system_id,
        },
    ).fetchone()

    if ecs_row:
        et = (ecs_row[0] or "monthly").strip().lower()
        if et == "input":
            et = "monthly"
        rn = (result_name or ecs_row[1] or "").strip()
        if et in ("semester", "yearly") and not rn:
            raise HTTPException(
                status_code=400,
                detail="result_name is required for semester/yearly comments",
            )
        return et, rn

    if result_name and str(result_name).strip():
        rn = str(result_name).strip()
        ecs_by_name = db.execute(
            text("""
                SELECT exam_type
                FROM exam_calculate_sign
                WHERE academic_id = :academic_id
                  AND program_id = :program_id
                  AND grade_group_id = :grade_group_id
                  AND result_name = :result_name
                  AND is_active = 1
                LIMIT 1
            """),
            {
                "academic_id": academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id,
                "result_name": rn,
            },
        ).fetchone()
        if ecs_by_name:
            et = (ecs_by_name[0] or "monthly").strip().lower()
            if et == "input":
                et = "monthly"
            return et, rn

    return "monthly", (result_name or "").strip()


def can_user_comment_on_result(
    db: Session,
    current_user: Any,
    program_id: int,
    grade_id: int,
    shift_id: int,
    academic_id: int,
    grade_type_id: Optional[int],
) -> bool:
    if is_parent_user(current_user):
        return False
    teacher_id = _current_user_id(current_user)
    return is_homeroom_teacher_for_class(
        db,
        teacher_id,
        program_id,
        grade_id,
        shift_id,
        academic_id,
        grade_type_id,
    )


def save_teacher_comment(
    db: Session,
    current_user: Any,
    student_id: int,
    program_id: int,
    grade_id: int,
    shift_id: int,
    academic_id: int,
    marks_system_id: int,
    comment: str,
    grade_type_id: Optional[int] = None,
    result_name: Optional[str] = None,
    exam_type: Optional[str] = None,
) -> Dict[str, Any]:
    if is_parent_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Parents cannot edit teacher comments",
        )

    teacher_id = _current_user_id(current_user)
    if not is_homeroom_teacher_for_class(
        db,
        teacher_id,
        program_id,
        grade_id,
        shift_id,
        academic_id,
        grade_type_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Only the homeroom teacher for this class can add or edit comments",
        )

    exam_type_resolved, result_name_resolved = resolve_exam_type_for_comment(
        db,
        program_id,
        grade_id,
        academic_id,
        marks_system_id,
        result_name,
        exam_type,
    )

    text_comment = validate_teacher_comment_text(comment)

    grade_row = db.execute(
        text("SELECT group_id FROM grade WHERE id = :grade_id"),
        {"grade_id": grade_id},
    ).fetchone()
    if not grade_row:
        raise HTTPException(status_code=404, detail="Grade not found")
    grade_group_id = grade_row[0]

    params = {
        "comment": text_comment if text_comment else None,
        "student_id": student_id,
        "program_id": program_id,
        "grade_id": grade_id,
        "grade_group_id": grade_group_id,
        "academic_id": academic_id,
        "marks_system_id": marks_system_id,
    }

    if exam_type_resolved == "yearly":
        if not result_name_resolved:
            raise HTTPException(status_code=400, detail="result_name is required")
        params["exam_name"] = result_name_resolved
        lookup = db.execute(
            text("""
                SELECT id FROM marks_yearly
                WHERE student_id = :student_id
                  AND program_id = :program_id
                  AND grade_id = :grade_id
                  AND academic_id = :academic_id
                  AND exam_name = :exam_name
                ORDER BY id DESC
                LIMIT 1
            """),
            params,
        ).fetchone()
        if not lookup:
            raise HTTPException(
                status_code=404,
                detail="No yearly result record found for this student and exam",
            )
        db.execute(
            text("""
                UPDATE marks_yearly
                SET teacher_comment = :comment, updated_at = NOW()
                WHERE id = :id
            """),
            {"comment": params["comment"], "id": lookup[0]},
        )
        table = "marks_yearly"
    elif exam_type_resolved == "semester":
        if not result_name_resolved:
            raise HTTPException(status_code=400, detail="result_name is required")
        params["exam_name"] = result_name_resolved
        lookup = db.execute(
            text("""
                SELECT id FROM marks_semester
                WHERE student_id = :student_id
                  AND program_id = :program_id
                  AND grade_id = :grade_id
                  AND academic_id = :academic_id
                  AND exam_name = :exam_name
                ORDER BY id DESC
                LIMIT 1
            """),
            params,
        ).fetchone()
        if not lookup:
            raise HTTPException(
                status_code=404,
                detail="No semester result record found for this student and exam",
            )
        db.execute(
            text("""
                UPDATE marks_semester
                SET teacher_comment = :comment, updated_at = NOW()
                WHERE id = :id
            """),
            {"comment": params["comment"], "id": lookup[0]},
        )
        table = "marks_semester"
    else:
        lookup = db.execute(
            text("""
                SELECT id FROM marks_monthly
                WHERE student_id = :student_id
                  AND program_id = :program_id
                  AND grade_id = :grade_id
                  AND academic_id = :academic_id
                  AND marks_system_id = :marks_system_id
                ORDER BY id DESC
                LIMIT 1
            """),
            params,
        ).fetchone()
        if not lookup:
            raise HTTPException(
                status_code=404,
                detail="No monthly result record found for this student and exam. Save marks first.",
            )
        db.execute(
            text("""
                UPDATE marks_monthly
                SET teacher_comment = :comment, updated_at = NOW()
                WHERE id = :id
            """),
            {"comment": params["comment"], "id": lookup[0]},
        )
        table = "marks_monthly"

    db.commit()
    return {
        "success": True,
        "comment": text_comment,
        "table": table,
        "exam_type": exam_type_resolved,
    }
