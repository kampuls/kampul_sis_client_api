import ast
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_INIT = ROOT / "app" / "api" / "desktop" / "__init__.py"
MARKS_SETUP = ROOT / "app" / "api" / "desktop" / "marks_setup.py"
MIGRATIONS = ROOT / "app" / "core" / "migrations.py"


def _load_cleanup_helpers():
    parsed = ast.parse(MARKS_SETUP.read_text(encoding="utf-8"))
    wanted = {
        "_SUBJECT_FORMULA",
        "_SUBJECT_TERM",
        "_remove_csv_subject",
        "_remove_formula_subject",
    }
    nodes = [
        node
        for node in parsed.body
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name) and target.id in wanted
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
        )
        or isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]
    namespace = {"re": re, "Any": Any}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MARKS_SETUP), "exec"), namespace)
    return namespace["_remove_csv_subject"], namespace["_remove_formula_subject"]


def test_desktop_router_mounts_typed_marks_setup_surface():
    source = DESKTOP_INIT.read_text(encoding="utf-8")

    assert "marks_setup_router" in source
    assert 'prefix="/marks-setup"' in source

    marks_source = MARKS_SETUP.read_text(encoding="utf-8")
    assert '@router.get("/grade-groups"' in marks_source
    assert '@router.post("/subject-groups/delete"' in marks_source
    assert '@router.post("/subject-groups/clone"' in marks_source
    assert '@router.post("/subject-groups/bulk-max"' in marks_source
    assert '@router.post("/grade-scales/clone"' in marks_source


def test_marks_setup_mutations_are_authenticated_scoped_and_atomic():
    source = MARKS_SETUP.read_text(encoding="utf-8")

    assert "Depends(get_current_desktop_user)" in source
    assert 'SUBJECT_GROUP_PERMISSION = "ViewSubjectGroups"' in source
    assert "sg.academic_id = :academic_id" in source
    assert "FOR UPDATE" in source
    assert "db.commit()" in source
    assert "db.rollback()" in source
    assert "target_academic_id" in source
    assert "target_grade_group_id" in source
    assert "The destination Grade Group must use the same program" in source
    assert "LOWER(TRIM(group_name))" in source


def test_grade_scale_clone_is_scoped_remapped_and_atomic():
    source = MARKS_SETUP.read_text(encoding="utf-8")

    assert 'GRADE_SCALE_PERMISSION = "ViewNites"' in source
    assert "gs.academic_id = :academic_id" in source
    assert "gg.academic_id = :academic_id" in source
    assert "payload.target_academic_id" in source
    assert "payload.target_grade_group_id" in source
    assert "INSERT INTO grade_scale" in source
    assert "UPDATE grade_scale" in source
    assert "scale_discount = :scale_discount" in source
    assert "is_overall = :is_overall" in source
    assert "Choose automatic Grade Group matching" in source


def test_marks_setup_junction_tables_are_owned_by_server_migrations():
    migrations = MIGRATIONS.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS marks_system_subjects" in migrations
    assert "CREATE TABLE IF NOT EXISTS exam_calculate_sign_subjects" in migrations


def test_legacy_subject_lookup_does_not_depend_on_database_collation():
    source = MARKS_SETUP.read_text(encoding="utf-8")

    assert "FIND_IN_SET" not in source
    assert ") AS normalized_match" in source
    assert 'system["normalized_match"]' in source


def test_csv_subject_cleanup_is_exact_and_preserves_other_subjects():
    _remove_csv_subject, _ = _load_cleanup_helpers()
    value, changed = _remove_csv_subject("1, 10, 21", 1)

    assert changed is True
    assert value == "10,21"
    assert _remove_csv_subject(value, 2) == (value, False)


def test_formula_cleanup_only_changes_legacy_subject_id_formulas():
    _, _remove_formula_subject = _load_cleanup_helpers()
    assert _remove_formula_subject("+1+10-21", 10) == ("+1-21", True)
    assert _remove_formula_subject("MON1+MON2", 1) == ("MON1+MON2", False)
    assert _remove_formula_subject("1", 1) == ("", True)
