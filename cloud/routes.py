"""HTTP routes of the cloud app. Each one calls the same services the local app uses.

Errors keep their meaning: a rule the services reject (ValueError) or the database refuses (a trigger,
a revision that changed) comes back as 400/409 with the same Spanish message the local app shows.
"""
from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from cloud import auth

router = APIRouter(prefix='/api')


class Credentials(BaseModel):
    email: str
    password: str


class Allocation(BaseModel):
    part_id: int
    machine_id: int | None = None
    quantity: int


class Split(BaseModel):
    allocations: list[Allocation]


class Payment(BaseModel):
    amount: float
    paid_on: str
    method: str
    concept: str
    reference: str = ''
    account_id: int
    request_key: str
    expected_revision: int
    expected_quote_revision: int | None = None


METHODS = ('Transferencia', 'Efectivo', 'Depósito', 'Tarjeta', 'Pasarela de pago', 'Otro')


def rejected(exc: Exception):
    status = 409 if isinstance(exc, sqlite3.IntegrityError) else 400
    raise HTTPException(status_code=status, detail=str(exc)) from exc


def write(operation, *args, **kwargs):
    """Run a service write; its refusal comes back with the same message the local app shows."""
    try:
        return operation(*args, **kwargs)
    except (ValueError, sqlite3.IntegrityError) as exc:
        rejected(exc)
    except sqlite3.OperationalError as exc:
        raise HTTPException(status_code=503, detail='No se pudo guardar. La base está ocupada; inténtalo de nuevo.') from exc


def _order(order_id, snapshot=None):
    from services.queries import load_snapshot
    order = next((o for o in (snapshot or load_snapshot())['orders'] if o['id'] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail='El pedido no existe.')
    return order


def _owed_sale(order_id):
    """The active sale of an order that still has a balance, if any."""
    from services.sales import list_sales
    return next((s for s in list_sales() if s['order_id'] == order_id and s['status'] == 'Activa' and s['balance_cents'] > 0), None)


def _step(order):
    """Where the order stands and whether it can be handed over now (same rule as the local stepper)."""
    from services.order_board import tracking
    t = tracking(order)
    return dict(lane=t['lane'], action=t['action'], pending=t['pending'], blocked=t['blocked'], delivered=t['delivered'],
                can_deliver=t['lane'] == 'Salida' and not t['delivered'] and not order.get('commercial_cancelled'),
                unassigned=t['unassigned'])


@router.get('/health')
def health():
    import db
    if not db.postgres_enabled():
        return {'ok': False, 'detail': 'Falta DATABASE_URL de Postgres.'}
    with db.connect() as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
    secret = len(os.environ.get('NIMUS_SECRET', '')) >= 32
    return {'ok': secret, 'database': 'postgres', 'schema_version': version, 'expected': db.SCHEMA_VERSION,
            'session_secret': secret}


@router.post('/auth/login')
def login(credentials: Credentials, response: Response):
    user = auth.authenticate(credentials.email, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail='Correo o contraseña incorrectos.')
    auth.set_session(response, user['id'])
    return user


@router.post('/auth/logout')
def logout(response: Response):
    auth.clear_session(response)
    return {'ok': True}


@router.get('/auth/me')
def me(user=Depends(auth.current_user)):
    return user


def _money_rows(rows, party):
    return [dict(id=r['id'], code=r['code'], party=r.get(party) or '', balance_cents=r['balance_cents'],
                 due_on=r['due_on'] or None, overdue=bool(r['overdue'])) for r in rows]


@router.get('/hoy')
def today(user=Depends(auth.current_user)):
    """The day at a glance: what to produce, deliver, collect and pay, and the orders that need a look."""
    from services import expenses, sales
    from services.daily import daily_board
    from services.order_progress import manufacturing
    from services.queries import load_snapshot
    from utils.dates import now
    snapshot = load_snapshot()
    board = daily_board(snapshot)
    due = lambda r: (not r['overdue'], r['due_on'] or '9999', r['id'])
    collect = sorted([r for r in sales.list_sales() if r['status'] == 'Activa' and r['balance_cents'] > 0], key=due)
    pay = sorted([r for r in expenses.list_expenses() if r['status'] == 'Activo' and r['balance_cents'] > 0], key=due)
    attention = []
    for row in board['attention'][:8]:
        order = row['order']
        progress = manufacturing(order)
        attention.append(dict(id=order['id'], code=order['code'], project=order['project'], client=order['client'],
                              status=order['status'], deadline=order['deadline'], reasons=row['reasons'],
                              progress=progress.get('percent', order.get('progress', 0))))
    machines = [dict(id=m['id'], code=m['code'], name=m['name'], status=m['status'],
                     current=(m['current_job'] or {}).get('part_name'), next=(m['next_job'] or {}).get('part_name'))
                for m in snapshot['machines']]
    finances = user['role'] == 'admin'
    owed = {r['order_id']: dict(code=r['code'], balance_cents=r['balance_cents']) for r in collect if r['order_id']} if finances else {}
    handover = []
    for order in board['orders']:
        if _step(order)['can_deliver']:
            stock = order.get('fulfillment') == 'Stock'
            handover.append(dict(id=order['id'], code=order['code'], project=order['project'], client=order['client'],
                                 deadline=order['deadline'], stock=stock, owed=None if stock else owed.get(order['id'])))
    return dict(
        date=now().date().isoformat(),
        produce=dict(units=board['unassigned_units'], pieces=len(board['unassigned']), available_machines=len(board['available'])),
        deliver=dict(overdue=len(board['overdue']), today=len(board['due']), ready=len(board['ready']), rows=handover[:6]),
        collect=dict(total_cents=sum(r['balance_cents'] for r in collect), overdue=sum(r['overdue'] for r in collect),
                     rows=_money_rows(collect[:5], 'client')) if finances else None,
        pay=dict(total_cents=sum(r['balance_cents'] for r in pay), overdue=sum(r['overdue'] for r in pay),
                 rows=_money_rows(pay[:5], 'concept')) if finances else None,
        attention=attention, machines=machines)


@router.get('/pedidos')
def orders(user=Depends(auth.current_user)):
    from services.order_progress import fabrication_label
    from services.queries import load_snapshot
    snapshot = load_snapshot()
    return [dict(id=o['id'], code=o['code'], project=o['project'], client=o['client'], status=o['status'],
                 priority=o['priority'], deadline=o['deadline'], progress=o.get('progress', 0),
                 fabrication=fabrication_label(o), fulfillment=o.get('fulfillment'),
                 prototype=bool(o.get('development')), cancelled=bool(o.get('commercial_cancelled')))
            for o in snapshot['orders']]


@router.get('/pedidos/{order_id}')
def order_detail(order_id: int, user=Depends(auth.current_user)):
    """One order with its pieces and its commercial trail: quotation, sale and what is still owed."""
    from services.quotations import list_quotes
    from services.sales import list_sales
    order = _order(order_id)
    quote = next((q for q in list_quotes() if q['order_id'] == order_id), None)
    sale = next((s for s in list_sales() if s['order_id'] == order_id), None)
    trail = dict(
        quote=dict(id=quote['id'], code=quote['code'], total_cents=quote['total_cents']) if quote else None,
        sale=dict(id=sale['id'], code=sale['code'], status=sale['status'], payment_status=sale['payment_status'],
                  balance_cents=sale['balance_cents'], paid_cents=sale['paid_cents'], due_on=sale['due_on'])
        if sale and user['role'] == 'admin' else None,
        missing_sale=not quote and not sale and not order.get('development') and order.get('fulfillment') != 'Stock',
        missing_deadline=not order['deadline'] and not order.get('development') and order['status'] != 'Entregado')
    items = [dict(id=i['id'], name=i['name'], quantity=i['quantity'],
                  parts=[dict(id=p['id'], name=p['name'], required=p['quantity_required'], process=p['process'],
                              material=p['material'], unassigned=p['quantity_unassigned']) for p in i['parts']])
             for i in order['items']]
    return dict(id=order['id'], code=order['code'], project=order['project'], client=order['client'], status=order['status'],
                priority=order['priority'], deadline=order['deadline'], notes=order['notes'], progress=order.get('progress', 0),
                fulfillment=order.get('fulfillment'), completed_total=order.get('completed_total'),
                items=items, trail=trail, step=_step(order))


@router.post('/pedidos/{order_id}/entregar')
def deliver(order_id: int, user=Depends(auth.current_user)):
    """Hand the order over (or close a stock batch). Same checks as the local app: ready, prepared, paid if required."""
    from services.production import deliver_order
    order = _order(order_id)
    write(deliver_order, order_id)
    sale = None if order.get('fulfillment') == 'Stock' or user['role'] != 'admin' else _owed_sale(order_id)
    # Handing over is when the balance is collected: tell the screen which sale to open next.
    return dict(ok=True, collect=dict(id=sale['id'], code=sale['code'], balance_cents=sale['balance_cents']) if sale else None)


@router.get('/pedidos/{order_id}/reparto')
def split_plan(order_id: int, user=Depends(auth.current_user)):
    """Pieces still to assign, the machines, and the automatic suggestion the local app offers."""
    from services.assign_suggest import auto_split, pending_parts
    from services.queries import load_snapshot
    from services.timeline import availability_text, machine_timeline
    snapshot = load_snapshot()
    parts = pending_parts(_order(order_id, snapshot))
    machines = snapshot['machines']
    suggestion = [dict(part_id=part, machine_id=machine, quantity=units)
                  for (part, machine), units in auto_split(parts, machines).items()]
    return dict(
        parts=[dict(id=p['id'], name=p['name'], item=p['item_name'], material=p['material'] or '', unassigned=p['quantity_unassigned'])
               for p in parts],
        machines=[dict(id=m['id'], code=m['code'], name=m['name'], status=m['status'], material=m.get('loaded_material') or '',
                       availability=availability_text(machine_timeline(m, snapshot['jobs'])['availability'])
                       if m['status'] == 'Disponible' else m['status'])
                  for m in machines],
        suggestion=suggestion)


@router.post('/pedidos/{order_id}/reparto')
def split_save(order_id: int, split: Split, user=Depends(auth.current_user)):
    """Create the jobs of several pieces at once: all or none, with the order's priority."""
    from services.production import create_order_jobs
    created = write(create_order_jobs, order_id, [a.model_dump() for a in split.allocations])
    return dict(ok=True, jobs=len(created))


@router.get('/ventas/{sale_id}/cobro')
def payment_form(sale_id: int, user=Depends(auth.admin)):
    """What the payment form needs: the balance, the revisions it must match and the accounts."""
    from services import sales, treasury
    try:
        sale = sales.get_sale(sale_id)
    except (ValueError, StopIteration) as exc:
        raise HTTPException(status_code=404, detail='La venta no está disponible.') from exc
    return dict(id=sale['id'], code=sale['code'], client=sale['client'] or '', status=sale['status'],
                balance_cents=sale['balance_cents'], paid_cents=sale['paid_cents'],
                revision=sale['revision'], quote_revision=sale['quote_revision'],
                concept='Abono' if sale['paid_cents'] else 'Liquidación', methods=METHODS,
                accounts=[dict(id=a['id'], name=a['name'], kind=a['kind']) for a in treasury.accounts(active_only=True)])


@router.post('/ventas/{sale_id}/pagos')
def payment_save(sale_id: int, payment: Payment, user=Depends(auth.admin)):
    """Record money received for a sale (or its quotation). The request key makes a retried click harmless."""
    from services import sales
    if payment.method not in METHODS:
        raise HTTPException(status_code=400, detail='Selecciona un método de pago.')
    payment_id = write(sales.record_payment, sale_id, payment.amount, payment.paid_on, payment.method, payment.concept,
                       payment.reference, request_key=payment.request_key, expected_revision=payment.expected_revision,
                       expected_quote_revision=payment.expected_quote_revision, account_id=payment.account_id)
    sale = sales.get_sale(sale_id)
    return dict(ok=True, payment_id=payment_id, balance_cents=sale['balance_cents'], payment_status=sale['payment_status'])
