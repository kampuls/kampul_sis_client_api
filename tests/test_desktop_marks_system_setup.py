from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_INIT = ROOT / "app" / "api" / "desktop" / "__init__.py"
MARKS_SYSTEM_SETUP = ROOT / "app" / "api" / "desktop" / "marks_system_setup.py"


def test_desktop_router_mounts_marks_system_clone_surface():
    package = DESKTOP_INIT.read_text(encoding="utf-8")
    source = MARKS_SYSTEM_SETUP.read_text(encoding="utf-8")

    assert "marks_system_setup_router" in package
    assert 'prefix="/marks-system-setup"' in package
    assert '@router.post("/clone/preview"' in source
    assert '@router.post("/clone"' in source


def test_marks_system_clone_is_authenticated_scoped_and_atomic():
    source = MARKS_SYSTEM_SETUP.read_text(encoding="utf-8")

    assert "Depends(get_current_desktop_user)" in source
    assert 'MARKS_SYSTEM_PERMISSION = "ViewMarkSubjects"' in source
    assert "ms.academic_id = :academic_id" in source
    assert "gg.academic_id = :academic_id" in source
    assert "FOR UPDATE" in source
    assert "db.commit()" in source
    assert "db.rollback()" in source
    assert "target_academic_id" in source


def test_marks_system_clone_remaps_setup_but_never_copies_results():
    source = MARKS_SYSTEM_SETUP.read_text(encoding="utf-8")

    assert "target_by_name" in source
    assert "subjects_group" in source
    assert "system_id_map" in source
    assert "INSERT INTO marks_system_subjects" in source
    assert "INSERT INTO exam_calculate_sign_subjects" in source
    assert "INSERT INTO exam_calculate_sign" in source
    assert "INSERT INTO marks_input" not in source
    assert "INSERT INTO marks_monthly" not in source
    assert "INSERT INTO marks_semester" not in source
    assert "INSERT INTO marks_yearly" not in source


def test_marks_system_clone_rejects_partial_or_incompatible_setup():
    source = MARKS_SYSTEM_SETUP.read_text(encoding="utf-8")

    assert "Select every Marks System for Grade Group" in source
    assert 'f"subject(s): {names}."' in source
    assert "already has student marks" in source
    assert "if context.issues:" in source
    assert "raise HTTPException(status_code=409" in source


def test_marks_system_clone_can_skip_missing_subjects_explicitly():
    source = MARKS_SYSTEM_SETUP.read_text(encoding="utf-8")

    assert "copy_compatible_only: bool = False" in source
    assert "eligible_scopes" in source
    assert "Skipped Grade Group" in source
    assert "skipped_marks_systems" in source
    assert "skipped_subject_links" in source
    assert "warnings" in source


def test_marks_system_exam_dates_are_shifted_relative_to_academic_start():
    source = MARKS_SYSTEM_SETUP.read_text(encoding="utf-8")

    assert "def _shift_date" in source
    assert "target_start + timedelta" in source
    assert "context.source_start" in source
    assert "context.target_start" in source
