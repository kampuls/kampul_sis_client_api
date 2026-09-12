"""Add per-chat Telegram moderation policies and audit events."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "telegram_chat_moderation_settings",
        sa.Column("chat_id", sa.String(length=100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("file_policy", sa.String(length=20), nullable=False),
        sa.Column("blocked_extensions", sa.Text(), nullable=False),
        sa.Column("allowed_extensions", sa.Text(), nullable=False),
        sa.Column("link_policy", sa.String(length=20), nullable=False),
        sa.Column("allowed_domains", sa.Text(), nullable=False),
        sa.Column("exempt_admins", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("send_warning", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "telegram_moderation_events",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("chat_id", sa.String(length=100), nullable=False, index=True),
        sa.Column("message_id", sa.String(length=100), nullable=True),
        sa.Column("telegram_user_id", sa.String(length=100), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("telegram_moderation_events")
    op.drop_table("telegram_chat_moderation_settings")

