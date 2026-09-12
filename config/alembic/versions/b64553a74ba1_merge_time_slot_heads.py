"""merge time slot heads

Revision ID: b64553a74ba1
Revises: 8ce10e07bfe6, remove_scope_from_time_slots
Create Date: 2026-02-07 14:12:27.538797

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b64553a74ba1'
down_revision = ('8ce10e07bfe6', 'remove_scope_from_time_slots')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
