"""fix device notification preference defaults

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
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


def _default_is_enabled(value) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "b'1'"}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    defaults = {
        str(column["name"]): column.get("default")
        for column in inspector.get_columns("device_tokens")
        if column["name"] in _COLUMNS
    }
    original_columns = [column for column in _COLUMNS if column in defaults]
    broken_defaults = [
        column for column in original_columns if not _default_is_enabled(defaults[column])
    ]

    if original_columns and broken_defaults:
        all_off = " AND ".join(
            f"COALESCE(`{column}`, 0) = 0" for column in original_columns
        )
        set_enabled = ", ".join(f"`{column}` = 1" for column in original_columns)
        bind.execute(sa.text(
            f"UPDATE device_tokens SET {set_enabled} WHERE {all_off}"
        ))

    for column in _COLUMNS:
        if column not in defaults:
            op.add_column(
                "device_tokens",
                sa.Column(
                    column,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )
        else:
            op.alter_column(
                "device_tokens",
                column,
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "device_tokens",
            column,
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=None,
        )
