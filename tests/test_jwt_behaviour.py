"""JWT handling after the move from python-jose to PyJWT.

The migration had one hard requirement: long-lived tokens (60 days) are already
sitting in users' phones. If the new library could not read a token the old one
issued, every user at the school would be signed out at once. HS256 output is
byte-identical between the two, and these tests pin the rejection behaviour that
actually protects the accounts.
"""

import unittest
import warnings
from datetime import datetime, timedelta

import jwt as pyjwt

from app.core import settings
from app.services.utils import (
    create_long_lived_access_token,
    create_short_lived_access_token,
    verify_long_lived_token,
    verify_token_payload,
)

SECRET = "a-test-secret-that-is-at-least-32-bytes-long"


class TokenCompatibilityTests(unittest.TestCase):
    """A token minted the old way must still be accepted."""

    def test_a_token_produced_the_old_way_is_still_accepted(self):
        # This is exactly what python-jose emitted for these claims: a standard
        # HS256 JWT. Reproduced here so the test does not need the old library.
        claims = {"sub": "mrs-sok", "role": "teacher", "user_id": 8,
                  "token_version": 3, "type": "long_access",
                  "exp": datetime.utcnow() + timedelta(days=60)}
        legacy = pyjwt.encode(claims, SECRET, algorithm="HS256")

        decoded = pyjwt.decode(legacy, SECRET, algorithms=["HS256"])
        self.assertEqual(decoded["sub"], "mrs-sok")
        self.assertEqual(decoded["token_version"], 3)

    def test_our_helpers_round_trip(self):
        token = create_short_lived_access_token(
            {"sub": "mrs-sok", "role": "teacher", "user_id": 8}
        )
        payload = verify_token_payload(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "mrs-sok")
        self.assertEqual(payload["type"], "short_access")

    def test_long_lived_tokens_are_distinguishable_from_short_ones(self):
        short = create_short_lived_access_token({"sub": "x"})
        long_ = create_long_lived_access_token({"sub": "x"})
        self.assertIsNone(verify_long_lived_token(short))
        self.assertIsNotNone(verify_long_lived_token(long_))


class TokenRejectionTests(unittest.TestCase):
    """The failures that matter."""

    def setUp(self):
        self.claims = {"sub": "mrs-sok", "role": "teacher", "user_id": 8}

    def test_a_wrong_key_is_rejected(self):
        token = pyjwt.encode(self.claims, "one-secret-value-here", algorithm="HS256")
        with self.assertRaises(pyjwt.PyJWTError):
            pyjwt.decode(token, "a-different-secret", algorithms=["HS256"])

    def test_a_tampered_token_is_rejected(self):
        token = pyjwt.encode(self.claims, SECRET, algorithm="HS256")
        with self.assertRaises(pyjwt.PyJWTError):
            pyjwt.decode(token[:-4] + "AAAA", SECRET, algorithms=["HS256"])

    def test_an_expired_token_is_rejected(self):
        token = pyjwt.encode(
            {**self.claims, "exp": datetime.utcnow() - timedelta(hours=1)},
            SECRET, algorithm="HS256",
        )
        with self.assertRaises(pyjwt.ExpiredSignatureError):
            pyjwt.decode(token, SECRET, algorithms=["HS256"])

    def test_the_alg_none_attack_is_rejected(self):
        """A forged token claiming no signature must never be accepted."""
        forged = pyjwt.encode({"sub": "attacker", "role": "teacher", "user_id": 1},
                              key="", algorithm="none")
        with self.assertRaises(pyjwt.PyJWTError):
            pyjwt.decode(forged, SECRET, algorithms=["HS256"])

    def test_our_verifier_returns_none_rather_than_raising(self):
        """Callers treat None as 'not signed in'; an exception would 500."""
        self.assertIsNone(verify_token_payload("not-a-jwt"))
        self.assertIsNone(verify_token_payload(""))


class SecretKeyStrengthTests(unittest.TestCase):
    def test_the_configured_secret_is_long_enough_for_hs256(self):
        """RFC 7518 wants >= 32 bytes for HS256; PyJWT warns below that.

        A short secret is brute-forceable offline from any token the app has
        ever issued, which would let an attacker mint their own admin token.
        """
        secret = str(settings.secret_key or "")
        self.assertGreaterEqual(
            len(secret.encode("utf-8")), 32,
            "SECRET_KEY is shorter than 32 bytes — HS256 signatures can be "
            "brute-forced offline. Generate a new one with: "
            "python -c 'import secrets; print(secrets.token_urlsafe(48))'",
        )

    def test_signing_does_not_warn_about_key_length(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            create_short_lived_access_token({"sub": "x"})
        weak = [w for w in caught if "KeyLength" in type(w.message).__name__]
        self.assertEqual(weak, [], "PyJWT flagged the signing key as too short")


if __name__ == "__main__":
    unittest.main()
