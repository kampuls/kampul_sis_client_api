"""Isolated finance tests: real SQLAlchemy transactions without school credentials."""
import importlib.util
import sys
import types
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text, event, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1] / "app"
PREFIX = "_finance_test_app"
for suffix in ("", ".api", ".api.desktop", ".services", ".core", ".models"):
    module = types.ModuleType(PREFIX + suffix)
    module.__path__ = []
    sys.modules[PREFIX + suffix] = module
sys.modules[PREFIX + ".core"].get_db = lambda: None
sys.modules[PREFIX + ".models"].User = type("User", (), {})
for suffix in (".api.desktop.data", ".api.desktop.dashboard"):
    sys.modules[PREFIX + suffix] = types.ModuleType(PREFIX + suffix)
sys.modules[PREFIX + ".api.desktop.data"].get_current_desktop_user = lambda: None
sys.modules[PREFIX + ".api.desktop.dashboard"]._has_permission = lambda db, role, permission: True

def load(name, path):
    spec = importlib.util.spec_from_file_location(PREFIX + name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

rules = load(".services.finance_rules", "services/finance_rules.py")
schema = load(".core.finance_schema", "core/finance_schema.py")
api = load(".api.desktop.finance", "api/desktop/finance.py")

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def sqlite_lock_syntax(conn, cursor, statement, parameters, context, many):
        parameters = tuple(str(v) if isinstance(v, Decimal) else v for v in parameters)
        return statement.replace(" FOR UPDATE", "").replace("NOW()", "CURRENT_TIMESTAMP"), parameters
    schema.metadata.create_all(engine)
    with engine.begin() as conn:
        for statement in (
            "CREATE TABLE accounts(id INTEGER PRIMARY KEY,branch_id INTEGER,currency TEXT,balance NUMERIC)",
            "CREATE TABLE academic(id INTEGER PRIMARY KEY,academic_start DATE,academic_end DATE)",
            "CREATE TABLE branch(id INTEGER PRIMARY KEY)",
            "CREATE TABLE students(id INTEGER PRIMARY KEY,kName TEXT)",
            "CREATE TABLE invoice(id INTEGER PRIMARY KEY,invoice_no TEXT,ref TEXT,student_id INTEGER,academic_id INTEGER,branch_id INTEGER,payment_status TEXT,paid_amount NUMERIC,remaining_amount NUMERIC,isDone INTEGER,updated_at DATETIME)",
            "CREATE TABLE inventories(id INTEGER PRIMARY KEY,branch_id INTEGER,qty INTEGER,updated_at DATETIME)",
            "CREATE TABLE logtransaction(id INTEGER PRIMARY KEY,ref TEXT,accounts_id INTEGER,transaction_name TEXT,amount NUMERIC,currency TEXT,exchange_rate NUMERIC,created_at DATETIME,updated_at DATETIME,created_by INTEGER,updated_by INTEGER)",
        ):
            conn.execute(text(statement))
        conn.execute(text("INSERT INTO accounts VALUES(1,1,'USD',100),(2,2,'USD',100)"))
        conn.execute(text("INSERT INTO academic VALUES(1,'2026-01-01','2026-12-31'),(2,'2027-01-01','2027-12-31')"))
        conn.execute(text("INSERT INTO branch VALUES(1)"))
        conn.execute(text("INSERT INTO students VALUES(1,'Student')"))
        conn.execute(text("INSERT INTO invoice VALUES(1,'INV-1','unique-ref',1,1,1,'Partially Paid',10,50,0,NULL)"))
        conn.execute(text("INSERT INTO inventories VALUES(1,1,5,NULL)"))
    with Session(engine) as session:
        yield session
    engine.dispose()

@pytest.fixture
def user():
    return types.SimpleNamespace(id=7, role=1, workplace=1)

def cash(**overrides):
    data = dict(request_key=uuid4(), kind="expense", academic_id=1,branch_id=1,
                account_id=1,category="Supplies",party="Supplier",amount="25.00",
                exchange_rate="4100",entry_date=date(2026,9,16))
    data.update(overrides)
    return api.CashEntry(**data)

def test_cash_retry_is_not_a_second_payment(db, user):
    body = cash()
    assert api.create_cash_entry(body,db,user) == api.create_cash_entry(body,db,user)
    assert db.execute(text("SELECT balance FROM accounts WHERE id=1")).scalar() == 75
    assert db.execute(text("SELECT COUNT(*) FROM logtransaction")).scalar() == 1

def test_reversal_retains_original_and_only_credits_once(db,user):
    result=api.create_cash_entry(cash(),db,user)
    reason=api.Reason(reason="Entered twice")
    api.reverse_cash(result["id"],reason,db,user)
    api.reverse_cash(result["id"],reason,db,user)
    assert db.execute(text("SELECT balance FROM accounts WHERE id=1")).scalar() == 100
    assert db.execute(text("SELECT COUNT(*) FROM logtransaction")).scalar() == 2
    assert db.execute(select(schema.entries.c.reversed)).scalar() is True

def test_insufficient_cash_has_no_side_effect(db,user):
    with pytest.raises(HTTPException):
        api.create_cash_entry(cash(amount="101"),db,user)
    assert db.execute(text("SELECT balance FROM accounts WHERE id=1")).scalar() == 100
    assert db.execute(select(schema.entries.c.id)).first() is None

def test_other_branch_account_rejected(db,user):
    with pytest.raises(HTTPException):
        api.create_cash_entry(cash(account_id=2),db,user)

def test_permissions_checked_on_server(db,user,monkeypatch):
    monkeypatch.setattr(api,"_has_permission",lambda *args: False)
    with pytest.raises(HTTPException) as exc:
        api.create_cash_entry(cash(),db,user)
    assert exc.value.status_code == 403

def test_branch_scope_rejected(db,user,monkeypatch):
    monkeypatch.setattr(api,"_has_permission",lambda db,role,p: p != "ViewAllBranches")
    with pytest.raises(HTTPException):
        api.create_cash_entry(cash(branch_id=2,account_id=2),db,user)

def test_stock_cannot_go_negative_and_retry_is_once(db,user):
    body=api.StockMovement(request_key=uuid4(),academic_id=1,branch_id=1,product_id=1,kind="issued",quantity=5,reason="Uniform issued")
    first=api.move_stock(body,db,user)
    assert api.move_stock(body,db,user)==first
    assert db.execute(text("SELECT qty FROM inventories")).scalar()==0
    with pytest.raises(HTTPException):
        api.move_stock(body.model_copy(update={"request_key":uuid4()}),db,user)

def test_archive_does_not_change_cash(db,user):
    with pytest.raises(HTTPException):
        api.save_stock_settings(1,api.StockSetting(reorder_level=2,archived=True),db,user)
    db.execute(text("UPDATE inventories SET qty=0"))
    api.save_stock_settings(1,api.StockSetting(reorder_level=2,archived=True),db,user)
    assert db.execute(text("SELECT balance FROM accounts WHERE id=1")).scalar()==100

def test_partial_settlement_is_idempotent(db,user):
    body=api.Settlement(request_key=uuid4(),account_id=1,amount="20",exchange_rate="4100")
    api.settle(1,body,db,user);api.settle(1,body,db,user)
    assert db.execute(text("SELECT remaining_amount FROM invoice")).scalar()==30
    assert db.execute(text("SELECT paid_amount FROM invoice")).scalar()==30
    assert db.execute(text("SELECT balance FROM accounts WHERE id=1")).scalar()==120

def test_settlement_cannot_overpay(db,user):
    with pytest.raises(HTTPException):
        api.settle(1,api.Settlement(request_key=uuid4(),account_id=1,amount="51",exchange_rate="4100"),db,user)

def test_void_refunds_settlement_once_preserving_receipt(db,user):
    api.write_log(db,'unique-ref',1,'Original fee',Decimal('10'),'USD',Decimal('4100'),user.id)
    db.commit()
    api.settle(1,api.Settlement(request_key=uuid4(),account_id=1,amount="20",exchange_rate="4100"),db,user)
    reason=api.Reason(reason="Student cancellation")
    api.void_invoice(1,reason,db,user);api.void_invoice(1,reason,db,user)
    assert db.execute(text("SELECT balance FROM accounts WHERE id=1")).scalar()==90
    assert db.execute(text("SELECT payment_status FROM invoice")).scalar()=="Void"
    assert db.execute(text("SELECT COUNT(*) FROM invoice")).scalar()==1

def test_receipt_number_retry(db,user):
    body=api.ReceiptNumber(request_key=uuid4(),branch_id=1)
    first=api.receipt_number(body,db,user)
    assert api.receipt_number(body,db,user)==first
    assert api.receipt_number(api.ReceiptNumber(request_key=uuid4(),branch_id=1),db,user)!=first

@pytest.mark.parametrize("months,days",[(1,[-3,0,3]),(3,[-15,-7,0,3]),(6,[-15,-7,0,3]),(12,[-15,-7,0,3])])
def test_reminder_milestones(months,days):
    from datetime import timedelta
    end=date(2026,9,30)
    actual=[d for d in range(-20,6) if rules.reminder_offset(end,end+timedelta(days=d),months,3) is not None]
    assert actual==days

def test_grace_boundary():
    end=date(2026,9,30)
    assert rules.service_status(end,date(2026,10,3),3,True,"cross_year")=="In grace"
    assert rules.service_status(end,date(2026,10,4),3,True,"cross_year")=="Expired"

def test_cross_year_split():
    assert rules.split_coverage(date(2026,12,1),date(2027,2,28),[(1,date(2026,1,1),date(2026,12,31)),(2,date(2027,1,1),date(2027,12,31))]) == [
        (1,date(2026,12,1),date(2026,12,31)),(2,date(2027,1,1),date(2027,2,28))]

def test_missing_next_year_rejected():
    with pytest.raises(ValueError):
        rules.split_coverage(date(2026,12,1),date(2027,2,28),[(1,date(2026,1,1),date(2026,12,31))])

def test_calendar_month_inclusive_end():
    assert rules.coverage_end(date(2026,9,1),1)==date(2026,9,30)
    assert rules.coverage_end(date(2024,1,31),1)==date(2024,2,28)
    assert rules.money("1.005")==Decimal("1.01")

def coverage(**overrides):
    values=dict(request_key=uuid4(),invoice_id=1,service='Tuition',months=3,continuation='cross_year',
        start_date=date(2026,12,1),end_date=date(2027,2,28),renewal_amount='100',grace_days=3)
    values.update(overrides)
    return api.Coverage(**values)

def test_cross_year_coverage_allocated_without_charging_again(db,user):
    body=coverage()
    first=api.save_coverage(body,db,user)
    assert api.save_coverage(body,db,user)==first
    assert db.execute(select(schema.allocations.c.academic_id).order_by(schema.allocations.c.academic_id)).scalars().all()==[1,2]
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==100

def test_overlap_and_wrong_continuation_rejected(db,user):
    api.save_coverage(coverage(),db,user)
    with pytest.raises(HTTPException):
        api.save_coverage(coverage(),db,user)
    with pytest.raises(HTTPException):
        api.save_coverage(coverage(service='Transport',continuation='academic_end'),db,user)

def test_cancelling_coverage_preserves_debt(db,user):
    result=api.save_coverage(coverage(),db,user)
    api.cancel_coverage(result['id'],api.Reason(reason='Student stopped this service'),db,user)
    assert db.execute(select(schema.plans.c.cancelled)).scalar() is True
    assert db.execute(text('SELECT remaining_amount FROM invoice')).scalar()==50

def test_reusing_payment_key_with_different_amount_rejected(db,user):
    body=cash()
    api.create_cash_entry(body,db,user)
    with pytest.raises(HTTPException):
        api.create_cash_entry(body.model_copy(update={'amount':Decimal('30')}),db,user)

def test_atomic_cash_rollback_when_log_write_fails(db,user,monkeypatch):
    def fail(*args):
        raise RuntimeError('Simulated database failure')
    monkeypatch.setattr(api,'write_log',fail)
    with pytest.raises(RuntimeError):
        api.create_cash_entry(cash(),db,user)
    db.rollback()
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==100
    assert db.execute(select(schema.entries.c.id)).first() is None

def test_legacy_guard_rejects_destructive_inventory_and_cross_branch(db,user):
    guard=load('.services.desktop_finance_guard','services/desktop_finance_guard.py')
    db.execute(text('CREATE TABLE permissions(id INTEGER,permission_name TEXT)'))
    db.execute(text('CREATE TABLE role_permissions(role_id INTEGER,permission_id INTEGER)'))
    db.execute(text("INSERT INTO permissions VALUES(1,'EditInventory'),(2,'EditAccount')"))
    db.execute(text("INSERT INTO role_permissions VALUES(1,1),(1,2)"))
    with pytest.raises(guard.FinanceMutationRejected):
        guard.guard_finance_mutation(db,'DELETE FROM inventories WHERE id=:id',{'id':1},user)
    with pytest.raises(guard.FinanceMutationRejected):
        guard.guard_finance_mutation(db,'UPDATE accounts SET balance=0 WHERE id=:id',{'id':2},user)

@pytest.fixture
def reminder_worker(db, monkeypatch):
    from sqlalchemy.orm import declarative_base
    base = types.ModuleType(PREFIX + '.models.base')
    base.Base = declarative_base()
    monkeypatch.setitem(sys.modules, PREFIX + '.models.base', base)
    model = load('.models.notification', 'models/notification.py')
    base.Base.metadata.create_all(db.get_bind())
    monkeypatch.setattr(sys.modules[PREFIX + '.core'], 'SessionLocal', lambda: db, raising=False)
    notifications = types.ModuleType(PREFIX + '.services.notification_service')
    notifications.get_parent_device_tokens = lambda session, student: [{'user_id': 4, 'token': 'test'}]
    notifications.send_notification = lambda *args, **kwargs: True
    monkeypatch.setitem(sys.modules, PREFIX + '.services.notification_service', notifications)
    db.execute(text('CREATE TABLE parents(id INTEGER PRIMARY KEY,myChilds TEXT)'))
    db.execute(text("INSERT INTO parents VALUES(4,'1')"))
    db.execute(text('ALTER TABLE invoice ADD COLUMN due_date DATE'))
    db.execute(text("UPDATE invoice SET due_date='2027-02-28'"))
    db.connection().connection.create_function('FIND_IN_SET', 2, lambda value, csv: int(str(value) in csv.split(',')))
    worker = load('.services.finance_reminders', 'services/finance_reminders.py')
    return worker, model, notifications


def test_reminder_catches_up_only_latest_stage():
    assert rules.pending_milestone(date(2026,9,30),date(2026,9,28),1,3)==-3
    assert rules.pending_milestone(date(2026,9,30),date(2026,10,1),3,3)==0
    assert rules.pending_milestone(date(2026,9,30),date(2026,10,7),3,3) is None


def test_parent_inbox_and_push_are_not_duplicated(db,user,reminder_worker):
    worker, model, notifications = reminder_worker
    plan=api.save_coverage(coverage(),db,user)
    calls=[]
    notifications.send_notification=lambda *args,**kwargs: calls.append(kwargs) or True
    worker.deliver_period(db,plan['id'],date(2027,2,21))
    worker.deliver_period(db,plan['id'],date(2027,2,22))
    assert db.query(model.Notification).count()==1
    assert len(calls)==1
    assert db.execute(select(schema.reminders.c.state)).scalar()=='sent'


def test_push_retry_reuses_parent_inbox(db,user,reminder_worker):
    worker, model, notifications=reminder_worker
    plan=api.save_coverage(coverage(),db,user)
    notifications.send_notification=lambda *args,**kwargs: False
    worker.deliver_period(db,plan['id'],date(2027,2,21))
    notifications.send_notification=lambda *args,**kwargs: True
    worker.deliver_period(db,plan['id'],date(2027,2,21))
    assert db.query(model.Notification).count()==1
    assert db.execute(select(schema.reminders.c.attempts)).scalar()==2
    assert db.execute(select(schema.reminders.c.state)).scalar()=='sent'


def test_no_device_keeps_one_inbox_notification(db,user,reminder_worker):
    worker,model,notifications=reminder_worker
    plan=api.save_coverage(coverage(),db,user)
    notifications.get_parent_device_tokens=lambda *args: []
    worker.deliver_period(db,plan['id'],date(2027,2,21))
    worker.deliver_period(db,plan['id'],date(2027,2,21))
    assert db.query(model.Notification).count()==1
    assert db.execute(select(schema.reminders.c.attempts)).scalar()==1
    assert db.execute(select(schema.reminders.c.state)).scalar()=='inbox_only'


def test_one_off_and_cancelled_plans_do_not_notify(db,user,reminder_worker):
    worker,model,_=reminder_worker
    plan=api.save_coverage(coverage(months=0,continuation='one_off',start_date=date(2026,9,1),end_date=date(2026,9,30)),db,user)
    worker.deliver_period(db,plan['id'],date(2026,9,30))
    api.cancel_coverage(plan['id'],api.Reason(reason='Cancelled service'),db,user)
    worker.deliver_period(db,plan['id'],date(2026,9,30))
    assert db.query(model.Notification).count()==0


def test_debt_push_exception_has_bounded_retry(db,user,reminder_worker):
    worker,model,notifications=reminder_worker
    api.save_coverage(coverage(),db,user)
    calls=[]
    def unavailable(*args,**kwargs):
        calls.append(1)
        raise RuntimeError('Push unavailable')
    notifications.send_notification=unavailable
    for _ in range(7):
        worker.deliver_balance_reminders(db,date(2027,2,28))
    assert len(calls)==5
    assert db.query(model.Notification).count()==1
    assert db.execute(select(schema.debt_reminders.c.attempts)).scalar()==5


def test_paid_balance_does_not_notify(db,user,reminder_worker):
    worker,model,_=reminder_worker
    api.save_coverage(coverage(),db,user)
    db.execute(text('UPDATE invoice SET remaining_amount=0'))
    db.commit()
    worker.deliver_balance_reminders(db,date(2027,2,28))
    assert db.query(model.Notification).count()==0

@pytest.fixture
def expense(db):
    db.execute(text('''CREATE TABLE expenses(id INTEGER PRIMARY KEY,expense_no TEXT,ref TEXT,
        academic_id INTEGER,branch_id INTEGER,paid_amount NUMERIC,remaining_amount NUMERIC,
        payment_status TEXT,updated_at DATETIME)'''))
    db.execute(text("INSERT INTO expenses VALUES(1,'EXP-1','expense-ref',1,1,10,50,'Partially Paid',NULL)"))
    api.write_log(db,'expense-ref',1,'Original expense',Decimal('-10'),'USD',Decimal('4100'),7)
    db.commit()
    return 1


def test_expense_balance_payment_is_atomic_and_idempotent(db,user,expense):
    body=api.Settlement(request_key=uuid4(),account_id=1,amount='20',exchange_rate='4100')
    api.settle_expense(expense,body,db,user)
    api.settle_expense(expense,body,db,user)
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==80
    assert db.execute(text('SELECT remaining_amount FROM expenses')).scalar()==30
    with pytest.raises(HTTPException):
        api.reverse_cash(db.execute(select(schema.entries.c.id)).scalar(),api.Reason(reason='Cannot reverse alone'),db,user)


def test_expense_reversal_refunds_each_original_account_once(db,user,expense):
    db.execute(text("INSERT INTO accounts VALUES(3,1,'KHR',100000)"));db.commit()
    api.settle_expense(expense,api.Settlement(request_key=uuid4(),account_id=3,amount='82000',exchange_rate='4100'),db,user)
    reason=api.Reason(reason='Supplier returned the payment')
    api.reverse_legacy_expense(expense,reason,db,user)
    api.reverse_legacy_expense(expense,reason,db,user)
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==110
    assert db.execute(text('SELECT balance FROM accounts WHERE id=3')).scalar()==100000
    assert db.execute(text('SELECT payment_status FROM expenses')).scalar()=='Void'
    assert db.execute(select(schema.entries.c.reversed)).scalar() is True


def test_expense_overpayment_is_rejected(db,user,expense):
    with pytest.raises(HTTPException):
        api.settle_expense(expense,api.Settlement(request_key=uuid4(),account_id=1,amount='51',exchange_rate='4100'),db,user)
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==100


def test_ambiguous_legacy_expense_refund_requires_reconciliation(db,user,expense):
    db.execute(text('UPDATE expenses SET paid_amount=99'))
    with pytest.raises(HTTPException):
        api.reverse_legacy_expense(expense,api.Reason(reason='Refund request'),db,user)
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==100


def test_unreconciled_invoice_cannot_be_voided(db,user):
    with pytest.raises(HTTPException):
        api.void_invoice(1,api.Reason(reason='Refund requested'),db,user)
    assert db.execute(text('SELECT balance FROM accounts WHERE id=1')).scalar()==100
    assert db.execute(text('SELECT payment_status FROM invoice')).scalar()=='Partially Paid'


def test_cash_report_names_student_settlements(db,user):
    db.execute(text('ALTER TABLE accounts ADD COLUMN account_name TEXT'))
    db.execute(text("UPDATE accounts SET account_name='Cash USD'"))
    db.connection().connection.create_function('CONCAT', -1, lambda *parts: ''.join(str(p) for p in parts))
    api.settle(1,api.Settlement(request_key=uuid4(),account_id=1,amount='20',exchange_rate='4100'),db,user)
    result=api.cash_list(1,1,db,user)
    assert len(result)==1
    assert result[0]['counterparty']=='Student · INV-1'
    assert result[0]['payment_account']=='Cash USD'


def test_coverage_review_removes_classified_invoice(db,user):
    for name in ('pay_term','pay_from','next_payment','total_amount'):
        db.execute(text(f'ALTER TABLE invoice ADD COLUMN {name} TEXT'))
    assert len(api.coverage_review(1,1,db,user))==1
    api.save_coverage(coverage(),db,user)
    assert api.coverage_review(1,1,db,user)==[]
