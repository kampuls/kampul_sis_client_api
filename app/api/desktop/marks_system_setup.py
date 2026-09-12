"""Atomic Marks System cloning for the always-online desktop client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ...core import get_db
from ...models import Permission, RolePermission, User
from .data import get_current_desktop_user


router = APIRouter()
MARKS_SYSTEM_PERMISSION = "ViewMarkSubjects"
MAX_CLONE_ROWS = 10000


class MarksSystemCloneRequest(BaseModel):
    academic_id: int = Field(gt=0)
    target_academic_id: int = Field(gt=0)
    marks_system_ids: list[int] = Field(min_length=1, max_length=MAX_CLONE_ROWS)
    copy_compatible_only: bool = False


class MarksSystemClonePreview(BaseModel):
    ready: bool
    marks_systems: int
    calculation_rules: int
    subject_links: int
    calculation_subject_links: int
    skipped_marks_systems: int
    skipped_subject_links: int
    issues: list[str]
    warnings: list[str]


class MarksSystemCloneResult(BaseModel):
    success: bool = True
    created: int
    updated: int
    subject_links: int
    calculation_rules_created: int
    calculation_rules_updated: int
    calculation_subject_links: int
    skipped_marks_systems: int
    skipped_subject_links: int


@dataclass
class _CloneContext:
    systems: list[Mapping[str, Any]]
    system_subjects: dict[int, list[int]]
    rules: list[Mapping[str, Any]]
    rule_subjects: dict[int, list[int]]
    target_group_ids: dict[tuple[int, int], int]
    source_start: date
    target_start: date
    issues: list[str]
    warnings: list[str]
    skipped_marks_systems: int
    skipped_subject_links: int


def _mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def _normal(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _as_date(value: Any) -> date:
    return value.date() if isinstance(value, datetime) else value


def _shift_date(value: Any, source_start: date, target_start: date) -> date | None:
    if value is None:
        return None
    return target_start + timedelta(days=(_as_date(value) - source_start).days)


def _require_permission(db: Session, current_user: User) -> None:
    role_id = int(getattr(current_user, "role", 0) or 0)
    if role_id == 1:
        return
    allowed = (
        db.query(RolePermission.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(
            RolePermission.role_id == role_id,
            Permission.permission_name == MARKS_SYSTEM_PERMISSION,
        )
        .first()
    )
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {MARKS_SYSTEM_PERMISSION}",
        )


def _unique_ids(values: list[int]) -> list[int]:
    ids = list(dict.fromkeys(int(value) for value in values if int(value) > 0))
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one valid Marks System ID is required.",
        )
    return ids


def _academic(db: Session, academic_id: int) -> Mapping[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, academic_name, academic_us_name, academic_start, academic_end
            FROM academic
            WHERE id = :academic_id
            LIMIT 1
            """
        ),
        {"academic_id": academic_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="The selected academic year was not found.")
    academic = _mapping(row)
    if not academic["academic_start"] or not academic["academic_end"]:
        raise HTTPException(
            status_code=409,
            detail="The selected academic year must have start and end dates.",
        )
    return academic


def _prepare_context(
    db: Session,
    payload: MarksSystemCloneRequest,
    *,
    lock: bool,
) -> _CloneContext:
    if payload.target_academic_id == payload.academic_id:
        raise HTTPException(
            status_code=422,
            detail="The destination academic year must be different from the source year.",
        )
    system_ids = _unique_ids(payload.marks_system_ids)
    source_academic = _academic(db, payload.academic_id)
    target_academic = _academic(db, payload.target_academic_id)
    lock_sql = " FOR UPDATE" if lock else ""

    systems_statement = text(
        """
        SELECT ms.id, ms.marks_name, ms.marks_code, ms.program_id,
               ms.grade_group_id, ms.for_month, gg.group_name
        FROM marks_system ms
        INNER JOIN grade_group gg ON gg.id = ms.grade_group_id
        WHERE ms.academic_id = :academic_id
          AND gg.academic_id = :academic_id
          AND ms.id IN :system_ids
        """ + lock_sql
    ).bindparams(bindparam("system_ids", expanding=True))
    systems = [
        _mapping(row)
        for row in db.execute(
            systems_statement,
            {"academic_id": payload.academic_id, "system_ids": system_ids},
        ).fetchall()
    ]
    if len(systems) != len(system_ids):
        found = {int(row["id"]) for row in systems}
        missing = [value for value in system_ids if value not in found]
        raise HTTPException(
            status_code=404,
            detail=f"Some Marks Systems were not found in the source academic year: {missing}",
        )

    issues: list[str] = []
    warnings: list[str] = []
    scopes = {(int(row["program_id"]), int(row["grade_group_id"])) for row in systems}
    selected_by_scope: dict[tuple[int, int], set[int]] = {}
    for row in systems:
        key = (int(row["program_id"]), int(row["grade_group_id"]))
        selected_by_scope.setdefault(key, set()).add(int(row["id"]))

    # A calculation setup contains aggregate semester/year rules for the whole
    # Grade Group, so accepting a partial group would silently change output.
    for program_id, grade_group_id in sorted(scopes):
        rows = db.execute(
            text(
                """
                SELECT id FROM marks_system
                WHERE academic_id = :academic_id
                  AND program_id = :program_id
                  AND grade_group_id = :grade_group_id
                """ + lock_sql
            ),
            {
                "academic_id": payload.academic_id,
                "program_id": program_id,
                "grade_group_id": grade_group_id,
            },
        ).fetchall()
        all_ids = {int(row[0]) for row in rows}
        if all_ids != selected_by_scope[(program_id, grade_group_id)]:
            group_name = next(
                str(row["group_name"] or grade_group_id)
                for row in systems
                if int(row["grade_group_id"]) == grade_group_id
                and int(row["program_id"]) == program_id
            )
            issues.append(
                f"Select every Marks System for Grade Group '{group_name}' "
                "so its semester and yearly calculations remain complete."
            )

    target_groups = [
        _mapping(row)
        for row in db.execute(
            text(
                """
                SELECT id, program_id, group_name
                FROM grade_group
                WHERE academic_id = :academic_id
                ORDER BY id
                """ + lock_sql
            ),
            {"academic_id": payload.target_academic_id},
        ).fetchall()
    ]
    target_by_name: dict[tuple[int, str], list[int]] = {}
    for row in target_groups:
        key = (int(row["program_id"]), _normal(row["group_name"]))
        target_by_name.setdefault(key, []).append(int(row["id"]))

    target_group_ids: dict[tuple[int, int], int] = {}
    for row in systems:
        source_scope = (int(row["program_id"]), int(row["grade_group_id"]))
        if source_scope in target_group_ids:
            continue
        candidates = target_by_name.get(
            (int(row["program_id"]), _normal(row["group_name"])), []
        )
        if len(candidates) == 1:
            target_group_ids[source_scope] = candidates[0]
        elif not candidates:
            issues.append(
                f"No matching Grade Group for '{row['group_name']}' exists in the destination year."
            )
        else:
            issues.append(
                f"More than one destination Grade Group matches '{row['group_name']}'."
            )

    subjects_statement = text(
        """
        SELECT marks_system_id, subject_id
        FROM marks_system_subjects
        WHERE marks_system_id IN :system_ids
        ORDER BY marks_system_id, subject_id
        """
    ).bindparams(bindparam("system_ids", expanding=True))
    system_subjects: dict[int, list[int]] = {system_id: [] for system_id in system_ids}
    for row in db.execute(subjects_statement, {"system_ids": system_ids}).fetchall():
        system_subjects[int(row[0])].append(int(row[1]))

    scope_conditions = " OR ".join(
        f"(program_id = :program_{index} AND grade_group_id = :group_{index})"
        for index, _ in enumerate(sorted(scopes))
    )
    scope_params: dict[str, Any] = {"academic_id": payload.academic_id}
    for index, (program_id, grade_group_id) in enumerate(sorted(scopes)):
        scope_params[f"program_{index}"] = program_id
        scope_params[f"group_{index}"] = grade_group_id
    rules = [
        _mapping(row)
        for row in db.execute(
            text(
                """
                SELECT id, result_name, exam_type, formula_expression,
                       marks_system_id, program_id, grade_group_id,
                       divide_by_multiplier, is_active, sign_code
                FROM exam_calculate_sign
                WHERE academic_id = :academic_id AND ("""
                + scope_conditions
                + ")"
                + lock_sql
            ),
            scope_params,
        ).fetchall()
    ]
    selected_set = set(system_ids)
    for rule in rules:
        referenced_id = int(rule["marks_system_id"] or 0)
        if referenced_id > 0 and referenced_id not in selected_set:
            issues.append(
                f"Calculation rule '{rule['sign_code'] or rule['result_name']}' references an unselected Marks System."
            )

    rule_ids = [int(row["id"]) for row in rules]
    rule_subjects: dict[int, list[int]] = {rule_id: [] for rule_id in rule_ids}
    if rule_ids:
        rule_subject_statement = text(
            """
            SELECT exam_calculate_sign_id, subject_id
            FROM exam_calculate_sign_subjects
            WHERE exam_calculate_sign_id IN :rule_ids
            ORDER BY exam_calculate_sign_id, subject_id
            """
        ).bindparams(bindparam("rule_ids", expanding=True))
        for row in db.execute(rule_subject_statement, {"rule_ids": rule_ids}).fetchall():
            rule_subjects[int(row[0])].append(int(row[1]))

    subject_names: dict[int, str] = {}
    required_by_scope: dict[tuple[int, int], set[int]] = {}
    system_by_id = {int(row["id"]): row for row in systems}
    for system_id, subject_ids in system_subjects.items():
        system = system_by_id[system_id]
        scope = (int(system["program_id"]), int(system["grade_group_id"]))
        required_by_scope.setdefault(scope, set()).update(subject_ids)
    rule_by_id = {int(row["id"]): row for row in rules}
    for rule_id, subject_ids in rule_subjects.items():
        rule = rule_by_id[rule_id]
        scope = (int(rule["program_id"]), int(rule["grade_group_id"]))
        required_by_scope.setdefault(scope, set()).update(subject_ids)

    all_required = sorted(set().union(*required_by_scope.values())) if required_by_scope else []
    if all_required:
        names_statement = text(
            "SELECT id, subject_name FROM subjects WHERE id IN :subject_ids"
        ).bindparams(bindparam("subject_ids", expanding=True))
        subject_names = {
            int(row[0]): str(row[1] or row[0])
            for row in db.execute(names_statement, {"subject_ids": all_required}).fetchall()
        }
    configured_by_scope: dict[tuple[int, int], set[int]] = {}
    for scope, required in required_by_scope.items():
        target_group_id = target_group_ids.get(scope)
        if target_group_id is None or not required:
            continue
        configured = {
            int(row[0])
            for row in db.execute(
                text(
                    """
                    SELECT subject_id FROM subjects_group
                    WHERE academic_id = :academic_id
                      AND program_id = :program_id
                      AND grade_group_id = :grade_group_id
                    """ + lock_sql
                ),
                {
                    "academic_id": payload.target_academic_id,
                    "program_id": scope[0],
                    "grade_group_id": target_group_id,
                },
            ).fetchall()
        }
        configured_by_scope[scope] = configured
        missing = sorted(required - configured)
        if missing:
            source = next(
                row
                for row in systems
                if int(row["program_id"]) == scope[0]
                and int(row["grade_group_id"]) == scope[1]
            )
            names = ", ".join(subject_names.get(value, str(value)) for value in missing)
            message = (
                f"Destination Grade Group '{source['group_name']}' is missing "
                f"subject(s): {names}."
            )
            if payload.copy_compatible_only:
                warnings.append(message)
            else:
                issues.append(message)

    skipped_marks_systems = 0
    skipped_subject_links = 0
    if payload.copy_compatible_only:
        eligible_scopes: set[tuple[int, int]] = set()
        for scope in scopes:
            required = required_by_scope.get(scope, set())
            configured = configured_by_scope.get(scope, set())
            if not required or required.intersection(configured):
                eligible_scopes.add(scope)
                continue
            source = next(
                row
                for row in systems
                if int(row["program_id"]) == scope[0]
                and int(row["grade_group_id"]) == scope[1]
            )
            warnings.append(
                f"Skipped Grade Group '{source['group_name']}' because it has no "
                "compatible subjects in the destination year."
            )

        original_system_count = len(systems)
        original_subject_link_count = sum(len(values) for values in system_subjects.values())
        original_rule_subject_link_count = sum(len(values) for values in rule_subjects.values())

        systems = [
            row
            for row in systems
            if (int(row["program_id"]), int(row["grade_group_id"])) in eligible_scopes
        ]
        eligible_system_ids = {int(row["id"]) for row in systems}
        system_subjects = {
            system_id: [
                subject_id
                for subject_id in subject_ids
                if subject_id
                in configured_by_scope.get(
                    (
                        int(system_by_id[system_id]["program_id"]),
                        int(system_by_id[system_id]["grade_group_id"]),
                    ),
                    set(subject_ids),
                )
            ]
            for system_id, subject_ids in system_subjects.items()
            if system_id in eligible_system_ids
        }
        rules = [
            row
            for row in rules
            if (int(row["program_id"]), int(row["grade_group_id"])) in eligible_scopes
            and (
                int(row["marks_system_id"] or 0) == 0
                or int(row["marks_system_id"]) in eligible_system_ids
            )
        ]
        eligible_rule_ids = {int(row["id"]) for row in rules}
        rule_subjects = {
            rule_id: [
                subject_id
                for subject_id in subject_ids
                if subject_id
                in configured_by_scope.get(
                    (
                        int(rule_by_id[rule_id]["program_id"]),
                        int(rule_by_id[rule_id]["grade_group_id"]),
                    ),
                    set(subject_ids),
                )
            ]
            for rule_id, subject_ids in rule_subjects.items()
            if rule_id in eligible_rule_ids
        }
        skipped_marks_systems = original_system_count - len(systems)
        skipped_subject_links = (
            original_subject_link_count
            + original_rule_subject_link_count
            - sum(len(values) for values in system_subjects.values())
            - sum(len(values) for values in rule_subjects.values())
        )
        if not systems:
            issues.append(
                "No compatible Marks Systems remain to copy. Configure at least one "
                "matching destination subject first."
            )

    # Refuse to overwrite duplicate or already-used destination systems.
    for system in systems:
        scope = (int(system["program_id"]), int(system["grade_group_id"]))
        target_group_id = target_group_ids.get(scope)
        if target_group_id is None:
            continue
        code = _normal(system["marks_code"])
        match_column = "LOWER(TRIM(marks_code))" if code else "LOWER(TRIM(marks_name))"
        match_value = code or _normal(system["marks_name"])
        matches = db.execute(
            text(
                f"""
                SELECT id FROM marks_system
                WHERE academic_id = :academic_id
                  AND program_id = :program_id
                  AND grade_group_id = :grade_group_id
                  AND {match_column} = :match_value
                """ + lock_sql
            ),
            {
                "academic_id": payload.target_academic_id,
                "program_id": int(system["program_id"]),
                "grade_group_id": target_group_id,
                "match_value": match_value,
            },
        ).fetchall()
        if len(matches) > 1:
            issues.append(
                f"Destination has duplicate Marks Systems for '{system['marks_code'] or system['marks_name']}'."
            )
        elif matches:
            used = int(
                db.execute(
                    text("SELECT COUNT(*) FROM marks_input WHERE marks_system_id = :system_id"),
                    {"system_id": int(matches[0][0])},
                ).scalar()
                or 0
            )
            if used:
                issues.append(
                    f"Destination Marks System '{system['marks_code'] or system['marks_name']}' already has student marks."
                )

    return _CloneContext(
        systems=systems,
        system_subjects=system_subjects,
        rules=rules,
        rule_subjects=rule_subjects,
        target_group_ids=target_group_ids,
        source_start=_as_date(source_academic["academic_start"]),
        target_start=_as_date(target_academic["academic_start"]),
        issues=list(dict.fromkeys(issues)),
        warnings=list(dict.fromkeys(warnings)),
        skipped_marks_systems=skipped_marks_systems,
        skipped_subject_links=skipped_subject_links,
    )


def _preview(context: _CloneContext) -> MarksSystemClonePreview:
    return MarksSystemClonePreview(
        ready=not context.issues,
        marks_systems=len(context.systems),
        calculation_rules=len(context.rules),
        subject_links=sum(len(values) for values in context.system_subjects.values()),
        calculation_subject_links=sum(len(values) for values in context.rule_subjects.values()),
        skipped_marks_systems=context.skipped_marks_systems,
        skipped_subject_links=context.skipped_subject_links,
        issues=context.issues,
        warnings=context.warnings,
    )


@router.post("/clone/preview", response_model=MarksSystemClonePreview)
def preview_marks_system_clone(
    payload: MarksSystemCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> MarksSystemClonePreview:
    _require_permission(db, current_user)
    return _preview(_prepare_context(db, payload, lock=False))


@router.post("/clone", response_model=MarksSystemCloneResult)
def clone_marks_systems(
    payload: MarksSystemCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_desktop_user),
) -> MarksSystemCloneResult:
    _require_permission(db, current_user)
    try:
        context = _prepare_context(db, payload, lock=True)
        if context.issues:
            raise HTTPException(status_code=409, detail={"issues": context.issues})

        created = updated = subject_links = 0
        system_id_map: dict[int, int] = {}
        for source in context.systems:
            source_id = int(source["id"])
            scope = (int(source["program_id"]), int(source["grade_group_id"]))
            target_group_id = context.target_group_ids[scope]
            code = _normal(source["marks_code"])
            match_column = "LOWER(TRIM(marks_code))" if code else "LOWER(TRIM(marks_name))"
            match_value = code or _normal(source["marks_name"])
            existing = db.execute(
                text(
                    f"""
                    SELECT id FROM marks_system
                    WHERE academic_id = :academic_id
                      AND program_id = :program_id
                      AND grade_group_id = :grade_group_id
                      AND {match_column} = :match_value
                    LIMIT 1 FOR UPDATE
                    """
                ),
                {
                    "academic_id": payload.target_academic_id,
                    "program_id": int(source["program_id"]),
                    "grade_group_id": target_group_id,
                    "match_value": match_value,
                },
            ).first()
            values = {
                "marks_name": source["marks_name"],
                "marks_code": source["marks_code"],
                "program_id": int(source["program_id"]),
                "grade_group_id": target_group_id,
                "academic_id": payload.target_academic_id,
                "for_month": _shift_date(
                    source["for_month"], context.source_start, context.target_start
                ),
                "user_id": int(current_user.id),
            }
            if existing is None:
                result = db.execute(
                    text(
                        """
                        INSERT INTO marks_system (
                            marks_name, marks_code, program_id, grade_group_id,
                            academic_id, for_month, created_by, updated_by,
                            created_at, updated_at
                        ) VALUES (
                            :marks_name, :marks_code, :program_id, :grade_group_id,
                            :academic_id, :for_month, :user_id, :user_id, NOW(), NOW()
                        )
                        """
                    ),
                    values,
                )
                target_system_id = int(result.lastrowid)
                created += 1
            else:
                target_system_id = int(existing[0])
                db.execute(
                    text(
                        """
                        UPDATE marks_system
                        SET marks_name = :marks_name,
                            marks_code = :marks_code,
                            for_month = :for_month,
                            updated_by = :user_id,
                            updated_at = NOW()
                        WHERE id = :target_id
                        """
                    ),
                    {**values, "target_id": target_system_id},
                )
                updated += 1
            system_id_map[source_id] = target_system_id
            db.execute(
                text("DELETE FROM marks_system_subjects WHERE marks_system_id = :system_id"),
                {"system_id": target_system_id},
            )
            for subject_id in context.system_subjects[source_id]:
                db.execute(
                    text(
                        """
                        INSERT INTO marks_system_subjects (
                            marks_system_id, subject_id, created_at, updated_at
                        ) VALUES (:system_id, :subject_id, NOW(), NOW())
                        """
                    ),
                    {"system_id": target_system_id, "subject_id": subject_id},
                )
                subject_links += 1

        rules_created = rules_updated = rule_subject_links = 0
        for source in context.rules:
            source_rule_id = int(source["id"])
            source_system_id = int(source["marks_system_id"] or 0)
            target_system_id = system_id_map.get(source_system_id, 0)
            scope = (int(source["program_id"]), int(source["grade_group_id"]))
            target_group_id = context.target_group_ids[scope]
            existing = db.execute(
                text(
                    """
                    SELECT id FROM exam_calculate_sign
                    WHERE academic_id = :academic_id
                      AND program_id = :program_id
                      AND grade_group_id = :grade_group_id
                      AND LOWER(TRIM(exam_type)) = :exam_type
                      AND COALESCE(marks_system_id, 0) = :marks_system_id
                      AND LOWER(TRIM(COALESCE(sign_code, ''))) = :sign_code
                    LIMIT 1 FOR UPDATE
                    """
                ),
                {
                    "academic_id": payload.target_academic_id,
                    "program_id": int(source["program_id"]),
                    "grade_group_id": target_group_id,
                    "exam_type": _normal(source["exam_type"]),
                    "marks_system_id": target_system_id,
                    "sign_code": _normal(source["sign_code"]),
                },
            ).first()
            values = {
                "result_name": source["result_name"],
                "exam_type": source["exam_type"],
                "formula_expression": source["formula_expression"],
                "marks_system_id": target_system_id,
                "academic_id": payload.target_academic_id,
                "program_id": int(source["program_id"]),
                "grade_group_id": target_group_id,
                "divide_by_multiplier": source["divide_by_multiplier"],
                "is_active": source["is_active"],
                "sign_code": source["sign_code"],
            }
            if existing is None:
                result = db.execute(
                    text(
                        """
                        INSERT INTO exam_calculate_sign (
                            result_name, exam_type, formula_expression,
                            marks_system_id, academic_id, program_id, grade_group_id,
                            divide_by_multiplier, is_active, sign_code,
                            created_at, updated_at
                        ) VALUES (
                            :result_name, :exam_type, :formula_expression,
                            :marks_system_id, :academic_id, :program_id, :grade_group_id,
                            :divide_by_multiplier, :is_active, :sign_code, NOW(), NOW()
                        )
                        """
                    ),
                    values,
                )
                target_rule_id = int(result.lastrowid)
                rules_created += 1
            else:
                target_rule_id = int(existing[0])
                db.execute(
                    text(
                        """
                        UPDATE exam_calculate_sign
                        SET result_name = :result_name,
                            formula_expression = :formula_expression,
                            divide_by_multiplier = :divide_by_multiplier,
                            is_active = :is_active,
                            updated_at = NOW()
                        WHERE id = :target_rule_id
                        """
                    ),
                    {**values, "target_rule_id": target_rule_id},
                )
                rules_updated += 1
            db.execute(
                text(
                    "DELETE FROM exam_calculate_sign_subjects "
                    "WHERE exam_calculate_sign_id = :rule_id"
                ),
                {"rule_id": target_rule_id},
            )
            for subject_id in context.rule_subjects[source_rule_id]:
                db.execute(
                    text(
                        """
                        INSERT INTO exam_calculate_sign_subjects (
                            exam_calculate_sign_id, subject_id, created_at, updated_at
                        ) VALUES (:rule_id, :subject_id, NOW(), NOW())
                        """
                    ),
                    {"rule_id": target_rule_id, "subject_id": subject_id},
                )
                rule_subject_links += 1

        db.commit()
        return MarksSystemCloneResult(
            created=created,
            updated=updated,
            subject_links=subject_links,
            calculation_rules_created=rules_created,
            calculation_rules_updated=rules_updated,
            calculation_subject_links=rule_subject_links,
            skipped_marks_systems=context.skipped_marks_systems,
            skipped_subject_links=context.skipped_subject_links,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
