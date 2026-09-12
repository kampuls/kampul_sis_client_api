"""Add attendance participation rules (enabled by default when no rule exists)."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "attendance_processing_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "scope_type", "scope_id", name="uq_attendance_processing_scope"
        ),
    )
    op.create_index(
        "ix_attendance_processing_rules_scope_type",
        "attendance_processing_rules",
        ["scope_type"],
    )
    op.create_index(
        "ix_attendance_processing_rules_scope_id",
        "attendance_processing_rules",
        ["scope_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attendance_processing_rules_scope_id",
        table_name="attendance_processing_rules",
    )
    op.drop_index(
        "ix_attendance_processing_rules_scope_type",
        table_name="attendance_processing_rules",
    )
    op.drop_table("attendance_processing_rules")

