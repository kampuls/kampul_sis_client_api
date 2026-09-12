"""Add school_overviews table

Revision ID: b87bfd048c51
Revises: 3da87776798d
Create Date: 2026-02-26 15:54:27.161233

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b87bfd048c51'
down_revision = '3da87776798d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'school_overviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('icon_name', sa.String(length=100), nullable=True),
        sa.Column('color_code', sa.String(length=50), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_school_overviews_id'), 'school_overviews', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_school_overviews_id'), table_name='school_overviews')
    op.drop_table('school_overviews')
