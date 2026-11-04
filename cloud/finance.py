"""Finance routes of the cloud app: summary and cash forecast, expenses, treasury and partner capital. Administration only.

Same services as views/finance_workspace.py, expenses.py, treasury.py and partners.py. Money moves only as
recorded payments; voiding keeps the history, and every change carries the revision (or reconciliation
token) the screen loaded.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud import auth
from cloud.routes import write

router = APIRouter(prefix='/api')
METHODS = ('Transferencia', 'Efectivo', 'Tarjeta', 'Depósito', 'Otro')


class Expense(BaseModel):
    payload: dict
    request_key: str
    paid: bool = False
    account: str = ''
    method: str = 'Transferencia'


class ExpensePayment(BaseModel):
    amount: float
    paid_on: str
    account: str
    method: str
    reference: str = ''
    request_key: str
    expected_revision: int


class Reason(BaseModel):
    reason: str


class Cancel(Reason):
    expected_revision: int


class Account(BaseModel):
    name: str
    kind: str
    active: bool = True
    expected_revision: int | None = None


class Injection(BaseModel):
    partner: str
    amount: float
    moved_on: str
    account_id: int
    concept: str = 'Inyección a cuenta NIMUS'
    reference: str = ''
    receipt: str = 'Pendiente'
    notes: str = ''
    request_key: str


class Void(Reason):
    expected: str


@router.get('/resumen')
def summary(user=Depends(auth.admin)):
    """Financial health (cash, burn, runway, coverage), the six-month trend and this month's cash forecast."""
    from services import cash_projection, financial_health as fh
    from utils.dates import now
    today = now().date()
    data = fh.load()
    h = fh.health(data, today)
    report, result = cash_projection.workspace(today.strftime('%Y-%m'))
    keys = ('cash_cents', 'burn_cents', 'runway_months', 'result_cents', 'coverage_percent', 'margin_percent', 'break_even_cents',
            'break_even_multiple', 'partner_share_percent', 'collection_percent', 'receivable_cents', 'payable_cents', 'liquidity',
            'overall', 'verdict')
    return dict(
        health={k: h.get(k) for k in keys} | dict(tones=h.get('tones') or {}),
        trend=fh.trend(data, today),
        month=dict(month=report['month'], registered_cents=report['registered_cents'], paid_cents=report['paid_cents'],
                   pending_cents=report['pending_cents'], overdue_cents=report['overdue_cents'],
                   projected_cents=result['projected_cents'], after_cents=result['after_cents'], unassigned_cents=result['unassigned_cents'],
                   accounts=[dict(id=a['id'], name=a['name'], kind=a['kind'], balance_cents=a['balance_cents'], pending_cents=a['pending_cents'],
                                  after_cents=a['after_cents'], confirmed_at=a.get('confirmed_at')) for a in result['accounts']]))


def _expense_row(r):
    return dict(id=r['id'], code=r['code'], expense_on=r['expense_on'] or None, due_on=r['due_on'] or None, concept=r['concept'],
                category=r['category'], subtype=r['subtype'] or '', supplier=r['supplier'] or '', account=r['account'], unit=r['unit'],
                cost_type=r['cost_type'], status=r['status'], payment_status=r['payment_status'], overdue=bool(r['overdue']),
                total_cents=r['total_cents'], paid_cents=r['paid_cents'], balance_cents=r['balance_cents'], receipt_type=r['receipt_type'],
                control=r['control'], order=r.get('order_code') or '', revision=r['revision'])


@router.get('/gastos')
def expenses(desde: str, hasta: str, buscar: str = '', categoria: str = 'Todas', estado: str = 'Todos', user=Depends(auth.admin)):
    from services import expenses as e, treasury
    from services.expense_catalog import CATEGORIES, COST_TYPES, RECEIPTS, TAX_MODES, UNITS
    r = write(e.report, desde, hasta, search=buscar, category=categoria, status=estado)
    return dict(rows=[_expense_row(x) for x in r['rows']], pending=[_expense_row(x) for x in r['pending'][:30]],
                total_cents=r['total_cents'], paid_cents=r['paid_cents'], balance_cents=r['balance_cents'],
                all_balance_cents=r['all_balance_cents'], overdue_cents=r['overdue_cents'], missing_receipts=r['missing_receipts'],
                by_category=r['categories'],
                options=dict(categories=CATEGORIES, cost_types=COST_TYPES, receipts=RECEIPTS, tax_modes=TAX_MODES, units=UNITS,
                             methods=METHODS, accounts=[a['name'] for a in treasury.accounts(active_only=True)]))


@router.get('/gastos/{expense_id}')
def expense(expense_id: int, user=Depends(auth.admin)):
    from services import expenses as e
    x = write(e.get_expense, expense_id)
    row = _expense_row(x) | dict(notes=x.get('notes') or '', receipt_ref=x.get('receipt_ref') or '', tax_mode=x['tax_mode'],
                                 subtotal_cents=x['subtotal_cents'], tax_cents=x['tax_cents'], cancel_reason=x.get('cancel_reason') or '')
    row['payments'] = [dict(id=p['id'], code=p['code'], amount_cents=p['amount_cents'], paid_on=p['paid_on'], account=p['account'],
                            method=p['method'], reference=p.get('reference') or '', voided=bool(p.get('voided_at')),
                            void_reason=p.get('void_reason') or '') for p in x.get('payments', [])]
    return row


@router.post('/gastos')
def expense_create(body: Expense, user=Depends(auth.admin)):
    """A new expense; paid=True records its full payment in the same step (account and method required)."""
    from services import expenses as e
    from utils.dates import now
    payment = None
    if body.paid:
        if not body.account:
            raise HTTPException(status_code=400, detail='Selecciona la cuenta o caja desde la que pagaste.')
        total = write(e.normalize, body.payload)['total_cents']
        payment = dict(amount=total / 100, paid_on=body.payload.get('expense_on') or now().date().isoformat(),
                       account=body.account, method=body.method)
    return dict(ok=True, id=write(e.create, body.payload, request_key=body.request_key, payment=payment))


@router.post('/gastos/{expense_id}/pagos')
def expense_pay(expense_id: int, body: ExpensePayment, user=Depends(auth.admin)):
    from services import expenses as e
    pid = write(e.record_payment, expense_id, body.amount, body.paid_on, body.account, body.method, body.reference,
                request_key=body.request_key, expected_revision=body.expected_revision)
    return dict(ok=True, payment_id=pid)


@router.post('/gastos/pagos/{payment_id}/anular')
def expense_void(payment_id: int, body: Reason, user=Depends(auth.admin)):
    from services import expenses as e
    write(e.void_payment, payment_id, body.reason)
    return dict(ok=True)


@router.post('/gastos/{expense_id}/cancelar')
def expense_cancel(expense_id: int, body: Cancel, user=Depends(auth.admin)):
    from services import expenses as e
    write(e.cancel, expense_id, body.reason, expected_revision=body.expected_revision)
    return dict(ok=True)


@router.get('/tesoreria')
def treasury_view(desde: str, hasta: str, cuenta: str = 'all', direccion: str = 'Todos', buscar: str = '', user=Depends(auth.admin)):
    """Accounts with their balance and the money in and out of the period (sales, quotes, expenses and partners)."""
    from services import cash_projection, treasury
    account = 'all' if cuenta == 'all' else int(cuenta)
    ledger = write(treasury.ledger, desde, hasta, account_id=account, direction=direccion, search=buscar)
    balances = {a['id']: a for a in cash_projection.overview()['accounts']}
    accounts = [dict(id=a['id'], name=a['name'], kind=a['kind'], active=bool(a['active']), revision=a['revision'],
                     balance_cents=(balances.get(a['id']) or {}).get('balance_cents'))
                for a in treasury.accounts()]
    rows = [dict(source=r['source'], id=r['id'], code=r['code'], paid_on=r['paid_on'], amount_cents=r['amount'], sign=r['sign'],
                 method=r['method'] or '', reference=r['reference'] or '', document=r['document'] or '', party=r['party'] or '',
                 concept=r['concept'] or '', account=r['account_name'], category=r['category'] or '',
                 record_kind=r['record_kind'], record_id=r['record_id']) for r in ledger['rows'][:400]]
    return dict(accounts=accounts, kinds=treasury.KINDS, rows=rows, income_cents=ledger['income'], outflow_cents=ledger['outflow'],
                net_cents=ledger['net'], unassigned=ledger['unassigned'], by_account=ledger['accounts'])


@router.post('/tesoreria/cuentas')
def account_create(body: Account, user=Depends(auth.admin)):
    from services import treasury
    return dict(ok=True, id=write(treasury.save_account, body.name, body.kind, active=body.active))


@router.put('/tesoreria/cuentas/{account_id}')
def account_update(account_id: int, body: Account, user=Depends(auth.admin)):
    from services import treasury
    write(treasury.save_account, body.name, body.kind, account_id=account_id, expected_revision=body.expected_revision, active=body.active)
    return dict(ok=True)


@router.get('/socios')
def partners(user=Depends(auth.admin)):
    """Partner capital: money put into NIMUS accounts, purchases paid by a partner and reimbursements."""
    from services import partners as p, reconciliation, sheet_migration, treasury
    rows = []
    for r in sheet_migration.partner_rows():
        rows.append(dict(id=r['id'], code=f"SOC-{r['id']:04d}", moved_on=r['moved_on'], partner=r['partner'] or 'Sin identificar',
                         movement=r['movement'], concept=r['concept'] or '', party=r['party'] or '', amount_cents=r['amount_cents'],
                         sign=r['sign'], account=r.get('account_name') or '', reference=r.get('reference') or '', receipt=r.get('receipt') or '',
                         expense=r.get('expense_code') or '', voided=bool(r.get('voided_at')), void_reason=r.get('void_reason') or '',
                         pending_cents=r.get('pending_cents') or 0,
                         can_void=r['sign'] == 1 and not r.get('linked_expense_id') and not r.get('voided_at'),
                         token=reconciliation.token(reconciliation.state('capital', r['id'])) if r['sign'] == 1 and not r.get('voided_at') else None))
    rows.sort(key=lambda r: (r['moved_on'] or '', r['id']), reverse=True)
    active = [r for r in rows if not r['voided']]
    return dict(rows=rows, partners=p.saved_partners(),
                accounts=[dict(id=a['id'], name=a['name'], kind=a['kind']) for a in treasury.accounts(active_only=True)],
                injected_cents=sum(r['amount_cents'] for r in active if r['sign'] == 1),
                covered_cents=sum(r['amount_cents'] for r in active if r['movement'] == 'Compra pagada por socio'),
                reimbursable_cents=sum(r['pending_cents'] for r in active))


@router.post('/socios')
def injection_create(body: Injection, user=Depends(auth.admin)):
    from services import partners as p
    cid = write(p.register_injection, body.partner, body.amount, body.moved_on, body.account_id, concept=body.concept,
                reference=body.reference, receipt=body.receipt, notes=body.notes, request_key=body.request_key)
    return dict(ok=True, id=cid)


@router.post('/socios/{movement_id}/anular')
def injection_void(movement_id: int, body: Void, user=Depends(auth.admin)):
    from services import partners as p
    write(p.void_injection, movement_id, body.reason, expected=body.expected)
    return dict(ok=True)
