"""add_market_tables

Revision ID: e8f9a0b1c2d3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e8f9a0b1c2d3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "market_stores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_user_id", sa.Integer(), nullable=False),
        sa.Column("seller_user_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("seller_user_id", "seller_user_type", name="uq_market_store_seller"),
    )
    op.create_index("ix_market_stores_seller_user_id", "market_stores", ["seller_user_id"])
    op.create_table(
        "market_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("market_stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("market_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(10), server_default="USD", nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_market_listings_status_created", "market_listings", ["status", "created_at"])
    op.create_table(
        "market_listing_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("market_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "market_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("market_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("market_stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), nullable=False),
        sa.Column("buyer_user_type", sa.String(20), nullable=False),
        sa.Column("seller_user_id", sa.Integer(), nullable=False),
        sa.Column("seller_user_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("buyer_note", sa.Text(), nullable=True),
        sa.Column("seller_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_market_orders_buyer", "market_orders", ["buyer_user_id", "buyer_user_type"])
    op.create_index("ix_market_orders_seller", "market_orders", ["seller_user_id", "seller_user_type"])
    op.create_table(
        "market_seller_bans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_type", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("market_seller_bans")
    op.drop_table("market_orders")
    op.drop_table("market_listing_images")
    op.drop_table("market_listings")
    op.drop_table("market_stores")
    op.drop_table("market_categories")
