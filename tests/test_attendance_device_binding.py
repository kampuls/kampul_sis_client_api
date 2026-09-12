from datetime import datetime, timedelta
import json
import unittest

from app.models.attendance_primary_device import (
    AttendancePrimaryDevice,
    AttendancePrimaryDeviceEvent,
)
from app.schemas.employee_attendance import CheckInOutResponse
from app.services.attendance_device_binding import (
    ATTENDANCE_DEVICE_CHANGE_DAYS,
    AttendanceDeviceChangeLocked,
    AttendancePrimaryDeviceMismatch,
    binding_status,
    change_locked_detail,
    change_primary_attendance_device,
    ensure_existing_primary_matches,
    ensure_or_register_primary_for_attendance,
    mismatch_detail,
    normalize_attendance_device_identity,
    refresh_matching_primary_device_metadata,
    reset_primary_attendance_device,
)


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if self.model is AttendancePrimaryDevice:
            return self.session.binding
        return None


class _FakeSession:
    def __init__(self, binding=None):
        self.binding = binding
        self.events = []
        self.deleted = []

    def query(self, model):
        return _FakeQuery(self, model)

    def add(self, value):
        if isinstance(value, AttendancePrimaryDevice):
            self.binding = value
        elif isinstance(value, AttendancePrimaryDeviceEvent):
            self.events.append(value)

    def delete(self, value):
        self.deleted.append(value)
        if value is self.binding:
            self.binding = None


class AttendanceDeviceBindingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 21, 8, 0, 0)
        self.phone_one = normalize_attendance_device_identity(
            "A" * 43,
            "Samsung Galaxy S24",
            "android",
        )
        self.phone_two = normalize_attendance_device_identity(
            "B" * 43,
            "Pisith's iPhone",
            "ios",
        )

    def test_first_successful_attendance_stages_primary_and_cooldown(self):
        db = _FakeSession()

        binding = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        self.assertIs(db.binding, binding)
        self.assertEqual(binding.device_name, "Samsung Galaxy S24")
        self.assertEqual(
            binding.change_available_at,
            self.now + timedelta(days=ATTENDANCE_DEVICE_CHANGE_DAYS),
        )
        self.assertEqual([event.action for event in db.events], ["auto_registered"])

    def test_same_phone_remains_allowed_after_registration(self):
        db = _FakeSession()
        first = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        second = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now + timedelta(days=1),
        )

        self.assertIs(first, second)
        self.assertEqual(len(db.events), 1)

    def test_same_installation_can_refresh_generic_iphone_model(self):
        db = _FakeSession()
        original = normalize_attendance_device_identity(
            "C" * 43,
            "iPhone (iPhone)",
            "ios",
        )
        binding = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=original,
            now=self.now,
        )
        resolved = normalize_attendance_device_identity(
            "C" * 43,
            "iPhone 16 Pro Max",
            "ios",
        )

        changed = refresh_matching_primary_device_metadata(binding, resolved)

        self.assertTrue(changed)
        self.assertEqual(binding.device_name, "iPhone 16 Pro Max")
        self.assertEqual(binding.device_id_hash, resolved.id_hash)
        self.assertEqual(len(db.events), 1)

    def test_different_installation_cannot_refresh_saved_model(self):
        db = _FakeSession()
        binding = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        changed = refresh_matching_primary_device_metadata(
            binding,
            self.phone_two,
        )

        self.assertFalse(changed)
        self.assertEqual(binding.device_name, "Samsung Galaxy S24")

    def test_other_phone_is_blocked(self):
        db = _FakeSession()
        ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        with self.assertRaises(AttendancePrimaryDeviceMismatch):
            ensure_or_register_primary_for_attendance(
                db,
                user_id=10,
                identity=self.phone_two,
                now=self.now + timedelta(days=1),
            )

    def test_verified_previous_installation_id_migrates_same_phone(self):
        db = _FakeSession()
        legacy_identity = normalize_attendance_device_identity(
            "L" * 43,
            "samsung SM-A055F",
            "android",
        )
        stable_identity = normalize_attendance_device_identity(
            "S" * 43,
            "samsung SM-A055F",
            "android",
        )
        binding = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=legacy_identity,
            now=self.now,
        )

        migrated = ensure_existing_primary_matches(
            db,
            user_id=10,
            identity=stable_identity,
            previous_identity=legacy_identity,
        )

        self.assertIs(migrated, binding)
        self.assertEqual(binding.device_id_hash, stable_identity.id_hash)
        self.assertEqual(
            [event.action for event in db.events],
            ["auto_registered", "installation_id_migrated"],
        )

    def test_model_name_alone_cannot_migrate_another_phone(self):
        db = _FakeSession()
        original = normalize_attendance_device_identity(
            "L" * 43,
            "samsung SM-A055F",
            "android",
        )
        another_phone = normalize_attendance_device_identity(
            "N" * 43,
            "samsung SM-A055F",
            "android",
        )
        wrong_previous = normalize_attendance_device_identity(
            "W" * 43,
            "samsung SM-A055F",
            "android",
        )
        ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=original,
            now=self.now,
        )

        with self.assertRaises(AttendancePrimaryDeviceMismatch):
            ensure_existing_primary_matches(
                db,
                user_id=10,
                identity=another_phone,
                previous_identity=wrong_previous,
            )

    def test_mismatch_detail_names_the_primary_phone_for_older_apps(self):
        db = _FakeSession()
        binding = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        detail = mismatch_detail(binding)

        self.assertEqual(detail["code"], "attendance_primary_device_mismatch")
        self.assertEqual(detail["primary_device_name"], "Samsung Galaxy S24")
        self.assertIn("primary attendance phone", detail["message"])
        self.assertIn("Samsung Galaxy S24", detail["message"])
        self.assertIsInstance(detail["registered_at"], str)
        self.assertIsInstance(detail["change_available_at"], str)
        self.assertIsInstance(json.dumps(detail), str)

    def test_change_is_locked_until_30_days_then_restarts_cooldown(self):
        db = _FakeSession()
        ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        with self.assertRaises(AttendanceDeviceChangeLocked) as locked:
            change_primary_attendance_device(
                db,
                user_id=10,
                identity=self.phone_two,
                now=self.now + timedelta(days=29),
            )
        locked_detail = change_locked_detail(locked.exception)
        self.assertIsInstance(locked_detail["change_available_at"], str)
        self.assertIsInstance(json.dumps(locked_detail), str)

        changed_at = self.now + timedelta(days=30)
        status = change_primary_attendance_device(
            db,
            user_id=10,
            identity=self.phone_two,
            now=changed_at,
        )

        self.assertTrue(status["is_current_device_primary"])
        self.assertFalse(status["can_change"])
        self.assertEqual(
            db.binding.change_available_at,
            changed_at + timedelta(days=30),
        )
        self.assertEqual(db.events[-1].action, "employee_changed")

    def test_admin_reset_clears_binding_and_next_attendance_registers_again(self):
        db = _FakeSession()
        ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_one,
            now=self.now,
        )

        had_primary = reset_primary_attendance_device(
            db,
            user_id=10,
            actor_user_id=1,
            reason="Employee replaced a lost phone",
        )

        self.assertTrue(had_primary)
        self.assertIsNone(db.binding)
        self.assertEqual(db.events[-1].action, "admin_reset")
        empty_status = binding_status(None, self.phone_two, now=self.now)
        self.assertFalse(empty_status["has_primary_device"])

        replacement = ensure_or_register_primary_for_attendance(
            db,
            user_id=10,
            identity=self.phone_two,
            now=self.now + timedelta(hours=1),
        )
        self.assertEqual(replacement.device_name, "Pisith's iPhone")
        self.assertEqual(db.events[-1].action, "auto_registered")

    def test_attendance_response_marks_one_time_phone_registration(self):
        response = CheckInOutResponse(
            success=True,
            message="Check-in successful",
            timestamp=self.now,
            action="check_in",
            primary_device_registered=True,
            primary_device_name="Samsung Galaxy S24",
        )

        self.assertTrue(response.primary_device_registered)
        self.assertEqual(response.primary_device_name, "Samsung Galaxy S24")


if __name__ == "__main__":
    unittest.main()
