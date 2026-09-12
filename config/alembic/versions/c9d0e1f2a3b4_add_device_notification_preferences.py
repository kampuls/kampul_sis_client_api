"""add device notification preferences

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


_COLUMNS = (
    "notifications_enabled",
    "attendance_notifications_enabled",
    "leave_notifications_enabled",
    "message_notifications_enabled",
    "announcement_notifications_enabled",
    "market_notifications_enabled",
    "other_notifications_enabled",
)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return column_name in {
        column["name"] for column in sa.inspect(bind).get_columns(table_name)
    }


def upgrade() -> None:
    for column_name in _COLUMNS:
        if not _has_column("device_tokens", column_name):
            op.add_column(
                "device_tokens",
                sa.Column(
                    column_name,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )


def downgrade() -> None:
    for column_name in reversed(_COLUMNS):
        if _has_column("device_tokens", column_name):
            op.drop_column("device_tokens", column_name)
