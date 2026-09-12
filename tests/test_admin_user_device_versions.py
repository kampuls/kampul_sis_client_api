from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.admin_users import (
    _active_staff_device_tokens,
    _app_device_payload,
)
from app.models.device import DeviceToken


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    DeviceToken.__table__.create(engine)
    return Session(engine)


def test_staff_device_lookup_excludes_colliding_parent_and_student_ids():
    db = _session()
    try:
        db.add_all(
            [
                DeviceToken(
                    user_id=7,
                    user_type="teacher",
                    device_token="staff",
                    device_type="ios",
                    device_name="Staff iPhone",
                    app_version="1.3.1",
                    is_active=True,
                ),
                DeviceToken(
                    user_id=7,
                    user_type="parent",
                    device_token="parent",
                    device_type="android",
                    device_name="Parent phone",
                    app_version="9.9.9",
                    is_active=True,
                ),
                DeviceToken(
                    user_id=7,
                    user_type="student",
                    device_token="student",
                    app_version="8.8.8",
                    is_active=True,
                ),
            ]
        )
        db.commit()

        rows = _active_staff_device_tokens(db, [7])

        assert [row.device_token for row in rows] == ["staff"]
    finally:
        db.close()


def test_staff_devices_are_ordered_by_latest_activity_and_keep_metadata_together():
    db = _session()
    try:
        earlier = datetime(2026, 8, 8, 8, 0)
        later = earlier + timedelta(hours=1)
        db.add_all(
            [
                DeviceToken(
                    user_id=9,
                    user_type="teacher",
                    device_token="old",
                    device_type="android",
                    device_name="Galaxy S24",
                    app_version="1.3.1",
                    is_active=True,
                    last_used_at=earlier,
                ),
                DeviceToken(
                    user_id=9,
                    user_type="teacher",
                    device_token="latest",
                    device_type="ios",
                    device_name="iPhone 17 Pro Max",
                    app_version="1.2.9",
                    is_active=True,
                    last_used_at=later,
                ),
            ]
        )
        db.commit()

        rows = _active_staff_device_tokens(db, [9])
        payload = _app_device_payload(rows[0])

        assert [row.device_token for row in rows] == ["latest", "old"]
        assert payload["device_type"] == "ios"
        assert payload["device_name"] == "iPhone 17 Pro Max"
        assert payload["app_version"] == "1.2.9"
        assert payload["last_seen_at"] == later.isoformat()
    finally:
        db.close()
