"""Actual spending first; cash coverage scenarios never post transactions."""
from db import connect
from contextlib import nullcontext
from services import budgets, expenses, treasury
from services.quotations import cents


def register(*, concept, amount, expense_on, category='', paid=False, account_id=None,
             method='', paid_on=None, supplier='', cost_type='Variable', due_on=None,
             notes='', request_key,_conn=None):
    if not isinstance(paid, bool):
        raise ValueError('Selecciona si el gasto ya está pagado.')
    with (nullcontext(_conn) if _conn is not None else connect(write=True)) as conn:
        account = 'Por definir'
        if paid or account_id is not None:
            if type(account_id) is not int:
                raise ValueError('Selecciona una cuenta o caja válida.')
            row = conn.execute('SELECT * FROM treasury_accounts WHERE id=?', (account_id,)).fetchone()
            if not row:
                raise ValueError('La cuenta seleccionada ya no está disponible.')
            account = row['name']
        data = dict(expenses.defaults(), concept=concept, amount=amount, expense_on=expense_on,
                    category=category or 'Sin clasificar', account=account, supplier=supplier,
                    cost_type=cost_type, due_on=due_on, notes=notes)
        normalized = expenses.normalize(data)
        payment = expenses._payment_values(amount, paid_on or expense_on, account, method) if paid else None
        if account_id is not None and not conn.execute('SELECT 1 FROM expenses WHERE request_key=?', (request_key,)).fetchone():
            treasury.validate_account(conn, account_id)
        return expenses._insert(conn, normalized, request_key, payment)


def report(month,_conn=None):
    if _conn is None:
        with connect() as conn:return report(month,_conn=conn)
    start, end = budgets.bounds(month)
    all_rows = expenses._rows(_conn)
    current = [r for r in all_rows if r['status'] == 'Activo' and start <= (r['expense_on'] or '') <= end]
    pending = sorted((r for r in all_rows if r['status'] == 'Activo' and r['balance_cents'] > 0),
                     key=lambda r: (not r['overdue'], r['due_on'] or '9999', r['id']))
    ledger = treasury.ledger(start, end,_conn=_conn)
    payments = [r for r in ledger['rows'] if r['source'] == 'expense']
    with nullcontext(_conn) as conn:
        partners = [dict(r) for r in conn.execute('''SELECT e.category,p.amount_cents FROM partner_expense_settlements p
            JOIN expenses e ON e.id=p.expense_id WHERE e.status='Activo' AND p.paid_on BETWEEN ? AND ?''', (start, end))]
        undated_payments = conn.execute("SELECT COUNT(*) FROM expense_payments WHERE voided_at IS NULL AND COALESCE(paid_on,'')='' ").fetchone()[0]
    groups = {}
    def group(category):
        return groups.setdefault(category, dict(category=category, registered_cents=0, paid_cents=0, pending_cents=0, partner_cents=0))
    for row in current:
        g = group(row['category']); g['registered_cents'] += row['total_cents']; g['pending_cents'] += row['balance_cents']
    accounts = {}
    for row in payments:
        group(row['category'])['paid_cents'] += row['amount']
        a = accounts.setdefault(row['account_id'], dict(account=row['account_name'], kind=row['account_kind'], paid_cents=0))
        a['paid_cents'] += row['amount']
    for row in partners:
        group(row['category'])['partner_cents'] += row['amount_cents']
    return dict(month=month, start=start, end=end, expenses=current, payments=payments, pending=pending,
                categories=sorted(groups.values(), key=lambda r: (-r['paid_cents'], -r['registered_cents'], r['category'])),
                accounts=list(accounts.values()), registered_cents=sum(r['total_cents'] for r in current),
                paid_cents=sum(r['amount'] for r in payments), partner_cents=sum(r['amount_cents'] for r in partners),
                pending_cents=sum(r['balance_cents'] for r in pending), overdue_cents=sum(r['balance_cents'] for r in pending if r['overdue']),
                undated_expenses=sum(not r['expense_on'] for r in all_rows if r['status']=='Activo'), undated_payments=undated_payments)


def project_coverage(*, available=None, reserve=0, project_cost=None, pending_cents=0,allow_negative_available=False):
    """Current confirmed cash minus current unpaid bills, reserve and project.

    Sales forecasts, receivables and historical cash flow are deliberately absent.
    A positive result means funding coverage only, never project profitability.
    """
    if type(pending_cents) is not int or pending_cents < 0:
        raise ValueError('Revisa el saldo de gastos pendientes.')
    missing = []
    if available is None: missing.append('Dinero confirmado en cuentas y efectivo')
    if project_cost is None: missing.append('Costo estimado del proyecto')
    values = {}
    for key, value in (('available', available), ('reserve', reserve), ('project_cost', project_cost)):
        if value is None: continue
        if isinstance(value, bool): raise ValueError('Usa importes válidos sin negativos.')
        if key=='available' and allow_negative_available:
            from decimal import ROUND_HALF_UP
            from services.quotations import number
            amount=int((number(value,'Saldo',minimum=-1000000000)*100).quantize(1,rounding=ROUND_HALF_UP))
        else:amount = cents(value)
        values[key] = amount
    if missing: return dict(missing=missing)
    if not values['project_cost']:
        raise ValueError('El costo del proyecto debe ser mayor que cero.')
    after_bills = values['available'] - pending_cents - values.get('reserve', 0)
    after_project = after_bills - values['project_cost']
    return dict(missing=[], available_cents=values['available'], pending_cents=pending_cents,
                reserve_cents=values.get('reserve', 0), project_cents=values['project_cost'],
                before_project_cents=after_bills, after_project_cents=after_project,
                shortfall_cents=max(0, -after_project), covered=after_project >= 0)
