"""add_news_audience_and_images

Revision ID: b3c4d5e6f7a8
Revises: ab12cd34ef56
Create Date: 2026-02-25 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'ab12cd34ef56'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add target_audience column to news
    op.add_column(
        'news',
        sa.Column(
            'target_audience',
            sa.String(length=50),
            nullable=False,
            server_default='all',
        ),
    )

    # Create news_images table
    op.create_table(
        'news_images',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('news_id', sa.Integer(), nullable=False, index=True),
        sa.Column('image_url', sa.String(length=500), nullable=False),
        sa.Column('caption', sa.String(length=255), nullable=True),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('news_images')
    op.drop_column('news', 'target_audience')

