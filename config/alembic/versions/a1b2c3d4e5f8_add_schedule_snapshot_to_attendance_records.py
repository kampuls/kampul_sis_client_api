"""add schedule snapshot to attendance_records

Revision ID: a1b2c3d4e5f8
Revises: a1b2c3d4e5f7
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_index(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index in {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    columns = [
        ("schedule_id", sa.Integer()),
        ("scheduled_start", sa.String(length=8)),
        ("scheduled_end", sa.String(length=8)),
        ("snapshot_late_grace_minutes", sa.Integer()),
        ("snapshot_allow_early_leave_mins", sa.Integer()),
    ]
    for name, col_type in columns:
        if not _has_column("attendance_records", name):
            op.add_column(
                "attendance_records",
                sa.Column(name, col_type, nullable=True),
            )

    if (
        _has_column("attendance_records", "schedule_id")
        and not _has_index("attendance_records", "idx_attendance_records_schedule_id")
    ):
        op.create_index(
            "idx_attendance_records_schedule_id",
            "attendance_records",
            ["schedule_id"],
            unique=False,
        )


def downgrade() -> None:
    if _has_index("attendance_records", "idx_attendance_records_schedule_id"):
        op.drop_index(
            "idx_attendance_records_schedule_id",
            table_name="attendance_records",
        )

    for name in [
        "snapshot_allow_early_leave_mins",
        "snapshot_late_grace_minutes",
        "scheduled_end",
        "scheduled_start",
        "schedule_id",
    ]:
        if _has_column("attendance_records", name):
            op.drop_column("attendance_records", name)
