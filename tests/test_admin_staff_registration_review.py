from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app/api/v1/admin_users.py").read_text(encoding="utf-8")


def test_admin_user_status_filter_keeps_inactive_and_pending_distinct():
    listing = SOURCE.split('def list_admin_users(', 1)[1].split(
        '@router.get("/admin/users/{user_id}/registration-review")',
        1,
    )[0]

    assert 'where_conditions.append("u.status = :status")' in listing
    assert 'params["status"] = status' in listing
    assert 'where_conditions.append("u.status != 1")' not in listing
    assert "2=pending registration" in listing


def test_registration_review_is_pending_only_and_returns_submitted_sections():
    review = SOURCE.split('def get_admin_user_registration_review(', 1)[1].split(
        '@router.post("/admin/users/{user_id}/approve-registration")',
        1,
    )[0]

    assert "_ensure_admin(current_user)" in review
    assert 'int(values.get("status") or 0) != 2' in review
    assert "u.identityNumber" in review
    assert "u.bankAccountNumber" in review
    assert "u.numberOfDependents" in review
    assert "u.created_at" in review
    assert "status.HTTP_409_CONFLICT" in review


def test_mobile_registration_approval_is_atomic_and_pending_only():
    approval = SOURCE.split('def approve_admin_staff_registration(', 1)[1].split(
        '@router.put("/admin/users/{user_id}")',
        1,
    )[0]

    assert ".with_for_update()" in approval
    assert "if current_status != 2" in approval
    assert "target.status = 1" in approval
    assert "db.commit()" in approval
    assert "db.rollback()" in approval
    assert "payload.apply_default_locks" in approval
    assert "UserHomeAppPermission(" in approval
    assert "notify_staff_registration_approved" in approval
