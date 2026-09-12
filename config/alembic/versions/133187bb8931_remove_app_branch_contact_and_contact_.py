"""remove_app_branch_contact_and_contact_type

Revision ID: 133187bb8931
Revises: 5954ddc230d3
Create Date: 2026-02-24 21:21:03.218867

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '133187bb8931'
down_revision = '5954ddc230d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove app_branch_contact from branch
    op.drop_column('branch', 'app_branch_contact')
    
    # Remove contact_type from branch_contacts
    op.drop_column('branch_contacts', 'contact_type')


def downgrade() -> None:
    # Add back app_branch_contact to branch
    op.add_column('branch', sa.Column('app_branch_contact', sa.Text(), nullable=True))
    
    # Add back contact_type to branch_contacts
    op.add_column('branch_contacts', sa.Column('contact_type', sa.String(length=50), nullable=True))
