"""Add configurable automatic replies for Telegram General Groups."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "telegram_group_reply_settings",
        sa.Column("chat_id", sa.String(length=100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("features", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("telegram_group_reply_settings")
