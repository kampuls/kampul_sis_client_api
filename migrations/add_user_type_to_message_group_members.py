"""Add user_type to message_group_members

Revision ID: add_user_type_to_members
Revises: 
Create Date: 2026-02-16 12:20:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_type_to_members'
down_revision = 'add_grade_refs_to_schedules'
branch_labels = None
depends_on = None


def upgrade():
    # Add user_type column to message_group_members
    # ENUM values: 'teacher', 'parent', 'student', 'employee'
    op.add_column('message_group_members', 
                  sa.Column('user_type', sa.Enum('teacher', 'parent', 'student', 'employee', name='user_type_enum'), 
                           nullable=True, server_default='teacher'))
    
    # Backfill existing data
    # For now, we'll mark all as 'teacher' by default
    # You may need to run a custom script to properly identify users vs parents
    connection = op.get_bind()
    
    # Mark parents by checking if user_id exists in parents table but not in users
    connection.execute(sa.text("""
        UPDATE message_group_members mgm
        INNER JOIN parents p ON mgm.user_id = p.id
        LEFT JOIN users u ON mgm.user_id = u.id
        SET mgm.user_type = 'parent'
        WHERE u.id IS NULL
    """))
    
    # After backfill, make the column not nullable
    op.alter_column('message_group_members', 'user_type', 
                   existing_type=sa.Enum('teacher', 'parent', 'student', 'employee', name='user_type_enum'),
                   nullable=False,
                   server_default=None)


def downgrade():
    # Remove the column
    op.drop_column('message_group_members', 'user_type')
    # Drop the enum type (MySQL/MariaDB handles this automatically)
