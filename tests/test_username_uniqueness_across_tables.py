"""A username must be unique across employees AND parents.

Several endpoints resolve a caller from the ``sub`` claim alone. Parent
registration used to check uniqueness only within the ``parents`` table, so a
parent could register as an existing teacher's username and then be served that
teacher's account.
"""

import unittest
from datetime import date

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.auth import _username_is_free
from app.models import Parent, User
from app.models.base import Base


class UsernameUniquenessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine, tables=[User.__table__, Parent.__table__]
        )
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(
            User(
                id=1,
                uniqueId="emp-1",
                username="msophea",
                password=bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode(),
                kName="ក",
                eName="Sophea",
                height=1.6,
                gender="F",
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
        )
        self.db.add(
            Parent(
                id=1,
                uniqueid="par-1",
                username="pdara",
                password=bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode(),
                status=1,
                created_at=date.today(),
                updated_at=date.today(),
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_teacher_username_is_not_free_for_a_parent(self):
        self.assertFalse(_username_is_free(self.db, "msophea"))

    def test_parent_username_is_not_free_for_a_teacher(self):
        self.assertFalse(_username_is_free(self.db, "pdara"))

    def test_unused_username_is_free(self):
        self.assertTrue(_username_is_free(self.db, "pnewfamily"))

    def test_blank_username_is_never_free(self):
        self.assertFalse(_username_is_free(self.db, ""))
        self.assertFalse(_username_is_free(self.db, "   "))


if __name__ == "__main__":
    unittest.main()
