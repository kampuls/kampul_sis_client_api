"""Add a per-chat toggle for Telegram new-member verification."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "telegram_tracked_chats",
        sa.Column(
            "member_verification_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "telegram_tracked_chats",
        "member_verification_enabled",
    )
