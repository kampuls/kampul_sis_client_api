import unittest
from types import SimpleNamespace

from app.api.v1.leave_management import (
    _current_workplace_id,
    _department_name_map,
    _employee_name_fields,
)


class _DepartmentRows:
    def all(self):
        return [
            (3, "Human Resources", "ធនធានមនុស្ស"),
            (7, "", "បឋមសិក្សា"),
        ]


class _DepartmentSession:
    def __init__(self):
        self.sql = ""
        self.params = None

    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params
        return _DepartmentRows()


class LeaveEmployeeIdentitySerializationTests(unittest.TestCase):
    def test_names_are_returned_in_separate_exact_database_fields(self):
        user = SimpleNamespace(
            id=17,
            eName="SOK Dara",
            kName="សុខ ដារ៉ា",
            username="dara17",
        )

        result = _employee_name_fields(user)

        self.assertEqual(result["user_name"], "SOK Dara")
        self.assertEqual(result["user_name_en"], "SOK Dara")
        self.assertEqual(result["user_name_kh"], "សុខ ដារ៉ា")

    def test_missing_name_variant_remains_null_without_translation(self):
        user = SimpleNamespace(
            id=18,
            eName="LIN Maya",
            kName=None,
            username="maya18",
        )

        result = _employee_name_fields(user)

        self.assertEqual(result["user_name"], "LIN Maya")
        self.assertEqual(result["user_name_en"], "LIN Maya")
        self.assertIsNone(result["user_name_kh"])

    def test_stored_name_spacing_is_not_rewritten(self):
        user = SimpleNamespace(
            id=19,
            eName="  LIM Sothy  ",
            kName="  លឹម សុធី  ",
            username="sothy19",
        )

        result = _employee_name_fields(user)

        self.assertEqual(result["user_name_en"], "  LIM Sothy  ")
        self.assertEqual(result["user_name_kh"], "  លឹម សុធី  ")

    def test_department_names_use_the_live_department_table(self):
        session = _DepartmentSession()

        result = _department_name_map(session, {3, 7})

        self.assertIn("FROM department", session.sql)
        self.assertNotIn("FROM departments", session.sql)
        self.assertEqual(session.params, {"department_ids": [3, 7]})
        self.assertEqual(result[3], "Human Resources")
        self.assertEqual(result[7], "បឋមសិក្សា")

    def test_current_workplace_id_uses_live_user_branch(self):
        self.assertEqual(_current_workplace_id(SimpleNamespace(workplace=7)), 7)
        self.assertIsNone(_current_workplace_id(SimpleNamespace(workplace=0)))
        self.assertIsNone(_current_workplace_id(SimpleNamespace(workplace=None)))
        self.assertIsNone(_current_workplace_id(SimpleNamespace()))


if __name__ == "__main__":
    unittest.main()
