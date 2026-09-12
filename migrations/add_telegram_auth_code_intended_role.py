"""Store the app-selected role on Telegram authorization codes."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "telegram_bot_auth_codes",
        sa.Column(
            "intended_role",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    op.drop_column("telegram_bot_auth_codes", "intended_role")

