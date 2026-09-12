"""One employee must not be able to read another's payroll or ID details.

``UserResponse`` carries the entire employee row — salary, bank account, NSSF
number, national ID. ``GET /users/{user_id}`` is open to any signed-in account
(the app uses it to look colleagues up), so those fields have to be blanked for
everyone except the person themselves and admins.
"""

import unittest
from datetime import date

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.users import (
    _PRIVATE_STAFF_FIELDS,
    _may_see_private_staff_fields,
    _redact_private_staff_fields,
)
from app.models import User
from app.models.base import Base


def _staff(uid, username, admin_role=2):
    return User(
        id=uid, uniqueId=f"e{uid}", username=username,
        password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
        kName="ក", eName=username, height=1.6, gender="F",
        dob=date(1988, 1, 1), nationality="KH", religion="-", province="-",
        district="-", commune="-", education="-", workplace=1, isForeigner=0,
        role=admin_role, status=1, token_version=1,
        baseSalary=1234.56, bankAccountNumber="000123456",
        bankAccountName="Sok Dara", bankName="ABA", nssfNumber="NS-99",
        identityNumber="ID-4242",
    )


def _parent_principal(pid=7):
    return type(
        "ParentAsUser",
        (),
        {"id": pid, "is_parent": True, "user_type": "parent", "role": "parent"},
    )()


class StaffPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[User.__table__])
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(_staff(5, "sophea"))
        self.db.add(_staff(6, "dara"))
        self.db.add(_staff(1, "admin", admin_role=1))
        self.db.commit()
        self.target = self.db.get(User, 5)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_a_colleague_cannot_see_salary_or_bank_details(self):
        other = self.db.get(User, 6)
        data = _redact_private_staff_fields(self.target, other)
        for field in _PRIVATE_STAFF_FIELDS:
            with self.subTest(field=field):
                self.assertIsNone(data[field], f"{field} leaked to a colleague")

    def test_a_parent_cannot_see_them_either(self):
        data = _redact_private_staff_fields(self.target, _parent_principal())
        self.assertIsNone(data["baseSalary"])
        self.assertIsNone(data["bankAccountNumber"])
        self.assertIsNone(data["identityNumber"])

    def test_a_parent_sharing_the_targets_id_is_still_refused(self):
        """Parent #5 is not employee #5."""
        self.assertFalse(_may_see_private_staff_fields(_parent_principal(5), 5))

    def test_you_can_see_your_own(self):
        data = _redact_private_staff_fields(self.target, self.target)
        self.assertEqual(data["baseSalary"], 1234.56)
        self.assertEqual(data["bankAccountNumber"], "000123456")

    def test_an_admin_can_see_them(self):
        admin = self.db.get(User, 1)
        data = _redact_private_staff_fields(self.target, admin)
        self.assertEqual(data["baseSalary"], 1234.56)

    def test_non_private_fields_are_untouched(self):
        """Redaction must not change the response shape the app relies on."""
        other = self.db.get(User, 6)
        data = _redact_private_staff_fields(self.target, other)
        self.assertEqual(data["id"], 5)
        self.assertEqual(data["username"], "sophea")
        self.assertEqual(data["eName"], "sophea")
        self.assertEqual(data["workplace"], 1)
        self.assertIn("departmentId", data)


if __name__ == "__main__":
    unittest.main()
