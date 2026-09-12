"""
Create branch_contacts table to store multiple contacts per branch.

Revision ID: add_branch_contact_table
Revises: add_branch_app_fields
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_branch_contact_table"
down_revision = "add_branch_app_fields"
branch_labels = None
depends_on = None


def upgrade():
  op.create_table(
    "branch_contacts",
    sa.Column("id", sa.Integer(), primary_key=True, index=True),
    sa.Column("branch_id", sa.Integer(), nullable=False, index=True),
    sa.Column("label", sa.String(length=100), nullable=True),
    sa.Column("contact_type", sa.String(length=50), nullable=True),
    sa.Column("value", sa.String(length=255), nullable=False),
    sa.Column("sort_order", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
  )


def downgrade():
  op.drop_table("branch_contacts")

