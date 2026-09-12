import asyncio
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.auth import (
    _normalize_to_e164,
    _store_telegram_otp_session,
    _telegram_otp_error,
    _verify_firebase_registration_phone,
)
from app.api.v1 import auth
from app.core.migrations import _migrate_telegram_otp_security
from app.models import Parent, User
from app.schemas import UserCreate
from app.schemas.parents import ParentCreate
from app.services import telegram_otp_security


CREATE_SECURE_TABLE = """
CREATE TABLE telegram_otp_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone VARCHAR(50) NOT NULL UNIQUE,
    phone_code_hash VARCHAR(255) NOT NULL,
    session_string TEXT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    registration_token_hash VARCHAR(64) NULL,
    registration_expires_at DATETIME NULL,
    registration_used_at DATETIME NULL
)
"""


class TelegramOtpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.db = sessionmaker(bind=self.engine)()
        self.db.execute(text(CREATE_SECURE_TABLE))
        self.db.commit()
        telegram_otp_security.reset_throttle_for_tests()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        telegram_otp_security.reset_throttle_for_tests()

    def _verified_session(self, phone="+855961234567") -> int:
        result = self.db.execute(
            text(
                """
                INSERT INTO telegram_otp_sessions (
                    phone, phone_code_hash, session_string, expires_at, used_at
                ) VALUES (
                    :phone, 'hash', NULL, :expires_at, :used_at
                )
                """
            ),
            {
                "phone": phone,
                "expires_at": datetime.utcnow() + timedelta(minutes=5),
                "used_at": datetime.utcnow(),
            },
        )
        self.db.commit()
        return int(result.lastrowid)

    def test_registration_proof_is_hashed_short_lived_and_single_use(self):
        session_id = self._verified_session()
        token = telegram_otp_security.issue_registration_proof(
            self.db,
            session_id=session_id,
        )
        self.db.commit()

        stored = self.db.execute(
            text(
                """
                SELECT registration_token_hash, registration_expires_at
                FROM telegram_otp_sessions
                WHERE id = :id
                """
            ),
            {"id": session_id},
        ).one()
        self.assertNotEqual(stored.registration_token_hash, token)
        self.assertEqual(len(stored.registration_token_hash), 64)
        self.assertIsNotNone(stored.registration_expires_at)

        self.assertTrue(
            telegram_otp_security.claim_registration_proof(
                self.db,
                phone="+855961234567",
                token=token,
            )
        )
        self.assertFalse(
            telegram_otp_security.claim_registration_proof(
                self.db,
                phone="+855961234567",
                token=token,
            )
        )

    def test_registration_claim_rolls_back_with_failed_account_transaction(self):
        session_id = self._verified_session()
        token = telegram_otp_security.issue_registration_proof(
            self.db,
            session_id=session_id,
        )
        self.db.commit()

        self.assertTrue(
            telegram_otp_security.claim_registration_proof(
                self.db,
                phone="+855961234567",
                token=token,
            )
        )
        self.db.rollback()
        self.assertTrue(
            telegram_otp_security.claim_registration_proof(
                self.db,
                phone="+855961234567",
                token=token,
            )
        )

    def test_resend_replaces_session_and_invalidates_old_registration_proof(self):
        session_id = self._verified_session()
        telegram_otp_security.issue_registration_proof(
            self.db,
            session_id=session_id,
        )
        self.db.commit()

        _store_telegram_otp_session(
            self.db,
            phone="+855961234567",
            phone_code_hash="new-hash",
            session_string="new-session",
        )
        rows = self.db.execute(
            text(
                """
                SELECT phone_code_hash, session_string, used_at,
                       registration_token_hash
                FROM telegram_otp_sessions
                WHERE phone = '+855961234567'
                """
            )
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].phone_code_hash, "new-hash")
        self.assertEqual(rows[0].session_string, "new-session")
        self.assertIsNone(rows[0].used_at)
        self.assertIsNone(rows[0].registration_token_hash)

    def test_phone_normalization_rejects_invalid_input(self):
        self.assertEqual(_normalize_to_e164("096 123 4567"), "+855961234567")
        self.assertEqual(_normalize_to_e164("+855 96 123 4567"), "+855961234567")
        with self.assertRaises(ValueError):
            _normalize_to_e164("+0")
        with self.assertRaises(ValueError):
            _normalize_to_e164("not-a-phone")

    def test_error_payload_marks_sms_fallback_and_retry_after(self):
        with self.assertRaises(HTTPException) as raised:
            _telegram_otp_error(
                503,
                "telegram_unreachable",
                fallback_to_sms=True,
                retry_after=45,
            )
        self.assertEqual(
            raised.exception.detail,
            {
                "code": "telegram_unreachable",
                "fallback_to_sms": True,
                "retry_after_seconds": 45,
            },
        )
        self.assertEqual(raised.exception.headers, {"Retry-After": "45"})

    def test_send_throttle_limits_phone_even_when_ip_changes(self):
        with (
            patch.object(telegram_otp_security, "_redis", return_value=None),
            patch.object(telegram_otp_security.settings, "telegram_otp_max_sends_per_phone", 2),
            patch.object(telegram_otp_security.settings, "telegram_otp_max_sends_per_ip", 10),
            patch.object(telegram_otp_security.settings, "telegram_otp_window_seconds", 900),
        ):
            self.assertTrue(telegram_otp_security.allow_send("+855961234567", "1.1.1.1"))
            self.assertTrue(telegram_otp_security.allow_send("+855961234567", "2.2.2.2"))
            self.assertFalse(telegram_otp_security.allow_send("+855961234567", "3.3.3.3"))

    def test_firebase_registration_token_uses_configured_project_and_exact_phone(self):
        with (
            patch.object(auth, "GOOGLE_AUTH_AVAILABLE", True),
            patch.object(auth.settings, "firebase_project_id", "multischool-pro"),
            patch.object(
                auth.google_id_token,
                "verify_firebase_token",
                return_value={"phone_number": "+855961234567"},
            ) as verify,
        ):
            asyncio.run(
                _verify_firebase_registration_phone(
                    "firebase-token",
                    "096 123 4567",
                )
            )
            self.assertEqual(verify.call_args.args[0], "firebase-token")
            self.assertEqual(verify.call_args.args[2], "multischool-pro")

            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    _verify_firebase_registration_phone(
                        "firebase-token",
                        "097 123 4567",
                    )
                )
            self.assertEqual(raised.exception.status_code, 403)

    def test_firebase_registration_fails_closed_when_not_configured(self):
        with patch.object(auth, "GOOGLE_AUTH_AVAILABLE", False):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    _verify_firebase_registration_phone(
                        "firebase-token",
                        "0961234567",
                    )
                )
        self.assertEqual(raised.exception.status_code, 503)


class TelegramOtpMigrationTests(unittest.TestCase):
    def test_legacy_duplicates_are_deduplicated_before_unique_index(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE telegram_otp_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone VARCHAR(50) NOT NULL,
                        phone_code_hash VARCHAR(255) NOT NULL,
                        session_string TEXT NULL,
                        expires_at DATETIME NOT NULL,
                        used_at DATETIME NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            for code_hash in ("old", "new"):
                connection.execute(
                    text(
                        """
                        INSERT INTO telegram_otp_sessions
                            (phone, phone_code_hash, expires_at)
                        VALUES ('+855961234567', :hash, :expires_at)
                        """
                    ),
                    {
                        "hash": code_hash,
                        "expires_at": datetime.utcnow() + timedelta(minutes=5),
                    },
                )
            connection.commit()

            _migrate_telegram_otp_security(connection)

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("telegram_otp_sessions")
            }
            self.assertIn("registration_token_hash", columns)
            self.assertIn("registration_expires_at", columns)
            self.assertIn("registration_used_at", columns)
            remaining = connection.execute(
                text("SELECT id, phone_code_hash FROM telegram_otp_sessions")
            ).all()
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].phone_code_hash, "new")
            unique_indexes = [
                item
                for item in inspect(connection).get_indexes("telegram_otp_sessions")
                if item.get("unique")
            ]
            self.assertTrue(
                any(item.get("column_names") == ["phone"] for item in unique_indexes)
            )
        engine.dispose()


class TelegramOtpRegistrationCompletionTests(unittest.TestCase):
    """Exercise the final form submission after a successful Telegram OTP."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        User.__table__.create(self.engine)
        Parent.__table__.create(self.engine)
        with self.engine.begin() as connection:
            connection.execute(text(CREATE_SECURE_TABLE))
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _registration_token(self, phone: str) -> str:
        result = self.db.execute(
            text(
                """
                INSERT INTO telegram_otp_sessions (
                    phone, phone_code_hash, session_string, expires_at, used_at
                ) VALUES (
                    :phone, 'verified-hash', NULL, :expires_at, :used_at
                )
                """
            ),
            {
                "phone": phone,
                "expires_at": datetime.utcnow() + timedelta(minutes=5),
                "used_at": datetime.utcnow(),
            },
        )
        self.db.commit()
        token = telegram_otp_security.issue_registration_proof(
            self.db,
            session_id=int(result.lastrowid),
        )
        self.db.commit()
        return token

    def test_staff_final_form_creates_pending_account_and_consumes_proof(self):
        phone = "+855961234567"
        token = self._registration_token(phone)
        payload = UserCreate(
            username="otp_staff_success",
            password="Strong!Pass123",
            kName="បុគ្គលិកសាកល្បង",
            eName="OTP Staff Test",
            height=170,
            gender="male",
            dob=date(1990, 1, 1),
            nationality="Cambodian",
            religion="None",
            province="Phnom Penh",
            district="Test District",
            commune="Test Commune",
            education="Bachelor",
            workplace=1,
            status=1,
            role=1,
            isForeigner=1,
            phone=phone,
        )

        response = asyncio.run(
            auth.register(
                user=payload,
                background_tasks=BackgroundTasks(),
                db=self.db,
                authorization=f"Bearer {token}",
            )
        )

        saved = self.db.query(User).filter(User.username == payload.username).one()
        self.assertEqual(saved.phone, phone)
        self.assertEqual(saved.role, 2)
        self.assertEqual(saved.status, 2)
        self.assertTrue(response.access_token)
        self.assertTrue(response.pending_approval)
        used_at = self.db.execute(
            text(
                "SELECT registration_used_at FROM telegram_otp_sessions "
                "WHERE phone = :phone"
            ),
            {"phone": phone},
        ).scalar_one()
        self.assertIsNotNone(used_at)

    def test_parent_final_form_creates_pending_account_and_consumes_proof(self):
        phone = "+855971234567"
        token = self._registration_token(phone)
        payload = ParentCreate(
            fatherName="OTP Parent Test",
            fatherPhone=phone,
            parentRole="father",
        )

        response = asyncio.run(
            auth.register_parent(
                parent_data=payload,
                background_tasks=BackgroundTasks(),
                db=self.db,
                authorization=f"Bearer {token}",
            )
        )

        saved = self.db.query(Parent).filter(Parent.id == response.parent_id).one()
        self.assertEqual(saved.fatherPhone, phone)
        self.assertEqual(saved.status, 0)
        self.assertTrue(response.access_token)
        self.assertTrue(response.username)
        self.assertTrue(response.password)
        self.assertTrue(response.pending_approval)
        used_at = self.db.execute(
            text(
                "SELECT registration_used_at FROM telegram_otp_sessions "
                "WHERE phone = :phone"
            ),
            {"phone": phone},
        ).scalar_one()
        self.assertIsNotNone(used_at)


if __name__ == "__main__":
    unittest.main()
