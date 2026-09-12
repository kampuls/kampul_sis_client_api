"""add_partners_table

Revision ID: c7d8e9f0a1b2
Revises: 1891e72a404e
Create Date: 2026-02-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = "1891e72a404e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(length=255), nullable=True),
        sa.Column("icon_name", sa.String(length=100), nullable=True),
        sa.Column("website_url", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=120), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_partners_id"),
        "partners",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partners_branch_id"),
        "partners",
        ["branch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_partners_branch_id"), table_name="partners")
    op.drop_index(op.f("ix_partners_id"), table_name="partners")
    op.drop_table("partners")

