from types import SimpleNamespace

from app.api.v1.notifications import _notification_preferences_payload
from app.core.migrations import _notification_default_is_enabled
from app.services.notification_service import (
    filter_tokens_by_notification_preferences,
    notification_preference_category,
    token_allows_notification,
)


def test_notification_category_mapping_and_critical_bypass():
    assert notification_preference_category({"type": "attendance_reminder"}) == "attendance"
    assert notification_preference_category({"type": "leave_request_updated"}) == "leave"
    assert notification_preference_category({"type": "group_message"}) == "messages"
    assert notification_preference_category({"type": "new_news"}) == "announcements"
    assert notification_preference_category({"type": "market_order_update"}) == "marketplace"
    assert notification_preference_category({"type": "profile_edit_reply"}) == "other"
    assert notification_preference_category({"type": "force_logout"}) is None


def test_token_preferences_suppress_only_optional_categories():
    token = {
        "token": "abc",
        "notifications_enabled": True,
        "leave_notifications_enabled": False,
    }
    assert not token_allows_notification(token, {"type": "leave_request"})
    assert token_allows_notification(token, {"type": "attendance_reminder"})
    token["notifications_enabled"] = False
    assert not token_allows_notification(token, {"type": "new_news"})
    assert token_allows_notification(token, {"type": "force_logout"})

    token["notifications_enabled"] = 0
    assert not token_allows_notification(token, {"type": "attendance_reminder"})

    token["notifications_enabled"] = None
    token["attendance_notifications_enabled"] = None
    assert token_allows_notification(token, {"type": "attendance_reminder"})


def test_preferences_payload_defaults_and_saved_values():
    assert _notification_preferences_payload(None, registered=False)["leave_enabled"]
    row = SimpleNamespace(
        notifications_enabled=True,
        attendance_notifications_enabled=False,
        leave_notifications_enabled=True,
        message_notifications_enabled=False,
        announcement_notifications_enabled=True,
        market_notifications_enabled=False,
        other_notifications_enabled=True,
    )
    payload = _notification_preferences_payload(row, registered=True)
    assert payload["registered"] is True
    assert payload["attendance_enabled"] is False
    assert payload["messages_enabled"] is False
    assert payload["marketplace_enabled"] is False
    assert payload["other_enabled"] is True


def test_legacy_null_preferences_fail_open():
    row = SimpleNamespace(
        notifications_enabled=None,
        attendance_notifications_enabled=None,
        leave_notifications_enabled=None,
        message_notifications_enabled=None,
        announcement_notifications_enabled=None,
        market_notifications_enabled=None,
        other_notifications_enabled=None,
    )
    payload = _notification_preferences_payload(row, registered=True)
    assert all(value is True for key, value in payload.items() if key != "registered")


def test_preference_query_failure_does_not_block_pushes():
    class BrokenQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            raise RuntimeError("preference columns are not migrated")

    class BrokenSession:
        def query(self, *_args, **_kwargs):
            return BrokenQuery()

    tokens = [{"token": "still-deliver"}]
    assert filter_tokens_by_notification_preferences(
        BrokenSession(), tokens, {"type": "attendance_reminder"}
    ) == tokens


def test_notification_default_detection_requires_explicit_enabled_default():
    assert _notification_default_is_enabled(1)
    assert _notification_default_is_enabled("true")
    assert not _notification_default_is_enabled(None)
    assert not _notification_default_is_enabled(0)
