"""market_category_i18n

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-06-26 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_categories",
        sa.Column("name_en", sa.String(100), nullable=True),
    )
    op.add_column(
        "market_categories",
        sa.Column("name_km", sa.String(100), nullable=True),
    )
    op.add_column(
        "market_categories",
        sa.Column("icon_key", sa.String(50), nullable=True),
    )
    op.execute(
        """
        UPDATE market_categories
        SET name_en = name,
            name_km = CASE name
                WHEN 'Books' THEN 'សៀវភៅ'
                WHEN 'Uniform' THEN 'ឯកសណ្ឋាន'
                WHEN 'Food' THEN 'អាហារ'
                WHEN 'Electronics' THEN 'គ្រឿងអេឡិចត្រូនិច'
                WHEN 'Other' THEN 'ផ្សេងៗ'
                ELSE name
            END,
            icon_key = CASE LOWER(name)
                WHEN 'books' THEN 'books'
                WHEN 'uniform' THEN 'uniform'
                WHEN 'food' THEN 'food'
                WHEN 'electronics' THEN 'electronics'
                ELSE 'other'
            END
        WHERE name_en IS NULL
        """
    )
    op.alter_column("market_categories", "name_en", nullable=False)
    op.alter_column("market_categories", "name_km", nullable=False)


def downgrade() -> None:
    op.drop_column("market_categories", "icon_key")
    op.drop_column("market_categories", "name_km")
    op.drop_column("market_categories", "name_en")
