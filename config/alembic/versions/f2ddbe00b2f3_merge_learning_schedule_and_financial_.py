"""Merge learning schedule and financial branches

Revision ID: f2ddbe00b2f3
Revises: d805abd1c36c, f5eee8d4229b
Create Date: 2026-02-07 01:26:38.263506

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2ddbe00b2f3'
down_revision = ('d805abd1c36c', 'f5eee8d4229b')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
