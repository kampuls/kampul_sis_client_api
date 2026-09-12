"""add minimum minutes before checkout setting

Revision ID: b8a7c2d1e4f9
Revises: 9d2b7c4a1e66
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8a7c2d1e4f9"
down_revision = "9d2b7c4a1e66"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if not _has_column("attendance_system_settings", "min_minutes_before_checkout"):
        op.add_column(
            "attendance_system_settings",
            sa.Column(
                "min_minutes_before_checkout",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("30"),
            ),
        )


def downgrade() -> None:
    if _has_column("attendance_system_settings", "min_minutes_before_checkout"):
        op.drop_column("attendance_system_settings", "min_minutes_before_checkout")
