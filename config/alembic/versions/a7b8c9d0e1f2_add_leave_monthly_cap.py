"""Add the monthly leave cap and its paid/unpaid day split.

Days beyond ``leave_types.max_days_per_month`` inside one calendar month stay
granted but cost no annual allowance. ``leave_request_days.day_cost`` keeps its
original meaning (how much leave was taken); ``paid_cost``/``unpaid_cost`` is a
derived split that ``services.leave_monthly_policy`` recomputes.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-02 10:00:00.000000
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


def upgrade():
    if not _has_column("leave_types", "max_days_per_month"):
        op.add_column(
            "leave_types",
            sa.Column("max_days_per_month", sa.Float(), nullable=True),
        )
    for column_name in ("paid_cost", "unpaid_cost"):
        if not _has_column("leave_request_days", column_name):
            op.add_column(
                "leave_request_days",
                sa.Column(column_name, sa.Float(), nullable=True),
            )

    # Existing leave predates any cap, so it is entirely paid. This keeps
    # balances identical until an administrator configures a monthly cap.
    op.get_bind().execute(
        sa.text(
            "UPDATE leave_request_days "
            "SET paid_cost = day_cost, unpaid_cost = 0 "
            "WHERE paid_cost IS NULL OR unpaid_cost IS NULL"
        )
    )


def downgrade():
    for column_name in ("unpaid_cost", "paid_cost"):
        if _has_column("leave_request_days", column_name):
            op.drop_column("leave_request_days", column_name)
    if _has_column("leave_types", "max_days_per_month"):
        op.drop_column("leave_types", "max_days_per_month")
