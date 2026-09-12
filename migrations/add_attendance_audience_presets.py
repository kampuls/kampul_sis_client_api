"""Add reusable fixed and dynamic attendance employee groups."""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "attendance_audience_presets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("preset_type", sa.String(length=20), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("is_foreigner", sa.Integer(), nullable=True),
        sa.Column("employee_ids_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "created_by",
            "name",
            name="uq_attendance_audience_preset_owner_name",
        ),
    )
    op.create_index(
        "ix_attendance_audience_presets_preset_type",
        "attendance_audience_presets",
        ["preset_type"],
    )
    op.create_index(
        "ix_attendance_audience_presets_branch_id",
        "attendance_audience_presets",
        ["branch_id"],
    )
    op.create_index(
        "ix_attendance_audience_presets_department_id",
        "attendance_audience_presets",
        ["department_id"],
    )
    op.create_index(
        "ix_attendance_audience_presets_is_foreigner",
        "attendance_audience_presets",
        ["is_foreigner"],
    )
    op.create_index(
        "ix_attendance_audience_presets_created_by",
        "attendance_audience_presets",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attendance_audience_presets_created_by",
        table_name="attendance_audience_presets",
    )
    op.drop_index(
        "ix_attendance_audience_presets_is_foreigner",
        table_name="attendance_audience_presets",
    )
    op.drop_index(
        "ix_attendance_audience_presets_department_id",
        table_name="attendance_audience_presets",
    )
    op.drop_index(
        "ix_attendance_audience_presets_branch_id",
        table_name="attendance_audience_presets",
    )
    op.drop_index(
        "ix_attendance_audience_presets_preset_type",
        table_name="attendance_audience_presets",
    )
    op.drop_table("attendance_audience_presets")
