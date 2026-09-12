from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: str, name: str, next_name: str) -> str:
    source = (ROOT / path).read_text(encoding="utf-8")
    return source.split(f"def {name}(", 1)[1].split(f"def {next_name}(", 1)[0]


def test_mobile_staff_approval_queues_the_same_result_notification():
    source = (ROOT / "app/api/v1/admin_users.py").read_text(encoding="utf-8")
    update = source.split("def update_admin_user(", 1)[1].split(
        '@router.get("/admin/users/{user_id}/home-app-permissions")',
        1,
    )[0]

    assert "previous_status == 2" in update
    assert "notify_staff_registration_approved" in update
    assert "background_tasks.add_task(" in update


def test_pending_student_request_is_visible_and_saved_without_tokens():
    block = _function_source(
        "app/api/v1/students.py",
        "_notify_admins_new_pending_child_bg",
        "create_student",
    )

    assert "get_app_admin_user_ids(db)" in block
    assert "if tokens:" not in block
    assert "android_show_system_notification=True" in block
    assert "user_ids=admin_targets" in block


def test_profile_edit_replies_and_student_decisions_keep_inbox_delivery():
    reply = _function_source(
        "app/api/v1/app_admin.py",
        "_send_profile_edit_reply_bg",
        "_approve_profile_edit_core",
    )
    student_decision = _function_source(
        "app/api/v1/app_admin.py",
        "_notify_parent_pending_decision_bg",
        "approve_pending_student",
    )

    for block in (reply, student_decision):
        assert "if not tokens:" not in block
        assert "android_show_system_notification=True" in block
        assert "user_ids=" in block


def test_active_app_admin_queries_exclude_disabled_staff_accounts():
    source = (ROOT / "app/services/notification_service.py").read_text(
        encoding="utf-8"
    )
    user_ids = source.split("def get_app_admin_user_ids(", 1)[1].split(
        "def get_role_permission_user_ids(",
        1,
    )[0]
    tokens = source.split("def get_app_admin_device_tokens(", 1)[1].split(
        "def resolve_device_tokens_for_users(",
        1,
    )[0]

    for block in (user_ids, tokens):
        assert "INNER JOIN users u ON u.id = aa.user_id" in block
        assert "u.status = 1" in block
