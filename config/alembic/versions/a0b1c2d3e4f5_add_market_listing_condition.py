"""add_market_listing_condition

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-06-26 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_listings",
        sa.Column("condition", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("market_listings", "condition")
