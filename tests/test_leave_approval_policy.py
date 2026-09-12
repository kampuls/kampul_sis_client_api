import importlib.util
from pathlib import Path
import unittest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "leave_approval_policy.py"
)
_SPEC = importlib.util.spec_from_file_location("leave_approval_policy", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
approval_day_limit_allows = _MODULE.approval_day_limit_allows


class LeaveApprovalPolicyTests(unittest.TestCase):
    def test_one_day_approver_only_gets_requests_up_to_one_day(self):
        self.assertTrue(approval_day_limit_allows(1, 0.5))
        self.assertTrue(approval_day_limit_allows(1, 1))
        self.assertFalse(approval_day_limit_allows(1, 1.5))
        self.assertFalse(approval_day_limit_allows(1, 2))

    def test_two_day_approver_only_gets_requests_up_to_two_days(self):
        self.assertTrue(approval_day_limit_allows(2, 2))
        self.assertFalse(approval_day_limit_allows(2, 2.5))
        self.assertFalse(approval_day_limit_allows(2, 3))

    def test_unlimited_approver_gets_requests_of_any_length(self):
        self.assertTrue(approval_day_limit_allows(None, 1))
        self.assertTrue(approval_day_limit_allows(None, 30))

    def test_legacy_request_without_total_days_keeps_zero_day_fallback(self):
        self.assertTrue(approval_day_limit_allows(1, None))


if __name__ == "__main__":
    unittest.main()
