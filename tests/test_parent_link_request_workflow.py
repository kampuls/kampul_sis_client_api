from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENTS_SOURCE = (ROOT / "app/api/v1/parents.py").read_text(encoding="utf-8")
NOTIFICATION_SOURCE = (
    ROOT / "app/services/link_request_notification_service.py"
).read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_link_request_accepts_current_and_legacy_qr_identifiers_atomically():
    request = _between(
        PARENTS_SOURCE,
        "async def request_link_child(",
        '@router.get("/admin/link-requests/pending"',
    )

    assert "studentid = :student_identifier" in request
    assert "id = :internal_id" in request
    assert "FOR UPDATE" in request
    assert "db.commit()" in request
    assert "db.rollback()" in request
    assert "background_tasks.add_task(notify_admins_new_link_request" in request


def test_approval_locks_request_and_parent_before_linking_child():
    approval = _between(
        PARENTS_SOURCE,
        "async def process_link_request(",
        '@router.get("/link-requests/pending"',
    )

    assert approval.count("FOR UPDATE") >= 2
    assert "UPDATE parent_student_link_requests" in approval
    assert "UPDATE parents SET myChilds" in approval
    assert "db.commit()" in approval
    assert "db.rollback()" in approval
    assert "background_tasks.add_task(notify_parent_link_request_decision" in approval


def test_link_notifications_are_visible_persistent_and_actionable():
    assert "if tokens:" not in NOTIFICATION_SOURCE
    assert NOTIFICATION_SOURCE.count("android_show_system_notification=True") == 2
    assert NOTIFICATION_SOURCE.count("user_ids=") >= 2
    assert 'redirect_route="admin_link_requests"' in NOTIFICATION_SOURCE
    assert 'redirect_route="my_children"' in NOTIFICATION_SOURCE
    assert '"type": "link_request"' in NOTIFICATION_SOURCE
    assert '"type": "link_request_reply"' in NOTIFICATION_SOURCE
    assert 'f"link_request:{row[0]}:{row[7]}"' in NOTIFICATION_SOURCE
