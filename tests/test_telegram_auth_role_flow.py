import unittest
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.telegram_webhook import (
    _require_telegram_admin,
    ensure_telegram_auth_codes_table,
    generate_bot_auth_code,
)


class TelegramAuthRoleFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def register_now(dbapi_connection, _connection_record):
            dbapi_connection.create_function(
                "NOW",
                0,
                lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    async def test_generated_code_persists_the_app_selected_role(self):
        result = await generate_bot_auth_code(
            intended_role="general",
            db=self.db,
            current_user=object(),
        )

        saved_role = self.db.execute(
            text("""
                SELECT intended_role
                FROM telegram_bot_auth_codes
                WHERE code = :code
            """),
            {"code": result["code"]},
        ).scalar_one()
        self.assertEqual(result["intended_role"], "general")
        self.assertEqual(saved_role, "general")

    async def test_invalid_role_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            await generate_bot_auth_code(
                intended_role="telegram_button",
                db=self.db,
                current_user=object(),
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_quick_role_setup_requires_an_app_administrator(self):
        _require_telegram_admin(SimpleNamespace(role=1))

        with self.assertRaises(HTTPException) as raised:
            _require_telegram_admin(SimpleNamespace(role=2))

        self.assertEqual(raised.exception.status_code, 403)

    def test_legacy_auth_table_gets_intended_role_column(self):
        self.db.execute(text("""
            CREATE TABLE telegram_bot_auth_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(6) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                used_at DATETIME NULL,
                used_for_chat_id VARCHAR(100) NULL
            )
        """))
        self.db.commit()

        ensure_telegram_auth_codes_table(self.db)

        columns = {
            column["name"]
            for column in inspect(self.engine).get_columns(
                "telegram_bot_auth_codes"
            )
        }
        self.assertIn("intended_role", columns)


if __name__ == "__main__":
    unittest.main()
