"""Comprehensive baseline migration - all tables in logical order

Revision ID: 0001_baseline
Revises:
Create Date: 2026-01-04 00:00:00.000000

This migration creates ALL database tables in the correct dependency order.
Consolidates all previous migrations into a single, clean baseline.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    BASELINE MIGRATION - No tables created here.
    Tables are created by application startup in main.py run_database_migrations().
    This migration serves as a reference point for schema versioning.
    """
    pass


def downgrade():
    """
    BASELINE MIGRATION - No tables dropped here.
    Tables are managed by application startup, not migrations.
    """
    pass
    op.create_table('notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_type', sa.String(50), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('data', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_deletable', sa.Boolean(), nullable=True, default=True),
        sa.Column('redirect_route', sa.String(100), nullable=True),
        sa.Column('redirect_args', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_notifications_user', 'user_id', 'user_type'),
        sa.Index('idx_notifications_read', 'is_read')
    )

    # ==========================================
    # 3. ATTENDANCE SYSTEM TABLES
    # ==========================================

    # Attendance system settings
    op.create_table('attendance_system_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('require_location', sa.Boolean(), nullable=True, default=True),
        sa.Column('block_mock_location', sa.Boolean(), nullable=True, default=True),
        sa.Column('block_developer_options', sa.Boolean(), nullable=True, default=False),
        sa.Column('block_rooted_devices', sa.Boolean(), nullable=True, default=False),
        sa.Column('allowed_ip_ranges', sa.Text(), nullable=True),
        sa.Column('allow_early_clock_in_mins', sa.Integer(), nullable=True),
        sa.Column('allow_late_clock_out_mins', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Work locations
    op.create_table('work_locations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('latitude', sa.Float(precision=10, scale=8), nullable=False),
        sa.Column('longitude', sa.Float(precision=11, scale=8), nullable=False),
        sa.Column('radius_meters', sa.Float(), nullable=True, default=100.0),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], name='fk_work_locations_branch'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_work_locations_created_by'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_work_locations_updated_by'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_work_locations_branch', 'branch_id'),
        sa.Index('idx_work_locations_active', 'is_active')
    )

    # Attendance records
    op.create_table('attendance_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('check_in_time', sa.DateTime(), nullable=True),
        sa.Column('check_out_time', sa.DateTime(), nullable=True),
        sa.Column('check_in_latitude', sa.Float(precision=10, scale=8), nullable=True),
        sa.Column('check_in_longitude', sa.Float(precision=11, scale=8), nullable=True),
        sa.Column('check_out_latitude', sa.Float(precision=10, scale=8), nullable=True),
        sa.Column('check_out_longitude', sa.Float(precision=11, scale=8), nullable=True),
        sa.Column('check_in_location_id', sa.Integer(), nullable=True),
        sa.Column('check_out_location_id', sa.Integer(), nullable=True),
        sa.Column('is_mock_location', sa.Boolean(), nullable=True, default=False),
        sa.Column('device_info', sa.Text(), nullable=True),
        sa.Column('attendance_date', sa.Date(), nullable=False),
        sa.Column('work_hours', sa.Float(), nullable=True),
        sa.Column('status', sa.Enum('present', 'absent', 'half_day', 'late', name='attendance_status'), nullable=True, default='present'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['check_in_location_id'], ['work_locations.id'], name='fk_attendance_records_check_in_location'),
        sa.ForeignKeyConstraint(['check_out_location_id'], ['work_locations.id'], name='fk_attendance_records_check_out_location'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_attendance_records_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_attendance_records_user_date', 'user_id', 'attendance_date'),
        sa.Index('idx_attendance_records_date', 'attendance_date')
    )

    # Daily attendance (legacy)
    op.create_table('daily_attendance',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('grade_id', sa.Integer(), nullable=False),
        sa.Column('grade_type_id', sa.Integer(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attendance_date', sa.Date(), nullable=False),
        sa.Column('academic_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('created_by_type', sa.Enum('teacher', 'parent', 'student', name='user_type'), nullable=False, server_default='teacher'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_attendance_student', 'student_id'),
        sa.Index('idx_attendance_program', 'program_id'),
        sa.Index('idx_attendance_grade', 'grade_id'),
        sa.Index('idx_attendance_grade_type', 'grade_type_id'),
        sa.Index('idx_attendance_shift', 'shift_id'),
        sa.Index('idx_attendance_date', 'attendance_date'),
        sa.Index('ix_daily_attendance_created_by_type', 'created_by_type')
    )

    # ==========================================
    # 4. ADS & NOTIFICATIONS
    # ==========================================

    # Ads table
    op.create_table('ads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('subtitle', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(500), nullable=False),
        sa.Column('image_path', sa.String(500), nullable=True),
        sa.Column('ad_type', sa.String(50), nullable=False, server_default='general'),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('action_data', sa.JSON(), nullable=True),
        sa.Column('button_text', sa.String(100), nullable=True),
        sa.Column('button_color', sa.String(20), nullable=True, server_default='#1976D2'),
        sa.Column('target_audience', sa.String(50), nullable=True, server_default='all'),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('display_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('click_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('view_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('academic_id', sa.Integer(), nullable=True),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_ads_active', 'is_active', 'start_date', 'end_date'),
        sa.Index('idx_ads_order', 'display_order'),
        sa.Index('idx_ads_academic', 'academic_id'),
        sa.Index('idx_ads_branch', 'branch_id')
    )

    # Ad clicks table
    op.create_table('ad_clicks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ad_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_type', sa.String(50), nullable=True),
        sa.Column('clicked_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('device_info', sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(['ad_id'], ['ads.id'], ondelete='CASCADE', name='fk_ad_clicks_ad'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_clicks_ad', 'ad_id'),
        sa.Index('idx_clicks_user', 'user_id')
    )

    # Device tokens
    op.create_table('device_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_type', sa.String(50), nullable=False),
        sa.Column('device_token', sa.String(500), nullable=False),
        sa.Column('device_type', sa.String(50), nullable=True),
        sa.Column('device_name', sa.String(255), nullable=True),
        sa.Column('app_version', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'user_type', 'device_token', name='unique_user_device'),
        sa.Index('idx_tokens_user', 'user_id', 'user_type'),
        sa.Index('idx_tokens_active', 'is_active', 'last_used_at')
    )

    # Parent permission interactions
    op.create_table('parent_permission_interactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('learning_id', sa.Integer(), nullable=False),
        sa.Column('interaction_date', sa.Date(), nullable=False),
        sa.Column('interaction_type', sa.Enum('requested', 'cancelled', name='interaction_type'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_permission_parent_date', 'parent_id', 'interaction_date'),
        sa.Index('ix_permission_student_learning', 'student_id', 'learning_id')
    )

    # ==========================================
    # 5. LEAVE MANAGEMENT
    # ==========================================

    # Leave types
    op.create_table('leave_types',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_days_per_year', sa.Integer(), nullable=True),
        sa.Column('requires_approval', sa.Boolean(), nullable=True, default=True),
        sa.Column('requires_documentation', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_paid', sa.Boolean(), nullable=True, default=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_leave_types_created_by'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_leave_types_updated_by'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_leave_types_name')
    )

    # Leave policies
    op.create_table('leave_policies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('applicable_roles', sa.JSON(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], name='fk_leave_policies_branch'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_leave_policies_created_by'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_leave_policies_department'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_leave_policies_updated_by'),
        sa.PrimaryKeyConstraint('id')
    )

    # Leave balances
    op.create_table('leave_balances',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('leave_type_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('allocated_days', sa.Float(), nullable=True, default=0.0),
        sa.Column('used_days', sa.Float(), nullable=True, default=0.0),
        sa.Column('remaining_days', sa.Float(), nullable=True, default=0.0),
        sa.Column('carried_forward', sa.Float(), nullable=True, default=0.0),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_leave_balances_created_by'),
        sa.ForeignKeyConstraint(['leave_type_id'], ['leave_types.id'], name='fk_leave_balances_leave_type'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_leave_balances_updated_by'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_leave_balances_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'leave_type_id', 'year', name='uq_leave_balances_user_type_year'),
        sa.Index('idx_leave_balances_user_year', 'user_id', 'year'),
        sa.Index('idx_leave_balances_user_type', 'user_id', 'leave_type_id')
    )

    # Leave requests
    op.create_table('leave_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('leave_type_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('total_days', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('contact_details', sa.String(255), nullable=True),
        sa.Column('emergency_contact', sa.String(255), nullable=True),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'cancelled', name='leave_status'), nullable=True, default='pending'),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_notes', sa.Text(), nullable=True),
        sa.Column('rejected_by', sa.Integer(), nullable=True),
        sa.Column('rejected_at', sa.DateTime(), nullable=True),
        sa.Column('rejected_reason', sa.Text(), nullable=True),
        sa.Column('attachment_url', sa.String(500), nullable=True),
        sa.Column('is_half_day', sa.Boolean(), nullable=True, default=False),
        sa.Column('half_day_type', sa.Enum('first_half', 'second_half', name='half_day_type'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name='fk_leave_requests_approved_by'),
        sa.ForeignKeyConstraint(['leave_type_id'], ['leave_types.id'], name='fk_leave_requests_leave_type'),
        sa.ForeignKeyConstraint(['rejected_by'], ['users.id'], name='fk_leave_requests_rejected_by'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_leave_requests_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_leave_requests_user', 'user_id'),
        sa.Index('idx_leave_requests_status', 'status'),
        sa.Index('idx_leave_requests_dates', 'start_date', 'end_date')
    )

    # Leave approvers
    op.create_table('leave_approvers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('leave_request_id', sa.Integer(), nullable=False),
        sa.Column('approver_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='approval_status'), nullable=True, default='pending'),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id'], name='fk_leave_approvers_approver'),
        sa.ForeignKeyConstraint(['leave_request_id'], ['leave_requests.id'], name='fk_leave_approvers_leave_request'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_leave_approvers_request', 'leave_request_id'),
        sa.Index('idx_leave_approvers_approver', 'approver_id')
    )

    # Leave history
    op.create_table('leave_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('leave_request_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Enum('created', 'submitted', 'approved', 'rejected', 'cancelled', 'modified', name='leave_action'), nullable=False),
        sa.Column('performed_by', sa.Integer(), nullable=False),
        sa.Column('old_status', sa.Enum('pending', 'approved', 'rejected', 'cancelled', name='leave_status'), nullable=True),
        sa.Column('new_status', sa.Enum('pending', 'approved', 'rejected', 'cancelled', name='leave_status'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['leave_request_id'], ['leave_requests.id'], name='fk_leave_history_request'),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], name='fk_leave_history_performed_by'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_leave_history_request', 'leave_request_id'),
        sa.Index('idx_leave_history_performed_by', 'performed_by')
    )

    # ==========================================
    # 6. FINANCIAL TABLES
    # ==========================================

    # User financials
    op.create_table('user_financials',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('bank_name', sa.String(100), nullable=True),
        sa.Column('bank_account_number', sa.String(50), nullable=True),
        sa.Column('bank_account_name', sa.String(100), nullable=True),
        sa.Column('nssf_number', sa.String(50), nullable=True),
        sa.Column('nssf_employee_id', sa.String(50), nullable=True),
        sa.Column('spouse_status', sa.Boolean(), nullable=True, default=False),
        sa.Column('dependent_count', sa.Integer(), nullable=True, default=0),
        sa.Column('is_resident', sa.Boolean(), nullable=True, default=True),
        sa.Column('base_salary', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_financials_user'),
        sa.Index('idx_financials_user', 'user_id')
    )

    # Salary history
    op.create_table('salary_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('base_salary', sa.Float(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_salary_history_created_by'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_salary_history_updated_by'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_salary_history_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_salary_history_user_active', 'user_id', 'is_active'),
        sa.Index('idx_salary_history_effective_date', 'effective_date')
    )

    # Salary deductions
    op.create_table('salary_deductions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('fixed_amount', 'hourly_rate', 'percentage', name='deduction_type'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_salary_deductions_created_by'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_salary_deductions_updated_by'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_salary_deductions_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_salary_deductions_user_active', 'user_id', 'is_active')
    )

    # Salary bonuses
    op.create_table('salary_bonuses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('fixed_amount', 'hourly_rate', 'percentage', name='bonus_type'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_salary_bonuses_created_by'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_salary_bonuses_updated_by'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_salary_bonuses_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_salary_bonuses_user_active', 'user_id', 'is_active')
    )

    # Bonus deduction rules
    op.create_table('bonus_deduction_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('calculation_type', sa.String(50), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_rules_type', 'type'),
        sa.Index('idx_rules_calculation', 'calculation_type'),
        sa.Index('idx_rules_active', 'is_active')
    )


def downgrade():
    """
    BASELINE MIGRATION - No tables dropped here.
    Tables are managed by application startup, not migrations.
    """
    pass
    # ==========================================
    # ORIGINAL CODE (now handled by main.py)
    # ==========================================
    op.drop_table('bonus_deduction_rules')
    op.drop_table('salary_bonuses')
    op.drop_table('salary_deductions')
    op.drop_table('salary_history')
    op.drop_table('user_financials')

    # Leave management tables
    op.drop_table('leave_history')
    op.drop_table('leave_approvers')
    op.drop_table('leave_requests')
    op.drop_table('leave_balances')
    op.drop_table('leave_policies')
    op.drop_table('leave_types')

    # Ads & notifications
    op.drop_table('parent_permission_interactions')
    op.drop_table('device_tokens')
    op.drop_table('ad_clicks')
    op.drop_table('ads')

    # Attendance system
    op.drop_table('daily_attendance')
    op.drop_table('attendance_records')
    op.drop_table('work_locations')
    op.drop_table('attendance_system_settings')

    # Core academic tables
    op.drop_table('enrollments')
    op.drop_table('classes')
    op.drop_table('parents')
    op.drop_table('teachers')
    op.drop_table('students')
    op.drop_table('notifications')

    # Users table
    op.drop_table('users')

    # Organizational tables
    op.drop_table('roles')
    op.drop_table('branch')
    op.drop_table('departments')

