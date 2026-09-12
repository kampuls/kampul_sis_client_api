"""merge conflicting heads

Revision ID: 8ce10e07bfe6
Revises: add_grade_group_id_to_time_slots, f2ddbe00b2f3
Create Date: 2026-02-07 11:56:53.424772

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8ce10e07bfe6'
down_revision = ('add_grade_group_id_to_time_slots', 'f2ddbe00b2f3')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
