"""extend_market_store_profile

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_stores", sa.Column("tagline", sa.String(200), nullable=True))
    op.add_column("market_stores", sa.Column("contact_email", sa.String(120), nullable=True))
    op.add_column("market_stores", sa.Column("contact_phone", sa.String(50), nullable=True))
    op.add_column("market_stores", sa.Column("contact_telegram", sa.String(100), nullable=True))
    op.add_column("market_stores", sa.Column("address", sa.String(255), nullable=True))
    op.add_column("market_stores", sa.Column("logo_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("market_stores", "logo_url")
    op.drop_column("market_stores", "address")
    op.drop_column("market_stores", "contact_telegram")
    op.drop_column("market_stores", "contact_phone")
    op.drop_column("market_stores", "contact_email")
    op.drop_column("market_stores", "tagline")
