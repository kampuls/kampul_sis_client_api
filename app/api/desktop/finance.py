"""Typed finance operations with branch permissions, decimal money and audit history."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text, select, insert, update
from sqlalchemy.orm import Session

from ...core import get_db
from ...core.finance_schema import (plans, allocations, entries, movements, stock_settings,
                                    voids, numbers, reminders)
from ...models import User
from ...services.finance_rules import money, service_status, split_coverage
from .data import get_current_desktop_user
from .dashboard import _has_permission

router = APIRouter()

def require(db, user, permission, branch_id):
    if not _has_permission(db, int(user.role), permission):
        raise HTTPException(403, f'Permission required: {permission}')
    if branch_id <= 0 or (branch_id != int(user.workplace or 0) and
                         not _has_permission(db, int(user.role), 'ViewAllBranches')):
        raise HTTPException(403, 'This branch is outside your permitted scope')

def academic_exists(db, academic_id):
    if not db.execute(text('SELECT id FROM academic WHERE id=:id'), {'id': academic_id}).scalar():
        raise HTTPException(404, 'Academic year not found')

def rows(db, sql, parameters):
    return [dict(r) for r in db.execute(text(sql), parameters).mappings()]


def reconciled_payment_total(payments, expected):
    total = Decimal('0')
    for payment in payments:
        amount = money(payment['amount'] or 0)
        rate = Decimal(str(payment['exchange_rate'] or 0))
        if amount < 0 or payment['currency'] not in ('USD','KHR') or (payment['currency']=='KHR' and rate<=0):
            raise HTTPException(409,'Original payments need reconciliation before reversal')
        total += amount if payment['currency']=='USD' else money(amount/rate)
    if abs(total-money(expected or 0)) > Decimal('0.02'):
        raise HTTPException(409,'Original payments need reconciliation before reversal')

class Scope(BaseModel):
    branch_id: int = Field(gt=0)
    academic_id: int = Field(gt=0)

class CashEntry(Scope):
    request_key: UUID
    kind: Literal['income', 'expense']
    account_id: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=100)
    party: str = Field(min_length=1, max_length=200)
    document_ref: str = Field(default='', max_length=100)
    note: str = Field(default='', max_length=2000)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    exchange_rate: Decimal = Field(gt=0, max_digits=16, decimal_places=6)
    entry_date: date

class Reason(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

class Coverage(BaseModel):
    request_key: UUID
    invoice_id: int = Field(gt=0)
    service: str = Field(min_length=1, max_length=200)
    months: Literal[0, 1, 3, 6, 12]
    continuation: Literal['one_off', 'academic_end', 'cross_year']
    start_date: date
    end_date: date
    grace_days: int = Field(default=3, ge=0, le=30)
    renewal_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    previous_id: int | None = Field(default=None, gt=0)
    reminders_enabled: bool = True

class StockMovement(Scope):
    request_key: UUID
    product_id: int = Field(gt=0)
    kind: Literal['received', 'issued', 'returned', 'damaged', 'adjustment']
    quantity: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=5, max_length=500)
    document_ref: str = Field(default='', max_length=100)

class StockSetting(BaseModel):
    reorder_level: int = Field(ge=0, le=1000000)
    archived: bool = False

class ReceiptNumber(BaseModel):
    request_key: UUID
    branch_id: int = Field(gt=0)

@router.post('/receipt-number')
def receipt_number(body: ReceiptNumber, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'EditInvoice', body.branch_id)
    # Branch lock serializes allocation and retry even when multiple tills share a branch.
    db.execute(text('SELECT id FROM branch WHERE id=:id FOR UPDATE'), {'id': body.branch_id})
    row = db.execute(select(numbers).where(numbers.c.request_key == str(body.request_key))).mappings().first()
    if row and (row['branch_id'] != body.branch_id or row['created_by'] != user.id):
        raise HTTPException(409, 'Request key belongs to another operation')
    if row:
        number = row['id']
    else:
        number = db.execute(insert(numbers).values(request_key=str(body.request_key), branch_id=body.branch_id, created_by=user.id)).inserted_primary_key[0]
    db.commit()
    return {'number': f'FIN-{body.branch_id}-{number:08d}'}

@router.get('/options')
def options(branch_id: int = Query(default=0, ge=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    permissions = ['ViewInvoices', 'ViewExpense', 'ViewInventories', 'DashboardAccounting']
    if not any(_has_permission(db, int(user.role), p) for p in permissions):
        raise HTTPException(403, 'Finance access required')
    branch_choices = rows(db, 'SELECT id,branch_name AS name FROM branch ORDER BY branch_name', {}) if _has_permission(db,int(user.role),'ViewAllBranches') else rows(db,'SELECT id,branch_name AS name FROM branch WHERE id=:id',{'id':int(user.workplace or 0)})
    if branch_id <= 0 and branch_choices:
        branch_id = branch_choices[0]['id']
    if branch_id > 0:
        require(db, user, next(p for p in permissions if _has_permission(db, int(user.role), p)), branch_id)
    return {'branches': branch_choices,
            'accounts': rows(db, 'SELECT id, account_name AS name, currency FROM accounts WHERE branch_id=:branch_id', {'branch_id': branch_id}) if any(_has_permission(db,int(user.role),p) for p in ('ViewInvoices','ViewExpense')) else [],
            'products': rows(db, '''SELECT i.id, i.product_name AS name FROM inventories i
                LEFT JOIN finance_stock_settings s ON s.product_id=i.id
                WHERE i.branch_id=:branch_id AND COALESCE(s.archived,0)=0''', {'branch_id': branch_id}) if _has_permission(db,int(user.role),'ViewInventories') else [],
            'academics': rows(db, 'SELECT id, academic_us_name AS name,academic_start,academic_end FROM academic ORDER BY academic_start DESC', {})}

@router.get('/coverage')
def coverage_list(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewInvoices', branch_id)
    result = rows(db, '''SELECT c.*, s.kName AS student, i.invoice_no, i.remaining_amount, DATE(y.academic_end) AS academic_end_date,
        (SELECT COUNT(*) FROM finance_coverage n WHERE n.previous_id=c.id AND n.cancelled=0) AS renewed
        FROM finance_coverage c JOIN finance_coverage_academics a ON a.coverage_id=c.id JOIN academic y ON y.id=a.academic_id
        JOIN students s ON s.id=c.student_id JOIN invoice i ON i.id=c.invoice_id
        WHERE a.academic_id=:academic_id AND c.branch_id=:branch_id ORDER BY c.end_date,c.id''', locals_scope(academic_id, branch_id))
    today = datetime.now(ZoneInfo('Asia/Phnom_Penh')).date()
    for row in result:
        row['status'] = ('Cancelled' if row['cancelled'] else 'Renewed' if row['renewed'] else
                         service_status(row['end_date'], today, row['grace_days'], row['months'] == 1, row['continuation']))
        if (not row['cancelled'] and not row['renewed'] and row['continuation']=='academic_end'
                and row['end_date']>=row['academic_end_date'] and today>row['end_date']):
            row['status']='Completed'
    return result

def locals_scope(academic_id, branch_id):
    return {'academic_id': academic_id, 'branch_id': branch_id}

@router.post('/coverage')
def save_coverage(body: Coverage, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    invoice = db.execute(text('SELECT * FROM invoice WHERE id=:id FOR UPDATE'), {'id': body.invoice_id}).mappings().first()
    if not invoice:
        raise HTTPException(404, 'Invoice not found')
    require(db, user, 'EditInvoice', int(invoice['branch_id']))
    if invoice['payment_status'] == 'Void':
        raise HTTPException(409, 'A void invoice cannot provide service coverage')
    previous_request = db.execute(select(plans.c.id).where(plans.c.request_key == str(body.request_key))).scalar()
    if previous_request:
        existing = db.execute(select(plans).where(plans.c.id == previous_request)).mappings().one()
        if (existing['invoice_id'] != body.invoice_id or existing['created_by'] != user.id
                or existing['service'] != body.service.strip() or existing['start_date'] != body.start_date
                or existing['end_date'] != body.end_date):
            raise HTTPException(409, 'Request key belongs to another coverage operation')
        return {'id': previous_request}
    if body.end_date < body.start_date or (body.end_date-body.start_date).days > 1096:
        raise HTTPException(422, 'Coverage must be a valid period of no more than three years')
    if (body.continuation == 'one_off') != (body.months == 0):
        raise HTTPException(422, 'One-off charges must use the one-off frequency')
    year_rows = db.execute(text('SELECT id, DATE(academic_start), DATE(academic_end) FROM academic ORDER BY academic_start')).all()
    try:
        split = split_coverage(body.start_date, body.end_date, year_rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if body.continuation != 'cross_year' and (len(split) != 1 or split[0][0] != invoice['academic_id']):
        raise HTTPException(422, 'Choose cross-year continuation to cover another academic year')
    # Lock the student to protect against overlapping periods entered at separate tills.
    db.execute(text('SELECT id FROM students WHERE id=:id FOR UPDATE'), {'id': invoice['student_id']})
    overlap = db.execute(select(plans.c.id).where(plans.c.student_id == invoice['student_id'],
        plans.c.service == body.service.strip(), plans.c.cancelled == False,
        plans.c.start_date <= body.end_date, plans.c.end_date >= body.start_date)).first()
    if overlap:
        raise HTTPException(409, 'This service already has coverage in the selected period')
    if body.previous_id:
        previous = db.execute(select(plans).where(plans.c.id == body.previous_id).with_for_update()).mappings().first()
        if not previous or previous['student_id'] != invoice['student_id'] or previous['service'] != body.service.strip() or previous['cancelled']:
            raise HTTPException(422, 'The preceding period must belong to the same student and service')
        if previous['continuation'] == 'one_off' or previous['end_date'] >= body.start_date:
            raise HTTPException(422, 'The previous period cannot be renewed with these dates')
        if previous['branch_id'] != invoice['branch_id']:
            raise HTTPException(422, 'Transfer the service explicitly before changing branches')
        if db.execute(select(plans.c.id).where(plans.c.previous_id==body.previous_id)).first():
            raise HTTPException(409, 'This period already has a renewal; review that renewal instead')
    values = body.model_dump(exclude={'request_key'})
    values.update(request_key=str(body.request_key), service=body.service.strip(), student_id=invoice['student_id'], branch_id=invoice['branch_id'], created_by=user.id, cancelled=False)
    new_id = db.execute(insert(plans).values(**values)).inserted_primary_key[0]
    for year_id, left, right in split:
        db.execute(insert(allocations).values(coverage_id=new_id, academic_id=year_id, start_date=left, end_date=right))
    db.commit()
    return {'id': new_id}

@router.post('/coverage/{coverage_id}/cancel')
def cancel_coverage(coverage_id: int, body: Reason, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    row = db.execute(select(plans).where(plans.c.id == coverage_id).with_for_update()).mappings().first()
    if not row:
        raise HTTPException(404, 'Coverage not found')
    require(db, user, 'EditInvoice', row['branch_id'])
    db.execute(update(plans).where(plans.c.id == coverage_id).values(cancelled=True,
        cancellation_reason=body.reason, cancelled_by=user.id, cancelled_at=datetime.now()))
    db.execute(update(reminders).where(reminders.c.coverage_id == coverage_id, reminders.c.state != 'sent').values(state='cancelled', error=body.reason))
    db.commit()
    return {'success': True}

@router.post('/cash-entries')
def create_cash_entry(body: CashEntry, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'AddExpense' if body.kind == 'expense' else 'EditAccount', body.branch_id)
    academic_exists(db, body.academic_id)
    account = db.execute(text('SELECT * FROM accounts WHERE id=:id FOR UPDATE'), {'id': body.account_id}).mappings().first()
    if not account or account['branch_id'] != body.branch_id:
        raise HTTPException(422, 'Choose an account in the selected branch')
    existing = db.execute(select(entries).where(entries.c.request_key == str(body.request_key))).mappings().first()
    if existing:
        if (existing['created_by'] != user.id or existing['account_id'] != body.account_id
                or existing['amount'] != body.amount or existing['kind'] != body.kind):
            raise HTTPException(409, 'Request key already used')
        return {'id': existing['id']}
    currency = str(account['currency']).upper()
    if currency not in ('USD', 'KHR'):
        raise HTTPException(422, 'Unsupported account currency')
    amount = money(body.amount)
    delta = -amount if body.kind == 'expense' else amount
    if Decimal(str(account['balance'] or 0)) + delta < 0:
        raise HTTPException(409, 'The account has insufficient funds')
    values = body.model_dump(exclude={'request_key'})
    values.update(request_key=str(body.request_key), currency=currency, amount=amount, created_by=user.id, reversed=False)
    entry_id = db.execute(insert(entries).values(**values)).inserted_primary_key[0]
    db.execute(text('UPDATE accounts SET balance=COALESCE(balance,0)+:delta WHERE id=:id'), {'delta': delta, 'id': body.account_id})
    write_log(db, f'FIN-CASH-{entry_id}', body.account_id, f'{body.kind.title()}: {body.category} — {body.party}', delta, currency, body.exchange_rate, user.id)
    db.commit()
    return {'id': entry_id}

def write_log(db, ref, account_id, label, amount, currency, rate, actor):
    db.execute(text('''INSERT INTO logtransaction
        (ref,accounts_id,transaction_name,amount,currency,exchange_rate,created_at,updated_at,created_by,updated_by)
        VALUES (:ref,:account,:label,:amount,:currency,:rate,NOW(),NOW(),:actor,:actor)'''),
        {'ref': ref, 'account': account_id, 'label': label, 'amount': amount, 'currency': currency, 'rate': rate, 'actor': actor})

@router.post('/cash-entries/{entry_id}/reverse')
def reverse_cash(entry_id: int, body: Reason, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    entry = db.execute(select(entries).where(entries.c.id == entry_id).with_for_update()).mappings().first()
    if not entry:
        raise HTTPException(404, 'Entry not found')
    if entry['kind'] in ('settlement','expense_settlement'):
        raise HTTPException(409, 'Reverse the linked invoice or expense so its balance stays consistent')
    require(db, user, 'DeleteExpense' if entry['kind'] == 'expense' else 'EditAccount', entry['branch_id'])
    if entry['reversed']:
        return {'success': True}
    account = db.execute(text('SELECT balance FROM accounts WHERE id=:id FOR UPDATE'), {'id': entry['account_id']}).scalar()
    delta = entry['amount'] if entry['kind'] == 'expense' else -entry['amount']
    if account is None or account + delta < 0:
        raise HTTPException(409, 'Insufficient balance to reverse this receipt')
    db.execute(text('UPDATE accounts SET balance=balance+:delta WHERE id=:id'), {'id': entry['account_id'], 'delta': delta})
    write_log(db, f"FIN-CASH-{entry_id}", entry['account_id'], f"Reversal: {body.reason}", delta, entry['currency'], entry['exchange_rate'], user.id)
    db.execute(update(entries).where(entries.c.id == entry_id).values(reversed=True, reversal_reason=body.reason, reversed_by=user.id, reversed_at=datetime.now()))
    db.commit()
    return {'success': True}

@router.get('/cash-entries')
def cash_list(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewExpense', branch_id)
    return rows(db, '''SELECT e.*,a.account_name AS payment_account,
        CASE WHEN e.kind='settlement' THEN CONCAT(s.kName,' · ',i.invoice_no)
        WHEN e.kind='expense_settlement' THEN e.note ELSE e.party END AS counterparty
        FROM finance_cash_entries e JOIN accounts a ON a.id=e.account_id
        LEFT JOIN invoice i ON e.kind='settlement' AND e.party=CAST(i.id AS CHAR)
        LEFT JOIN students s ON s.id=i.student_id
        WHERE e.academic_id=:academic_id AND e.branch_id=:branch_id ORDER BY e.entry_date DESC,e.id DESC''',locals_scope(academic_id,branch_id))

@router.get('/stock')
def stock_list(branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewInventories', branch_id)
    return rows(db, '''SELECT i.id,i.product_code,i.product_name,i.qty,i.buy_amount,i.sell_amount,i.currency,
        COALESCE(s.reorder_level,0) AS reorder_level,COALESCE(s.archived,0) AS archived,
        CASE WHEN COALESCE(s.archived,0)=1 THEN 'Archived' WHEN i.qty<=COALESCE(s.reorder_level,0) THEN 'Low stock' ELSE 'Available' END AS status
        FROM inventories i LEFT JOIN finance_stock_settings s ON s.product_id=i.id
        WHERE i.branch_id=:branch_id ORDER BY i.product_name''', {'branch_id': branch_id})

@router.post('/stock-movements')
def move_stock(body: StockMovement, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'EditInventory', body.branch_id)
    academic_exists(db, body.academic_id)
    product = db.execute(text('SELECT * FROM inventories WHERE id=:id FOR UPDATE'), {'id': body.product_id}).mappings().first()
    if not product or product['branch_id'] != body.branch_id:
        raise HTTPException(422, 'Product is outside this branch')
    old = db.execute(select(movements.c.id).where(movements.c.request_key == str(body.request_key))).scalar()
    if old:
        existing = db.execute(select(movements).where(movements.c.id == old)).mappings().one()
        expected = -body.quantity if body.kind in ('issued','damaged') else body.quantity
        if (existing['created_by'] != user.id or existing['product_id'] != body.product_id
                or existing['quantity'] != expected or existing['kind'] != body.kind):
            raise HTTPException(409, 'Request key belongs to another stock movement')
        return {'id': old}
    if body.quantity == 0 or (body.kind != 'adjustment' and body.quantity < 0):
        raise HTTPException(422, 'Enter a positive quantity; only adjustments can be negative')
    if db.execute(select(stock_settings.c.archived).where(stock_settings.c.product_id == body.product_id)).scalar():
        raise HTTPException(409, 'Reactivate this product before recording stock')
    delta = -body.quantity if body.kind in ('issued', 'damaged') else body.quantity
    balance = int(product['qty'] or 0) + delta
    if balance < 0:
        raise HTTPException(409, 'Not enough stock')
    db.execute(text('UPDATE inventories SET qty=:qty,updated_at=NOW() WHERE id=:id'), {'qty': balance, 'id': body.product_id})
    values = body.model_dump(exclude={'request_key'})
    values.update(request_key=str(body.request_key), quantity=delta, balance_after=balance, created_by=user.id)
    movement_id = db.execute(insert(movements).values(**values)).inserted_primary_key[0]
    db.commit()
    return {'id': movement_id}

@router.get('/stock-movements')
def movement_list(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewInventories', branch_id)
    return rows(db, '''SELECT m.*,i.product_name FROM finance_stock_movements m JOIN inventories i ON i.id=m.product_id
        WHERE m.academic_id=:academic_id AND m.branch_id=:branch_id ORDER BY m.id DESC''', locals_scope(academic_id, branch_id))

@router.post('/stock/{product_id}/settings')
def save_stock_settings(product_id: int, body: StockSetting, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    product = db.execute(text('SELECT branch_id,qty FROM inventories WHERE id=:id FOR UPDATE'), {'id': product_id}).mappings().first()
    if not product:
        raise HTTPException(404, 'Product not found')
    require(db, user, 'EditInventory', product['branch_id'])
    if body.archived and product['qty'] != 0:
        raise HTTPException(409, 'Resolve remaining stock before archiving this product')
    old = db.execute(select(stock_settings.c.product_id).where(stock_settings.c.product_id == product_id)).first()
    if old:
        db.execute(update(stock_settings).where(stock_settings.c.product_id == product_id).values(**body.model_dump()))
    else:
        db.execute(insert(stock_settings).values(product_id=product_id, **body.model_dump()))
    db.commit()
    return {'success': True}

@router.post('/invoices/{invoice_id}/void')
def void_invoice(invoice_id: int, body: Reason, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    invoice = db.execute(text('SELECT * FROM invoice WHERE id=:id FOR UPDATE'), {'id': invoice_id}).mappings().first()
    if not invoice:
        raise HTTPException(404, 'Invoice not found')
    require(db, user, 'DeleteReceipt', int(invoice['branch_id']))
    if db.execute(select(voids.c.invoice_id).where(voids.c.invoice_id == invoice_id)).first():
        return {'success': True}
    # Ref-based legacy records with collisions must be reconciled, never guessed.
    count = db.execute(text('SELECT COUNT(*) FROM invoice WHERE ref=:ref'), {'ref': invoice['ref']}).scalar()
    if count != 1:
        raise HTTPException(409, 'This legacy reference is shared; reconcile it before voiding')
    payments = rows(db, '''SELECT accounts_id,currency,exchange_rate,SUM(amount) AS amount
        FROM logtransaction WHERE ref=:ref GROUP BY accounts_id,currency,exchange_rate ORDER BY accounts_id''', {'ref': invoice['ref']})
    payments += rows(db, '''SELECT account_id AS accounts_id,currency,exchange_rate,amount
        FROM finance_cash_entries WHERE kind='settlement' AND party=:invoice_id AND reversed=0''', {'invoice_id': str(invoice_id)})
    reconciled_payment_total(payments,invoice['paid_amount'])
    for payment in sorted(payments,key=lambda p:p['accounts_id']):
        amount = Decimal(str(payment['amount'] or 0))
        account = db.execute(text('SELECT balance FROM accounts WHERE id=:id FOR UPDATE'), {'id': payment['accounts_id']}).scalar()
        if account is None or account-amount < 0:
            raise HTTPException(409, 'Insufficient funds in the original account to refund this invoice')
        db.execute(text('UPDATE accounts SET balance=balance-:amount WHERE id=:id'), {'amount': amount, 'id': payment['accounts_id']})
        write_log(db, invoice['ref'], payment['accounts_id'], f'Void {invoice["invoice_no"]}: {body.reason}', -amount, payment['currency'], payment['exchange_rate'], user.id)
    db.execute(insert(voids).values(invoice_id=invoice_id, reason=body.reason, created_by=user.id))
    db.execute(update(entries).where(entries.c.kind == 'settlement', entries.c.party == str(invoice_id)).values(reversed=True, reversal_reason=body.reason, reversed_by=user.id, reversed_at=datetime.now()))
    db.execute(text("UPDATE invoice SET payment_status='Void',remaining_amount=0,isDone=1 WHERE id=:id"), {'id': invoice_id})
    db.execute(update(plans).where(plans.c.invoice_id == invoice_id).values(cancelled=True))
    db.commit()
    return {'success': True}

@router.get('/summary')
def financial_summary(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'DashboardAccounting', branch_id)
    scope = locals_scope(academic_id, branch_id)
    invoices = db.execute(text("""SELECT COALESCE(SUM(total_amount),0) AS billed,
        COALESCE(SUM(paid_amount),0) AS paid, COALESCE(SUM(remaining_amount),0) AS outstanding
        FROM invoice WHERE academic_id=:academic_id AND branch_id=:branch_id AND payment_status<>'Void'"""), scope).mappings().one()
    result = [{'metric': 'Student fees billed', 'amount': invoices['billed'], 'currency': 'USD'},
              {'metric': 'Student fees collected', 'amount': invoices['paid'], 'currency': 'USD'},
              {'metric': 'Student balances outstanding', 'amount': invoices['outstanding'], 'currency': 'USD'}]
    legacy = db.execute(text("""SELECT COALESCE(SUM(paid_amount),0) FROM expenses
        WHERE academic_id=:academic_id AND branch_id=:branch_id AND COALESCE(payment_status,'')<>'Void'"""), scope).scalar()
    result.append({'metric': 'Legacy expenses paid', 'amount': legacy, 'currency': 'USD'})
    for r in db.execute(text("""SELECT kind,currency,SUM(amount) AS amount FROM finance_cash_entries
        WHERE academic_id=:academic_id AND branch_id=:branch_id AND reversed=0 AND kind IN ('income','expense')
        GROUP BY kind,currency"""), scope).mappings():
        result.append({'metric': 'Other income' if r['kind']=='income' else 'Expenses paid', 'amount': r['amount'], 'currency': r['currency']})
    return result

@router.get('/legacy-expenses')
def legacy_expenses(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewExpense', branch_id)
    return rows(db, """SELECT id,expense_no,total_amount,paid_amount,remaining_amount,payment_status,
        payment_method,note,created_at FROM expenses WHERE academic_id=:academic_id AND branch_id=:branch_id
        ORDER BY created_at DESC""", locals_scope(academic_id, branch_id))

@router.post('/legacy-expenses/{expense_id}/reverse')
def reverse_legacy_expense(expense_id: int, body: Reason, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    expense = db.execute(text('SELECT * FROM expenses WHERE id=:id FOR UPDATE'), {'id': expense_id}).mappings().first()
    if not expense:
        raise HTTPException(404, 'Expense not found')
    require(db, user, 'DeleteExpense', int(expense['branch_id']))
    if expense['payment_status'] == 'Void':
        return {'success': True}
    if db.execute(text('SELECT COUNT(*) FROM expenses WHERE ref=:ref'), {'ref': expense['ref']}).scalar() != 1:
        raise HTTPException(409, 'Shared legacy reference must be reconciled before reversal')
    payments = rows(db, """SELECT accounts_id,currency,exchange_rate,-SUM(amount) AS amount
        FROM logtransaction WHERE ref=:ref GROUP BY accounts_id,currency,exchange_rate
        ORDER BY accounts_id""", {'ref': expense['ref']})
    payments += rows(db, """SELECT account_id AS accounts_id,currency,exchange_rate,amount
        FROM finance_cash_entries WHERE kind='expense_settlement' AND party=:id AND reversed=0""", {'id':str(expense_id)})
    reconciled_payment_total(payments,expense['paid_amount'])
    for payment in sorted(payments,key=lambda p:p['accounts_id']):
        account = db.execute(text('SELECT * FROM accounts WHERE id=:id FOR UPDATE'), {'id': payment['accounts_id']}).mappings().first()
        if not account or account['currency']!=payment['currency'] or payment['amount']<0:
            raise HTTPException(409,'Original payment accounts must be available and reconciled')
        refund=money(payment['amount'])
        db.execute(text('UPDATE accounts SET balance=COALESCE(balance,0)+:amount WHERE id=:id'), {'id':account['id'],'amount':refund})
        write_log(db, expense['ref'], account['id'], 'Expense reversal: '+body.reason, refund, account['currency'], payment['exchange_rate'], user.id)
    db.execute(update(entries).where(entries.c.kind=='expense_settlement',entries.c.party==str(expense_id)).values(
        reversed=True,reversal_reason=body.reason,reversed_by=user.id,reversed_at=datetime.now()))
    db.execute(text("UPDATE expenses SET payment_status='Void',remaining_amount=0,updated_at=NOW() WHERE id=:id"), {'id':expense_id})
    db.commit()
    return {'success': True}

@router.get('/invoices/{invoice_id}/editable')
def invoice_editable(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    invoice=db.execute(text('SELECT branch_id,paid_amount,payment_status FROM invoice WHERE id=:id'),{'id':invoice_id}).mappings().first()
    if not invoice:
        raise HTTPException(404,'Invoice not found')
    require(db,user,'EditInvoice',int(invoice['branch_id']))
    linked=db.execute(select(plans.c.id).where(plans.c.invoice_id==invoice_id)).first()
    if invoice['payment_status']=='Void' or Decimal(str(invoice['paid_amount'] or 0))>0 or linked:
        raise HTTPException(409,'Posted payments and service coverage are retained for audit. Use Collect balance or Void and reissue instead of editing this receipt.')
    bundle=db.execute(text("SELECT id FROM invoice_items WHERE invoice_id=:id AND table_name='items_group' LIMIT 1"),{'id':invoice_id}).first()
    if bundle:
        snapshot=db.execute(text("""SELECT m.id FROM finance_stock_movements m JOIN invoice i ON i.ref=m.document_ref
            WHERE i.id=:id LIMIT 1"""),{'id':invoice_id}).first()
        if not snapshot:
            raise HTTPException(409,'This legacy bundle has no stock snapshot. Void and record any physical returns explicitly.')
    return {'allowed':True}

@router.get('/reminders')
def reminder_list(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewInvoices', branch_id)
    scope = locals_scope(academic_id, branch_id)
    renewals = rows(db, '''SELECT d.id,d.milestone,d.state,d.attempts,d.error,d.updated_at,c.service,s.kName AS student,
        'Renewal' AS reminder_type FROM finance_reminder_delivery d
        JOIN finance_coverage c ON c.id=d.coverage_id JOIN finance_coverage_academics a ON a.coverage_id=c.id
        JOIN students s ON s.id=c.student_id WHERE a.academic_id=:academic_id AND c.branch_id=:branch_id''', scope)
    debts = rows(db, '''SELECT d.id,d.milestone,d.state,d.attempts,d.error,d.updated_at,i.invoice_no AS service,
        s.kName AS student,'Balance' AS reminder_type FROM finance_debt_reminder_delivery d
        JOIN invoice i ON i.id=d.invoice_id JOIN students s ON s.id=i.student_id
        WHERE i.academic_id=:academic_id AND i.branch_id=:branch_id''', scope)
    result = renewals + debts
    result.sort(key=lambda r: r.get('updated_at') or datetime.min, reverse=True)
    return result

@router.get('/balances')
def balances(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewInvoices', branch_id)
    result = rows(db, '''SELECT i.id,i.invoice_no,s.kName AS student,i.total_amount,i.paid_amount,i.remaining_amount,
        i.due_date,i.next_payment,i.payment_status FROM invoice i JOIN students s ON s.id=i.student_id
        WHERE i.academic_id=:academic_id AND i.branch_id=:branch_id AND i.remaining_amount>0
        AND i.payment_status<>'Void' ORDER BY i.due_date''', locals_scope(academic_id, branch_id))
    today=datetime.now(ZoneInfo('Asia/Phnom_Penh')).date()
    for row in result:
        due=date.fromisoformat(str(row['due_date'])[:10]) if row['due_date'] else None
        overdue=max(0,(today-due).days) if due else 0
        row['overdue_days']=overdue
        row['aging']='No due date' if due is None else 'Not overdue' if overdue==0 else '1–30 days' if overdue<=30 else '31–60 days' if overdue<=60 else '61–90 days' if overdue<=90 else 'Over 90 days'
    return result

@router.get('/invoices')
def invoice_choices(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db, user, 'ViewInvoices', branch_id)
    return rows(db, '''SELECT i.id, CONCAT(i.invoice_no,' — ',s.kName) AS name FROM invoice i
        JOIN students s ON s.id=i.student_id WHERE i.academic_id=:academic_id AND i.branch_id=:branch_id
        AND i.payment_status<>'Void' ORDER BY i.id DESC''', locals_scope(academic_id, branch_id))

@router.get('/coverage-review')
def coverage_review(academic_id: int = Query(gt=0), branch_id: int = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    require(db,user,'ViewInvoices',branch_id)
    return rows(db, '''SELECT i.id,i.invoice_no,s.kName AS student,i.pay_term,
        i.pay_from AS start_date,i.next_payment,i.total_amount,i.remaining_amount,
        'Review and classify service coverage' AS action_required
        FROM invoice i JOIN students s ON s.id=i.student_id
        WHERE i.academic_id=:academic_id AND i.branch_id=:branch_id
        AND i.payment_status<>'Void'
        AND NOT EXISTS (SELECT 1 FROM finance_coverage c WHERE c.invoice_id=i.id)
        ORDER BY i.id DESC''',locals_scope(academic_id,branch_id))

class Settlement(BaseModel):
    request_key: UUID
    account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    exchange_rate: Decimal = Field(gt=0, max_digits=16, decimal_places=6)

@router.post('/invoices/{invoice_id}/settle')
def settle(invoice_id: int, body: Settlement, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    invoice = db.execute(text('SELECT * FROM invoice WHERE id=:id FOR UPDATE'), {'id': invoice_id}).mappings().first()
    if not invoice:
        raise HTTPException(404, 'Invoice not found')
    require(db, user, 'EditInvoice', int(invoice['branch_id']))
    if invoice['payment_status'] == 'Void':
        raise HTTPException(409, 'Cannot collect against a void invoice')
    ref = 'SETTLE-' + str(body.request_key)
    previous = db.execute(select(entries).where(entries.c.request_key==str(body.request_key))).mappings().first()
    if previous:
        if (previous['kind']!='settlement' or previous['party']!=str(invoice_id) or previous['amount']!=body.amount or previous['account_id']!=body.account_id
                or previous['exchange_rate']!=body.exchange_rate or previous['created_by']!=user.id):
            raise HTTPException(409,'Request key belongs to another payment')
        return {'success': True}
    account = db.execute(text('SELECT * FROM accounts WHERE id=:id FOR UPDATE'), {'id': body.account_id}).mappings().first()
    if not account or account['branch_id'] != invoice['branch_id'] or account['currency'] not in ('USD','KHR'):
        raise HTTPException(422, 'Select an account in the invoice branch')
    usd = money(body.amount if account['currency'] == 'USD' else body.amount/body.exchange_rate)
    if usd <= 0 or usd > Decimal(str(invoice['remaining_amount'])):
        raise HTTPException(422, 'Payment must not exceed the outstanding balance')
    db.execute(text('UPDATE accounts SET balance=COALESCE(balance,0)+:amount WHERE id=:id'), {'amount': body.amount, 'id': body.account_id})
    write_log(db, ref, body.account_id, f'Payment against {invoice["invoice_no"]}', body.amount, account['currency'], body.exchange_rate, user.id)
    # Durable link used by void/refund; do not depend on the display description.
    db.execute(insert(entries).values(request_key=str(body.request_key), kind='settlement', academic_id=invoice['academic_id'],
        branch_id=invoice['branch_id'], account_id=body.account_id, category='Invoice payment', party=str(invoice_id),
        document_ref=ref, note=invoice['invoice_no'], amount=body.amount, currency=account['currency'], exchange_rate=body.exchange_rate,
        entry_date=datetime.now(ZoneInfo('Asia/Phnom_Penh')).date(), reversed=False, created_by=user.id))
    remaining = money(invoice['remaining_amount']) - usd
    db.execute(text('''UPDATE invoice SET paid_amount=paid_amount+:usd,remaining_amount=:remaining,
        payment_status=:status,updated_at=NOW() WHERE id=:id'''),
        {'usd': usd, 'remaining': remaining, 'status': 'Paid' if remaining == 0 else 'Partially Paid', 'id': invoice_id})
    db.commit()
    return {'success': True}


@router.post('/legacy-expenses/{expense_id}/settle')
def settle_expense(expense_id: int, body: Settlement, db: Session = Depends(get_db), user: User = Depends(get_current_desktop_user)):
    expense=db.execute(text('SELECT * FROM expenses WHERE id=:id FOR UPDATE'),{'id':expense_id}).mappings().first()
    if not expense:
        raise HTTPException(404,'Expense not found')
    require(db,user,'AddExpense',int(expense['branch_id']))
    if expense['payment_status']=='Void':
        raise HTTPException(409,'Cannot pay a reversed expense')
    previous=db.execute(select(entries).where(entries.c.request_key==str(body.request_key))).mappings().first()
    if previous:
        if (previous['kind']!='expense_settlement' or previous['party']!=str(expense_id)
                or previous['account_id']!=body.account_id or previous['amount']!=body.amount
                or previous['exchange_rate']!=body.exchange_rate or previous['created_by']!=user.id):
            raise HTTPException(409,'Request key belongs to another payment')
        return {'success':True}
    account=db.execute(text('SELECT * FROM accounts WHERE id=:id FOR UPDATE'),{'id':body.account_id}).mappings().first()
    if not account or account['branch_id']!=expense['branch_id'] or account['currency'] not in ('USD','KHR'):
        raise HTTPException(422,'Choose a supported account in the expense branch')
    usd=money(body.amount if account['currency']=='USD' else body.amount/body.exchange_rate)
    if usd<=0 or usd>money(expense['remaining_amount'] or 0):
        raise HTTPException(422,'Payment must not exceed the expense balance')
    if money(account['balance'] or 0)<body.amount:
        raise HTTPException(409,'The payment account has insufficient funds')
    ref='EXPAY-'+str(body.request_key)
    db.execute(text('UPDATE accounts SET balance=balance-:amount WHERE id=:id'),{'amount':body.amount,'id':body.account_id})
    write_log(db,ref,body.account_id,'Payment against '+expense['expense_no'],-body.amount,account['currency'],body.exchange_rate,user.id)
    db.execute(insert(entries).values(request_key=str(body.request_key),kind='expense_settlement',
        academic_id=expense['academic_id'],branch_id=expense['branch_id'],account_id=body.account_id,
        category='Expense balance payment',party=str(expense_id),document_ref=ref,note=expense['expense_no'],
        amount=body.amount,currency=account['currency'],exchange_rate=body.exchange_rate,
        entry_date=datetime.now(ZoneInfo('Asia/Phnom_Penh')).date(),reversed=False,created_by=user.id))
    remaining=money(expense['remaining_amount'])-usd
    db.execute(text("""UPDATE expenses SET paid_amount=COALESCE(paid_amount,0)+:paid,remaining_amount=:remaining,
        payment_status=:status,updated_at=NOW() WHERE id=:id"""),{'paid':usd,'remaining':remaining,'status':'Paid' if remaining==0 else 'Partially Paid','id':expense_id})
    db.commit()
    return {'success':True}
