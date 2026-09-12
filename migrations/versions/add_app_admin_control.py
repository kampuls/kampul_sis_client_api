"""
Migration: Add App Admin Control system
- Creates app_admins table for Super Admin tracking
- Adds is_locked column to admin features
- Adds app_admin_control_enabled column to settings
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

def upgrade():
    # Create app_admins table for Super Admin tracking
    op.create_table(
        'app_admins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('is_super_admin', sa.Boolean(), default=False, nullable=False),
        sa.Column('is_locked', sa.Boolean(), default=False, nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('locked_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['locked_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index for faster lookups
    op.create_index('ix_app_admins_user_id', 'app_admins', ['user_id'])
    op.create_index('ix_app_admins_is_super_admin', 'app_admins', ['is_super_admin'])
    
    # Add app_admin_control_enabled to settings table
    op.add_column('settings', sa.Column('app_admin_control_enabled', sa.Boolean(), default=True, nullable=True))
    
    # Add is_locked to admin_logs for tracking locked feature attempts
    op.add_column('admin_logs', sa.Column('is_locked_feature', sa.Boolean(), default=False, nullable=True))
    
    # Add lock-related columns to admin_features if it exists, otherwise skip
    try:
        op.add_column('admin_features', sa.Column('is_locked', sa.Boolean(), default=False, nullable=True))
        op.add_column('admin_features', sa.Column('locked_at', sa.DateTime(), nullable=True))
        op.add_column('admin_features', sa.Column('locked_by', sa.Integer(), nullable=True))
    except Exception:
        # Column might already exist
        pass

def downgrade():
    # Remove columns from admin_features
    try:
        op.drop_column('admin_features', 'locked_by')
        op.drop_column('admin_features', 'locked_at')
        op.drop_column('admin_features', 'is_locked')
    except Exception:
        pass
    
    # Remove column from admin_logs
    op.drop_column('admin_logs', 'is_locked_feature')
    
    # Remove column from settings
    op.drop_column('settings', 'app_admin_control_enabled')
    
    # Drop indexes
    op.drop_index('ix_app_admins_is_super_admin', table_name='app_admins')
    op.drop_index('ix_app_admins_user_id', table_name='app_admins')
    
    # Drop table
    op.drop_table('app_admins')
