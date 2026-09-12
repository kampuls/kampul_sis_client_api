"""add early leave and makeup session settings

Revision ID: 9d2b7c4a1e66
Revises: c1f4a2d9e8ab
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d2b7c4a1e66"
down_revision = "c1f4a2d9e8ab"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if not _has_column("attendance_system_settings", "allow_early_leave_mins"):
        op.add_column(
            "attendance_system_settings",
            sa.Column(
                "allow_early_leave_mins",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    if not _has_column("attendance_system_settings", "allow_makeup_missing_sessions"):
        op.add_column(
            "attendance_system_settings",
            sa.Column(
                "allow_makeup_missing_sessions",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    if _has_column("attendance_system_settings", "allow_makeup_missing_sessions"):
        op.drop_column("attendance_system_settings", "allow_makeup_missing_sessions")

    if _has_column("attendance_system_settings", "allow_early_leave_mins"):
        op.drop_column("attendance_system_settings", "allow_early_leave_mins")
