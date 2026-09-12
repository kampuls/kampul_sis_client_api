"""add check_in_security_events for rate-limit and IP anomaly audit

Revision ID: d4e8f0a1b2c3
Revises: b8a7c2d1e4f9
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e8f0a1b2c3"
down_revision = "b8a7c2d1e4f9"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def upgrade() -> None:
    if _has_table("check_in_security_events"):
        return
    op.create_table(
        "check_in_security_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default="info",
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_check_in_security_events_created_at",
        "check_in_security_events",
        ["created_at"],
    )
    op.create_index(
        "ix_check_in_security_events_user_id",
        "check_in_security_events",
        ["user_id"],
    )
    op.create_index(
        "ix_check_in_security_events_client_ip",
        "check_in_security_events",
        ["client_ip"],
    )
    op.create_index(
        "ix_check_in_security_events_event_type",
        "check_in_security_events",
        ["event_type"],
    )
    op.create_index(
        "ix_check_in_security_events_severity",
        "check_in_security_events",
        ["severity"],
    )


def downgrade() -> None:
    if _has_table("check_in_security_events"):
        op.drop_table("check_in_security_events")
