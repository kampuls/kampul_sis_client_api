from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "app" / "api" / "desktop" / "staff_registrations.py"
).read_text(encoding="utf-8")


def _function_source(name: str, next_marker: str | None = None) -> str:
    start = SOURCE.index(f"def {name}(")
    if next_marker is None:
        return SOURCE[start:]
    end = SOURCE.index(next_marker, start)
    return SOURCE[start:end]


def test_pending_staff_actions_require_the_existing_role_permission():
    permission_check = _function_source(
        "_has_pending_staff_permission",
        "def _require_pending_staff_permission(",
    )
    details = _function_source(
        "get_pending_staff_registration",
        '@router.post("/{user_id}/approve")',
    )
    approval = _function_source("approve_pending_staff_registration")

    assert 'PENDING_STAFF_PERMISSION = "ViewPendingEmployees"' in SOURCE
    assert "RolePermission.role_id == role_id" in permission_check
    assert "Permission.permission_name == PENDING_STAFF_PERMISSION" in permission_check
    assert "_require_pending_staff_permission(db, current_user)" in details
    assert "_require_pending_staff_permission(db, current_user)" in approval


def test_pending_staff_approval_is_atomic_and_only_activates_status_two():
    approval = _function_source("approve_pending_staff_registration")

    assert ".with_for_update()" in approval
    assert "if current_status == ACTIVE_STAFF_STATUS" in approval
    assert "if current_status != PENDING_STAFF_STATUS" in approval
    assert "target.status = ACTIVE_STAFF_STATUS" in approval
    assert "db.commit()" in approval
    assert "db.rollback()" in approval
    assert '"already_approved": True' in approval
    assert "background_tasks.add_task(notify_staff_registration_approved" in approval


def test_desktop_router_exposes_typed_staff_registration_surface():
    source = (ROOT / "app" / "api" / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert "staff_registrations_router" in source
    assert 'prefix="/staff-registrations"' in source


def test_new_staff_notifications_include_desktop_role_approvers():
    auth_source = (ROOT / "app" / "api" / "v1" / "auth.py").read_text(
        encoding="utf-8"
    )
    service_source = (
        ROOT / "app" / "services" / "registration_notification_service.py"
    ).read_text(encoding="utf-8")

    assert "background_tasks.add_task(" in auth_source
    assert "notify_approvers_new_staff_registration" in auth_source
    assert "get_app_admin_user_ids(db)" in service_source
    assert "get_role_permission_user_ids(" in service_source
    assert 'PENDING_STAFF_PERMISSION = "ViewPendingEmployees"' in service_source
    assert "android_show_system_notification=True" in service_source
    assert 'redirect_route="pending_staff_registrations"' in service_source
