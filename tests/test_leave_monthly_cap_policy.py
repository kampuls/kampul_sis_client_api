import unittest
from datetime import date, timedelta

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
from app.services import leave_monthly_policy

ACADEMIC_ID = 2026
USER_ID = 7


class LeaveMonthlyCapPolicyTests(unittest.TestCase):
    """The monthly cap splits leave into paid and unpaid without losing days."""

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
        self.leave_type = LeaveType(
            id=3,
            name="Annual Leave",
            max_days_per_year=10,
            max_days_per_month=1,
            is_paid=True,
            requires_approval=True,
        )
        self.session.add_all(
            [
                self.leave_type,
                LeaveTypeAllocation(
                    leave_type_id=3,
                    academic_id=ACADEMIC_ID,
                    allocated_days=10,
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _add_request(self, days, status="approved", request_id=None):
        """Store one request whose days carry the given (date, cost) pairs."""
        request = LeaveRequest(
            id=request_id,
            user_id=USER_ID,
            leave_type_id=3,
            start_date=days[0][0],
            end_date=days[-1][0],
            status=status,
            academic_id=ACADEMIC_ID,
            total_days=sum(cost for _, cost in days),
        )
        request.days = [
            LeaveRequestDay(
                leave_date=leave_date,
                scope="full_day" if cost == 1.0 else "sessions",
                day_cost=cost,
            )
            for leave_date, cost in days
        ]
        self.session.add(request)
        self.session.commit()
        return request

    def _costs(self, request):
        return [
            (day.leave_date, day.paid_cost, day.unpaid_cost)
            for day in sorted(request.days, key=lambda d: d.leave_date)
        ]

    def _balance(self):
        return _leave_balance_value(
            self.session, USER_ID, self.leave_type, ACADEMIC_ID
        )

    # ── The core rule ────────────────────────────────────────────────────────

    def test_second_day_in_a_month_is_granted_but_unpaid(self):
        request = self._add_request(
            [(date(2026, 3, 4), 1.0), (date(2026, 3, 18), 1.0)]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        self.assertEqual(
            self._costs(request),
            [
                (date(2026, 3, 4), 1.0, 0.0),
                (date(2026, 3, 18), 0.0, 1.0),
            ],
        )
        balance = self._balance()
        # Two days were taken, but only the first one costs allowance.
        self.assertEqual(balance.taken_days, 1.0)
        self.assertEqual(balance.unpaid_days, 1.0)
        self.assertEqual(balance.total_taken_days, 2.0)
        self.assertEqual(balance.remaining_days, 9.0)

    def test_day_cost_is_never_modified_by_the_split(self):
        request = self._add_request(
            [(date(2026, 3, 4), 1.0), (date(2026, 3, 18), 1.0)]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        for day in request.days:
            self.assertEqual(day.day_cost, 1.0)
            self.assertAlmostEqual(day.paid_cost + day.unpaid_cost, day.day_cost)

    def test_each_calendar_month_gets_its_own_allowance(self):
        request = self._add_request(
            [
                (date(2026, 3, 4), 1.0),
                (date(2026, 3, 18), 1.0),
                (date(2026, 4, 2), 1.0),
            ]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        self.assertEqual(
            self._costs(request),
            [
                (date(2026, 3, 4), 1.0, 0.0),
                (date(2026, 3, 18), 0.0, 1.0),
                # April starts a fresh cap.
                (date(2026, 4, 2), 1.0, 0.0),
            ],
        )

    def test_boundary_day_splits_fractionally_for_session_leave(self):
        request = self._add_request(
            [(date(2026, 3, 4), 0.5), (date(2026, 3, 5), 1.0)]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        # Cap 1.0: the half day is fully paid, the next day is half paid.
        self.assertEqual(
            self._costs(request),
            [
                (date(2026, 3, 4), 0.5, 0.0),
                (date(2026, 3, 5), 0.5, 0.5),
            ],
        )
        self.assertEqual(self._balance().taken_days, 1.0)

    def test_cap_is_filled_chronologically_across_separate_requests(self):
        later = self._add_request([(date(2026, 3, 20), 1.0)], request_id=1)
        earlier = self._add_request([(date(2026, 3, 2), 1.0)], request_id=2)
        leave_monthly_policy.recompute_for_request(self.session, earlier)
        self.session.commit()

        # The earlier leave date takes the cap regardless of submission order.
        self.assertEqual(self._costs(earlier), [(date(2026, 3, 2), 1.0, 0.0)])
        self.assertEqual(self._costs(later), [(date(2026, 3, 20), 0.0, 1.0)])

    # ── Reversibility ────────────────────────────────────────────────────────

    def test_cancelling_the_paid_day_promotes_the_unpaid_day(self):
        first = self._add_request([(date(2026, 3, 4), 1.0)], request_id=1)
        second = self._add_request([(date(2026, 3, 18), 1.0)], request_id=2)
        leave_monthly_policy.recompute_for_request(self.session, second)
        self.session.commit()
        self.assertEqual(self._costs(second), [(date(2026, 3, 18), 0.0, 1.0)])

        first.status = "cancelled"
        leave_monthly_policy.recompute_for_request(self.session, first)
        self.session.commit()

        # The released cap slot goes to the surviving day.
        self.assertEqual(self._costs(second), [(date(2026, 3, 18), 1.0, 0.0)])
        self.assertEqual(self._balance().unpaid_days, 0.0)

    def test_clearing_the_cap_returns_every_unpaid_day_to_the_balance(self):
        request = self._add_request(
            [
                (date(2026, 3, 4), 1.0),
                (date(2026, 3, 18), 1.0),
                (date(2026, 3, 25), 1.0),
            ]
        )
        leave_monthly_policy.recompute_leave_type(
            self.session, self.leave_type, ACADEMIC_ID
        )
        self.session.commit()
        self.assertEqual(self._balance().unpaid_days, 2.0)

        self.leave_type.max_days_per_month = None
        totals = leave_monthly_policy.recompute_leave_type(
            self.session, self.leave_type, ACADEMIC_ID
        )
        self.session.commit()

        self.assertEqual(totals["restored_days"], 2.0)
        balance = self._balance()
        self.assertEqual(balance.unpaid_days, 0.0)
        self.assertEqual(balance.taken_days, 3.0)
        self.assertEqual(balance.remaining_days, 7.0)
        self.assertEqual(
            self._costs(request),
            [
                (date(2026, 3, 4), 1.0, 0.0),
                (date(2026, 3, 18), 1.0, 0.0),
                (date(2026, 3, 25), 1.0, 0.0),
            ],
        )

    def test_enabling_a_cap_backfills_existing_leave(self):
        # Leave stored before any cap existed is entirely paid.
        self.leave_type.max_days_per_month = None
        request = self._add_request(
            [(date(2026, 3, 4), 1.0), (date(2026, 3, 18), 1.0)]
        )
        leave_monthly_policy.recompute_leave_type(
            self.session, self.leave_type, ACADEMIC_ID
        )
        self.session.commit()
        self.assertEqual(self._balance().remaining_days, 8.0)

        self.leave_type.max_days_per_month = 1
        totals = leave_monthly_policy.recompute_leave_type(
            self.session, self.leave_type, ACADEMIC_ID
        )
        self.session.commit()

        self.assertEqual(totals["newly_unpaid_days"], 1.0)
        self.assertEqual(totals["affected_users"], 1)
        # The over-cap day is handed back to the allowance and reported unpaid.
        self.assertEqual(self._balance().remaining_days, 9.0)
        self.assertEqual(self._balance().unpaid_days, 1.0)
        self.assertEqual(
            [day.day_cost for day in request.days], [1.0, 1.0]
        )

    def test_recompute_is_idempotent(self):
        request = self._add_request(
            [(date(2026, 3, 4), 1.0), (date(2026, 3, 18), 1.0)]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()
        first_pass = self._costs(request)

        totals = leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        self.assertEqual(self._costs(request), first_pass)
        self.assertEqual(totals["changed_days"], 0)

    def test_no_cap_leaves_every_day_fully_paid(self):
        self.leave_type.max_days_per_month = 0  # 0 disables the policy
        request = self._add_request(
            [(date(2026, 3, 4), 1.0), (date(2026, 3, 18), 1.0)]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        self.assertEqual(self._balance().unpaid_days, 0.0)
        self.assertEqual(self._balance().taken_days, 2.0)

    def test_rejected_and_cancelled_leave_never_consumes_the_cap(self):
        self._add_request([(date(2026, 3, 2), 1.0)], status="rejected")
        self._add_request([(date(2026, 3, 3), 1.0)], status="cancelled")
        approved = self._add_request([(date(2026, 3, 10), 1.0)])
        leave_monthly_policy.recompute_for_request(self.session, approved)
        self.session.commit()

        self.assertEqual(self._costs(approved), [(date(2026, 3, 10), 1.0, 0.0)])

    def test_pending_leave_reserves_the_cap_ahead_of_a_later_request(self):
        pending = self._add_request(
            [(date(2026, 3, 2), 1.0)], status="pending", request_id=1
        )
        approved = self._add_request([(date(2026, 3, 20), 1.0)], request_id=2)
        leave_monthly_policy.recompute_for_request(self.session, approved)
        self.session.commit()

        self.assertEqual(self._costs(pending), [(date(2026, 3, 2), 1.0, 0.0)])
        self.assertEqual(self._costs(approved), [(date(2026, 3, 20), 0.0, 1.0)])

    # ── Leave stays askable once the yearly allowance is spent ───────────────

    def test_days_beyond_the_yearly_allowance_are_unpaid_not_blocked(self):
        # One paid day a month for 10 months uses the whole 10-day allowance.
        used_up = self._add_request(
            [(date(2026, m, 5), 1.0) for m in range(1, 11)], request_id=1
        )
        leave_monthly_policy.recompute_for_request(self.session, used_up)
        self.session.commit()
        self.assertEqual(self._balance().remaining_days, 0.0)

        # November is a fresh month, so its first day is inside the monthly
        # cap — but the yearly allowance is gone, so it must still be unpaid
        # rather than paid (which would have been rejected at submission).
        extra = self._add_request([(date(2026, 11, 3), 1.0)], request_id=2)
        leave_monthly_policy.recompute_for_request(self.session, extra)
        self.session.commit()

        self.assertEqual(self._costs(extra), [(date(2026, 11, 3), 0.0, 1.0)])
        balance = self._balance()
        self.assertEqual(balance.taken_days, 10.0)
        self.assertEqual(balance.unpaid_days, 1.0)
        self.assertEqual(balance.total_taken_days, 11.0)
        # The paid balance stops at zero instead of going negative.
        self.assertEqual(balance.remaining_days, 0.0)

    def test_simulate_reports_a_fresh_month_as_unpaid_when_allowance_is_gone(self):
        used_up = self._add_request(
            [(date(2026, m, 5), 1.0) for m in range(1, 11)]
        )
        leave_monthly_policy.recompute_for_request(self.session, used_up)
        self.session.commit()

        result = leave_monthly_policy.simulate(
            self.session,
            USER_ID,
            self.leave_type,
            ACADEMIC_ID,
            {date(2026, 11, 3): 1.0},
        )

        # Nothing is charged, so the submission balance check cannot reject it.
        self.assertEqual(result["paid_days"], 0.0)
        self.assertEqual(result["unpaid_days"], 1.0)

    def test_freeing_yearly_allowance_promotes_a_later_month(self):
        used_up = self._add_request(
            [(date(2026, m, 5), 1.0) for m in range(1, 11)], request_id=1
        )
        extra = self._add_request([(date(2026, 11, 3), 1.0)], request_id=2)
        leave_monthly_policy.recompute_for_request(self.session, extra)
        self.session.commit()
        self.assertEqual(self._costs(extra), [(date(2026, 11, 3), 0.0, 1.0)])

        # Cancelling an early month returns allowance, so the November day
        # becomes paid even though it sits in a completely different month.
        used_up.status = "cancelled"
        leave_monthly_policy.recompute_for_request(self.session, used_up)
        self.session.commit()

        self.assertEqual(self._costs(extra), [(date(2026, 11, 3), 1.0, 0.0)])

    def test_a_type_without_a_cap_never_marks_days_unpaid(self):
        self.leave_type.max_days_per_month = None
        request = self._add_request(
            [(date(2026, m, 5), 1.0) for m in range(1, 11)]
        )
        leave_monthly_policy.recompute_for_request(self.session, request)
        self.session.commit()

        # Without a monthly cap the balance check governs instead, so the
        # split must not invent unpaid days of its own.
        self.assertEqual(self._balance().unpaid_days, 0.0)
        self.assertEqual(self._balance().taken_days, 10.0)

    # ── Pre-submit simulation ────────────────────────────────────────────────

    def test_simulate_reports_the_unpaid_portion_without_writing(self):
        existing = self._add_request([(date(2026, 3, 4), 1.0)])
        leave_monthly_policy.recompute_for_request(self.session, existing)
        self.session.commit()

        result = leave_monthly_policy.simulate(
            self.session,
            USER_ID,
            self.leave_type,
            ACADEMIC_ID,
            {date(2026, 3, 20): 1.0, date(2026, 4, 6): 1.0},
        )

        self.assertEqual(result["paid_days"], 1.0)   # April only
        self.assertEqual(result["unpaid_days"], 1.0)  # March is already used
        self.assertEqual(
            [(m["month"], m["unpaid_days"]) for m in result["months"]],
            [("2026-03", 1.0), ("2026-04", 0.0)],
        )
        # Nothing was persisted by the simulation.
        self.assertEqual(self._costs(existing), [(date(2026, 3, 4), 1.0, 0.0)])

    def test_simulate_matches_what_the_recompute_later_stores(self):
        self._add_request([(date(2026, 3, 4), 0.5)], request_id=1)
        leave_monthly_policy.recompute_leave_type(
            self.session, self.leave_type, ACADEMIC_ID
        )
        self.session.commit()

        proposed = {date(2026, 3, 10): 1.0}
        simulated = leave_monthly_policy.simulate(
            self.session, USER_ID, self.leave_type, ACADEMIC_ID, proposed
        )
        stored = self._add_request([(date(2026, 3, 10), 1.0)], request_id=2)
        leave_monthly_policy.recompute_for_request(self.session, stored)
        self.session.commit()

        self.assertEqual(simulated["paid_days"], stored.days[0].paid_cost)
        self.assertEqual(simulated["unpaid_days"], stored.days[0].unpaid_cost)

    def test_simulate_can_exclude_the_request_being_edited(self):
        existing = self._add_request([(date(2026, 3, 4), 1.0)], request_id=1)
        leave_monthly_policy.recompute_for_request(self.session, existing)
        self.session.commit()

        result = leave_monthly_policy.simulate(
            self.session,
            USER_ID,
            self.leave_type,
            ACADEMIC_ID,
            {date(2026, 3, 20): 1.0},
            exclude_request_id=1,
        )

        self.assertEqual(result["unpaid_days"], 0.0)

    def test_unsplit_legacy_rows_are_read_as_fully_paid(self):
        # Rows written before the migration have NULL paid/unpaid columns.
        request = self._add_request([(date(2026, 3, 4), 1.0)])
        for day in request.days:
            day.paid_cost = None
            day.unpaid_cost = None
        self.session.commit()

        balance = self._balance()
        self.assertEqual(balance.taken_days, 1.0)
        self.assertEqual(balance.unpaid_days, 0.0)
        self.assertEqual(balance.remaining_days, 9.0)


if __name__ == "__main__":
    unittest.main()
