"""Add grade_id and grade_type_id to learning_class_schedules

Revision ID: add_grade_refs_to_schedules
Revises: 
Create Date: 2026-02-09 10:10:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_grade_refs_to_schedules'
down_revision = None  # Update this to your latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Add grade_id and grade_type_id columns to learning_class_schedules
    op.add_column('learning_class_schedules', 
                  sa.Column('grade_id', sa.Integer(), nullable=True))
    op.add_column('learning_class_schedules', 
                  sa.Column('grade_type_id', sa.String(255), nullable=True))
    
    # Optionally backfill existing data
    # This SQL populates the new columns based on existing grade_group_id
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE learning_class_schedules lcs
        LEFT JOIN grade g ON g.group_id = lcs.grade_group_id AND g.academic_id = lcs.academic_id
        SET lcs.grade_id = g.id,
            lcs.grade_type_id = g.grade_type_id
        WHERE g.id IS NOT NULL
    """))


def downgrade():
    # Remove the columns
    op.drop_column('learning_class_schedules', 'grade_type_id')
    op.drop_column('learning_class_schedules', 'grade_id')
