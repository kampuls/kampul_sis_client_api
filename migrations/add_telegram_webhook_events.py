"""Add cross-worker idempotency claims for Telegram webhook processing."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "telegram_webhook_events",
        sa.Column("event_key", sa.String(length=255), primary_key=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.String(length=100), nullable=True),
        sa.Column("telegram_user_id", sa.String(length=100), nullable=True),
        sa.Column("claim_token", sa.String(length=32), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_twe_processed_at",
        "telegram_webhook_events",
        ["processed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_twe_processed_at", table_name="telegram_webhook_events")
    op.drop_table("telegram_webhook_events")
