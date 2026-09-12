from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import notification_service
from app.services import registration_notification_service as registration_notifications


def _session_with_user(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def test_staff_registration_approvers_are_combined_and_deduplicated():
    db = object()
    with (
        patch.object(
            notification_service,
            "get_app_admin_user_ids",
            return_value=[{"id": 7, "user_type": "teacher"}],
        ),
        patch.object(
            notification_service,
            "get_role_permission_user_ids",
            return_value=[
                {"id": 7, "user_type": "teacher"},
                {"id": 9, "user_type": "employee"},
            ],
        ) as permission_targets,
    ):
        result = registration_notifications.get_staff_registration_approver_user_ids(db)

    assert result == [
        {"id": 7, "user_type": "teacher"},
        {"id": 9, "user_type": "teacher"},
    ]
    permission_targets.assert_called_once_with(
        db,
        registration_notifications.PENDING_STAFF_PERMISSION,
    )


def test_new_staff_registration_uses_fresh_session_visible_push_and_inbox():
    user = SimpleNamespace(
        id=42,
        username="dara.staff",
        eName="Dara Sok",
        kName="សុខ ដារ៉ា",
    )
    db = _session_with_user(user)
    approvers = [{"id": 7, "user_type": "teacher"}]
    tokens = [{"id": 11, "token": "fcm", "device_type": "android"}]

    with (
        patch.object(registration_notifications, "SessionLocal", return_value=db),
        patch.object(
            registration_notifications,
            "get_staff_registration_approver_user_ids",
            return_value=approvers,
        ),
        patch.object(
            notification_service,
            "resolve_device_tokens_for_users",
            return_value=tokens,
        ),
        patch.object(notification_service, "send_notification", return_value=True) as send,
    ):
        registration_notifications.notify_approvers_new_staff_registration(42)

    kwargs = send.call_args.kwargs
    assert kwargs["device_tokens"] == tokens
    assert kwargs["user_ids"] == approvers
    assert kwargs["db"] is db
    assert kwargs["android_show_system_notification"] is True
    assert kwargs["channel_id"] == "message_channel"
    assert kwargs["data"]["type"] == "new_user_registration"
    assert kwargs["data"]["user_role"] == "employee"
    assert kwargs["redirect_route"] == "pending_staff_registrations"
    db.close.assert_called_once()


def test_staff_approval_is_saved_even_without_a_device_token():
    user = SimpleNamespace(
        id=42,
        username="dara.staff",
        eName="Dara Sok",
        kName="សុខ ដារ៉ា",
    )
    db = _session_with_user(user)

    with (
        patch.object(registration_notifications, "SessionLocal", return_value=db),
        patch.object(
            notification_service,
            "resolve_device_tokens_for_users",
            return_value=[],
        ),
        patch.object(notification_service, "send_notification", return_value=False) as send,
    ):
        registration_notifications.notify_staff_registration_approved(42)

    kwargs = send.call_args.kwargs
    assert kwargs["device_tokens"] == []
    assert kwargs["user_ids"] == [{"id": 42, "user_type": "teacher"}]
    assert kwargs["data"]["type"] == "staff_registration_approved"
    assert kwargs["android_show_system_notification"] is True
    db.close.assert_called_once()


def test_send_notification_copies_inbox_redirect_into_push_data():
    db = object()
    with (
        patch.object(notification_service, "save_notification") as save,
        patch.object(
            notification_service,
            "resolve_device_tokens_for_users",
            return_value=[],
        ),
    ):
        notification_service.send_notification(
            device_tokens=[],
            title="Request updated",
            body="Tap to review",
            data={"type": "request_updated"},
            db=db,
            user_ids=[{"id": 3, "user_type": "teacher"}],
            redirect_route="profile_edit_requests",
            redirect_args={"request_id": 18},
        )

    saved_data = save.call_args.kwargs["data"]
    assert saved_data["redirect_route"] == "profile_edit_requests"
    assert saved_data["request_id"] == "18"


def test_failed_inbox_write_rolls_back_the_session():
    db = MagicMock()
    db.add.side_effect = RuntimeError("write failed")

    result = notification_service.save_notification(
        db=db,
        user_id=3,
        user_type="teacher",
        title="Title",
        body="Body",
    )

    assert result is None
    db.rollback.assert_called_once()


def test_invalid_fcm_token_cleanup_uses_an_independent_session():
    cleanup_db = MagicMock()
    with patch(
        "app.core.database.SessionLocal",
        return_value=cleanup_db,
    ):
        notification_service._delete_invalid_device_token(
            {"id": 81, "token": "expired"},
            "expired",
        )

    statement, params = cleanup_db.execute.call_args.args
    assert "DELETE FROM device_tokens WHERE id" in str(statement)
    assert params == {"tid": 81}
    cleanup_db.commit.assert_called_once()
    cleanup_db.close.assert_called_once()
