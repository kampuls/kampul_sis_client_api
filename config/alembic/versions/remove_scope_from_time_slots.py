"""remove scope fields from time slots

Revision ID: remove_scope_from_time_slots
Revises: add_grade_group_id_to_time_slots
Create Date: 2026-02-07 14:07:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_scope_from_time_slots'
down_revision = 'add_grade_group_id_to_time_slots'
branch_labels = None
depends_on = None


def upgrade():
    """Remove grade_group_id and grade_id from learning_time_slots to make slots globally reusable."""
    
    # Drop foreign key constraints first (if they exist)
    try:
        op.drop_constraint('fk_learning_time_slots_grade_group_id', 'learning_time_slots', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('fk_learning_time_slots_grade_id', 'learning_time_slots', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    # Drop the columns
    op.drop_column('learning_time_slots', 'grade_group_id')
    op.drop_column('learning_time_slots', 'grade_id')


def downgrade():
    """Restore grade_group_id and grade_id columns."""
    
    # Add columns back
    op.add_column('learning_time_slots', sa.Column('grade_group_id', sa.Integer(), nullable=True))
    op.add_column('learning_time_slots', sa.Column('grade_id', sa.Integer(), nullable=True))
    
    # Restore foreign keys (best effort)
    try:
        op.create_foreign_key(
            'fk_learning_time_slots_grade_group_id',
            'learning_time_slots', 'grade_group',
            ['grade_group_id'], ['id']
        )
    except Exception:
        pass
    
    try:
        op.create_foreign_key(
            'fk_learning_time_slots_grade_id',
            'learning_time_slots', 'grade',
            ['grade_id'], ['id']
        )
    except Exception:
        pass
