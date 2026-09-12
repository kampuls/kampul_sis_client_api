"""Add optional workplace-specific Telegram notification destinations."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "telegram_attendance_settings",
        sa.Column(
            "branch_routing_mode",
            sa.String(length=20),
            nullable=True,
            server_default="all",
        ),
    )
    op.create_table(
        "telegram_branch_notification_routes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "settings_id",
            sa.Integer(),
            sa.ForeignKey("telegram_attendance_settings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("attendance_chat_id", sa.String(length=100), nullable=True),
        sa.Column("leave_chat_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "settings_id",
            "branch_id",
            name="uq_telegram_branch_notification_route",
        ),
    )
    op.create_index(
        "ix_telegram_branch_notification_routes_settings_id",
        "telegram_branch_notification_routes",
        ["settings_id"],
    )
    op.create_index(
        "ix_telegram_branch_notification_routes_branch_id",
        "telegram_branch_notification_routes",
        ["branch_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_branch_notification_routes_branch_id",
        table_name="telegram_branch_notification_routes",
    )
    op.drop_index(
        "ix_telegram_branch_notification_routes_settings_id",
        table_name="telegram_branch_notification_routes",
    )
    op.drop_table("telegram_branch_notification_routes")
    op.drop_column("telegram_attendance_settings", "branch_routing_mode")
