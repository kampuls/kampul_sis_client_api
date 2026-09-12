import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.leave_notification_service import _eligible_approvers


class LeaveScopeSecurityTests(unittest.TestCase):
    def test_empty_scope_is_not_an_eligible_decision_notification_scope(self):
        no_scope_viewer = SimpleNamespace(
            user_id=20,
            can_approve_all=False,
            can_view_all_requests=True,
            department_id=None,
            branch_id=None,
            max_days_can_approve=None,
        )
        scoped_approver = SimpleNamespace(
            user_id=21,
            can_approve_all=False,
            can_view_all_requests=False,
            department_id=5,
            branch_id=7,
            max_days_can_approve=None,
        )
        query = Mock()
        query.filter.return_value.all.return_value = [
            no_scope_viewer,
            scoped_approver,
        ]
        db = Mock()
        db.query.return_value = query
        requester = SimpleNamespace(departmentId=5, workplace=7)

        eligible = _eligible_approvers(db, requester, request_days=1.0)

        self.assertEqual([item.user_id for item in eligible], [21])


if __name__ == "__main__":
    unittest.main()
