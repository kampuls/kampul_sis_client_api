"""add_learning_time_slot_scopes

Revision ID: 3cc9dd364f0a
Revises: b64553a74ba1
Create Date: 2026-02-07 15:00:09.747526

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3cc9dd364f0a'
down_revision = 'b64553a74ba1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'learning_time_slot_scopes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('time_slot_id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(20), nullable=False, comment='grade_group or grade'),
        sa.Column('scope_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['time_slot_id'], ['learning_time_slots.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_learning_time_slot_scopes_id'), 'learning_time_slot_scopes', ['id'], unique=False)
    op.create_index(op.f('ix_learning_time_slot_scopes_time_slot_id'), 'learning_time_slot_scopes', ['time_slot_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_learning_time_slot_scopes_time_slot_id'), table_name='learning_time_slot_scopes')
    op.drop_index(op.f('ix_learning_time_slot_scopes_id'), table_name='learning_time_slot_scopes')
    op.drop_table('learning_time_slot_scopes')
