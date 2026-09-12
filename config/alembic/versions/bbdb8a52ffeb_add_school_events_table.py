"""Add school_events table

Revision ID: bbdb8a52ffeb
Revises: b87bfd048c51
Create Date: 2026-02-26 17:02:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'bbdb8a52ffeb'
down_revision = 'b87bfd048c51'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'school_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('title_kh', sa.String(length=255), nullable=True),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('round', sa.String(length=50), nullable=True),
        sa.Column('participant_group', sa.String(length=150), nullable=True),
        sa.Column('time_of_day', sa.String(length=100), nullable=True),
        sa.Column('academic_year', sa.String(length=20), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color_code', sa.String(length=50), nullable=True),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_school_events_id'), 'school_events', ['id'], unique=False)
    op.create_index(op.f('ix_school_events_event_date'), 'school_events', ['event_date'], unique=False)
    op.create_index(op.f('ix_school_events_academic_year'), 'school_events', ['academic_year'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_school_events_academic_year'), table_name='school_events')
    op.drop_index(op.f('ix_school_events_event_date'), table_name='school_events')
    op.drop_index(op.f('ix_school_events_id'), table_name='school_events')
    op.drop_table('school_events')
