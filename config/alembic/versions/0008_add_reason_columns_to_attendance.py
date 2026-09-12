"""Add reason columns to attendance records

Revision ID: 0008
Revises: 0007
Create Date: 2024-01-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007_add_leave_management_system'
branch_labels = None
depends_on = None


def upgrade():
    # Add reason columns to attendance_records table
    op.add_column('attendance_records', sa.Column('late_reason', sa.Text(), nullable=True))
    op.add_column('attendance_records', sa.Column('leave_early_reason', sa.Text(), nullable=True))


def downgrade():
    # Remove reason columns from attendance_records table
    op.drop_column('attendance_records', 'leave_early_reason')
    op.drop_column('attendance_records', 'late_reason')
