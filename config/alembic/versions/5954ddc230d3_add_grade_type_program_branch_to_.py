"""add_grade_type_program_branch_to_message_groups

Revision ID: 5954ddc230d3
Revises: 245dd0dc5d2c
Create Date: 2026-02-16 02:51:58.154904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5954ddc230d3'
down_revision = '245dd0dc5d2c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to message_groups table
    op.add_column('message_groups', sa.Column('grade_type_id', sa.Integer(), nullable=True))
    op.add_column('message_groups', sa.Column('program_id', sa.Integer(), nullable=True))
    op.add_column('message_groups', sa.Column('branch_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('message_groups', 'branch_id')
    op.drop_column('message_groups', 'program_id')
    op.drop_column('message_groups', 'grade_type_id')
