import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "attendance_mutation_replay.py"
)
SPEC = importlib.util.spec_from_file_location(
    "attendance_mutation_replay",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AttendanceMutationReplayTests(unittest.TestCase):
    def test_recent_auto_submission_is_replay(self):
        now = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)
        self.assertTrue(
            MODULE.is_recent_auto_checkin_replay(
                requested_action="auto",
                open_check_in_time=now - timedelta(seconds=30),
                now=now,
            )
        )

    def test_explicit_checkout_is_never_replay(self):
        now = datetime(2026, 7, 23, 8, 0)
        self.assertFalse(
            MODULE.is_recent_auto_checkin_replay(
                requested_action="check_out",
                open_check_in_time=now - timedelta(seconds=10),
                now=now,
            )
        )

    def test_old_open_session_is_not_replay(self):
        now = datetime(2026, 7, 23, 8, 0)
        self.assertFalse(
            MODULE.is_recent_auto_checkin_replay(
                requested_action="auto",
                open_check_in_time=now - timedelta(minutes=5),
                now=now,
            )
        )


if __name__ == "__main__":
    unittest.main()
