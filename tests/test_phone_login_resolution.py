"""Regression tests for phone/Telegram/Firebase login account resolution.

The old resolver checked the employee table first, ignored the role the user
picked on the login screen, and took ``.first()`` on a phone match. A teacher
whose own child attended the school could never sign in as a parent, and a
number present on two parent rows signed the caller into whichever row came back
first.
"""

import unittest
from datetime import date

import bcrypt
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.auth import _create_phone_login_token_response
from app.models import Parent, User
from app.models.base import Base


def _make_user(**overrides):
    base = dict(
        uniqueId="emp",
        username="teacher",
        password=bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode(),
        kName="ក",
        eName="Teacher",
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
        role=2,
        status=1,
        token_version=1,
    )
    base.update(overrides)
    return User(**base)


def _make_parent(**overrides):
    base = dict(
        uniqueid="par",
        username="parent",
        password=bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode(),
        status=1,
        created_at=date.today(),
        updated_at=date.today(),
    )
    base.update(overrides)
    return Parent(**base)


class PhoneLoginResolutionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[User.__table__, Parent.__table__]
        )
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_teacher_who_is_also_a_parent_can_sign_in_as_parent(self):
        """The same number is on a staff row and a parent row."""
        self.db.add(_make_user(id=1, username="mrs-sok", phone="096111111"))
        self.db.add(
            _make_parent(id=1, username="sok-family", fatherPhone="096111111")
        )
        self.db.commit()

        as_parent = _create_phone_login_token_response(
            self.db, "+85596111111", requested_role="parent"
        )
        self.assertEqual(as_parent["role"], "parent")

        as_teacher = _create_phone_login_token_response(
            self.db, "+85596111111", requested_role="teacher"
        )
        self.assertEqual(as_teacher["role"], "teacher")

    def test_same_type_duplicate_locks_the_account(self):
        """Two parent rows sharing the father's phone (legacy sibling rows).

        This is a data error, not a role choice. With the lock switched on it
        is a 423; the flag is set explicitly here rather than relying on the
        global default, which made this test depend on execution order.
        """
        from app.core import settings
        from app.services import phone_conflict

        self.db.add(_make_parent(id=1, username="child-a", fatherPhone="096111111"))
        self.db.add(_make_parent(id=2, username="child-b", fatherPhone="096111111"))
        self.db.commit()
        phone_conflict.invalidate_cache()

        was = settings.phone_conflict_lock_enabled
        settings.phone_conflict_lock_enabled = True
        try:
            with self.assertRaises(HTTPException) as raised:
                _create_phone_login_token_response(self.db, "096111111")
            self.assertEqual(raised.exception.status_code, 423)
            self.assertEqual(
                raised.exception.detail["code"], "phone_linked_to_multiple_accounts"
            )
        finally:
            settings.phone_conflict_lock_enabled = was
            phone_conflict.invalidate_cache()

    def test_with_the_lock_off_the_ambiguous_login_is_still_refused(self):
        """Deferring the lockout must not reopen the wrong-account coin flip."""
        from app.core import settings
        from app.services import phone_conflict

        self.db.add(_make_parent(id=1, username="child-a", fatherPhone="096111111"))
        self.db.add(_make_parent(id=2, username="child-b", fatherPhone="096111111"))
        self.db.commit()
        phone_conflict.invalidate_cache()

        was = settings.phone_conflict_lock_enabled
        settings.phone_conflict_lock_enabled = False
        try:
            with self.assertRaises(HTTPException) as raised:
                _create_phone_login_token_response(self.db, "096111111")
            self.assertEqual(raised.exception.status_code, 409)
        finally:
            settings.phone_conflict_lock_enabled = was
            phone_conflict.invalidate_cache()

    def test_staff_plus_parent_asks_for_a_role_instead_of_locking(self):
        """Mrs Sok is legitimately both; older builds send no role hint."""
        from app.services import phone_conflict

        self.db.add(_make_user(id=1, username="mrs-sok", phone="096111111"))
        self.db.add(_make_parent(id=1, username="sok-family", fatherPhone="096111111"))
        self.db.commit()
        phone_conflict.invalidate_cache()

        with self.assertRaises(HTTPException) as raised:
            _create_phone_login_token_response(self.db, "096111111")
        self.assertEqual(raised.exception.status_code, 409)
        phone_conflict.invalidate_cache()

    def test_unapproved_parent_cannot_sign_in_by_phone(self):
        self.db.add(
            _make_parent(id=1, username="pending", fatherPhone="096111111", status=2)
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            _create_phone_login_token_response(self.db, "096111111")
        self.assertEqual(raised.exception.status_code, 403)

    def test_inactive_employee_cannot_sign_in_by_phone(self):
        self.db.add(_make_user(id=1, username="left-school", phone="096111111", status=0))
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            _create_phone_login_token_response(self.db, "096111111")
        self.assertEqual(raised.exception.status_code, 403)

    def test_unknown_number_reports_not_registered(self):
        result = _create_phone_login_token_response(self.db, "096000000")
        self.assertFalse(result["registered"])

    def test_guardian_phone_is_matched(self):
        self.db.add(_make_parent(id=1, username="guardian", gPhone="096111111"))
        self.db.commit()
        result = _create_phone_login_token_response(self.db, "096111111")
        self.assertEqual(result["role"], "parent")

    def test_blank_phone_column_is_never_matched(self):
        """A degenerate input must not match rows with an empty phone."""
        self.db.add(_make_user(id=1, username="no-phone", phone=""))
        self.db.add(_make_parent(id=1, username="no-phone-parent", fatherPhone=""))
        self.db.commit()

        result = _create_phone_login_token_response(self.db, "+855")
        self.assertFalse(result["registered"])


if __name__ == "__main__":
    unittest.main()
