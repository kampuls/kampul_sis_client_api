"""Durable parent inbox reminders; push delivery is retried with a stable key."""
import json
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text, select, insert, update
from ..core import SessionLocal
from ..core.finance_schema import plans, reminders, debt_reminders
from ..models.notification import Notification
from .finance_rules import pending_milestone

logger = logging.getLogger(__name__)

def run_finance_reminders():
    now = datetime.now(ZoneInfo('Asia/Phnom_Penh'))
    if not 8 <= now.hour < 18:
        return
    # A dedicated connection keeps the advisory lock across per-recipient commits.
    db = SessionLocal()
    lock = db.get_bind().connect()
    try:
        if lock.execute(text("SELECT GET_LOCK('finance_reminder_delivery',0)")).scalar() != 1:
            return
        coverage_ids = db.execute(select(plans.c.id).where(plans.c.cancelled == False,
            plans.c.reminders_enabled == True, plans.c.continuation != 'one_off')).scalars().all()
        for coverage_id in coverage_ids:
            try:
                deliver_period(db, coverage_id, now.date())
            except Exception:
                db.rollback()
                logger.exception('Finance reminder failed for coverage %s', coverage_id)
        deliver_balance_reminders(db, now.date())
    finally:
        try:
            lock.execute(text("SELECT RELEASE_LOCK('finance_reminder_delivery')"))
        finally:
            lock.close()
            db.close()

def deliver_period(db, coverage_id, today):
    row = db.execute(text('''SELECT c.*,s.kName AS student,i.payment_status FROM finance_coverage c
        JOIN students s ON s.id=c.student_id JOIN invoice i ON i.id=c.invoice_id
        WHERE c.id=:id AND c.cancelled=0 AND c.reminders_enabled=1
        AND i.payment_status<>'Void'
        AND NOT EXISTS (SELECT 1 FROM finance_coverage n WHERE n.previous_id=c.id AND n.cancelled=0)'''), {'id': coverage_id}).mappings().first()
    if not row:
        return
    row = dict(row)
    row['end_date'] = date.fromisoformat(str(row['end_date'])[:10])
    if row['continuation'] == 'one_off':
        return
    if row['continuation'] == 'academic_end':
        year_end = db.execute(text('''SELECT MAX(DATE(a.academic_end)) FROM academic a
            JOIN finance_coverage_academics ca ON ca.academic_id=a.id WHERE ca.coverage_id=:id'''), {'id': coverage_id}).scalar()
        if year_end and row['end_date'] >= date.fromisoformat(str(year_end)[:10]):
            return
    milestone = pending_milestone(row['end_date'], today, row['months'], row['grace_days'])
    if milestone is None:
        return
    parents = db.execute(text('SELECT id FROM parents WHERE FIND_IN_SET(:student_id,myChilds)>0'), {'student_id': row['student_id']}).scalars().all()
    for parent_id in parents or [0]:
        delivery = db.execute(select(reminders).where(reminders.c.coverage_id == coverage_id,
            reminders.c.parent_id == parent_id, reminders.c.milestone == milestone)).mappings().first()
        if delivery and (delivery['state'] in ('sent', 'cancelled', 'inbox_only') or delivery['attempts'] >= 5):
            continue
        if delivery is None:
            delivery_id = db.execute(insert(reminders).values(coverage_id=coverage_id, parent_id=parent_id,
                milestone=milestone, state='pending', attempts=0)).inserted_primary_key[0]
            db.commit()
            delivery = db.execute(select(reminders).where(reminders.c.id == delivery_id)).mappings().one()
        delivery_id = delivery['id']
        if parent_id == 0:
            db.execute(update(reminders).where(reminders.c.id == delivery_id).values(state='missing_parent', error='Link a verified parent to this student', updated_at=datetime.now()))
            db.commit()
            continue
        # Recheck authoritative coverage after each external delivery and before the next.
        active = db.execute(select(plans.c.id).where(plans.c.id == coverage_id, plans.c.cancelled == False)).scalar()
        renewed = db.execute(select(plans.c.id).where(plans.c.previous_id == coverage_id, plans.c.cancelled == False)).first()
        if not active or renewed:
            return
        title = 'ការរំលឹកការបង់ប្រាក់ / Payment reminder'
        body = (f"{row['student']} — {row['service']}\n"
                f"សុពលភាពដល់ / Covered through: {row['end_date']:%d %b %Y}\n"
                f"ថ្លៃបន្ត / Renewal: USD {row['renewal_amount']:.2f}\n"
                f"សូមទាក់ទងការិយាល័យសាលា / Please contact the school office to renew.")
        key = f'finance:{coverage_id}:{milestone}:{parent_id}'
        payload = {'type': 'payment_reminder', 'notification_key': key, 'student_id': str(row['student_id'])}
        if not delivery['notification_id']:
            notification = Notification(user_id=parent_id, user_type='parent', title=title, body=body,
                data=json.dumps(payload), is_read=False, is_deletable=True)
            db.add(notification)
            db.flush()
            db.execute(update(reminders).where(reminders.c.id == delivery_id).values(notification_id=notification.id))
            db.commit()
        from .notification_service import get_parent_device_tokens, send_notification
        tokens = [t for t in get_parent_device_tokens(db, row['student_id']) if int(t.get('user_id', 0)) == parent_id]
        try:
            sent = bool(tokens) and send_notification(tokens, title, body, data=payload)
            state = 'sent' if sent else 'inbox_only' if not tokens else 'retry'
            error = None if sent else 'Saved to parent inbox; no active device' if not tokens else 'Push delivery failed'
        except Exception as exc:
            state, error = 'retry', str(exc)[:500]
        db.execute(update(reminders).where(reminders.c.id == delivery_id).values(state=state,
            attempts=delivery['attempts']+1, error=error, updated_at=datetime.now()))
        db.commit()

def deliver_balance_reminders(db, today):
    """Only reviewed, reminder-enabled coverage opts legacy invoices into debt notices."""
    invoice_ids=db.execute(text("""SELECT DISTINCT i.id FROM invoice i
        JOIN finance_coverage c ON c.invoice_id=i.id
        WHERE i.remaining_amount>0 AND i.payment_status<>'Void'
        AND c.reminders_enabled=1 AND c.cancelled=0""")).scalars().all()
    for invoice_id in invoice_ids:
        try:
            invoice=db.execute(text("""SELECT i.*,s.kName AS student FROM invoice i
                JOIN students s ON s.id=i.student_id WHERE i.id=:id AND i.remaining_amount>0
                AND i.payment_status<>'Void'"""),{'id':invoice_id}).mappings().first()
            if not invoice or not invoice['due_date']:
                continue
            due=date.fromisoformat(str(invoice['due_date'])[:10])
            milestone=pending_milestone(due,today,1,3)
            if milestone is None:
                continue
            parents=db.execute(text('SELECT id FROM parents WHERE FIND_IN_SET(:id,myChilds)>0'),{'id':invoice['student_id']}).scalars().all()
            for parent_id in parents or [0]:
                row=db.execute(select(debt_reminders).where(debt_reminders.c.invoice_id==invoice_id,
                    debt_reminders.c.parent_id==parent_id,debt_reminders.c.milestone==milestone)).mappings().first()
                if row and (row['state'] in ('sent','inbox_only','cancelled') or row['attempts']>=5):
                    continue
                if row is None:
                    delivery_id=db.execute(insert(debt_reminders).values(invoice_id=invoice_id,parent_id=parent_id,
                        milestone=milestone,state='pending',attempts=0)).inserted_primary_key[0]
                    db.commit()
                    row=db.execute(select(debt_reminders).where(debt_reminders.c.id==delivery_id)).mappings().one()
                delivery_id=row['id']
                if parent_id==0:
                    db.execute(update(debt_reminders).where(debt_reminders.c.id==delivery_id).values(state='missing_parent',error='No linked parent',updated_at=datetime.now()))
                    db.commit()
                    continue
                current=db.execute(text("SELECT remaining_amount FROM invoice WHERE id=:id AND payment_status<>'Void'"),{'id':invoice_id}).scalar()
                if current is None or current<=0:
                    db.execute(update(debt_reminders).where(debt_reminders.c.id==delivery_id).values(state='cancelled'))
                    db.commit()
                    continue
                title='ការរំលឹកសមតុល្យ / Outstanding balance'
                body=f"{invoice['student']} · {invoice['invoice_no']}\nសមតុល្យ / Balance: USD {current:.2f}\nកាលបរិច្ឆេទបង់ / Due: {due:%d %b %Y}\nសូមទាក់ទងការិយាល័យសាលា / Please contact the school office."
                payload={'type':'payment_balance_reminder','notification_key':f'debt:{invoice_id}:{milestone}:{parent_id}'}
                if not row['notification_id']:
                    notification=Notification(user_id=parent_id,user_type='parent',title=title,body=body,data=json.dumps(payload),is_read=False,is_deletable=True)
                    db.add(notification);db.flush()
                    db.execute(update(debt_reminders).where(debt_reminders.c.id==delivery_id).values(notification_id=notification.id))
                    db.commit()
                from .notification_service import get_parent_device_tokens,send_notification
                tokens=[t for t in get_parent_device_tokens(db,invoice['student_id']) if int(t.get('user_id',0))==parent_id]
                error = None
                try:
                    sent=bool(tokens) and send_notification(tokens,title,body,data=payload)
                except Exception as exc:
                    sent=False
                    error=str(exc)[:500]
                db.execute(update(debt_reminders).where(debt_reminders.c.id==delivery_id).values(
                    state='sent' if sent else 'inbox_only' if not tokens else 'retry',
                    attempts=row['attempts']+1,error=None if sent else error or 'Parent inbox saved; push unavailable',updated_at=datetime.now()))
                db.commit()
        except Exception:
            db.rollback()
            logger.exception('Debt reminder failed for invoice %s',invoice_id)
