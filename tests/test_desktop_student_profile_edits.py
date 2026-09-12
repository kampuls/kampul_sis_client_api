from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "app" / "api" / "desktop" / "student_profile_edits.py"
).read_text(encoding="utf-8")
APP_ADMIN_SOURCE = (
    ROOT / "app" / "api" / "v1" / "app_admin.py"
).read_text(encoding="utf-8")
PARENTS_SOURCE = (
    ROOT / "app" / "api" / "v1" / "parents.py"
).read_text(encoding="utf-8")
NOTIFICATION_SOURCE = (
    ROOT / "app" / "services" / "notification_service.py"
).read_text(encoding="utf-8")
SEED_SOURCE = (
    ROOT / "app" / "core" / "seed_permissions.py"
).read_text(encoding="utf-8")


def test_profile_edit_review_accepts_app_admin_or_desktop_role_permission():
    assert "Depends(get_current_desktop_user)" in SOURCE
    assert 'PROFILE_EDIT_REVIEW_PERMISSION = "ReviewStudentProfileEdits"' in SOURCE
    assert "AppAdmin.user_id == current_user.id" in SOURCE
    assert "RolePermission.role_id == role_id" in SOURCE
    assert "Permission.permission_name == PROFILE_EDIT_REVIEW_PERMISSION" in SOURCE
    assert SOURCE.count(
        "_require_profile_edit_review_permission(db, current_user)"
    ) == 3
    assert 'request_status == "pending"' in SOURCE
    assert '"can_decide": request_status == "pending"' in SOURCE


def test_profile_edit_decisions_reuse_the_canonical_flutter_workflows():
    assert "return await _approve_profile_edit_core(" in SOURCE
    assert "action=EditRequestAction()" in SOURCE
    assert "return await _reject_profile_edit_core(" in SOURCE
    assert "action=EditRequestAction(reason=action.reason)" in SOURCE
    assert "background_tasks=background_tasks" in SOURCE
    assert "return await _approve_profile_edit_core(" in APP_ADMIN_SOURCE
    assert "return await _reject_profile_edit_core(" in APP_ADMIN_SOURCE
    assert "Only active App Admins can approve requests" in APP_ADMIN_SOURCE
    assert "Only active App Admins can reject requests" in APP_ADMIN_SOURCE


def test_profile_edit_permission_is_seeded_for_the_admin_role():
    assert '"ReviewStudentProfileEdits"' in SEED_SOURCE
    assert 'TARGET_ROLE_NAME = "Admin"' in SEED_SOURCE
    assert "permissions_map[name] = perm" in SEED_SOURCE
    assert "RolePermission(" in SEED_SOURCE


def test_profile_edit_notifications_include_permitted_desktop_users_without_fcm():
    assert "def get_role_permission_user_ids(" in NOTIFICATION_SOURCE
    assert "INNER JOIN role_permissions rp ON rp.role_id = u.role" in NOTIFICATION_SOURCE
    assert '"ReviewStudentProfileEdits"' in PARENTS_SOURCE
    assert "review_targets.extend(" in PARENTS_SOURCE
    assert "user_ids=review_targets" in PARENTS_SOURCE

    notification_block = PARENTS_SOURCE.split(
        "def _send_profile_edit_request_bg(", 1
    )[1].split("def _resolve_requester_name", 1)[0]
    assert "if tokens:" not in notification_block
    assert "notification_service.send_notification(" in notification_block


def test_desktop_router_exposes_student_profile_edit_surface():
    router_source = (
        ROOT / "app" / "api" / "desktop" / "__init__.py"
    ).read_text(encoding="utf-8")

    assert "student_profile_edits_router" in router_source
    assert 'prefix="/student-profile-edits"' in router_source
