"""Add bilingual title and reason fields to schedule exceptions.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-03 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        column["name"]
        for column in inspector.get_columns("attendance_schedule_exceptions")
    }


def upgrade():
    existing = _columns()
    definitions = (
        ("title_en", sa.String(length=150)),
        ("title_km", sa.String(length=150)),
        ("reason_en", sa.String(length=500)),
        ("reason_km", sa.String(length=500)),
    )
    for name, column_type in definitions:
        if name not in existing:
            op.add_column(
                "attendance_schedule_exceptions",
                sa.Column(name, column_type, nullable=True),
            )

    # Existing overrides remain readable in both languages. This is fallback,
    # not translation: admins can later replace either language independently.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE attendance_schedule_exceptions SET "
            "title_en = COALESCE(title_en, reason), "
            "title_km = COALESCE(title_km, reason), "
            "reason_en = COALESCE(reason_en, reason), "
            "reason_km = COALESCE(reason_km, reason)"
        )
    )


def downgrade():
    existing = _columns()
    for name in ("reason_km", "reason_en", "title_km", "title_en"):
        if name in existing:
            op.drop_column("attendance_schedule_exceptions", name)
