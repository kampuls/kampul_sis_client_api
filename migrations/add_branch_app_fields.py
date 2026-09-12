"""
Add app-specific fields to branch table for PAMA contact screen.

Revision ID: add_branch_app_fields
Revises: add_grade_refs_to_schedules
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_branch_app_fields"
down_revision = "add_grade_refs_to_schedules"
branch_labels = None
depends_on = None


def upgrade():
  op.add_column(
    "branch",
    sa.Column("app_display_name", sa.String(length=150), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_cover", sa.String(length=255), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_contact", sa.Text(), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_facebook_url", sa.String(length=255), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_telegram_url", sa.String(length=255), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_youtube_url", sa.String(length=255), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_tiktok_url", sa.String(length=255), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("app_branch_google_map_url", sa.String(length=255), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("map_latitude", sa.Float(), nullable=True),
  )
  op.add_column(
    "branch",
    sa.Column("map_longitude", sa.Float(), nullable=True),
  )


def downgrade():
  op.drop_column("branch", "map_longitude")
  op.drop_column("branch", "map_latitude")
  op.drop_column("branch", "app_branch_google_map_url")
  op.drop_column("branch", "app_branch_tiktok_url")
  op.drop_column("branch", "app_branch_youtube_url")
  op.drop_column("branch", "app_branch_telegram_url")
  op.drop_column("branch", "app_branch_facebook_url")
  op.drop_column("branch", "app_branch_contact")
  op.drop_column("branch", "app_branch_cover")
  op.drop_column("branch", "app_display_name")

