"""Add can_cancel_approved_leave to leave_approvers

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-27 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'leave_approvers',
        sa.Column('can_cancel_approved_leave', sa.Boolean(), nullable=True, server_default=sa.text('0'))
    )


def downgrade():
    op.drop_column('leave_approvers', 'can_cancel_approved_leave')
