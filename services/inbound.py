"""Future inventory orders; physical quantities post only on confirmed receipt."""
import json
from contextlib import nullcontext
from datetime import date
from db import connect
from services.inventory import _resolve_receipt_sku,_receive_manual
from services.production import _code
from services.recipes import positive
from services import expenses,expense_control
from services.quotations import cents
from services.order_status import STAGES,status
from utils.dates import now,timestamp


def _text(value):return ' '.join(str(value or '').split())[:5000]


def _day(value,label,*,optional=False):
    if not value and optional:return None
    try:return date.fromisoformat(str(value)).isoformat()
    except (ValueError,TypeError):raise ValueError('Revisa '+label+'.') from None


def list_orders(conn=None):
    with (connect() if conn is None else nullcontext(conn)) as c:
        rows=[dict(r) for r in c.execute('''SELECT p.*,s.part,s.material,s.process,s.component_id,s.collection,
            COALESCE((SELECT SUM(m.quantity) FROM inventory_inbound_events e
                JOIN inventory_movements m ON m.id=e.movement_id
                WHERE e.order_id=p.id AND e.kind='Recepción'
                AND NOT EXISTS(SELECT 1 FROM inventory_movements x WHERE x.reversal_of=m.id)),0) received
            FROM inventory_inbound_orders p JOIN inventory_skus s ON s.id=p.sku_id ORDER BY p.id DESC''')]
        events=[dict(e,payload=json.loads(e['payload'])) for e in c.execute('''SELECT e.*,
            EXISTS(SELECT 1 FROM inventory_movements r WHERE r.reversal_of=e.movement_id) reversed
            FROM inventory_inbound_events e ORDER BY e.id''')]
        links={r['order_id']:r['expense_id'] for r in c.execute('SELECT order_id,expense_id FROM inventory_inbound_expenses')}
        finance={r['id']:r for r in expenses._rows(c)} if links else {}
    for r in rows:
        own=[e for e in events if e['order_id']==r['id']]
        r['stage']='Solicitado'
        for event in own:
            if event['kind']=='Seguimiento':
                r.update(supplier=event['payload']['supplier'],expected_on=event['payload']['expected_on'])
                r['stage']=event['payload'].get('stage') or r['stage']
        r['cancelled']=any(e['kind']=='Cancelación' for e in own)
        r['remaining']=r['quantity']-r['received']
        r['pending']=0 if r['cancelled'] else r['remaining']
        r['status']=status(r['stage'],r['quantity'],r['received'],r['cancelled'])
        r['token']=f"{own[-1]['id'] if own else 0}:{r['received']}"
        r['overdue']=bool(r['pending'] and r['expected_on'] and r['expected_on']<now().date().isoformat())
        r['events']=own
        e=finance.get(links.get(r['id']))
        r.update(expense_id=e['id'] if e else None,expense_code=e['code'] if e else '',
            expense_status=e['payment_status'] if e else 'Sin gasto vinculado',
            expense_total_cents=e['total_cents'] if e else None,expense_paid_cents=e['paid_cents'] if e else None,
            expense_balance_cents=(e['balance_cents'] if e['status']=='Activo' else 0) if e else None)
    return rows


def _get(conn,identity):
    row=next((r for r in list_orders(conn) if r['id']==identity),None)
    if not row:raise ValueError('El pedido de inventario ya no existe.')
    return row


def get(identity):
    with connect() as conn:return _get(conn,identity)


def create(quantity,destination,reference,*,supplier='',ordered_on=None,expected_on=None,notes='',request_key,financial=None,**reference_fields):
    positive(quantity);reference=_text(reference);supplier=_text(supplier);notes=_text(notes)
    ordered=_day(ordered_on or now().date(),'la fecha del pedido');expected=_day(expected_on,'la fecha prevista',optional=True)
    if ordered>now().date().isoformat():raise ValueError('La fecha del pedido no puede ser futura.')
    if expected and expected<ordered:raise ValueError('La llegada prevista no puede ser anterior al pedido.')
    if destination not in ('Colección','Stock') or not reference or not request_key:raise ValueError('Completa ubicación y referencia del pedido.')
    payload=_financial(financial,ordered) if financial is not None else None
    with connect(write=True) as conn:
        sku_id=_resolve_receipt_sku(conn,**reference_fields)
        values=(sku_id,quantity,destination,supplier,reference,ordered,expected,notes)
        prior=conn.execute('SELECT * FROM inventory_inbound_orders WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if tuple(prior[k] for k in ('sku_id','quantity','destination','supplier','reference','ordered_on','expected_on','notes'))!=values:
                raise ValueError('Este pedido ya se guardó con otros datos. Abre un registro nuevo.')
            link=conn.execute('SELECT payload,request_key FROM inventory_inbound_expenses WHERE order_id=?',(prior['id'],)).fetchone()
            original=json.loads(link['payload']) if link and link['request_key']=='purchase:'+request_key else None
            if original!=payload:
                raise ValueError('El pedido ya se guardó con otros datos de gasto. Abre un registro nuevo.')
            return prior['id']
        identity,code=_code(conn,'inventory_inbound_orders','PIN')
        conn.execute('''INSERT INTO inventory_inbound_orders(id,code,sku_id,quantity,destination,supplier,reference,ordered_on,expected_on,notes,created_at,request_key)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(identity,code,*values,timestamp(),request_key))
        if payload is not None:_create_expense(conn,identity,payload,'purchase:'+request_key)
        return identity


def _financial(data,ordered):
    if not isinstance(data,dict):raise ValueError('Completa los datos del gasto de la compra.')
    amount=cents(data.get('amount'))
    if amount<=0:raise ValueError('Indica el total del pedido, mayor que cero.')
    paid=data.get('paid',False)
    if not isinstance(paid,bool):raise ValueError('Selecciona Por pagar o Ya pagado.')
    aid=data.get('account_id')
    if aid is not None and type(aid) is not int:raise ValueError('Selecciona una cuenta activa.')
    day=_day(data.get('paid_on') or ordered,'la fecha del pago') if paid else None
    if day and day>now().date().isoformat():raise ValueError('El pago no puede tener fecha futura.')
    due=_day(data.get('due_on'),'el vencimiento del pago',optional=True) if not paid else None
    return dict(amount_cents=amount,paid=paid,account_id=aid,method=_text(data.get('method')) if paid else '',
                paid_on=day,due_on=due,category=_text(data.get('category') or 'Producción / materiales'))


def _link(conn,identity,eid,payload,key):
    conn.execute('INSERT INTO inventory_inbound_expenses(order_id,expense_id,payload,created_at,request_key) VALUES(?,?,?,?,?)',
        (identity,eid,json.dumps(payload,ensure_ascii=False,sort_keys=True),timestamp(),key))
    expenses._audit(conn,eid,'Vinculado a compra '+conn.execute('SELECT code FROM inventory_inbound_orders WHERE id=?',(identity,)).fetchone()[0])


def _create_expense(conn,identity,payload,key):
    row=_get(conn,identity)
    eid=expense_control.register(concept=f"{row['code']} · {row['part']} ×{row['quantity']}",
        amount=payload['amount_cents']/100,expense_on=row['ordered_on'],supplier=row['supplier'],
        category=payload['category'],paid=payload['paid'],account_id=payload['account_id'],method=payload['method'],
        paid_on=payload['paid_on'],due_on=payload['due_on'],notes=f"Compra de inventario {row['code']} · Referencia: {row['reference']}\n{row['notes']}",
        request_key=key,_conn=conn)
    _link(conn,identity,eid,payload,key)
    return eid


def attach_expense(identity,*,financial=None,existing_expense_id=None,expected_expense_revision=None,expected_token,request_key):
    if not request_key:raise ValueError('Abre de nuevo el formulario de gasto.')
    if existing_expense_id is not None and type(existing_expense_id) is not int:raise ValueError('Selecciona un gasto existente válido.')
    with connect(write=True) as conn:
        row=_get(conn,identity)
        payload=dict(existing_expense_id=existing_expense_id) if existing_expense_id is not None else _financial(financial,row['ordered_on'])
        prior=conn.execute('SELECT * FROM inventory_inbound_expenses WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['order_id']!=identity or json.loads(prior['payload'])!=payload:raise ValueError('Esta vinculación ya se guardó con otros datos.')
            return prior['expense_id']
        if row['expense_id']:raise ValueError('Este pedido ya tiene un gasto vinculado. Ábrelo para registrar pagos o corregirlo.')
        if row['token']!=expected_token:raise ValueError('El pedido cambió. Actualiza antes de vincular su gasto.')
        if existing_expense_id is not None:
            e=expenses._get(conn,existing_expense_id)
            if e['status']!='Activo' or e['revision']!=expected_expense_revision:raise ValueError('El gasto cambió o está cancelado. Actualiza la selección.')
            if conn.execute('SELECT 1 FROM inventory_inbound_expenses WHERE expense_id=?',(existing_expense_id,)).fetchone():
                raise ValueError('El gasto ya pertenece a otro pedido de inventario.')
            _link(conn,identity,existing_expense_id,payload,request_key)
            return existing_expense_id
        if row['cancelled']:raise ValueError('Para un pedido cancelado, vincula un gasto existente si realmente corresponde.')
        return _create_expense(conn,identity,payload,request_key)


def purchase_for_expense(eid):
    with connect() as conn:
        row=conn.execute('''SELECT p.id,p.code,p.reference FROM inventory_inbound_expenses l
            JOIN inventory_inbound_orders p ON p.id=l.order_id WHERE l.expense_id=?''',(eid,)).fetchone()
        return dict(row) if row else None


def _prior(conn,key,identity,kind,payload):
    if not key:raise ValueError('Vuelve a abrir la operación.')
    row=conn.execute('SELECT * FROM inventory_inbound_events WHERE request_key=?',(key,)).fetchone()
    if row and (row['order_id']!=identity or row['kind']!=kind or json.loads(row['payload'])!=payload):
        raise ValueError('La operación ya se guardó con otros datos. Abre el formulario otra vez.')
    return row


def _check(row,token):
    if row['token']!=token:raise ValueError('El pedido cambió en otra ventana. Actualiza antes de continuar.')
    if row['cancelled']:raise ValueError('El pedido está cancelado.')


def _event(conn,identity,kind,payload,notes,key,movement=None):
    return conn.execute('''INSERT INTO inventory_inbound_events(order_id,kind,movement_id,payload,notes,created_at,request_key)
        VALUES(?,?,?,?,?,?,?)''',(identity,kind,movement,json.dumps(payload,ensure_ascii=False,sort_keys=True),notes,timestamp(),key)).lastrowid


def receive(identity,quantity,*,received_on=None,notes='',expected_token,request_key):
    positive(quantity);day=_day(received_on or now().date(),'la fecha de recepción');notes=_text(notes)
    payload=dict(quantity=quantity,received_on=day,notes=notes)
    with connect(write=True) as conn:
        if prior:=_prior(conn,request_key,identity,'Recepción',payload):return prior['movement_id']
        row=_get(conn,identity);_check(row,expected_token)
        if not row['ordered_on']<=day<=now().date().isoformat():raise ValueError('La recepción debe estar entre la fecha del pedido y hoy.')
        if quantity>row['remaining']:raise ValueError(f"Solo faltan {row['remaining']} unidades de este pedido.")
        movement=_receive_manual(conn,quantity,row['destination'],
            f"{row['code']} · recepción {day}"+(' · '+notes if notes else ''),sku_id=row['sku_id'],request_key='inbound:'+request_key)
        _event(conn,identity,'Recepción',payload,notes,request_key,movement)
        return movement


def follow_up(identity,*,supplier,expected_on,notes,expected_token,request_key,stage=None):
    supplier=_text(supplier);notes=_text(notes);expected=_day(expected_on,'la fecha prevista',optional=True)
    if stage is not None and stage not in STAGES:raise ValueError('Elige un estado válido.')
    # A status change explains itself; a follow-up without one needs a note.
    if not notes and stage is None:raise ValueError('Escribe una nota de seguimiento.')
    payload=dict(supplier=supplier,expected_on=expected,notes=notes)
    if stage is not None:payload['stage']=stage
    with connect(write=True) as conn:
        if prior:=_prior(conn,request_key,identity,'Seguimiento',payload):return prior['id']
        row=_get(conn,identity);_check(row,expected_token)
        if not row['pending']:raise ValueError('El pedido ya está recibido.')
        if expected and expected<row['ordered_on']:raise ValueError('La llegada prevista no puede ser anterior al pedido.')
        return _event(conn,identity,'Seguimiento',payload,notes,request_key)


def cancel(identity,reason,*,expected_token,request_key):
    reason=_text(reason)
    if not reason:raise ValueError('Escribe el motivo de cancelación.')
    payload=dict(reason=reason)
    with connect(write=True) as conn:
        if prior:=_prior(conn,request_key,identity,'Cancelación',payload):return prior['id']
        row=_get(conn,identity);_check(row,expected_token)
        if not row['pending']:raise ValueError('No hay unidades pendientes por cancelar.')
        if row['expense_id'] and not row['received'] and not row['expense_paid_cents'] and row['expense_status']!='Cancelado':
            e=expenses._get(conn,row['expense_id'])
            expenses.cancel(e['id'],'Compra '+row['code']+' cancelada sin recepción ni pagos: '+reason,expected_revision=e['revision'],_conn=conn)
        return _event(conn,identity,'Cancelación',payload,reason,request_key)
