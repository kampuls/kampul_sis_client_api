from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "app" / "api" / "desktop" / "parent_registrations.py"
).read_text(encoding="utf-8")


def _function_source(name: str, next_marker: str | None = None) -> str:
    start = SOURCE.index(f"def {name}(")
    if next_marker is None:
        return SOURCE[start:]
    end = SOURCE.index(next_marker, start)
    return SOURCE[start:end]


def test_parent_registration_details_require_active_app_admin():
    details = _function_source(
        "get_parent_registration",
        '@router.post("/{parent_id}/approve")',
    )

    assert "_require_app_admin(db, current_user)" in details
    assert "_fetch_linked_students" in SOURCE
    assert '"students": [student.model_dump() for student in students]' in SOURCE


def test_parent_approval_reuses_canonical_linked_child_workflow():
    approval = _function_source("approve_parent_registration")

    assert "process_parent_registration(" in approval
    assert 'AdminParentRegistrationAction(action="approve")' in approval
    assert "background_tasks=background_tasks" in approval
    assert "current_user=current_user" in approval


def test_desktop_router_exposes_parent_registration_surface():
    router_source = (ROOT / "app" / "api" / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert "parent_registrations_router" in router_source
    assert 'prefix="/parent-registrations"' in router_source
