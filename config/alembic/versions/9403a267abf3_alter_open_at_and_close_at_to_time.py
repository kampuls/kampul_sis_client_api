"""Alter open_at and close_at to TIME

Revision ID: 9403a267abf3
Revises: e94be061e7e6
Create Date: 2026-02-24 22:49:40.499001

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9403a267abf3'
down_revision = 'e94be061e7e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('branch', 'open_at', type_=sa.Time(), existing_type=sa.String(length=50))
    op.alter_column('branch', 'close_at', type_=sa.Time(), existing_type=sa.String(length=50))


def downgrade() -> None:
    op.alter_column('branch', 'close_at', type_=sa.String(length=50), existing_type=sa.Time())
    op.alter_column('branch', 'open_at', type_=sa.String(length=50), existing_type=sa.Time())
