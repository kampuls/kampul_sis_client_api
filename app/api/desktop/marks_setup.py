"""Atomic subject-group mark setup operations for the always-online desktop."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import Permission, RolePermission, User
from .data import get_current_desktop_user


router = APIRouter()
SUBJECT_GROUP_PERMISSION = "ViewSubjectGroups"
GRADE_SCALE_PERMISSION = "ViewNites"
MAX_SETUP_ROWS = 10000


class SubjectGroupSelection(BaseModel):
    academic_id: int = Field(gt=0)
    setup_ids: list[int] = Field(min_length=1, max_length=MAX_SETUP_ROWS)


class SubjectGroupCloneRequest(SubjectGroupSelection):
    target_academic_id: int = Field(gt=0)
    target_grade_group_id: int | None = Field(default=None, gt=0)
    max_mark: Decimal | None = Field(default=None, gt=0, le=Decimal("100000"))


class SubjectGroupBulkMaxRequest(SubjectGroupSelection):
    max_mark: Decimal = Field(gt=0, le=Decimal("100000"))


class GradeScaleCloneRequest(BaseModel):
    academic_id: int = Field(gt=0)
    target_academic_id: int = Field(gt=0)
    target_grade_group_id: int | None = Field(default=None, gt=0)
    scale_ids: list[int] = Field(min_length=1, max_length=MAX_SETUP_ROWS)


class SubjectGroupDeleteResult(BaseModel):
    success: bool = True
    deleted: int
    marks_input_deleted: int
    references_updated: int
    marks_systems_deactivated: int


class SubjectGroupCloneResult(BaseModel):
    success: bool = True
    created: int
    updated: int
    skipped: int
    missing_grade_groups: list[str]


class SubjectGroupBulkMaxResult(BaseModel):
    success: bool = True
    updated: int
    max_mark: Decimal


class GradeScaleCloneResult(BaseModel):
    success: bool = True
    created: int
    updated: int
    skipped: int
    missing_grade_groups: list[str]


class MarksSetupGradeGroupOption(BaseModel):
    id: int
    group_name: str
    program_id: int
    academic_id: int


def _require_subject_group_permission(db: Session, current_user: User) -> None:
    role_id = int(getattr(current_user, "role", 0) or 0)
    if role_id == 1:
        return
    allowed = (
        db.query(RolePermission.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(
            RolePermission.role_id == role_id,
            Permission.permission_name == SUBJECT_GROUP_PERMISSION,
        )
        .first()
    )
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {SUBJECT_GROUP_PERMISSION}",
        )


def _has_permission(db: Session, current_user: User, permission_name: str) -> bool:
    role_id = int(getattr(current_user, "role", 0) or 0)
    if role_id == 1:
        return True
    return (
        db.query(RolePermission.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(
            RolePermission.role_id == role_id,
            Permission.permission_name == permission_name,
        )
        .first()
        is not None
    )


def _require_grade_scale_permission(db: Session, current_user: User) -> None:
    if not _has_permission(db, current_user, GRADE_SCALE_PERMISSION):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {GRADE_SCALE_PERMISSION}",
        )


def _require_grade_group_options_permission(
    db: Session,
    current_user: User,
) -> None:
    if _has_permission(db, current_user, SUBJECT_GROUP_PERMISSION):
        return
    _require_grade_scale_permission(db, current_user)


def _unique_positive_ids(values: list[int]) -> list[int]:
    ids = list(dict.fromkeys(int(value) for value in values if int(value) > 0))
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one valid subject-group setup ID is required.",
        )
    if len(ids) > MAX_SETUP_ROWS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A maximum of {MAX_SETUP_ROWS} rows can be changed at once.",
        )
    return ids


def _mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def _remove_csv_subject(value: Any, subject_id: int) -> tuple[str, bool]:
    original = "" if value is None else str(value)
    tokens = [token.strip() for token in original.split(",") if token.strip()]
    remaining = [token for token in tokens if token != str(subject_id)]
    return ",".join(remaining), len(remaining) != len(tokens)


_SUBJECT_FORMULA = re.compile(r"^\s*[+-]?\d+(?:\s*[+-]\s*\d+)*\s*$")
_SUBJECT_TERM = re.compile(r"[+-]?\s*\d+")


def _remove_formula_subject(value: Any, subject_id: int) -> tuple[str, bool]:
    """Remove a subject only from legacy formulas made solely from subject IDs."""
    original = "" if value is None else str(value)
    if not original.strip() or _SUBJECT_FORMULA.fullmatch(original) is None:
        return original, False
    terms = _SUBJECT_TERM.findall(original)
    remaining = [
        term.replace(" ", "")
        for term in terms
        if term.replace(" ", "").lstrip("+-") != str(subject_id)
    ]
    changed = len(remaining) != len(terms)
    if not changed:
        return original, False
    normalized = "".join(
        term if index == 0 or term.startswith(("+", "-")) else "+" + term
        for index, term in enumerate(remaining)
    )
    return normalized, True


def _load_selected_setups(
    db: Session,
    academic_id: int,
    setup_ids: list[int],
) -> list[Mapping[str, Any]]:
    statement = text(
        """
        SELECT
            sg.id,
            sg.academic_id,
            sg.program_id,
            sg.grade_group_id,
            sg.subject_id,
            sg.full_marks,
            sg.calculate_marks,
            gg.group_name
        FROM subjects_group sg
        INNER JOIN grade_group gg ON gg.id = sg.grade_group_id
        WHERE sg.academic_id = :academic_id
          AND sg.id IN :setup_ids
        FOR UPDATE
        """
    ).bindparams(bindparam("setup_ids", expanding=True))
    rows = [
        _mapping(row)
        for row in db.execute(
            statement,
            {"academic_id": academic_id, "setup_ids": setup_ids},
        ).fetchall()
    ]
    if len(rows) != len(setup_ids):
        found = {int(row["id"]) for row in rows}
        missing = [setup_id for setup_id in setup_ids if setup_id not in found]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Some subject-group setups were not found in the selected academic "
                f"year: {missing}"
            ),
        )
    return rows


def _load_selected_grade_scales(
    db: Session,
    academic_id: int,
    scale_ids: list[int],
) -> list[Mapping[str, Any]]:
    statement = text(
        """
        SELECT
            gs.id,
            gs.academic_id,
            gs.grade_group_id,
            gs.min_marks,
            gs.max_marks,
            gs.us_grade,
            gs.kh_grade,
            gs.scale_discount,
            gs.is_overall,
            gg.group_name,
            gg.program_id
        FROM grade_scale gs
        INNER JOIN grade_group gg ON gg.id = gs.grade_group_id
        WHERE gs.academic_id = :academic_id
          AND gg.academic_id = :academic_id
          AND gs.id IN :scale_ids
        FOR UPDATE
        """
    ).bindparams(bindparam("scale_ids", expanding=True))
    rows = [
        _mapping(row)
        for row in db.execute(
            statement,
            {"academic_id": academic_id, "scale_ids": scale_ids},
        ).fetchall()
    ]
    if len(rows) != len(scale_ids):
        found = {int(row["id"]) for row in rows}
        missing = [scale_id for scale_id in scale_ids if scale_id not in found]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Some grade scales were not found in the selected academic "
                f"year: {missing}"
            ),
        )
    return rows


def _commit_or_rollback(db: Session, operation) -> Any:
    try:
        result = operation()
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/grade-groups", response_model=list[MarksSetupGradeGroupOption])
def list_grade_group_options(
    academic_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> list[MarksSetupGradeGroupOption]:
    _require_grade_group_options_permission(db, current_user)
    rows = db.execute(
        text(
            """
            SELECT id, group_name, program_id, academic_id
            FROM grade_group
            WHERE academic_id = :academic_id
            ORDER BY program_id, group_name, id
            """
        ),
        {"academic_id": academic_id},
    ).fetchall()
    return [MarksSetupGradeGroupOption(**dict(_mapping(row))) for row in rows]


@router.post("/grade-scales/clone", response_model=GradeScaleCloneResult)
def clone_grade_scales(
    payload: GradeScaleCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> GradeScaleCloneResult:
    _require_grade_scale_permission(db, current_user)
    if payload.target_academic_id == payload.academic_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The destination academic year must be different from the source year.",
        )
    scale_ids = _unique_positive_ids(payload.scale_ids)

    def operation() -> GradeScaleCloneResult:
        sources = _load_selected_grade_scales(
            db,
            payload.academic_id,
            scale_ids,
        )
        target_exists = db.execute(
            text("SELECT id FROM academic WHERE id = :academic_id LIMIT 1"),
            {"academic_id": payload.target_academic_id},
        ).first()
        if target_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The destination academic year was not found.",
            )

        explicit_target_group: Mapping[str, Any] | None = None
        if payload.target_grade_group_id is not None:
            source_group_ids = {int(source["grade_group_id"]) for source in sources}
            if len(source_group_ids) != 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Choose automatic Grade Group matching when copying scales "
                        "from more than one source Grade Group."
                    ),
                )
            target_row = db.execute(
                text(
                    """
                    SELECT id, program_id, group_name
                    FROM grade_group
                    WHERE id = :grade_group_id
                      AND academic_id = :academic_id
                    LIMIT 1
                    FOR UPDATE
                    """
                ),
                {
                    "grade_group_id": payload.target_grade_group_id,
                    "academic_id": payload.target_academic_id,
                },
            ).first()
            if target_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        "The destination Grade Group was not found in the selected "
                        "academic year."
                    ),
                )
            explicit_target_group = _mapping(target_row)
            source_program_ids = {int(source["program_id"]) for source in sources}
            if source_program_ids != {int(explicit_target_group["program_id"])}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "The destination Grade Group must use the same program as "
                        "the selected source Grade Group."
                    ),
                )

        target_groups = []
        if explicit_target_group is None:
            target_groups = db.execute(
                text(
                    """
                    SELECT id, program_id, LOWER(TRIM(group_name)) AS group_key
                    FROM grade_group
                    WHERE academic_id = :academic_id
                    ORDER BY id
                    FOR UPDATE
                    """
                ),
                {"academic_id": payload.target_academic_id},
            ).fetchall()
        target_by_key: dict[tuple[int, str], int] = {}
        for row in target_groups:
            group = _mapping(row)
            target_by_key.setdefault(
                (int(group["program_id"]), str(group["group_key"] or "")),
                int(group["id"]),
            )

        created = 0
        updated = 0
        missing: list[str] = []
        for source in sources:
            group_name = str(source["group_name"] or "").strip()
            target_group_id = (
                int(explicit_target_group["id"])
                if explicit_target_group is not None
                else target_by_key.get(
                    (int(source["program_id"]), group_name.lower())
                )
            )
            if target_group_id is None:
                missing.append(group_name or f"Group {source['grade_group_id']}")
                continue

            existing = db.execute(
                text(
                    """
                    SELECT id
                    FROM grade_scale
                    WHERE academic_id = :academic_id
                      AND grade_group_id = :grade_group_id
                      AND min_marks = :min_marks
                      AND max_marks = :max_marks
                    ORDER BY id
                    LIMIT 1
                    FOR UPDATE
                    """
                ),
                {
                    "academic_id": payload.target_academic_id,
                    "grade_group_id": target_group_id,
                    "min_marks": source["min_marks"],
                    "max_marks": source["max_marks"],
                },
            ).first()
            values = {
                "academic_id": payload.target_academic_id,
                "grade_group_id": target_group_id,
                "min_marks": source["min_marks"],
                "max_marks": source["max_marks"],
                "us_grade": source["us_grade"],
                "kh_grade": source["kh_grade"],
                "scale_discount": source["scale_discount"],
                "is_overall": int(source["is_overall"] or 0),
            }
            if existing is None:
                db.execute(
                    text(
                        """
                        INSERT INTO grade_scale (
                            academic_id,
                            grade_group_id,
                            min_marks,
                            max_marks,
                            us_grade,
                            kh_grade,
                            scale_discount,
                            is_overall,
                            created_at,
                            updated_at
                        ) VALUES (
                            :academic_id,
                            :grade_group_id,
                            :min_marks,
                            :max_marks,
                            :us_grade,
                            :kh_grade,
                            :scale_discount,
                            :is_overall,
                            NOW(),
                            NOW()
                        )
                        """
                    ),
                    values,
                )
                created += 1
            else:
                db.execute(
                    text(
                        """
                        UPDATE grade_scale
                        SET us_grade = :us_grade,
                            kh_grade = :kh_grade,
                            scale_discount = :scale_discount,
                            is_overall = :is_overall,
                            updated_at = NOW()
                        WHERE id = :scale_id
                        """
                    ),
                    {**values, "scale_id": int(existing[0])},
                )
                updated += 1

        missing_names = list(dict.fromkeys(missing))
        return GradeScaleCloneResult(
            created=created,
            updated=updated,
            skipped=len(sources) - created - updated,
            missing_grade_groups=missing_names,
        )

    return _commit_or_rollback(db, operation)


@router.post("/subject-groups/delete", response_model=SubjectGroupDeleteResult)
def delete_subject_group_setups(
    payload: SubjectGroupSelection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> SubjectGroupDeleteResult:
    _require_subject_group_permission(db, current_user)
    setup_ids = _unique_positive_ids(payload.setup_ids)

    def operation() -> SubjectGroupDeleteResult:
        rows = _load_selected_setups(db, payload.academic_id, setup_ids)
        marks_input_deleted = 0
        references_updated = 0
        deactivated_system_ids: set[int] = set()

        for setup in rows:
            scope = {
                "academic_id": int(setup["academic_id"]),
                "program_id": int(setup["program_id"]),
                "grade_group_id": int(setup["grade_group_id"]),
                "subject_id": int(setup["subject_id"]),
            }
            marks_input_deleted += int(
                db.execute(
                    text(
                        """
                        DELETE FROM marks_input
                        WHERE academic_id = :academic_id
                          AND program_id = :program_id
                          AND grade_group_id = :grade_group_id
                          AND subject_id = :subject_id
                        """
                    ),
                    scope,
                ).rowcount
                or 0
            )

            systems = db.execute(
                text(
                    """
                    SELECT
                        ms.id,
                        ms.subjects_ids,
                        EXISTS (
                            SELECT 1
                            FROM marks_system_subjects mss
                            WHERE mss.marks_system_id = ms.id
                              AND mss.subject_id = :subject_id
                        ) AS normalized_match
                    FROM marks_system ms
                    WHERE ms.academic_id = :academic_id
                      AND ms.program_id = :program_id
                      AND ms.grade_group_id = :grade_group_id
                    FOR UPDATE
                    """
                ),
                scope,
            ).fetchall()

            for system_row in systems:
                system = _mapping(system_row)
                marks_system_id = int(system["id"])
                system_scope = {**scope, "marks_system_id": marks_system_id}
                new_subjects, csv_changed = _remove_csv_subject(
                    system.get("subjects_ids"), scope["subject_id"]
                )
                if not bool(system["normalized_match"]) and not csv_changed:
                    continue

                if csv_changed:
                    db.execute(
                        text(
                            """
                            UPDATE marks_system
                            SET subjects_ids = :subjects_ids,
                                updated_by = :updated_by,
                                updated_at = NOW()
                            WHERE id = :marks_system_id
                            """
                        ),
                        {
                            "subjects_ids": new_subjects,
                            "updated_by": int(current_user.id),
                            "marks_system_id": marks_system_id,
                        },
                    )
                    references_updated += 1

                references_updated += int(
                    db.execute(
                        text(
                            """
                            DELETE FROM marks_system_subjects
                            WHERE marks_system_id = :marks_system_id
                              AND subject_id = :subject_id
                            """
                        ),
                        system_scope,
                    ).rowcount
                    or 0
                )

                sign_rows = db.execute(
                    text(
                        """
                        SELECT id, formula_expression
                        FROM exam_calculate_sign
                        WHERE academic_id = :academic_id
                          AND program_id = :program_id
                          AND grade_group_id = :grade_group_id
                          AND marks_system_id = :marks_system_id
                        FOR UPDATE
                        """
                    ),
                    system_scope,
                ).fetchall()
                for sign_row in sign_rows:
                    sign = _mapping(sign_row)
                    sign_id = int(sign["id"])
                    references_updated += int(
                        db.execute(
                            text(
                                """
                                DELETE FROM exam_calculate_sign_subjects
                                WHERE exam_calculate_sign_id = :sign_id
                                  AND subject_id = :subject_id
                                """
                            ),
                            {"sign_id": sign_id, "subject_id": scope["subject_id"]},
                        ).rowcount
                        or 0
                    )
                    formula, formula_changed = _remove_formula_subject(
                        sign.get("formula_expression"), scope["subject_id"]
                    )
                    if formula_changed:
                        if formula:
                            db.execute(
                                text(
                                    """
                                    UPDATE exam_calculate_sign
                                    SET formula_expression = :formula,
                                        updated_at = NOW()
                                    WHERE id = :sign_id
                                    """
                                ),
                                {"formula": formula, "sign_id": sign_id},
                            )
                        else:
                            db.execute(
                                text(
                                    "DELETE FROM exam_calculate_sign_subjects "
                                    "WHERE exam_calculate_sign_id = :sign_id"
                                ),
                                {"sign_id": sign_id},
                            )
                            db.execute(
                                text("DELETE FROM exam_calculate_sign WHERE id = :sign_id"),
                                {"sign_id": sign_id},
                            )
                        references_updated += 1

                normalized_count = int(
                    db.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM marks_system_subjects
                            WHERE marks_system_id = :marks_system_id
                            """
                        ),
                        {"marks_system_id": marks_system_id},
                    ).scalar()
                    or 0
                )
                csv_count = len(
                    [token for token in new_subjects.split(",") if token.strip()]
                )
                if normalized_count == 0 and csv_count == 0:
                    db.execute(
                        text(
                            """
                            UPDATE marks_system
                            SET status = 0,
                                updated_by = :updated_by,
                                updated_at = NOW()
                            WHERE id = :marks_system_id
                            """
                        ),
                        {
                            "updated_by": int(current_user.id),
                            "marks_system_id": marks_system_id,
                        },
                    )
                    deactivated_system_ids.add(marks_system_id)

            db.execute(
                text("DELETE FROM subjects_group WHERE id = :setup_id"),
                {"setup_id": int(setup["id"])},
            )

        return SubjectGroupDeleteResult(
            deleted=len(rows),
            marks_input_deleted=marks_input_deleted,
            references_updated=references_updated,
            marks_systems_deactivated=len(deactivated_system_ids),
        )

    return _commit_or_rollback(db, operation)


@router.post("/subject-groups/clone", response_model=SubjectGroupCloneResult)
def clone_subject_group_setups(
    payload: SubjectGroupCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> SubjectGroupCloneResult:
    _require_subject_group_permission(db, current_user)
    if payload.target_academic_id == payload.academic_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The destination academic year must be different from the source year.",
        )
    setup_ids = _unique_positive_ids(payload.setup_ids)

    def operation() -> SubjectGroupCloneResult:
        sources = _load_selected_setups(db, payload.academic_id, setup_ids)
        target_exists = db.execute(
            text("SELECT id FROM academic WHERE id = :academic_id LIMIT 1"),
            {"academic_id": payload.target_academic_id},
        ).first()
        if target_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The destination academic year was not found.",
            )

        explicit_target_group: Mapping[str, Any] | None = None
        if payload.target_grade_group_id is not None:
            target_row = db.execute(
                text(
                    """
                    SELECT id, program_id, group_name
                    FROM grade_group
                    WHERE id = :grade_group_id
                      AND academic_id = :academic_id
                    LIMIT 1
                    FOR UPDATE
                    """
                ),
                {
                    "grade_group_id": payload.target_grade_group_id,
                    "academic_id": payload.target_academic_id,
                },
            ).first()
            if target_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        "The destination Grade Group was not found in the selected "
                        "academic year."
                    ),
                )
            explicit_target_group = _mapping(target_row)
            source_program_ids = {int(source["program_id"]) for source in sources}
            if source_program_ids != {int(explicit_target_group["program_id"])}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "The destination Grade Group must use the same program as "
                        "every selected source setup."
                    ),
                )

        target_groups = []
        if explicit_target_group is None:
            target_groups = db.execute(
                text(
                    """
                    SELECT id, program_id, LOWER(TRIM(group_name)) AS group_key
                    FROM grade_group
                    WHERE academic_id = :academic_id
                    ORDER BY id
                    """
                ),
                {"academic_id": payload.target_academic_id},
            ).fetchall()
        target_by_key: dict[tuple[int, str], int] = {}
        for row in target_groups:
            group = _mapping(row)
            target_by_key.setdefault(
                (int(group["program_id"]), str(group["group_key"] or "")),
                int(group["id"]),
            )

        created = 0
        updated = 0
        missing: list[str] = []
        for source in sources:
            group_name = str(source["group_name"] or "").strip()
            target_group_id = (
                int(explicit_target_group["id"])
                if explicit_target_group is not None
                else target_by_key.get(
                    (int(source["program_id"]), group_name.lower())
                )
            )
            if target_group_id is None:
                missing.append(group_name or f"Group {source['grade_group_id']}")
                continue

            maximum = payload.max_mark or Decimal(str(source["full_marks"]))
            existing = db.execute(
                text(
                    """
                    SELECT id
                    FROM subjects_group
                    WHERE academic_id = :academic_id
                      AND program_id = :program_id
                      AND grade_group_id = :grade_group_id
                      AND subject_id = :subject_id
                    ORDER BY id
                    LIMIT 1
                    FOR UPDATE
                    """
                ),
                {
                    "academic_id": payload.target_academic_id,
                    "program_id": int(source["program_id"]),
                    "grade_group_id": target_group_id,
                    "subject_id": int(source["subject_id"]),
                },
            ).first()
            values = {
                "academic_id": payload.target_academic_id,
                "program_id": int(source["program_id"]),
                "grade_group_id": target_group_id,
                "subject_id": int(source["subject_id"]),
                "full_marks": maximum,
                "calculate_marks": Decimal(str(source["calculate_marks"])),
                "user_id": int(current_user.id),
                "noted": f"Cloned from academic {payload.academic_id}",
            }
            if existing is None:
                db.execute(
                    text(
                        """
                        INSERT INTO subjects_group (
                            grade_group_id,
                            program_id,
                            subject_id,
                            full_marks,
                            calculate_marks,
                            academic_id,
                            created_by,
                            updated_by,
                            noted,
                            created_at,
                            updated_at
                        ) VALUES (
                            :grade_group_id,
                            :program_id,
                            :subject_id,
                            :full_marks,
                            :calculate_marks,
                            :academic_id,
                            :user_id,
                            :user_id,
                            :noted,
                            NOW(),
                            NOW()
                        )
                        """
                    ),
                    values,
                )
                created += 1
            else:
                db.execute(
                    text(
                        """
                        UPDATE subjects_group
                        SET full_marks = :full_marks,
                            calculate_marks = :calculate_marks,
                            updated_by = :user_id,
                            updated_at = NOW()
                        WHERE id = :setup_id
                        """
                    ),
                    {**values, "setup_id": int(existing[0])},
                )
                updated += 1

        missing_names = list(dict.fromkeys(missing))
        return SubjectGroupCloneResult(
            created=created,
            updated=updated,
            skipped=len(sources) - created - updated,
            missing_grade_groups=missing_names,
        )

    return _commit_or_rollback(db, operation)


@router.post("/subject-groups/bulk-max", response_model=SubjectGroupBulkMaxResult)
def bulk_update_subject_group_maximum(
    payload: SubjectGroupBulkMaxRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> SubjectGroupBulkMaxResult:
    _require_subject_group_permission(db, current_user)
    setup_ids = _unique_positive_ids(payload.setup_ids)

    def operation() -> SubjectGroupBulkMaxResult:
        _load_selected_setups(db, payload.academic_id, setup_ids)
        statement = text(
            """
            UPDATE subjects_group
            SET full_marks = :max_mark,
                updated_by = :updated_by,
                updated_at = NOW()
            WHERE academic_id = :academic_id
              AND id IN :setup_ids
            """
        ).bindparams(bindparam("setup_ids", expanding=True))
        db.execute(
            statement,
            {
                "max_mark": payload.max_mark,
                "updated_by": int(current_user.id),
                "academic_id": payload.academic_id,
                "setup_ids": setup_ids,
            },
        )
        return SubjectGroupBulkMaxResult(
            updated=len(setup_ids),
            max_mark=payload.max_mark,
        )

    return _commit_or_rollback(db, operation)
