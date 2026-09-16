"""Additive finance migration. Existing invoices and balances are not rewritten."""
from sqlalchemy import (MetaData, Table, Column, Integer, String, Date, DateTime,
                        Numeric, Text, Boolean, UniqueConstraint, func)

metadata = MetaData()

def identity():
    return Column('id', Integer, primary_key=True, autoincrement=True)

plans = Table('finance_coverage', metadata, identity(),
    Column('request_key', String(64), nullable=False, unique=True),
    Column('invoice_id', Integer, nullable=False, index=True),
    Column('student_id', Integer, nullable=False, index=True),
    Column('branch_id', Integer, nullable=False, index=True),
    Column('service', String(200), nullable=False),
    Column('months', Integer, nullable=False),
    Column('continuation', String(30), nullable=False),
    Column('start_date', Date, nullable=False), Column('end_date', Date, nullable=False),
    Column('grace_days', Integer, nullable=False),
    Column('renewal_amount', Numeric(14, 2), nullable=False),
    Column('previous_id', Integer, unique=True),
    Column('reminders_enabled', Boolean, nullable=False, default=True),
    Column('cancelled', Boolean, nullable=False, default=False),
    Column('cancellation_reason', String(500)), Column('cancelled_by', Integer),
    Column('cancelled_at', DateTime),
    Column('created_by', Integer, nullable=False),
    Column('created_at', DateTime, server_default=func.now()))
allocations = Table('finance_coverage_academics', metadata, identity(),
    Column('coverage_id', Integer, nullable=False, index=True),
    Column('academic_id', Integer, nullable=False, index=True),
    Column('start_date', Date, nullable=False), Column('end_date', Date, nullable=False),
    UniqueConstraint('coverage_id', 'academic_id'))
entries = Table('finance_cash_entries', metadata, identity(),
    Column('request_key', String(64), nullable=False, unique=True),
    Column('kind', String(20), nullable=False),
    Column('academic_id', Integer, nullable=False, index=True),
    Column('branch_id', Integer, nullable=False, index=True),
    Column('account_id', Integer, nullable=False),
    Column('category', String(100), nullable=False),
    Column('party', String(200), nullable=False),
    Column('document_ref', String(100)), Column('note', Text),
    Column('amount', Numeric(14, 2), nullable=False),
    Column('currency', String(3), nullable=False),
    Column('exchange_rate', Numeric(16, 6), nullable=False),
    Column('entry_date', Date, nullable=False),
    Column('reversed', Boolean, nullable=False, default=False),
    Column('reversal_reason', String(500)),
    Column('reversed_by', Integer), Column('reversed_at', DateTime),
    Column('created_by', Integer, nullable=False),
    Column('created_at', DateTime, server_default=func.now()))
movements = Table('finance_stock_movements', metadata, identity(),
    Column('request_key', String(64), nullable=False, unique=True),
    Column('product_id', Integer, nullable=False, index=True),
    Column('branch_id', Integer, nullable=False, index=True),
    Column('academic_id', Integer, nullable=False, index=True),
    Column('kind', String(30), nullable=False), Column('quantity', Integer, nullable=False),
    Column('balance_after', Integer, nullable=False),
    Column('reason', String(500), nullable=False), Column('document_ref', String(100)),
    Column('created_by', Integer, nullable=False),
    Column('created_at', DateTime, server_default=func.now()))
stock_settings = Table('finance_stock_settings', metadata,
    Column('product_id', Integer, primary_key=True),
    Column('reorder_level', Integer, nullable=False, default=0),
    Column('archived', Boolean, nullable=False, default=False))
voids = Table('finance_invoice_voids', metadata,
    Column('invoice_id', Integer, primary_key=True),
    Column('reason', String(500), nullable=False),
    Column('created_by', Integer, nullable=False),
    Column('created_at', DateTime, server_default=func.now()))
numbers = Table('finance_receipt_numbers', metadata, identity(),
    Column('request_key', String(64), nullable=False, unique=True),
    Column('branch_id', Integer, nullable=False), Column('created_by', Integer, nullable=False))
reminders = Table('finance_reminder_delivery', metadata, identity(),
    Column('coverage_id', Integer, nullable=False, index=True),
    Column('parent_id', Integer, nullable=False), Column('milestone', Integer, nullable=False),
    Column('state', String(30), nullable=False), Column('attempts', Integer, default=0, nullable=False),
    Column('error', String(500)), Column('notification_id', Integer),
    Column('updated_at', DateTime, server_default=func.now()),
    UniqueConstraint('coverage_id', 'parent_id', 'milestone'))
debt_reminders = Table('finance_debt_reminder_delivery', metadata, identity(),
    Column('invoice_id', Integer, nullable=False, index=True),
    Column('parent_id', Integer, nullable=False), Column('milestone', Integer, nullable=False),
    Column('state', String(30), nullable=False), Column('attempts', Integer, default=0, nullable=False),
    Column('error', String(500)), Column('notification_id', Integer),
    Column('updated_at', DateTime, server_default=func.now()),
    UniqueConstraint('invoice_id', 'parent_id', 'milestone'))

def migrate_finance(connection):
    metadata.create_all(connection, checkfirst=True)
    connection.commit()
