"""add_enable_schedule_reminders

Revision ID: add_enable_schedule_reminders
Revises: 
Create Date: 2026-04-01

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_enable_schedule_reminders"
down_revision = "258f3b85cde3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add enable_schedule_reminders to settings table
    op.add_column('settings', sa.Column('enable_schedule_reminders', sa.String(length=11), server_default='yes', nullable=True))


def downgrade() -> None:
    # Remove the column
    op.drop_column('settings', 'enable_schedule_reminders')
