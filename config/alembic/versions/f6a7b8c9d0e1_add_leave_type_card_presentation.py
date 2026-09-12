"""Add leave-type card display order and color.

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-08-03 14:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def upgrade():
    if not _has_column("leave_types", "display_order"):
        op.add_column(
            "leave_types",
            sa.Column("display_order", sa.Integer(), nullable=True),
        )
    if not _has_column("leave_types", "color_hex"):
        op.add_column(
            "leave_types",
            sa.Column("color_hex", sa.String(length=7), nullable=True),
        )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id FROM leave_types "
            "ORDER BY created_at ASC, id ASC"
        )
    ).fetchall()
    preset_colors = (
        "#1877F2",
        "#43A047",
        "#42A5F5",
        "#FFB300",
        "#E91E63",
    )
    for index, row in enumerate(rows, start=1):
        connection.execute(
            sa.text(
                "UPDATE leave_types SET "
                "display_order = COALESCE(display_order, :display_order), "
                "color_hex = COALESCE(color_hex, :color_hex) "
                "WHERE id = :leave_type_id"
            ),
            {
                "display_order": index,
                "color_hex": preset_colors[(index - 1) % len(preset_colors)],
                "leave_type_id": int(row[0]),
            },
        )


def downgrade():
    if _has_column("leave_types", "color_hex"):
        op.drop_column("leave_types", "color_hex")
    if _has_column("leave_types", "display_order"):
        op.drop_column("leave_types", "display_order")
