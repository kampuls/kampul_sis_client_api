"""add feature_locks table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create feature_locks table
    op.create_table(
        'feature_locks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feature_id', sa.String(100), nullable=False, unique=True),
        sa.Column('feature_name', sa.String(200), nullable=False),
        sa.Column('is_locked', sa.Boolean(), default=False, nullable=False),
        sa.Column('locked_by', sa.Integer(), nullable=True),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True),
        sa.ForeignKeyConstraint(['locked_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_feature_locks_feature_id', 'feature_id'),
        sa.Index('ix_feature_locks_is_locked', 'is_locked'),
    )
    
    # Insert default features
    default_features = [
        ('company_settings', 'Company Settings'),
        ('manage_branches', 'Manage Branches'),
        ('school_overview', 'School Overview'),
        ('app_branding', 'App Branding'),
        ('manage_top_students', 'Students of the Month'),
        ('users_management', 'Users Management'),
        ('roles_permissions', 'Roles & Permissions'),
        ('news_updates', 'News & Updates'),
        ('academic_programs', 'Academic Programs'),
        ('school_events', 'School Events'),
        ('hot_events', 'Hot Events'),
        ('partners', 'Partners'),
        ('manage_forms', 'Dynamic Forms'),
        ('school_documents', 'School Documents'),
        ('manage_news', 'Manage News'),
        ('manage_link_requests', 'Link Requests'),
        ('splash_ads', 'Splash Ads'),
        ('manage_ads', 'Manage Ads'),
        ('attendance_dashboard', 'Attendance Dashboard'),
        ('attendance_security', 'Attendance Security'),
        ('hr_management', 'HR Management'),
        ('payroll_dashboard', 'Payroll Dashboard'),
        ('leave_management', 'Leave Management'),
        ('department_management', 'Department Management'),
        ('schedule_management', 'Schedule Management'),
        ('live_class', 'Live Class'),
        ('admin_pickup', 'Admin Pickup'),
        ('company_settings_menu', 'Company Settings'),
        ('price_visibility', 'Price Visibility'),
    ]
    
    # Insert default features (all unlocked)
    op.bulk_insert(
        sa.table('feature_locks',
            sa.column('feature_id', sa.String),
            sa.column('feature_name', sa.String),
            sa.column('is_locked', sa.Boolean),
            sa.column('created_at', sa.DateTime),
        ),
        [
            {'feature_id': fid, 'feature_name': fname, 'is_locked': False, 'created_at': datetime.utcnow()}
            for fid, fname in default_features
        ]
    )


def downgrade() -> None:
    op.drop_table('feature_locks')
