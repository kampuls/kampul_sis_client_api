"""Add social media fields to AcademicProgram

Revision ID: d5add89dd848
Revises: 1891e72a404e
Create Date: 2026-02-26 09:39:51.968632

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5add89dd848'
down_revision = '1891e72a404e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('academic_programs', sa.Column('facebook_url', sa.String(length=255), nullable=True))
    op.add_column('academic_programs', sa.Column('telegram_url', sa.String(length=255), nullable=True))
    op.add_column('academic_programs', sa.Column('youtube_url', sa.String(length=255), nullable=True))
    op.add_column('academic_programs', sa.Column('tiktok_url', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('academic_programs', 'tiktok_url')
    op.drop_column('academic_programs', 'youtube_url')
    op.drop_column('academic_programs', 'telegram_url')
    op.drop_column('academic_programs', 'facebook_url')
