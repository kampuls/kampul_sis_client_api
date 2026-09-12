"""Add employee self-enrollment for attendance schedule exceptions.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-03 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if not _has_column(
        "attendance_schedule_exceptions",
        "self_enrollment_enabled",
    ):
        op.add_column(
            "attendance_schedule_exceptions",
            sa.Column(
                "self_enrollment_enabled",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if not _has_table("attendance_schedule_exception_enrollments"):
        op.create_table(
            "attendance_schedule_exception_enrollments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("exception_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("occurrence_date", sa.Date(), nullable=False),
            sa.Column(
                "enrolled_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "user_id",
                "occurrence_date",
                name="uq_attendance_exception_enrollment_user_date",
            ),
        )
        op.create_index(
            "idx_attendance_exception_enrollment_exception",
            "attendance_schedule_exception_enrollments",
            ["exception_id"],
        )
        op.create_index(
            "idx_attendance_exception_enrollment_date",
            "attendance_schedule_exception_enrollments",
            ["occurrence_date"],
        )


def downgrade():
    if _has_table("attendance_schedule_exception_enrollments"):
        op.drop_table("attendance_schedule_exception_enrollments")
    if _has_column(
        "attendance_schedule_exceptions",
        "self_enrollment_enabled",
    ):
        op.drop_column(
            "attendance_schedule_exceptions",
            "self_enrollment_enabled",
        )
