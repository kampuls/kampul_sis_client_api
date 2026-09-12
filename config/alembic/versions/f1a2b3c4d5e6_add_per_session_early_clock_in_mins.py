"""add per_session_early_clock_in_mins to attendance_system_settings

Revision ID: f1a2b3c4d5e6
Revises: d4e8f0a1b2c3
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "d4e8f0a1b2c3"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("attendance_system_settings", "per_session_early_clock_in_mins"):
        op.add_column(
            "attendance_system_settings",
            sa.Column("per_session_early_clock_in_mins", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("attendance_system_settings", "per_session_early_clock_in_mins"):
        op.drop_column("attendance_system_settings", "per_session_early_clock_in_mins")
