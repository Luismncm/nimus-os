"""HTTP routes of the cloud app. Each one calls the same services the local app uses.

Errors keep their meaning: a rule the services reject (ValueError) or the database refuses (a trigger,
a revision that changed) comes back as 400/409 with the same Spanish message the local app shows.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from cloud import auth

router = APIRouter(prefix='/api')


class Credentials(BaseModel):
    email: str
    password: str


def rejected(exc: Exception):
    status = 409 if isinstance(exc, sqlite3.IntegrityError) else 400
    raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get('/health')
def health():
    import db
    if not db.postgres_enabled():
        return {'ok': False, 'detail': 'Falta DATABASE_URL de Postgres.'}
    with db.connect() as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
    return {'ok': True, 'database': 'postgres', 'schema_version': version, 'expected': db.SCHEMA_VERSION}


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
    return dict(
        date=now().date().isoformat(),
        produce=dict(units=board['unassigned_units'], pieces=len(board['unassigned']), available_machines=len(board['available'])),
        deliver=dict(overdue=len(board['overdue']), today=len(board['due']), ready=len(board['ready'])),
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
    from services.queries import load_snapshot
    from services.sales import list_sales
    order = next((o for o in load_snapshot()['orders'] if o['id'] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail='El pedido no existe.')
    quote = next((q for q in list_quotes() if q['order_id'] == order_id), None)
    sale = next((s for s in list_sales() if s['order_id'] == order_id), None)
    trail = dict(
        quote=dict(id=quote['id'], code=quote['code'], total_cents=quote['total_cents']) if quote else None,
        sale=dict(id=sale['id'], code=sale['code'], status=sale['status'], payment_status=sale['payment_status'],
                  balance_cents=sale['balance_cents'], due_on=sale['due_on']) if sale and user['role'] == 'admin' else None,
        missing_sale=not quote and not sale and not order.get('development') and order.get('fulfillment') != 'Stock',
        missing_deadline=not order['deadline'] and not order.get('development') and order['status'] != 'Entregado')
    items = [dict(id=i['id'], name=i['name'], quantity=i['quantity'],
                  parts=[dict(id=p['id'], name=p['name'], required=p['quantity_required'], process=p['process'],
                              material=p['material'], unassigned=p['quantity_unassigned']) for p in i['parts']])
             for i in order['items']]
    return dict(id=order['id'], code=order['code'], project=order['project'], client=order['client'], status=order['status'],
                priority=order['priority'], deadline=order['deadline'], notes=order['notes'], progress=order.get('progress', 0),
                items=items, trail=trail)
