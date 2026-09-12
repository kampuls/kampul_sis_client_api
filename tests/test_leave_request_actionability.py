import unittest
from datetime import date, datetime, timezone
from inspect import getsource
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.api.v1.leave_management import (
    _can_send_review_reminder,
    _can_view_decision_contacts,
    _decision_contacts_for_request,
    _filter_to_approver_visibility_scope,
    _request_actionability,
    _review_reminder_available_at,
    _review_reminder_retry_after_seconds,
    list_requests_for_review,
)


def _request(**overrides):
    values = {
        "user_id": 10,
        "replacement_user_id": None,
        "status": "pending",
        "total_days": 2.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(user_id, *, role_id=2, department_id=5, branch_id=7):
    return SimpleNamespace(
        id=user_id,
        role_id=role_id,
        departmentId=department_id,
        workplace=branch_id,
    )


def _approver(
    *,
    limit=5.0,
    all_requests=False,
    view_all=False,
    can_cancel_approved=True,
    department_id=5,
    branch_id=7,
):
    return SimpleNamespace(
        max_days_can_approve=limit,
        can_approve_all=all_requests,
        can_view_all_requests=view_all,
        can_cancel_approved_leave=can_cancel_approved,
        department_id=department_id,
        branch_id=branch_id,
    )


class LeaveRequestActionabilityTests(unittest.TestCase):
    def test_scoped_approver_can_view_and_decide_pending_request(self):
        result = _request_actionability(
            _request(),
            _user(20),
            _user(10),
            _approver(),
        )

        self.assertTrue(result["can_view"])
        self.assertTrue(result["can_decide"])
        self.assertIsNone(result["reason"])

    def test_unrelated_user_cannot_view_request_details(self):
        result = _request_actionability(
            _request(),
            _user(20),
            _user(10),
            None,
        )

        self.assertFalse(result["can_view"])
        self.assertFalse(result["can_decide"])

    def test_requester_can_view_but_cannot_self_approve(self):
        result = _request_actionability(
            _request(),
            _user(10),
            _user(10),
            _approver(all_requests=True),
        )

        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_decide"])
        self.assertIn("own leave", str(result["reason"]))

    def test_approval_limit_is_explained_without_hiding_request(self):
        result = _request_actionability(
            _request(total_days=3.0),
            _user(20),
            _user(10),
            _approver(limit=2.0),
        )

        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_decide"])
        self.assertIn("exceeds", str(result["reason"]))

    def test_school_wide_visibility_never_uses_the_approval_day_limit(self):
        for approver in (
            _approver(limit=1.0, all_requests=True),
            _approver(
                limit=1.0,
                view_all=True,
                department_id=None,
                branch_id=None,
            ),
        ):
            query = Mock()

            result = _filter_to_approver_visibility_scope(query, approver)

            self.assertIs(result, query)
            query.filter.assert_not_called()

    def test_scoped_visibility_filters_only_organization_not_request_days(self):
        query = Mock()
        query.filter.return_value = query

        result = _filter_to_approver_visibility_scope(
            query,
            _approver(limit=1.0, department_id=5, branch_id=7),
        )

        self.assertIs(result, query)
        self.assertEqual(query.filter.call_count, 2)
        criteria = " ".join(
            str(call.args[0]) for call in query.filter.call_args_list
        )
        self.assertNotIn("total_days", criteria)

    def test_review_inbox_never_applies_day_limit_to_visible_rows(self):
        source = getsource(list_requests_for_review)

        self.assertIn("_filter_to_approver_visibility_scope", source)
        self.assertNotIn("_filter_to_approver_day_limit", source)

    def test_admin_without_approver_assignment_gets_read_only_access(self):
        result = _request_actionability(
            _request(),
            _user(20, role_id=1),
            _user(10),
            None,
        )

        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_decide"])
        self.assertIn("assigned leave approvers", str(result["reason"]))

    def test_view_all_allows_out_of_scope_visibility_but_not_decision(self):
        result = _request_actionability(
            _request(),
            _user(20, department_id=99, branch_id=99),
            _user(10),
            _approver(view_all=True, department_id=99, branch_id=99),
        )

        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_decide"])
        self.assertIn("assigned leave approvers", str(result["reason"]))

    def test_view_all_does_not_bypass_maximum_day_limit(self):
        result = _request_actionability(
            _request(total_days=3.0),
            _user(20),
            _user(10),
            _approver(limit=2.0, view_all=True),
        )

        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_decide"])
        self.assertIn("exceeds", str(result["reason"]))

    def test_empty_scope_never_becomes_school_wide_decision_authority(self):
        no_scope = _approver(
            view_all=True,
            department_id=None,
            branch_id=None,
        )

        result = _request_actionability(
            _request(),
            _user(20),
            _user(10),
            no_scope,
        )

        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_decide"])
        self.assertIn("assigned leave approvers", str(result["reason"]))

    def test_view_only_request_lists_only_approvers_who_can_decide(self):
        request = _request(total_days=3.0)
        requester = _user(10)
        eligible = _approver(limit=5.0)
        eligible.user_id = 20
        over_limit = _approver(limit=2.0)
        over_limit.user_id = 30
        out_of_scope = _approver(limit=5.0, department_id=99)
        out_of_scope.user_id = 40
        self_approver = _approver(limit=5.0)
        self_approver.user_id = 10

        users = {
            10: SimpleNamespace(
                id=10,
                status=1,
                eName="Requester",
                kName="",
                username="requester",
                phone="010 000 010",
            ),
            20: SimpleNamespace(
                id=20,
                status=1,
                eName="Eligible Approver",
                kName="",
                username="eligible",
                phone="  010 000 020  ",
            ),
            30: SimpleNamespace(
                id=30,
                status=1,
                eName="Limited Approver",
                kName="",
                username="limited",
                phone="010 000 030",
            ),
            40: SimpleNamespace(
                id=40,
                status=1,
                eName="Other Department",
                kName="",
                username="other",
                phone="010 000 040",
            ),
        }

        contacts = _decision_contacts_for_request(
            request,
            requester,
            [eligible, over_limit, out_of_scope, self_approver],
            users,
            {20: "/avatars/20.jpg"},
        )

        self.assertEqual([contact["user_id"] for contact in contacts], [20])
        self.assertEqual(contacts[0]["phone"], "010 000 020")
        self.assertEqual(contacts[0]["avatar"], "/avatars/20.jpg")

    def test_review_reminder_uses_15_minutes_then_one_hour(self):
        sent_at = datetime(2026, 7, 23, 2, 0, tzinfo=timezone.utc)
        request = _request(
            review_reminder_count=1,
            last_review_reminder_at=sent_at.replace(tzinfo=None),
        )

        self.assertEqual(
            _review_reminder_available_at(request),
            datetime(2026, 7, 23, 2, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(
            _review_reminder_retry_after_seconds(request, now=sent_at),
            15 * 60,
        )

        request.review_reminder_count = 2
        self.assertEqual(
            _review_reminder_available_at(request),
            datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            _review_reminder_retry_after_seconds(request, now=sent_at),
            60 * 60,
        )

    def test_requester_and_any_read_only_reviewer_can_send_reminder(self):
        request = _request()
        approver = _approver(view_all=True)

        self.assertTrue(
            _can_send_review_reminder(
                request,
                _user(10),
                None,
                {"can_view": True, "can_decide": False},
            )
        )
        self.assertTrue(
            _can_send_review_reminder(
                request,
                _user(20),
                approver,
                {"can_view": True, "can_decide": False},
            )
        )
        self.assertFalse(
            _can_send_review_reminder(
                request,
                _user(20),
                approver,
                {"can_view": True, "can_decide": True},
            )
        )
        self.assertTrue(
            _can_send_review_reminder(
                request,
                _user(20),
                _approver(view_all=False),
                {"can_view": True, "can_decide": False},
            )
        )
        self.assertFalse(
            _can_send_review_reminder(
                request,
                _user(20),
                None,
                {"can_view": True, "can_decide": False},
            )
        )

    def test_requester_cannot_see_approver_contact_details(self):
        request = _request()
        access = {"can_view": True, "can_decide": False}

        self.assertFalse(
            _can_view_decision_contacts(
                request,
                _user(10),
                _approver(view_all=True),
                access,
            )
        )
        self.assertTrue(
            _can_view_decision_contacts(
                request,
                _user(20),
                _approver(view_all=True),
                access,
            )
        )


    def test_scoped_approver_can_cancel_approved_leave(self):
        result = _request_actionability(
            _request(status="approved", start_date=datetime(2026, 7, 20).date()),
            _user(20),
            _user(10),
            _approver(),
        )
        self.assertTrue(result["can_view"])
        self.assertTrue(result["can_cancel"])
        self.assertIsNone(result["can_cancel_reason"])

    def test_admin_without_close_permission_cannot_cancel_approved_leave(self):
        result = _request_actionability(
            _request(status="approved", start_date=datetime(2026, 7, 20).date()),
            _user(20, role_id=1),
            _user(10),
            None,
        )
        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_cancel"])
        self.assertIn("permission", str(result["can_cancel_reason"]))

    def test_admin_with_close_permission_can_cancel_approved_leave(self):
        result = _request_actionability(
            _request(status="approved", start_date=datetime(2026, 7, 20).date()),
            _user(20, role_id=1),
            _user(10),
            _approver(),
        )
        self.assertTrue(result["can_view"])
        self.assertTrue(result["can_cancel"])

    def test_requester_cannot_cancel_approved_leave_without_permission(self):
        result = _request_actionability(
            _request(status="approved", start_date=datetime(2026, 12, 25).date()),
            _user(10),
            _user(10),
            None,
        )
        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_cancel"])
        self.assertIn("permission", str(result["can_cancel_reason"]))

    def test_original_approver_cannot_bypass_disabled_close_permission(self):
        result = _request_actionability(
            _request(status="approved", approver_id=20),
            _user(20),
            _user(10),
            _approver(can_cancel_approved=False),
        )
        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_cancel"])
        self.assertIn("permission", str(result["can_cancel_reason"]))

    def test_view_all_does_not_allow_out_of_scope_approved_cancellation(self):
        result = _request_actionability(
            _request(status="approved", start_date=datetime(2026, 7, 20).date()),
            _user(20, department_id=8),
            _user(10),
            _approver(view_all=True, department_id=8),
        )
        self.assertTrue(result["can_view"])
        self.assertFalse(result["can_cancel"])
        self.assertIn("outside your approver scope", str(result["can_cancel_reason"]))

    def test_cancel_approved_permission_is_required_for_other_approvers(self):
        result = _request_actionability(
            _request(status="approved", start_date=datetime(2026, 7, 20).date()),
            _user(20),
            _user(10),
            _approver(can_cancel_approved=False),
        )
        self.assertFalse(result["can_cancel"])
        self.assertIn("permission", str(result["can_cancel_reason"]))

    def test_approver_cannot_cancel_another_users_pending_request(self):
        result = _request_actionability(
            _request(status="pending"),
            _user(20),
            _user(10),
            _approver(),
        )
        self.assertTrue(result["can_decide"])
        self.assertFalse(result["can_cancel"])

    def test_requester_cannot_cancel_pending_leave_after_its_start_date(self):
        with patch(
            "app.api.v1.leave_management._today_kh",
            return_value=date(2026, 8, 24),
        ):
            result = _request_actionability(
                _request(status="pending", start_date=date(2026, 8, 23)),
                _user(10),
                _user(10),
                None,
            )

        self.assertFalse(result["can_cancel"])
        self.assertIn("already passed", str(result["can_cancel_reason"]))

    def test_requester_can_cancel_pending_leave_on_its_start_date(self):
        with patch(
            "app.api.v1.leave_management._today_kh",
            return_value=date(2026, 8, 24),
        ):
            result = _request_actionability(
                _request(status="pending", start_date=date(2026, 8, 24)),
                _user(10),
                _user(10),
                None,
            )

        self.assertTrue(result["can_cancel"])
        self.assertIsNone(result["can_cancel_reason"])

    def test_admin_cannot_cancel_another_users_past_pending_leave(self):
        with patch(
            "app.api.v1.leave_management._today_kh",
            return_value=date(2026, 8, 24),
        ):
            result = _request_actionability(
                _request(status="pending", start_date=date(2026, 8, 23)),
                _user(20, role_id=1),
                _user(10),
                None,
            )

        self.assertFalse(result["can_cancel"])
        self.assertIn("already passed", str(result["can_cancel_reason"]))

    def test_cancelled_leave_cannot_be_closed_twice(self):
        result = _request_actionability(
            _request(status="cancelled"),
            _user(20, role_id=1),
            _user(10),
            None,
        )
        self.assertFalse(result["can_cancel"])
        self.assertIn("already cancelled", str(result["can_cancel_reason"]))


if __name__ == "__main__":
    unittest.main()
