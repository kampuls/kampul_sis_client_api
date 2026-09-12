"""add_grade_id_and_grade_type_id_to_schedules

Revision ID: 56ed9bc1ae9f
Revises: 6bbc53eaeedd
Create Date: 2026-02-09 11:12:01.328922

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '56ed9bc1ae9f'
down_revision = '6bbc53eaeedd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add grade_id and grade_type_id columns to learning_class_schedules
    op.add_column('learning_class_schedules', 
        sa.Column('grade_id', sa.Integer(), nullable=True, comment='Reference to specific grade'))
    op.add_column('learning_class_schedules', 
        sa.Column('grade_type_id', sa.Integer(), nullable=True, comment='Specific single grade type ID for this schedule'))


def downgrade() -> None:
    # Remove the columns if rolling back
    op.drop_column('learning_class_schedules', 'grade_type_id')
    op.drop_column('learning_class_schedules', 'grade_id')

