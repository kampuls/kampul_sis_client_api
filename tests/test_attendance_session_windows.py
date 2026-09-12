import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_session_windows.py"
)
SPEC = importlib.util.spec_from_file_location(
    "attendance_session_windows",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AttendanceSessionWindowTests(unittest.TestCase):
    def test_late_checkout_buffer_never_reopens_missed_checkin(self):
        self.assertFalse(
            MODULE.is_session_check_in_open(
                now_minutes=13 * 60 + 14,
                window_open_minutes=7 * 60,
                session_end_minutes=12 * 60,
            )
        )
        self.assertTrue(
            MODULE.is_session_check_in_open(
                now_minutes=13 * 60 + 14,
                window_open_minutes=13 * 60,
                session_end_minutes=17 * 60,
            )
        )

    def test_auto_checks_out_while_open_session_is_actionable(self):
        action, target = MODULE.resolve_automatic_attendance_target(
            actionable_open_session_index=0,
            check_in_session_index=1,
        )

        self.assertEqual(action, "check_out")
        self.assertEqual(target, 0)

    def test_auto_checks_in_only_when_no_session_is_left_open(self):
        # -1 means nothing is open. Check-outs no longer expire, so this is
        # reached when every earlier session was already completed.
        action, target = MODULE.resolve_automatic_attendance_target(
            actionable_open_session_index=-1,
            check_in_session_index=1,
        )

        self.assertEqual(action, "check_in")
        self.assertEqual(target, 1)

    def test_unfinished_morning_checkout_wins_over_afternoon_checkin(self):
        """The employee forgot to check out of session 1 and taps in session 2.

        The tap must complete the missing morning check-out rather than open
        the afternoon session, which would abandon the morning entirely and
        record them hours late for a session they had been working through.
        """
        action, target = MODULE.resolve_automatic_attendance_target(
            actionable_open_session_index=0,
            check_in_session_index=1,
        )

        self.assertEqual(action, "check_out")
        self.assertEqual(target, 0)

    def test_stale_missed_session_checkin_rolls_forward(self):
        action, target = MODULE.resolve_explicit_attendance_target(
            requested_action="check_in",
            requested_session_index=0,
            requested_session_actionable=False,
            current_check_in_session_index=1,
        )

        self.assertEqual(action, "check_in")
        self.assertEqual(target, 1)

    def test_actionable_previous_checkout_is_preserved(self):
        action, target = MODULE.resolve_explicit_attendance_target(
            requested_action="check_out",
            requested_session_index=0,
            requested_session_actionable=True,
            current_check_in_session_index=1,
        )

        self.assertEqual(action, "check_out")
        self.assertEqual(target, 0)

    def test_checkout_without_an_open_record_rolls_to_current_checkin(self):
        # Not actionable now means "no check-in is open for that session",
        # not "the window closed" — a stale app screen asking to check out of
        # an already-completed session should start the current one instead.
        action, target = MODULE.resolve_explicit_attendance_target(
            requested_action="check_out",
            requested_session_index=0,
            requested_session_actionable=False,
            current_check_in_session_index=1,
        )

        self.assertEqual(action, "check_in")
        self.assertEqual(target, 1)


class OpenCheckOutAvailabilityTests(unittest.TestCase):
    """allow_late_clock_out_mins sets how long a check-out stays completable.

    Sessions 07:15-11:15 and 13:00-17:00 with a three-hour allowance, so
    session 1 remains closeable until 14:15 — deliberately overlapping the
    afternoon session.
    """

    SESSION_1_END = 11 * 60 + 15
    THREE_HOURS = 180

    def _available(self, hour: int, minute: int, allowance=THREE_HOURS) -> bool:
        return MODULE.open_check_out_is_available(
            now_minutes=hour * 60 + minute,
            session_end_minutes=self.SESSION_1_END,
            allow_late_clock_out_minutes=allowance,
        )

    def test_available_during_the_gap_between_sessions(self):
        # Noticing at lunch must work — session 1 ended, session 2 has not begun.
        self.assertTrue(self._available(12, 0))

    def test_available_inside_the_next_session(self):
        # The whole point: a 13:30 tap finishes the morning instead of
        # starting the afternoon and abandoning it.
        self.assertTrue(self._available(13, 30))

    def test_available_up_to_the_configured_deadline(self):
        self.assertTrue(self._available(14, 15))  # exactly on the deadline

    def test_closed_after_the_configured_deadline(self):
        self.assertFalse(self._available(14, 16))
        self.assertFalse(self._available(16, 45))

    def test_a_short_allowance_expires_before_the_next_session(self):
        # 30 minutes closes at 11:45, so an afternoon tap starts session 2.
        self.assertTrue(self._available(11, 45, allowance=30))
        self.assertFalse(self._available(13, 30, allowance=30))

    def test_no_allowance_configured_means_unlimited(self):
        self.assertTrue(self._available(22, 0, allowance=None))

    def test_a_session_without_an_end_time_stays_open(self):
        self.assertTrue(
            MODULE.open_check_out_is_available(
                now_minutes=22 * 60,
                session_end_minutes=None,
                allow_late_clock_out_minutes=self.THREE_HOURS,
            )
        )


class ManySessionBacklogTests(unittest.TestCase):
    """Several forgotten check-outs are cleared oldest first, one per tap.

    Four short sessions with a three-hour allowance, so their windows overlap
    heavily — the case where a single tap could otherwise be ambiguous.
    """

    SESSION_ENDS = {1: 9 * 60, 2: 10 * 60 + 30, 3: 12 * 60, 4: 16 * 60}
    THREE_HOURS = 180

    def _open_sessions_at(self, hour: int, minute: int):
        """Session numbers whose check-out is still completable."""
        now = hour * 60 + minute
        return [
            number
            for number, end in sorted(self.SESSION_ENDS.items())
            if MODULE.open_check_out_is_available(
                now_minutes=now,
                session_end_minutes=end,
                allow_late_clock_out_minutes=self.THREE_HOURS,
            )
        ]

    def test_the_oldest_still_open_session_is_taken_first(self):
        # 11:30: sessions 1 (until 12:00) and 2 (until 13:30) both qualify.
        # The endpoint stops at the first, so session 1 is closed first.
        self.assertEqual(self._open_sessions_at(11, 30)[0], 1)

    def test_an_expired_session_is_skipped_for_a_later_one(self):
        # 12:30: session 1's window closed at 12:00 and stays missing, while
        # session 2 (until 13:30) is still completable.
        available = self._open_sessions_at(12, 30)
        self.assertNotIn(1, available)
        self.assertEqual(available[0], 2)

    def test_windows_overlap_so_a_backlog_can_be_cleared_in_one_visit(self):
        # 11:00: every session so far is still closeable, so an employee who
        # forgot all of them can clear each with successive taps. Check-outs
        # are not delayed by the session transition wait — only check-ins are.
        self.assertEqual(self._open_sessions_at(11, 0), [1, 2, 3, 4])

    def test_a_short_allowance_leaves_no_overlap(self):
        # With 15 minutes nothing reaches the next session, so a forgotten
        # check-out is lost as soon as its own window closes.
        now = 11 * 60
        available = [
            number
            for number, end in sorted(self.SESSION_ENDS.items())
            if MODULE.open_check_out_is_available(
                now_minutes=now,
                session_end_minutes=end,
                allow_late_clock_out_minutes=15,
            )
        ]
        self.assertEqual(available, [3, 4])


class LateCheckOutClassificationTests(unittest.TestCase):
    """allow_late_clock_out_mins flags a late check-out, it never blocks it."""

    # Session 1 ends 11:15 (675 minutes), 30-minute allowance -> 11:45.
    SESSION_END = 11 * 60 + 15

    def _is_late(self, hour: int, minute: int, allowance: int = 30) -> bool:
        return MODULE.is_late_check_out(
            check_out_minutes=hour * 60 + minute,
            session_end_minutes=self.SESSION_END,
            allow_late_clock_out_minutes=allowance,
        )

    def test_check_out_inside_the_window_is_not_late(self):
        self.assertFalse(self._is_late(11, 15))
        self.assertFalse(self._is_late(11, 40))
        self.assertFalse(self._is_late(11, 45))  # exactly on the boundary

    def test_check_out_after_the_window_is_late(self):
        self.assertTrue(self._is_late(11, 46))
        self.assertTrue(self._is_late(16, 45))  # forgotten until the afternoon

    def test_zero_allowance_makes_any_overrun_late(self):
        self.assertFalse(self._is_late(11, 15, allowance=0))
        self.assertTrue(self._is_late(11, 16, allowance=0))

    def test_missing_allowance_is_treated_as_zero(self):
        self.assertTrue(
            MODULE.is_late_check_out(
                check_out_minutes=11 * 60 + 16,
                session_end_minutes=self.SESSION_END,
                allow_late_clock_out_minutes=None,
            )
        )

    def test_stale_target_never_rolls_back_to_an_earlier_session(self):
        action, target = MODULE.resolve_explicit_attendance_target(
            requested_action="check_in",
            requested_session_index=1,
            requested_session_actionable=False,
            current_check_in_session_index=0,
        )

        self.assertEqual(action, "check_in")
        self.assertEqual(target, 1)

if __name__ == "__main__":
    unittest.main()
