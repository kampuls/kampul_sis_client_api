"""Add open_at and close_at to branch

Revision ID: e94be061e7e6
Revises: 133187bb8931
Create Date: 2026-02-24 22:45:07.192485

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e94be061e7e6'
down_revision = '133187bb8931'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('branch', sa.Column('open_at', sa.String(length=50), nullable=True))
    op.add_column('branch', sa.Column('close_at', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('branch', 'close_at')
    op.drop_column('branch', 'open_at')
