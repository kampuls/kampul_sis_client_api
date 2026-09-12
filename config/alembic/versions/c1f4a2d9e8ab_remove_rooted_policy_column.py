"""remove rooted policy column from attendance settings

Revision ID: c1f4a2d9e8ab
Revises: f2ddbe00b2f3
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1f4a2d9e8ab"
down_revision = "f2ddbe00b2f3"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if _has_column("attendance_system_settings", "block_rooted_devices"):
        op.drop_column("attendance_system_settings", "block_rooted_devices")


def downgrade() -> None:
    if not _has_column("attendance_system_settings", "block_rooted_devices"):
        op.add_column(
            "attendance_system_settings",
            sa.Column("block_rooted_devices", sa.Boolean(), nullable=True, server_default=sa.text("0")),
        )
