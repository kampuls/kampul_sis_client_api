"""Add learning schedule tables

Revision ID: d805abd1c36c
Revises: 0008
Create Date: 2026-02-07 01:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'd805abd1c36c'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    """Smart migration that checks existence before creating tables/columns."""
    from alembic import op
    import sqlalchemy as sa
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # ========== learning_time_slots ==========
    if 'learning_time_slots' not in existing_tables:
        print("Creating table: learning_time_slots")
        op.create_table('learning_time_slots',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('slot_name', sa.String(100), nullable=False),
            sa.Column('start_time', sa.Time(), nullable=False),
            sa.Column('end_time', sa.Time(), nullable=False),
            sa.Column('duration_minutes', sa.Integer(), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id')
        )
    else:
        print("Table learning_time_slots already exists, checking columns...")
        # Check and add missing columns if needed
        existing_columns = {col['name'] for col in inspector.get_columns('learning_time_slots')}
        if 'updated_at' not in existing_columns:
            op.add_column('learning_time_slots', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')))

    # ========== learning_class_schedules ==========
    if 'learning_class_schedules' not in existing_tables:
        print("Creating table: learning_class_schedules")
        op.create_table('learning_class_schedules',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('academic_id', sa.Integer(), nullable=False),
            sa.Column('branch_id', sa.Integer(), nullable=False, comment='Links to branch table'),
            sa.Column('program_id', sa.Integer(), nullable=False),
            sa.Column('grade_group_id', sa.Integer(), nullable=False, comment='Links to grade_group table'),
            sa.Column('subject_id', sa.Integer(), nullable=False, comment='Links to subjects table'),
            sa.Column('teacher_id', sa.Integer(), nullable=False, comment='Links to teachers/users table'),
            sa.Column('time_slot_id', sa.Integer(), nullable=False),
            sa.Column('day_of_week', sa.SMALLINT(), nullable=False, comment='1=Monday, 7=Sunday'),
            sa.Column('room_number', sa.String(50), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('updated_by', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.Index('idx_academic', 'academic_id'),
            sa.Index('idx_branch', 'branch_id'),
            sa.Index('idx_grade_group', 'grade_group_id'),
            sa.Index('idx_subject', 'subject_id'),
            sa.Index('idx_teacher', 'teacher_id'),
            sa.Index('idx_day_time', 'day_of_week', 'time_slot_id'),
            sa.UniqueConstraint('branch_id', 'grade_group_id', 'subject_id', 'day_of_week', 'time_slot_id', 'academic_id', name='unique_schedule')
        )
    else:
        print("Table learning_class_schedules already exists, skipping...")

    # ========== learning_session_logs ==========
    if 'learning_session_logs' not in existing_tables:
        print("Creating table: learning_session_logs")
        op.create_table('learning_session_logs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('class_schedule_id', sa.Integer(), nullable=False),
            sa.Column('session_date', sa.Date(), nullable=False),
            sa.Column('teacher_id', sa.Integer(), nullable=False),
            sa.Column('start_time', sa.Time(), nullable=True),
            sa.Column('end_time', sa.Time(), nullable=True),
            sa.Column('topic_covered', sa.String(500), nullable=True),
            sa.Column('homework_assigned', sa.Text(), nullable=True),
            sa.Column('attendance_count', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('status', mysql.ENUM('scheduled', 'completed', 'cancelled'), nullable=False, server_default='scheduled'),
            sa.Column('cancellation_reason', sa.Text(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.Index('idx_schedule', 'class_schedule_id'),
            sa.Index('idx_date', 'session_date'),
            sa.UniqueConstraint('class_schedule_id', 'session_date', name='unique_session')
        )
    else:
        print("Table learning_session_logs already exists, skipping...")

    # ========== learning_schedule_exceptions ==========
    if 'learning_schedule_exceptions' not in existing_tables:
        print("Creating table: learning_schedule_exceptions")
        op.create_table('learning_schedule_exceptions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('class_schedule_id', sa.Integer(), nullable=False),
            sa.Column('exception_date', sa.Date(), nullable=False),
            sa.Column('exception_type', mysql.ENUM('cancelled', 'rescheduled', 'room_change', 'teacher_change'), nullable=False),
            sa.Column('new_time_slot_id', sa.Integer(), nullable=True),
            sa.Column('new_room_number', sa.String(50), nullable=True),
            sa.Column('substitute_teacher_id', sa.Integer(), nullable=True),
            sa.Column('reason', sa.String(500), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.Index('idx_schedule', 'class_schedule_id'),
            sa.Index('idx_date', 'exception_date')
        )
    else:
        print("Table learning_schedule_exceptions already exists, skipping...")
    
    print("✅ Learning schedule migration completed successfully!")


def downgrade():
    """Remove learning schedule tables in reverse order."""
    from alembic import op
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'learning_schedule_exceptions' in existing_tables:
        op.drop_table('learning_schedule_exceptions')
    
    if 'learning_session_logs' in existing_tables:
        op.drop_table('learning_session_logs')
    
    if 'learning_class_schedules' in existing_tables:
        op.drop_table('learning_class_schedules')
    
    if 'learning_time_slots' in existing_tables:
        op.drop_table('learning_time_slots')

