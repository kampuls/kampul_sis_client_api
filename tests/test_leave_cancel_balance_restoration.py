import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.leave_management import _leave_balance_value
from app.models.base import Base
from app.models.leave_management import (
    LeaveBalanceAdjustment,
    LeaveRequest,
    LeaveRequestDay,
    LeaveType,
    LeaveTypeAllocation,
)


class LeaveCancellationBalanceRestorationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                LeaveType.__table__,
                LeaveTypeAllocation.__table__,
                LeaveRequest.__table__,
                LeaveRequestDay.__table__,
                LeaveBalanceAdjustment.__table__,
            ],
        )
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_cancelling_approved_leave_restores_exact_fractional_days(self):
        leave_type = LeaveType(
            id=3,
            name="Annual Leave",
            max_days_per_year=10,
            is_paid=True,
            requires_approval=True,
        )
        self.session.add_all(
            [
                leave_type,
                LeaveTypeAllocation(
                    leave_type_id=3,
                    academic_id=2026,
                    allocated_days=10,
                ),
            ]
        )
        request = LeaveRequest(
            user_id=10,
            leave_type_id=3,
            start_date=date(2026, 7, 29),
            end_date=date(2026, 7, 30),
            status="approved",
            academic_id=2026,
            total_days=1.5,
        )
        request.days = [
            LeaveRequestDay(
                leave_date=date(2026, 7, 29),
                scope="full_day",
                day_cost=1.0,
            ),
            LeaveRequestDay(
                leave_date=date(2026, 7, 30),
                scope="sessions",
                session_indexes=[1],
                sessions_total=2,
                day_cost=0.5,
            ),
        ]
        self.session.add(request)
        self.session.commit()

        approved_balance = _leave_balance_value(
            self.session,
            user_id=10,
            leave_type=leave_type,
            academic_id=2026,
        )
        self.assertEqual(approved_balance.taken_days, 1.5)
        self.assertEqual(approved_balance.remaining_days, 8.5)
        self.assertEqual(approved_balance.available_to_request_days, 8.5)

        request.status = "cancelled"
        self.session.commit()

        cancelled_balance = _leave_balance_value(
            self.session,
            user_id=10,
            leave_type=leave_type,
            academic_id=2026,
        )
        self.assertEqual(cancelled_balance.taken_days, 0)
        self.assertEqual(cancelled_balance.remaining_days, 10)
        self.assertEqual(cancelled_balance.available_to_request_days, 10)

    def test_pending_leave_is_visible_and_reserved_for_new_requests(self):
        leave_type = LeaveType(
            id=4,
            name="Personal Leave",
            max_days_per_year=5,
            is_paid=True,
            requires_approval=True,
        )
        self.session.add(leave_type)
        request = LeaveRequest(
            user_id=11,
            leave_type_id=4,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            status="pending",
            academic_id=2026,
            total_days=1.0,
        )
        request.days = [
            LeaveRequestDay(
                leave_date=date(2026, 8, 10),
                scope="full_day",
                day_cost=1.0,
            )
        ]
        self.session.add(request)
        self.session.commit()

        balance = _leave_balance_value(
            self.session,
            user_id=11,
            leave_type=leave_type,
            academic_id=2026,
        )

        self.assertEqual(balance.remaining_days, 5)
        self.assertEqual(balance.pending_days, 1)
        self.assertEqual(balance.available_to_request_days, 4)


if __name__ == "__main__":
    unittest.main()
