"""Password-guessing throttle on the login endpoints.

Two things matter equally here: it must stop a brute force, and it must never
stand between a real person and their account. The second half is why most of
these tests are about NOT locking somebody out.
"""

import unittest
from types import SimpleNamespace

from app.core import settings
from app.services import login_throttle
from app.utils.client_ip import rate_limit_key, throttle_ip


def _request(peer="203.0.113.9", forwarded=None):
    headers = {}
    if forwarded is not None:
        headers["X-Forwarded-For"] = forwarded
    return SimpleNamespace(
        client=SimpleNamespace(host=peer),
        headers=SimpleNamespace(get=lambda k, d=None: headers.get(k, d)),
    )


class LoginThrottleTests(unittest.TestCase):
    def setUp(self):
        login_throttle.reset_all_for_tests()
        self._max = settings.login_max_failed_attempts

    def tearDown(self):
        login_throttle.reset_all_for_tests()
        settings.login_max_failed_attempts = self._max

    def test_a_few_wrong_passwords_do_not_lock(self):
        """Real people mistype. Nothing should happen for the first few."""
        for _ in range(settings.login_max_failed_attempts - 1):
            login_throttle.record_failure("msophea", "203.0.113.9")
        self.assertFalse(login_throttle.is_locked("msophea", "203.0.113.9"))

    def test_locks_once_the_threshold_is_reached(self):
        for _ in range(settings.login_max_failed_attempts):
            login_throttle.record_failure("msophea", "203.0.113.9")
        self.assertTrue(login_throttle.is_locked("msophea", "203.0.113.9"))

    def test_a_success_clears_the_counter(self):
        for _ in range(settings.login_max_failed_attempts - 1):
            login_throttle.record_failure("msophea", "203.0.113.9")
        login_throttle.clear("msophea", "203.0.113.9")
        self.assertFalse(login_throttle.is_locked("msophea", "203.0.113.9"))
        self.assertEqual(login_throttle.failures_for("msophea", "203.0.113.9"), 0)

    def test_one_account_being_attacked_does_not_lock_everybody(self):
        for _ in range(settings.login_max_failed_attempts * 3):
            login_throttle.record_failure("victim", None)
        self.assertTrue(login_throttle.is_locked("victim", None))
        self.assertFalse(login_throttle.is_locked("someone-else", None))

    def test_rotating_ip_does_not_reset_the_account_counter(self):
        """The whole point: IP rotation must not buy more guesses."""
        for i in range(settings.login_max_failed_attempts):
            login_throttle.record_failure("victim", f"198.51.100.{i}")
        self.assertTrue(login_throttle.is_locked("victim", "198.51.100.250"))

    def test_disabling_the_throttle_restores_old_behaviour(self):
        settings.login_throttle_enabled = False
        try:
            for _ in range(settings.login_max_failed_attempts * 5):
                login_throttle.record_failure("msophea", "203.0.113.9")
            self.assertFalse(login_throttle.is_locked("msophea", "203.0.113.9"))
        finally:
            settings.login_throttle_enabled = True

    def test_a_broken_backend_never_blocks_a_login(self):
        """Degrade open: a throttle that breaks logins is worse than the attack."""
        original = login_throttle.failures_for
        login_throttle.failures_for = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("redis exploded")
        )
        try:
            self.assertFalse(login_throttle.is_locked("msophea", "203.0.113.9"))
        finally:
            login_throttle.failures_for = original


class ClientIpTests(unittest.TestCase):
    def setUp(self):
        self._ranges = settings.trusted_proxy_ranges

    def tearDown(self):
        settings.trusted_proxy_ranges = self._ranges

    def test_forwarded_header_is_ignored_from_an_untrusted_peer(self):
        settings.trusted_proxy_ranges = "10.0.0.0/8"
        req = _request(peer="203.0.113.9", forwarded="1.2.3.4")
        self.assertEqual(throttle_ip(req), "203.0.113.9")

    def test_forwarded_header_is_used_from_a_trusted_proxy(self):
        settings.trusted_proxy_ranges = "10.0.0.0/8"
        req = _request(peer="10.1.2.3", forwarded="198.51.100.7")
        self.assertEqual(throttle_ip(req), "198.51.100.7")

    def test_no_ip_bucket_behind_an_undeclared_proxy(self):
        """Otherwise one shared proxy IP would lock the whole school out."""
        settings.trusted_proxy_ranges = ""
        req = _request(peer="10.1.2.3", forwarded="198.51.100.7")
        self.assertIsNone(throttle_ip(req))

    def test_direct_connection_still_gets_an_ip_bucket(self):
        settings.trusted_proxy_ranges = ""
        self.assertEqual(throttle_ip(_request(peer="203.0.113.9")), "203.0.113.9")

    def test_global_limiter_keeps_previous_behaviour_when_unconfigured(self):
        """Changing this without a configured range would bucket everyone together."""
        settings.trusted_proxy_ranges = ""
        req = _request(peer="10.1.2.3", forwarded="198.51.100.7")
        self.assertEqual(rate_limit_key(req), "198.51.100.7")

    def test_global_limiter_stops_trusting_the_header_once_configured(self):
        settings.trusted_proxy_ranges = "10.0.0.0/8"
        req = _request(peer="203.0.113.9", forwarded="1.2.3.4")
        self.assertEqual(rate_limit_key(req), "203.0.113.9")

    def test_garbage_forwarded_values_fall_back_to_the_peer(self):
        settings.trusted_proxy_ranges = "10.0.0.0/8"
        req = _request(peer="10.1.2.3", forwarded="not-an-ip")
        self.assertEqual(throttle_ip(req), "10.1.2.3")


class ForwardedForSpoofingTests(unittest.TestCase):
    """nginx here uses $proxy_add_x_forwarded_for, which APPENDS to whatever the
    client sent. The leftmost entry is therefore attacker-chosen; only the
    rightmost entries were added by our own proxy."""

    def setUp(self):
        self._ranges = settings.trusted_proxy_ranges
        # The real deployment: nginx on the host reaches the container through
        # the docker gateway.
        settings.trusted_proxy_ranges = "172.18.0.0/16"

    def tearDown(self):
        settings.trusted_proxy_ranges = self._ranges

    def test_a_spoofed_leading_entry_is_ignored(self):
        req = _request(peer="172.18.0.1", forwarded="1.2.3.4, 203.0.113.9")
        self.assertEqual(throttle_ip(req), "203.0.113.9")

    def test_several_spoofed_entries_are_ignored(self):
        req = _request(
            peer="172.18.0.1",
            forwarded="9.9.9.9, 8.8.8.8, evil, 203.0.113.9",
        )
        self.assertEqual(throttle_ip(req), "203.0.113.9")

    def test_a_single_honest_entry_still_works(self):
        req = _request(peer="172.18.0.1", forwarded="203.0.113.9")
        self.assertEqual(throttle_ip(req), "203.0.113.9")

    def test_extra_proxy_hops_are_walked_past(self):
        req = _request(peer="172.18.0.1", forwarded="203.0.113.9, 172.18.0.5")
        self.assertEqual(throttle_ip(req), "203.0.113.9")

    def test_an_untrusted_peer_is_never_believed(self):
        req = _request(peer="203.0.113.50", forwarded="1.2.3.4")
        self.assertEqual(throttle_ip(req), "203.0.113.50")

    def test_rotating_the_spoofed_entry_cannot_dodge_the_throttle(self):
        """The whole point: the bucket key must not move with the header."""
        keys = {
            throttle_ip(_request(peer="172.18.0.1",
                                 forwarded=f"{i}.{i}.{i}.{i}, 203.0.113.9"))
            for i in range(1, 20)
        }
        self.assertEqual(keys, {"203.0.113.9"})


if __name__ == "__main__":
    unittest.main()
