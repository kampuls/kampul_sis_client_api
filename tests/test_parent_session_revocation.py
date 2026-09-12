"""A parent session must be endable remotely.

Employees have had token_version for a while; parents did not. That mattered
because a token issued before the phone login refused ambiguous numbers may
belong to the wrong family, and nothing about the token reveals that — it was
signed legitimately for whichever account the old code happened to pick. Ending
the session is the only remedy, so it has to be possible.
"""

import unittest
from datetime import date

import bcrypt
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.dependencies import get_current_active_user
from app.models import Parent
from app.models.base import Base
from app.services.utils import create_short_lived_access_token


def _creds(token):
    class _C:
        credentials = token
    return _C()


class _Req:
    headers = {}


class ParentSessionRevocationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[Parent.__table__])
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(
            Parent(
                id=41, uniqueid="p41", username="sok-family",
                password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
                status=1, token_version=1,
                created_at=date.today(), updated_at=date.today(),
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _token(self, version=None):
        data = {"sub": "sok-family", "role": "parent", "user_id": 41}
        if version is not None:
            data["token_version"] = version
        return create_short_lived_access_token(data)

    def test_a_current_token_is_accepted(self):
        user = get_current_active_user(_Req(), _creds(self._token(1)), self.db)
        self.assertEqual(user.id, 41)

    def test_bumping_the_version_ends_the_session(self):
        token = self._token(1)
        self.db.query(Parent).filter(Parent.id == 41).update({"token_version": 2})
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            get_current_active_user(_Req(), _creds(token), self.db)
        self.assertEqual(raised.exception.status_code, 401)

    def test_a_pre_existing_token_without_the_claim_still_works(self):
        """Adding the column must not sign every parent out at once."""
        user = get_current_active_user(_Req(), _creds(self._token(None)), self.db)
        self.assertEqual(user.id, 41)

    def test_but_an_old_claimless_token_dies_once_revoked(self):
        """Otherwise a stale session would survive the very revocation aimed at it."""
        token = self._token(None)
        self.db.query(Parent).filter(Parent.id == 41).update({"token_version": 2})
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            get_current_active_user(_Req(), _creds(token), self.db)
        self.assertEqual(raised.exception.status_code, 401)

    def test_one_parents_revocation_does_not_affect_another(self):
        self.db.add(
            Parent(
                id=42, uniqueid="p42", username="other-family",
                password=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode(),
                status=1, token_version=1,
                created_at=date.today(), updated_at=date.today(),
            )
        )
        self.db.commit()
        other = create_short_lived_access_token(
            {"sub": "other-family", "role": "parent", "user_id": 42, "token_version": 1}
        )
        self.db.query(Parent).filter(Parent.id == 41).update({"token_version": 2})
        self.db.commit()
        user = get_current_active_user(_Req(), _creds(other), self.db)
        self.assertEqual(user.id, 42)


if __name__ == "__main__":
    unittest.main()
