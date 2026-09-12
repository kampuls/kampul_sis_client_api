"""
Add Telegram Attendance Settings table.
Migration for Telegram notification feature.
"""
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    # Create telegram_attendance_settings table
    op.create_table(
        "telegram_attendance_settings",
        sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
        sa.Column("bot_token", sa.String(length=500), nullable=True),
        sa.Column("chat_id", sa.String(length=100), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes for faster lookups
    op.create_index(
        "ix_telegram_attendance_settings_id",
        "telegram_attendance_settings",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_attendance_settings_id")
    op.drop_table("telegram_attendance_settings")
