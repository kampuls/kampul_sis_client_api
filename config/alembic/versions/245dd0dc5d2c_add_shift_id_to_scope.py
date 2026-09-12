"""add_shift_id_to_scope

Revision ID: 245dd0dc5d2c
Revises: 56ed9bc1ae9f
Create Date: 2026-02-12 23:35:48.661403

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '245dd0dc5d2c'
down_revision = '56ed9bc1ae9f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('learning_time_slot_scopes', sa.Column('shift_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('learning_time_slot_scopes', 'shift_id')
