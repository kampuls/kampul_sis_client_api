"""A parent may only reach their own children.

``parents.myChilds`` is a comma-separated list of student IDs and the ownership
check was hand-written at every call site. Two endpoints forgot it, letting any
signed-in parent walk the ID space and read other families' records. These tests
cover the shared helper those endpoints now go through.
"""

import unittest
from datetime import date

import bcrypt
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Parent, User
from app.models.base import Base
from app.services.child_access import (
    assert_can_access_parent_record,
    assert_can_access_student,
    is_parent,
    parent_child_ids,
    parent_owns_student,
)


def _parent_principal(pid):
    return type(
        "ParentAsUser",
        (),
        {"id": pid, "is_parent": True, "user_type": "parent", "role": "parent"},
    )()


class ChildAccessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[User.__table__, Parent.__table__]
        )
        self.db = sessionmaker(bind=self.engine)()

        def mk(pid, childs):
            return Parent(
                id=pid, uniqueid=f"p{pid}", username=f"fam{pid}",
                password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
                myChilds=childs, status=1,
                created_at=date.today(), updated_at=date.today(),
            )

        self.db.add(mk(1, "10,11"))
        self.db.add(mk(2, "20"))
        self.db.add(mk(3, None))
        # Shapes the column really holds in production.
        self.db.add(mk(4, " 40 , 41 ,"))
        self.db.add(mk(5, "50,,abc,51"))
        self.db.commit()

        self.staff = User(
            id=1, uniqueId="e1", username="teacher",
            password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
            kName="ក", eName="T", height=1.6, gender="F", dob=date(1988, 1, 1),
            nationality="KH", religion="-", province="-", district="-",
            commune="-", education="-", workplace=1, isForeigner=0,
            role=2, status=1, token_version=1,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_parent_reaches_their_own_child(self):
        assert_can_access_student(self.db, _parent_principal(1), 10)

    def test_parent_cannot_reach_another_familys_child(self):
        with self.assertRaises(HTTPException) as raised:
            assert_can_access_student(self.db, _parent_principal(1), 20)
        self.assertEqual(raised.exception.status_code, 403)

    def test_parent_with_no_children_reaches_nothing(self):
        with self.assertRaises(HTTPException):
            assert_can_access_student(self.db, _parent_principal(3), 10)

    def test_staff_may_reach_any_student(self):
        assert_can_access_student(self.db, self.staff, 10)
        assert_can_access_student(self.db, self.staff, 20)

    def test_parent_reaches_only_their_own_parent_record(self):
        assert_can_access_parent_record(self.db, _parent_principal(2), 2)
        with self.assertRaises(HTTPException) as raised:
            assert_can_access_parent_record(self.db, _parent_principal(2), 1)
        self.assertEqual(raised.exception.status_code, 403)

    def test_staff_may_read_any_parent_record(self):
        assert_can_access_parent_record(self.db, self.staff, 1)

    def test_messy_mychilds_values_are_parsed_safely(self):
        self.assertEqual(parent_child_ids(self.db, 4), {40, 41})
        self.assertEqual(parent_child_ids(self.db, 5), {50, 51})
        self.assertEqual(parent_child_ids(self.db, 3), set())

    def test_substring_ids_do_not_match(self):
        """'1' must not match the parent whose myChilds is '10,11'."""
        self.assertFalse(parent_owns_student(self.db, 1, 1))
        self.assertTrue(parent_owns_student(self.db, 1, 10))

    def test_principal_kind_detection(self):
        self.assertTrue(is_parent(_parent_principal(1)))
        self.assertFalse(is_parent(self.staff))


if __name__ == "__main__":
    unittest.main()
