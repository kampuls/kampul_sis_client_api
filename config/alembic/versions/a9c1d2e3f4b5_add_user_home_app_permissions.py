"""add user_home_app_permissions table

Revision ID: a9c1d2e3f4b5
Revises: f1a2b3c4d5e6
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "a9c1d2e3f4b5"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("user_home_app_permissions"):
        return

    op.create_table(
        "user_home_app_permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feature_id", sa.String(length=100), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("user_id", "feature_id", name="uq_user_home_feature"),
    )
    op.create_index(
        "ix_user_home_app_permissions_user_id",
        "user_home_app_permissions",
        ["user_id"],
    )
    op.create_index(
        "ix_user_home_app_permissions_feature_id",
        "user_home_app_permissions",
        ["feature_id"],
    )


def downgrade() -> None:
    if not _has_table("user_home_app_permissions"):
        return
    op.drop_index(
        "ix_user_home_app_permissions_feature_id",
        table_name="user_home_app_permissions",
    )
    op.drop_index(
        "ix_user_home_app_permissions_user_id",
        table_name="user_home_app_permissions",
    )
    op.drop_table("user_home_app_permissions")
