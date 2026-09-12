"""Accounts sharing a phone with another account of the same kind are locked.

Same-type duplicates are a data error: phone sign-in genuinely cannot tell the
two apart. The staff+parent pair is NOT a conflict — a teacher whose own child
attends the school is a real person with two roles, resolved by the role button.
"""

import unittest
from datetime import date

import bcrypt
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Parent, User
from app.models.base import Base
from app.services import phone_conflict
from app.services.phone_conflict import (
    PHONE_CONFLICT_CODE,
    find_conflict_for_account,
    list_all_conflicts,
)


def _user(uid, username, phone):
    return User(
        id=uid, uniqueId=f"e{uid}", username=username,
        password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
        kName="ក", eName=username, height=1.6, gender="F", dob=date(1988, 1, 1),
        nationality="KH", religion="-", province="-", district="-", commune="-",
        education="-", workplace=1, isForeigner=0, role=2, status=1,
        token_version=1, phone=phone,
    )


def _parent(pid, username, **phones):
    return Parent(
        id=pid, uniqueid=f"p{pid}", username=username,
        password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
        status=1, created_at=date.today(), updated_at=date.today(), **phones
    )


class PhoneConflictLockTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[User.__table__, Parent.__table__]
        )
        self.db = sessionmaker(bind=self.engine)()
        phone_conflict.invalidate_cache()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        phone_conflict.invalidate_cache()

    def _commit(self, *rows):
        for r in rows:
            self.db.add(r)
        self.db.commit()
        phone_conflict.invalidate_cache()

    def test_both_duplicated_parents_are_locked_not_just_one(self):
        """The formats differ; detection must still be symmetric."""
        self._commit(
            _parent(12, "child-a", fatherPhone="096555444"),
            _parent(77, "child-b", fatherPhone="+855 96 555 444"),
        )
        self.assertIsNotNone(find_conflict_for_account(self.db, 12, "parent"))
        self.assertIsNotNone(find_conflict_for_account(self.db, 77, "parent"))

    def test_both_duplicated_staff_are_locked(self):
        self._commit(
            _user(5, "teacher-a", "012777888"),
            _user(6, "teacher-b", "0 12 777 888"),
        )
        self.assertIsNotNone(find_conflict_for_account(self.db, 5, "teacher"))
        self.assertIsNotNone(find_conflict_for_account(self.db, 6, "teacher"))

    def test_staff_who_is_also_a_parent_is_not_locked(self):
        """Mrs Sok teaches here and her child studies here. Legitimate."""
        self._commit(
            _user(8, "mrs-sok", "096555999"),
            _parent(41, "sok-family", fatherPhone="096555999"),
        )
        self.assertIsNone(find_conflict_for_account(self.db, 8, "teacher"))
        self.assertIsNone(find_conflict_for_account(self.db, 41, "parent"))

    def test_one_row_holding_the_same_number_twice_is_not_a_conflict(self):
        self._commit(
            _parent(60, "same-col", fatherPhone="098111222", motherPhone="098111222")
        )
        self.assertIsNone(find_conflict_for_account(self.db, 60, "parent"))

    def test_clean_accounts_are_not_locked(self):
        self._commit(
            _user(9, "clean-teacher", "011222333"),
            _parent(50, "clean-parent", motherPhone="011999888"),
        )
        self.assertIsNone(find_conflict_for_account(self.db, 9, "teacher"))
        self.assertIsNone(find_conflict_for_account(self.db, 50, "parent"))

    def test_accounts_without_a_phone_are_not_locked(self):
        self._commit(
            _user(20, "no-phone-a", ""),
            _user(21, "no-phone-b", None),
            _parent(70, "no-phone-parent"),
            _parent(71, "no-phone-parent-2"),
        )
        for uid in (20, 21):
            self.assertIsNone(find_conflict_for_account(self.db, uid, "teacher"))
        for pid in (70, 71):
            self.assertIsNone(find_conflict_for_account(self.db, pid, "parent"))

    def test_students_are_never_locked(self):
        self.assertIsNone(find_conflict_for_account(self.db, 1, "student"))

    def test_payload_carries_the_code_the_app_branches_on(self):
        self._commit(
            _parent(12, "child-a", fatherPhone="096555444"),
            _parent(77, "child-b", fatherPhone="096555444"),
        )
        payload = find_conflict_for_account(self.db, 12, "parent").as_payload()
        self.assertEqual(payload["code"], PHONE_CONFLICT_CODE)
        self.assertEqual(payload["account_count"], 2)
        # Must not disclose who else holds the number.
        self.assertNotIn("account_ids", payload)
        self.assertNotIn("accounts", payload)

    def test_admin_worklist_reports_each_conflict_once(self):
        self._commit(
            _parent(12, "child-a", fatherPhone="096555444"),
            _parent(77, "child-b", fatherPhone="096555444"),
            _user(5, "teacher-a", "012777888"),
            _user(6, "teacher-b", "012777888"),
            _user(8, "mrs-sok", "096555999"),
            _parent(41, "sok-family", fatherPhone="096555999"),
        )
        conflicts = list_all_conflicts(self.db)
        self.assertEqual(len(conflicts), 2)
        self.assertEqual(
            {c.account_type for c in conflicts}, {"parent", "teacher"}
        )
        for c in conflicts:
            self.assertEqual(len(c.account_ids), 2)

    def test_fixing_the_number_unlocks_after_invalidation(self):
        self._commit(
            _parent(12, "child-a", fatherPhone="096555444"),
            _parent(77, "child-b", fatherPhone="096555444"),
        )
        self.assertIsNotNone(find_conflict_for_account(self.db, 12, "parent"))

        self.db.query(Parent).filter(Parent.id == 77).update(
            {"fatherPhone": "096000111"}
        )
        self.db.commit()
        phone_conflict.invalidate_cache()

        self.assertIsNone(find_conflict_for_account(self.db, 12, "parent"))
        self.assertIsNone(find_conflict_for_account(self.db, 77, "parent"))


class LockDisabledCleanupModeTests(unittest.TestCase):
    """With PHONE_CONFLICT_LOCK_ENABLED=false nobody is locked out, but the
    ambiguous PHONE login is still refused — that is the coin flip that signs
    someone into a stranger's account, and it is never optional."""

    def setUp(self):
        from app.core import settings

        self.settings = settings
        self._was = settings.phone_conflict_lock_enabled
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[User.__table__, Parent.__table__]
        )
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(_parent(12, "child-a", fatherPhone="096555444"))
        self.db.add(_parent(77, "child-b", fatherPhone="+855 96 555 444"))
        self.db.commit()
        phone_conflict.invalidate_cache()

    def tearDown(self):
        self.settings.phone_conflict_lock_enabled = self._was
        self.db.close()
        self.engine.dispose()
        phone_conflict.invalidate_cache()

    def test_the_lock_is_off_by_default(self):
        """Deploying must not lock 106 real accounts out before anyone has had
        a chance to clean the duplicate numbers up."""
        from app.core.config import Settings

        self.assertIs(
            Settings.model_fields["phone_conflict_lock_enabled"].default, False
        )

    def test_lock_on_blocks_password_login(self):
        from app.api.v1.auth import _assert_phone_not_shared

        self.settings.phone_conflict_lock_enabled = True
        with self.assertRaises(HTTPException) as raised:
            _assert_phone_not_shared(self.db, 12, "parent")
        self.assertEqual(raised.exception.status_code, 423)

    def test_lock_off_lets_them_keep_using_the_app(self):
        from app.api.v1.auth import _assert_phone_not_shared

        self.settings.phone_conflict_lock_enabled = False
        _assert_phone_not_shared(self.db, 12, "parent")  # must not raise

    def test_phone_login_is_refused_even_with_the_lock_off(self):
        from app.api.v1.auth import _create_phone_login_token_response

        self.settings.phone_conflict_lock_enabled = False
        with self.assertRaises(HTTPException) as raised:
            _create_phone_login_token_response(self.db, "096555444")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("more than one account", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()


class LockToggleTests(unittest.TestCase):
    """The lock must be flippable from the app: asking someone to edit an env
    file and redeploy while they work through duplicates is not realistic."""

    def setUp(self):
        from app.models.settings import SystemSettings

        self.SystemSettings = SystemSettings
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[SystemSettings.__table__])
        self.db = sessionmaker(bind=self.engine)()
        from datetime import time as _t
        self.db.add(SystemSettings(
            id=1, prefixid="P", academicid=1,
            time_allow_start=_t(7, 0), time_allow_end=_t(17, 0),
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_unset_falls_back_to_the_environment_default(self):
        from app.core import settings as env
        from app.services.phone_conflict import lock_is_enabled

        was = env.phone_conflict_lock_enabled
        try:
            env.phone_conflict_lock_enabled = False
            self.assertFalse(phone_conflict.lock_is_enabled(self.db))
            env.phone_conflict_lock_enabled = True
            self.assertTrue(lock_is_enabled(self.db))
        finally:
            env.phone_conflict_lock_enabled = was

    def test_the_database_value_wins_once_set(self):
        from app.core import settings as env
        from app.services.phone_conflict import lock_is_enabled, set_lock_enabled

        was = env.phone_conflict_lock_enabled
        try:
            env.phone_conflict_lock_enabled = False
            set_lock_enabled(self.db, True)
            self.assertTrue(lock_is_enabled(self.db))
            set_lock_enabled(self.db, False)
            self.assertFalse(lock_is_enabled(self.db))
        finally:
            env.phone_conflict_lock_enabled = was

    def test_a_read_failure_never_locks_people_out(self):
        """Guessing 'true' on a database hiccup would lock the school out."""
        from app.core import settings as env
        from app.services.phone_conflict import lock_is_enabled

        class Broken:
            def query(self, *a, **k):
                raise RuntimeError("database down")

        was = env.phone_conflict_lock_enabled
        try:
            env.phone_conflict_lock_enabled = False
            self.assertFalse(lock_is_enabled(Broken()))
        finally:
            env.phone_conflict_lock_enabled = was
