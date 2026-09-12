import unittest
from contextlib import ExitStack
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.api.v1 import leave_management
from app.schemas.leave_management import (
    LeaveCancelRequest,
    ManualLeaveCreate,
    LeaveRequestCreate,
    LeaveRequestDayIn,
)


class LeaveRequestTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def _submit(
        self,
        *,
        serialize_error=None,
        commit_error=None,
        cache_error=None,
        notification_error=None,
        requires_proof=False,
        proof_image_path=None,
    ):
        db = Mock()
        self.last_db = db
        events = []
        employee = SimpleNamespace(id=7, status=1)
        leave_type = SimpleNamespace(
            id=3,
            name="Annual Leave",
            is_active=True,
            requires_approval=True,
            requires_proof=requires_proof,
        )

        user_query = Mock()
        user_query.filter.return_value.with_for_update.return_value.first.return_value = (
            employee
        )
        leave_type_query = Mock()
        leave_type_query.filter.return_value.first.return_value = leave_type
        db.query.side_effect = [user_query, leave_type_query]

        captured = {}

        def add_request(value):
            captured["request"] = value
            value.id = 41
            value.created_at = datetime(2026, 8, 1, 8, 0)

        db.add.side_effect = add_request
        db.flush.side_effect = lambda: events.append("flush")
        db.rollback.side_effect = lambda: events.append("rollback")

        def commit():
            events.append("commit")
            if commit_error is not None:
                raise commit_error

        db.commit.side_effect = commit

        background_tasks = Mock()

        def schedule_notification(*_args, **_kwargs):
            events.append("notification")
            if notification_error is not None:
                raise notification_error

        background_tasks.add_task.side_effect = schedule_notification

        response = object()

        def serialize(*_args, **_kwargs):
            events.append("serialize")
            if serialize_error is not None:
                raise serialize_error
            return [response]

        serializer = Mock(side_effect=serialize)

        cache_invalidator = Mock()

        def invalidate_cache(*_args, **_kwargs):
            events.append("cache")
            if cache_error is not None:
                raise cache_error

        cache_invalidator.side_effect = invalidate_cache

        payload = LeaveRequestCreate(
            leave_type_id=3,
            reason="Family appointment",
            days=[LeaveRequestDayIn(leave_date=date(2026, 8, 5))],
            proof_image_path=proof_image_path,
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(leave_management, "_today_kh", return_value=date(2026, 8, 1))
            )
            stack.enter_context(
                patch.object(leave_management, "_active_academic_id", return_value=16)
            )
            stack.enter_context(
                patch.object(leave_management, "_holidays_in_range", return_value={})
            )
            stack.enter_context(
                patch.object(leave_management, "_existing_leave_days", return_value={})
            )
            stack.enter_context(
                patch.object(
                    leave_management,
                    "get_effective_day_attendance",
                    return_value={
                        "is_active_day": True,
                        "sessions": [{"start": "07:15", "end": "11:15"}],
                    },
                )
            )
            stack.enter_context(
                patch.object(leave_management, "_allocated_days", return_value=10.0)
            )
            stack.enter_context(
                patch.object(leave_management, "_sum_day_costs", return_value=0.0)
            )
            stack.enter_context(
                patch.object(
                    leave_management,
                    "_sum_policy_deductions",
                    return_value=0.0,
                )
            )
            stack.enter_context(patch.object(leave_management, "_add_history"))
            # The monthly-cap split needs a real session; this suite exercises
            # transaction ordering with a mock db, so stub it out. Its own
            # behaviour is covered by test_leave_monthly_cap_policy.
            stack.enter_context(
                patch.object(
                    leave_management.leave_monthly_policy,
                    "simulate",
                    return_value={
                        "cap_days": None,
                        "paid_days": 1.0,
                        "unpaid_days": 0.0,
                        "months": [],
                    },
                )
            )
            stack.enter_context(
                patch.object(
                    leave_management.leave_monthly_policy,
                    "recompute_for_request",
                    return_value={},
                )
            )
            stack.enter_context(
                patch.object(leave_management, "_serialize_requests", serializer)
            )
            stack.enter_context(
                patch.object(leave_management, "_is_admin", return_value=False)
            )
            stack.enter_context(
                patch.object(
                    leave_management,
                    "_invalidate_user_requests_cache",
                    cache_invalidator,
                )
            )
            stack.enter_context(patch.object(leave_management.logger, "warning"))
            stack.enter_context(patch.object(leave_management.logger, "error"))

            result = await leave_management.create_leave_request(
                payload,
                background_tasks,
                db,
                employee,
            )

        return {
            "result": result,
            "response": response,
            "db": db,
            "serializer": serializer,
            "background_tasks": background_tasks,
            "cache_invalidator": cache_invalidator,
            "request": captured.get("request"),
            "events": events,
        }

    async def test_response_is_prepared_before_commit_and_notification_is_post_commit(self):
        result = await self._submit()

        self.assertIs(result["result"], result["response"])
        result["serializer"].assert_called_once()
        result["db"].commit.assert_called_once()
        result["db"].rollback.assert_not_called()
        result["background_tasks"].add_task.assert_called_once()
        self.assertLess(
            result["events"].index("serialize"),
            result["events"].index("commit"),
        )
        self.assertLess(
            result["events"].index("commit"),
            result["events"].index("notification"),
        )

    async def test_precommit_response_failure_rolls_back_every_database_change(self):
        with self.assertRaisesRegex(RuntimeError, "response failed"):
            await self._submit(serialize_error=RuntimeError("response failed"))
        self.last_db.rollback.assert_called_once()
        self.last_db.commit.assert_not_called()

    async def test_commit_failure_rolls_back_every_database_change(self):
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            await self._submit(commit_error=RuntimeError("commit failed"))
        self.last_db.rollback.assert_called_once()

    async def test_postcommit_side_effect_failures_do_not_report_submission_failure(self):
        result = await self._submit(
            cache_error=RuntimeError("cache failed"),
            notification_error=RuntimeError("notification failed"),
        )

        self.assertIs(result["result"], result["response"])
        result["db"].commit.assert_called_once()
        result["db"].rollback.assert_not_called()

    async def test_optional_proof_is_saved_for_type_that_does_not_require_it(self):
        proof_path = "uploads/leave_proofs/u7_optional.jpg"

        result = await self._submit(proof_image_path=proof_path)

        self.assertEqual(result["request"].proof_image_path, proof_path)
        result["db"].commit.assert_called_once()

    async def test_required_proof_is_still_enforced(self):
        with self.assertRaises(HTTPException) as raised:
            await self._submit(requires_proof=True)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("proof image is required", str(raised.exception.detail))
        self.last_db.add.assert_not_called()

    async def test_required_proof_type_accepts_uploaded_proof(self):
        proof_path = "uploads/leave_proofs/u7_required.jpg"

        result = await self._submit(
            requires_proof=True,
            proof_image_path=proof_path,
        )

        self.assertEqual(result["request"].proof_image_path, proof_path)
        result["db"].commit.assert_called_once()


class ManualLeaveProofPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_required_proof_is_rejected_before_batch_writes(self):
        db = Mock()
        leave_type = SimpleNamespace(
            id=3,
            name="Medical Leave",
            is_active=True,
            requires_proof=True,
        )
        leave_type_query = Mock()
        leave_type_query.filter.return_value.first.return_value = leave_type
        db.query.return_value = leave_type_query
        payload = ManualLeaveCreate(
            user_ids=[8],
            leave_type_id=3,
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 5),
            reason="Medical appointment",
        )

        with (
            patch.object(leave_management, "_manual_leave_approver"),
            patch.object(leave_management, "ensure_schedule_exceptions_table") as ensure,
            self.assertRaises(HTTPException) as raised,
        ):
            await leave_management.create_manual_leave(
                payload,
                Mock(),
                db,
                SimpleNamespace(id=7, status=1),
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("proof image is required", str(raised.exception.detail))
        ensure.assert_not_called()
        db.add.assert_not_called()


class LeaveProofReferenceTests(unittest.TestCase):
    def test_shared_manual_proof_is_not_deleted_while_still_referenced(self):
        shared_path = "uploads/leave_proofs/u7_shared.jpg"
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(proof_image_path=shared_path)
        ]

        with patch.object(leave_management, "_delete_proof_file") as delete:
            leave_management._delete_unreferenced_proof_files(db, shared_path)

        delete.assert_not_called()

    def test_only_unreferenced_proof_from_attachment_set_is_deleted(self):
        first_path = "uploads/leave_proofs/u7_first.jpg"
        shared_path = "uploads/leave_proofs/u7_shared.jpg"
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(proof_image_path=shared_path)
        ]

        with patch.object(leave_management, "_delete_proof_file") as delete:
            leave_management._delete_unreferenced_proof_files(
                db,
                f"{first_path},{shared_path}",
            )

        delete.assert_called_once_with(first_path)


class LeaveCancellationTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def _cancel(
        self,
        *,
        request_status="pending",
        request_user_id=7,
        current_user_id=7,
        current_user_role_id=2,
        reason="Plans changed",
        request_start_date=date(2026, 8, 5),
        today=date(2026, 8, 1),
        serialize_error=None,
        commit_error=None,
        notification_error=None,
    ):
        events = []
        db = Mock()
        self.last_db = db
        employee = SimpleNamespace(
            id=current_user_id,
            role_id=current_user_role_id,
            status=1,
        )
        request = SimpleNamespace(
            id=41,
            user_id=request_user_id,
            creation_source="employee",
            status=request_status,
            start_date=request_start_date,
            end_date=request_start_date,
            proof_image_path="uploads/leave_proofs/u7_test.jpg",
            cancelled_by=None,
            cancelled_at=None,
            cancel_reason=None,
        )
        request_query = Mock()
        request_query.filter.return_value.with_for_update.return_value.first.return_value = (
            request
        )
        db.query.return_value = request_query
        db.flush.side_effect = lambda: events.append("flush")
        db.rollback.side_effect = lambda: events.append("rollback")

        def commit():
            events.append("commit")
            if commit_error is not None:
                raise commit_error

        db.commit.side_effect = commit
        response = object()

        def serialize(*_args, **_kwargs):
            events.append("serialize")
            if serialize_error is not None:
                raise serialize_error
            return [response]

        background_tasks = Mock()

        def schedule(*_args, **_kwargs):
            events.append("notification")
            if notification_error is not None:
                raise notification_error

        background_tasks.add_task.side_effect = schedule

        with (
            patch.object(leave_management, "_today_kh", return_value=today),
            patch.object(leave_management, "_add_history"),
            # Stubbed for the same reason as in the submission suite above.
            patch.object(
                leave_management.leave_monthly_policy,
                "recompute_for_request",
                return_value={},
            ),
            patch.object(leave_management, "_serialize_requests", side_effect=serialize),
            patch.object(
                leave_management,
                "_delete_unreferenced_proof_files",
                side_effect=lambda *_args: events.append("delete-proof"),
            ),
            patch.object(
                leave_management,
                "_invalidate_user_requests_cache",
                side_effect=lambda *_args: events.append("cache"),
            ),
            patch.object(leave_management.logger, "error"),
        ):
            result = await leave_management.cancel_request(
                request.id,
                LeaveCancelRequest(reason=reason),
                background_tasks,
                db,
                employee,
            )

        return {
            "result": result,
            "response": response,
            "db": db,
            "request": request,
            "events": events,
            "background_tasks": background_tasks,
        }

    async def test_cancel_response_is_prepared_before_atomic_commit(self):
        result = await self._cancel()

        self.assertIs(result["result"], result["response"])
        result["db"].flush.assert_called_once()
        result["db"].commit.assert_called_once()
        result["db"].rollback.assert_not_called()
        self.assertLess(
            result["events"].index("serialize"),
            result["events"].index("commit"),
        )
        self.assertLess(
            result["events"].index("commit"),
            result["events"].index("delete-proof"),
        )
        self.assertLess(
            result["events"].index("commit"),
            result["events"].index("notification"),
        )

    async def test_cancel_precommit_failure_rolls_back_every_database_change(self):
        with self.assertRaisesRegex(RuntimeError, "response failed"):
            await self._cancel(serialize_error=RuntimeError("response failed"))

        self.last_db.rollback.assert_called_once()
        self.last_db.commit.assert_not_called()

    async def test_cancel_commit_failure_rolls_back_every_database_change(self):
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            await self._cancel(commit_error=RuntimeError("commit failed"))

        self.last_db.rollback.assert_called_once()

    async def test_notification_scheduling_failure_does_not_fake_cancel_failure(self):
        result = await self._cancel(
            notification_error=RuntimeError("notification failed"),
        )

        self.assertIs(result["result"], result["response"])
        result["db"].commit.assert_called_once()
        result["db"].rollback.assert_not_called()

    async def test_past_pending_request_is_rejected_before_cancellation_writes(self):
        with self.assertRaises(HTTPException) as raised:
            await self._cancel(
                request_start_date=date(2026, 8, 5),
                today=date(2026, 8, 6),
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("already passed", str(raised.exception.detail))
        self.last_db.flush.assert_not_called()
        self.last_db.commit.assert_not_called()

    async def test_closing_someone_elses_approved_leave_requires_a_reason(self):
        with patch.object(
            leave_management,
            "_request_actionability",
            return_value={"can_cancel": True, "can_cancel_reason": None},
        ):
            with self.assertRaises(HTTPException) as raised:
                await self._cancel(
                    request_status="approved",
                    request_user_id=8,
                    current_user_id=7,
                    current_user_role_id=1,
                    reason=None,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("reason is required", str(raised.exception.detail))
        self.last_db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
