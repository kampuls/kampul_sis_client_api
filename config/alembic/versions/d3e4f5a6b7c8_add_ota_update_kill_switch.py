"""Add the remote Shorebird OTA update kill switch.

Revision ID: d3e4f5a6b7c8
Revises: current migration heads
"""

from alembic import op
import sqlalchemy as sa


revision = "d3e4f5a6b7c8"
down_revision = (
    "0001_initial_migration",
    "a9c1d2e3f4b5",
    "add_enable_schedule_reminders",
    "b2c3d4e5f6a7",
    "c2d3e4f5a6b7",
)
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "settings",
        sa.Column(
            "ota_updates_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade():
    op.drop_column("settings", "ota_updates_enabled")
