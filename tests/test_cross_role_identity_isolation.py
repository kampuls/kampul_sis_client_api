"""Regression tests for cross-table identity confusion.

``users``, ``parents`` and ``students`` each have their own auto-increment IDs,
so the same integer names three different people. These tests pin shut the paths
where a parent used to be resolved as the employee sharing their ID or username.
"""

import unittest
from datetime import date

import bcrypt
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.dependencies import (
    PARENT_MEMBER_TYPES,
    STAFF_MEMBER_TYPES,
    Principal,
    principal_from_user,
    require_admin,
)
from app.auth.parent_auth import get_parent_by_username, verify_parent_password
from app.models import Parent, User
from app.models.base import Base
from app.services.utils import create_short_lived_access_token
from app.utils.phone import get_phone_variations


def _credentials(token: str):
    """Minimal stand-in for HTTPAuthorizationCredentials."""

    class _C:
        credentials = token

    return _C()


class CrossRoleIdentityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[User.__table__, Parent.__table__]
        )
        self.db = sessionmaker(bind=self.engine)()

        # An admin employee and a parent that share the integer 1.
        self.db.add(
            User(
                id=1,
                uniqueId="emp-1",
                username="admin",
                password=bcrypt.hashpw(b"admin-pw", bcrypt.gensalt()).decode(),
                kName="\u1780",
                eName="Admin",
                height=1.7,
                gender="M",
                dob=date(1990, 1, 1),
                nationality="KH",
                religion="-",
                province="-",
                district="-",
                commune="-",
                education="-",
                workplace=1,
                isForeigner=0,
                role=1,
                status=1,
                token_version=1,
            )
        )
        self.db.add(
            Parent(
                id=1,
                uniqueid="u-1",
                username="parent-one",
                password=bcrypt.hashpw(b"parent-pw", bcrypt.gensalt()).decode(),
                fatherPhone="096111111",
                status=1,
                created_at=date.today(),
                updated_at=date.today(),
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_parent_token_cannot_pass_require_admin(self):
        """A parent whose ID matches an admin must not inherit admin rights."""
        token = create_short_lived_access_token(
            {"sub": "parent-one", "role": "parent", "user_id": 1}
        )
        with self.assertRaises(HTTPException) as raised:
            require_admin(credentials=_credentials(token), db=self.db)
        self.assertEqual(raised.exception.status_code, 403)

    def test_employee_admin_token_still_passes_require_admin(self):
        token = create_short_lived_access_token(
            {"sub": "admin", "role": "teacher", "user_id": 1, "token_version": 1}
        )
        self.assertEqual(
            require_admin(credentials=_credentials(token), db=self.db), 1
        )

    def test_require_admin_rejects_disabled_admin(self):
        self.db.query(User).filter(User.id == 1).update({"status": 0})
        self.db.commit()
        token = create_short_lived_access_token(
            {"sub": "admin", "role": "teacher", "user_id": 1, "token_version": 1}
        )
        with self.assertRaises(HTTPException):
            require_admin(credentials=_credentials(token), db=self.db)

    def test_require_admin_rejects_revoked_token_version(self):
        self.db.query(User).filter(User.id == 1).update({"token_version": 5})
        self.db.commit()
        token = create_short_lived_access_token(
            {"sub": "admin", "role": "teacher", "user_id": 1, "token_version": 1}
        )
        with self.assertRaises(HTTPException):
            require_admin(credentials=_credentials(token), db=self.db)

    def test_principal_carries_the_owning_table(self):
        parent_principal = principal_from_user(
            type("P", (), {"id": 1, "is_parent": True, "user_type": "parent"})()
        )
        self.assertEqual(parent_principal, Principal(1, "parent", PARENT_MEMBER_TYPES))

        staff_principal = principal_from_user(self.db.get(User, 1))
        self.assertEqual(staff_principal, Principal(1, "teacher", STAFF_MEMBER_TYPES))

    def test_parent_lookup_prefers_phone_over_row_id(self):
        """Typing a phone number must not resolve to the parent with that ID."""
        self.db.add(
            Parent(
                id=96111111,
                uniqueid="u-2",
                username="someone-else",
                password=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode(),
                fatherPhone="012999999",
                status=1,
                created_at=date.today(),
                updated_at=date.today(),
            )
        )
        self.db.commit()

        found = get_parent_by_username(self.db, "096111111")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, 1)

    def test_parent_lookup_matches_alternate_phone_formats(self):
        for typed in ("096111111", "96111111", "+85596111111", "85596111111"):
            with self.subTest(typed=typed):
                found = get_parent_by_username(self.db, typed)
                self.assertIsNotNone(found, f"{typed} should match stored 096111111")
                self.assertEqual(found.id, 1)

    def test_parent_lookup_refuses_ambiguous_phone(self):
        """Two rows sharing a phone must not silently resolve to the first."""
        self.db.add(
            Parent(
                id=2,
                uniqueid="u-3",
                username="sibling-row",
                password=bcrypt.hashpw(b"y", bcrypt.gensalt()).decode(),
                fatherPhone="096111111",
                status=1,
                created_at=date.today(),
                updated_at=date.today(),
            )
        )
        self.db.commit()
        self.assertIsNone(get_parent_by_username(self.db, "096111111"))

    def test_bad_password_hash_is_a_failed_login_not_a_crash(self):
        parent = self.db.get(Parent, 1)
        parent.password = "not-a-bcrypt-hash"
        self.assertFalse(verify_parent_password(parent, "anything"))

    def test_phone_variations_never_contain_empty_string(self):
        for probe in ("+855", "0", "+8550", "", "   ", "abc"):
            with self.subTest(probe=probe):
                self.assertNotIn("", get_phone_variations(probe))


if __name__ == "__main__":
    unittest.main()


class NotificationScopingTests(unittest.TestCase):
    """A notification row belongs to (user_id, user_type), never user_id alone."""

    def setUp(self):
        from app.models import Notification

        self.Notification = Notification
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[Notification.__table__])
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(
            Notification(
                id=1, user_id=57, user_type="teacher", title="Payroll", body="x",
                is_read=True,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_parent_cannot_touch_an_employees_notification(self):
        from app.services.notification_service import mark_as_unread

        self.assertIsNone(mark_as_unread(self.db, 1, 57, "parent"))
        self.assertTrue(self.db.get(self.Notification, 1).is_read)

    def test_owner_can_still_mark_it_unread(self):
        from app.services.notification_service import mark_as_unread

        self.assertIsNotNone(mark_as_unread(self.db, 1, 57, "teacher"))
        self.assertFalse(self.db.get(self.Notification, 1).is_read)
