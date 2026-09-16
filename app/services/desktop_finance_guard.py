"""Guard legacy finance mutations while screens move to typed finance endpoints."""
import re
from uuid import uuid4
from sqlalchemy import text

class FinanceMutationRejected(ValueError):
    pass

def _param(parameters, *names):
    lowered={str(k).lower():v for k,v in parameters.items()}
    return next((lowered[n.lower()] for n in names if n.lower() in lowered),None)

def guard_finance_mutation(connection, sql, parameters, user):
    normalized=sql.replace(chr(96),'')
    match=re.match(r'\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)',normalized,re.I)
    if not match:
        return
    operation,table=match.group(1).upper(),match.group(2).lower()
    if table.startswith('finance_'):
        raise FinanceMutationRejected('Use the typed finance API for finance records')
    permissions={
        'invoice':('EditInvoice',), 'invoice_items':('EditInvoice',),
        'expenses':('AddExpense','EditExpense','DeleteExpense'),
        'inventories':('AddInventory','EditInventory'),
        'accounts':('EditAccount','EditInvoice','AddExpense','AddInventory','EditInventory','AddAccount'),
        'logtransaction':('EditAccount','EditInvoice','AddExpense','AddInventory','EditInventory'),
    }
    if table not in permissions:
        return
    def permitted(name):
        return bool(connection.execute(text("""SELECT COUNT(*) FROM role_permissions rp
            JOIN permissions p ON p.id=rp.permission_id
            WHERE rp.role_id=:role AND p.permission_name=:name"""),{'role':user.role,'name':name}).scalar())
    if not any(permitted(name) for name in permissions[table]):
        raise FinanceMutationRejected('You do not have permission for this finance operation')
    if operation.startswith('DELETE') and table in ('inventories','expenses'):
        raise FinanceMutationRejected('Archive inventory or reverse expenses using the finance workspace')
    branch=None
    if operation.startswith('INSERT'):
        branch=_param(parameters,'branch_id','branchId')
        if table=='logtransaction':
            account=_param(parameters,'accounts_id','accountId','account_id')
            if account is not None:
                branch=connection.execute(text('SELECT branch_id FROM accounts WHERE id=:id'),{'id':account}).scalar()
    elif table in ('invoice','inventories','accounts','expenses'):
        id_match=re.search(r'\bWHERE\s+id\s*=\s*:(\w+)',normalized,re.I)
        if not id_match:
            raise FinanceMutationRejected('Legacy finance updates must identify one record')
        record_id=parameters.get(id_match.group(1))
        record=connection.execute(text(f'SELECT * FROM {table} WHERE id=:id FOR UPDATE'),{'id':record_id}).mappings().first()
        if record:
            branch=record['branch_id']
            if table=='invoice' and operation.startswith('DELETE'):
                linked=connection.execute(text('SELECT id FROM finance_coverage WHERE invoice_id=:id LIMIT 1'),{'id':record_id}).first()
                if record['paid_amount'] or record['payment_status']=='Void' or linked:
                    raise FinanceMutationRejected('Posted invoices must be voided, not deleted')
    elif table=='logtransaction' and operation.startswith('DELETE'):
        reference=_param(parameters,'ref')
        if reference is None or connection.execute(text('SELECT id FROM logtransaction WHERE ref=:ref LIMIT 1'),{'ref':reference}).first():
            raise FinanceMutationRejected('Financial transaction history cannot be deleted')
        return
    elif table=='invoice_items' and operation.startswith('DELETE'):
        invoice_id=_param(parameters,'id','invoiceId','invoice_id')
        branch=connection.execute(text('SELECT branch_id FROM invoice WHERE id=:id'),{'id':invoice_id}).scalar()
    if branch is None:
        if operation.startswith('INSERT'):
            raise FinanceMutationRejected('Finance mutations require a branch or payment account')
        return
    if int(branch)!=int(user.workplace or 0) and not permitted('ViewAllBranches'):
        raise FinanceMutationRejected('The financial record belongs to another branch')

def inventory_snapshot(connection, sql, parameters):
    normalized=sql.replace(chr(96),'')
    if not re.match(r'\s*UPDATE\s+inventories\s+SET\b',normalized,re.I):
        return None
    match=re.search(r'\bWHERE\s+id\s*=\s*:(\w+)',normalized,re.I)
    if not match:
        return None
    row=connection.execute(text('SELECT id,qty,branch_id FROM inventories WHERE id=:id FOR UPDATE'),
        {'id':parameters.get(match.group(1))}).mappings().first()
    return dict(row) if row else None

def record_inventory_change(connection, sql, parameters, before, last_insert_id, user):
    from ..core.finance_schema import movements
    from sqlalchemy import insert
    is_insert=bool(re.match(r'\s*INSERT\s+INTO\s+inventories\b',sql.replace(chr(96),''),re.I))
    product_id=before['id'] if before else last_insert_id if is_insert else None
    if not product_id:
        return
    after=connection.execute(text('SELECT id,qty,branch_id FROM inventories WHERE id=:id'),{'id':product_id}).mappings().first()
    if int(after['qty'] or 0) < 0:
        raise FinanceMutationRejected('Stock cannot fall below zero; refresh before retrying')
    delta=int(after['qty'] or 0)-(int(before['qty'] or 0) if before else 0)
    if not delta:
        return
    academic=_param(parameters,'financeAcademicId','academic_id')
    if not academic:
        academic=connection.execute(text("""SELECT id FROM academic
            ORDER BY CASE WHEN CURDATE() BETWEEN DATE(academic_start) AND DATE(academic_end) THEN 0 ELSE 1 END,id DESC LIMIT 1""")).scalar()
    if not academic:
        raise FinanceMutationRejected('Set up an academic year before changing stock')
    connection.execute(insert(movements).values(request_key=str(uuid4()),product_id=product_id,branch_id=after['branch_id'],
        academic_id=academic,kind='received' if is_insert else 'legacy_issue' if delta<0 else 'legacy_return_or_receipt',
        quantity=delta,balance_after=after['qty'],reason='Recorded by desktop inventory transaction',
        document_ref=_param(parameters,'financeReference','ref'),created_by=user.id))
