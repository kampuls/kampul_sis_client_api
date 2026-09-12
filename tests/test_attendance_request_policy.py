import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_request_policy.py"
)
SPEC = importlib.util.spec_from_file_location(
    "attendance_request_policy",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AttendanceRequestPolicyTests(unittest.TestCase):
    def validate(
        self,
        *,
        qr_type,
        qr_id,
        branch_id,
        version="1.2.8",
        user_agent="PAMA-School-App/1.0.0",
    ):
        return MODULE.validate_attendance_request_context(
            qr_type=qr_type,
            qr_id=qr_id,
            branch_id=branch_id,
            app_version=version,
            user_agent=user_agent,
        )

    def test_current_app_requires_explicit_context(self):
        violation = self.validate(qr_type=None, qr_id=None, branch_id=None)
        self.assertEqual(
            violation.code,
            "attendance_request_context_required",
        )

    def test_legacy_official_request_remains_compatible(self):
        self.assertIsNone(
            self.validate(
                qr_type=None,
                qr_id=None,
                branch_id=None,
                version="1.2.7",
            )
        )

    def test_unknown_client_fails_closed(self):
        violation = self.validate(
            qr_type=None,
            qr_id=None,
            branch_id=None,
            version=None,
            user_agent="curl/8.0",
        )
        self.assertEqual(
            violation.code,
            "attendance_request_context_required",
        )

    def test_branch_qr_must_match_branch(self):
        self.assertIsNone(
            self.validate(qr_type="branch", qr_id=7, branch_id=7)
        )
        violation = self.validate(qr_type="branch", qr_id=7, branch_id=8)
        self.assertEqual(violation.code, "invalid_branch_qr_context")

    def test_quick_attendance_cannot_inject_branch(self):
        self.assertIsNone(
            self.validate(qr_type="t_attendance", qr_id=1, branch_id=None)
        )
        violation = self.validate(
            qr_type="t_attendance",
            qr_id=1,
            branch_id=7,
        )
        self.assertEqual(
            violation.code,
            "invalid_quick_attendance_context",
        )

    def test_privileged_qr_has_fixed_shape(self):
        self.assertIsNone(
            self.validate(qr_type="r_attendance", qr_id=1, branch_id=None)
        )
        violation = self.validate(
            qr_type="r_attendance",
            qr_id=99,
            branch_id=None,
        )
        self.assertEqual(
            violation.code,
            "invalid_admin_attendance_context",
        )

    def test_admin_role_does_not_bypass_branch_without_override(self):
        self.assertFalse(
            MODULE.is_attendance_branch_authorized(
                8,
                {7},
                is_admin_override=False,
            )
        )
        self.assertTrue(
            MODULE.is_attendance_branch_authorized(
                8,
                {7},
                is_admin_override=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
