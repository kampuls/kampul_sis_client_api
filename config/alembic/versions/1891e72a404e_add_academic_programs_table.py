"""Add academic_programs table

Revision ID: 1891e72a404e
Revises: b3c4d5e6f7a8
Create Date: 2026-02-25 23:24:17.487264

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1891e72a404e'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'academic_programs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_name', sa.String(length=100), nullable=False),
        sa.Column('icon_name', sa.String(length=100), nullable=True),
        sa.Column('custom_logo_url', sa.String(length=255), nullable=True),
        sa.Column('color_start', sa.String(length=20), nullable=True),
        sa.Column('color_end', sa.String(length=20), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_academic_programs_id'), 'academic_programs', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_academic_programs_id'), table_name='academic_programs')
    op.drop_table('academic_programs')
