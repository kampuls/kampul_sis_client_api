import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "market_listing_lifecycle.py"
)
_SPEC = importlib.util.spec_from_file_location("market_listing_lifecycle", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class MarketListingLifecycleTests(unittest.TestCase):
    def test_new_listing_waits_three_days(self):
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        can_renew, next_at = _MODULE.listing_renewal_status(
            now - timedelta(days=2),
            None,
            now=now,
        )
        self.assertFalse(can_renew)
        self.assertEqual(next_at, now + timedelta(days=1))

    def test_listing_is_renewable_at_three_days(self):
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        can_renew, _ = _MODULE.listing_renewal_status(
            now - timedelta(days=3),
            None,
            now=now,
        )
        self.assertTrue(can_renew)

    def test_latest_renewal_controls_next_eligibility(self):
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        renewed_at = now - timedelta(days=2)
        self.assertEqual(
            _MODULE.effective_published_at(
                now - timedelta(days=100),
                renewed_at,
            ),
            renewed_at,
        )
        can_renew, next_at = _MODULE.listing_renewal_status(
            now - timedelta(days=100),
            renewed_at,
            now=now,
        )
        self.assertFalse(can_renew)
        self.assertEqual(next_at, renewed_at + timedelta(days=3))

    def test_naive_database_timestamps_are_treated_as_utc(self):
        created_at = datetime(2026, 6, 1)
        effective = _MODULE.effective_published_at(created_at, None)
        self.assertEqual(effective.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
