"""add session_index to attendance_records

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("attendance_records", "session_index"):
        op.add_column(
            "attendance_records",
            sa.Column("session_index", sa.Integer(), nullable=True),
        )
        op.create_index(
            "idx_attendance_records_session_index",
            "attendance_records",
            ["session_index"],
            unique=False,
        )


def downgrade() -> None:
    if _has_column("attendance_records", "session_index"):
        op.drop_index(
            "idx_attendance_records_session_index",
            table_name="attendance_records",
        )
        op.drop_column("attendance_records", "session_index")
