"""add_missing_financial_columns_snake_case

Revision ID: f5eee8d4229b
Revises: f47a463b22c5
Create Date: 2026-01-06 09:40:10.018329

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5eee8d4229b'
down_revision = 'f47a463b22c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing financial columns in snake_case naming
    op.add_column('users', sa.Column('bank_account_number', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('bank_account_name', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('bank_name', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('nssf_number', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('has_spouse', sa.Boolean(), nullable=True, default=False))
    op.add_column('users', sa.Column('resident', sa.Boolean(), nullable=True, default=True))
    op.add_column('users', sa.Column('number_of_dependents', sa.Integer(), nullable=True, default=0))
    op.add_column('users', sa.Column('employee_nssf', sa.Boolean(), nullable=True, default=True))


def downgrade() -> None:
    # Remove the added financial columns
    op.drop_column('users', 'employee_nssf')
    op.drop_column('users', 'number_of_dependents')
    op.drop_column('users', 'resident')
    op.drop_column('users', 'has_spouse')
    op.drop_column('users', 'nssf_number')
    op.drop_column('users', 'bank_name')
    op.drop_column('users', 'bank_account_name')
    op.drop_column('users', 'bank_account_number')
