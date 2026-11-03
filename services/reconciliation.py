"""Atomic corrections of existing records with before/after evidence and stale-write checks."""
import hashlib
from db import connect
from services import expenses,treasury
from services.quotations import cents
from utils.dates import timestamp
from services.guards import canonical as _encode

TABLES={'expense':'expense_payments','quote':'quotation_payments','sale':'sale_payments','capital':'capital_movements'}


def token(value): return hashlib.sha256(_encode(value).encode()).hexdigest()


def _state(conn,source,rid):
    table='expenses' if source=='expense_document' else TABLES.get(source)
    if not table: raise ValueError('Tipo de movimiento inválido.')
    row=conn.execute(f'SELECT * FROM {table} WHERE id=?',(rid,)).fetchone()
    if not row: raise ValueError('El registro ya no está disponible.')
    data=dict(row)
    if source=='expense_document':
        data['payments']=[dict(r) for r in conn.execute('SELECT * FROM expense_payments WHERE expense_id=? ORDER BY id',(rid,))]
        data['accounts']=[dict(r) for r in conn.execute("SELECT pa.* FROM payment_accounts pa JOIN expense_payments p ON pa.source='expense' AND pa.payment_id=p.id WHERE p.expense_id=? ORDER BY p.id",(rid,))]
        data['partners']=[dict(r) for r in conn.execute('SELECT * FROM partner_expense_settlements WHERE expense_id=?',(rid,))]
        data['capital']=[dict(r) for r in conn.execute('SELECT * FROM capital_movements WHERE linked_expense_id=? ORDER BY id',(rid,))]
    elif source!='capital':
        account=conn.execute('SELECT * FROM payment_accounts WHERE source=? AND payment_id=?',(source,rid)).fetchone()
        data['account_id']=account['account_id'] if account else None
        owner_table,owner_key={'expense':('expenses','expense_id'),'quote':('quotations','quote_id'),'sale':('sales','sale_id')}[source]
        data['owner_revision']=conn.execute(f'SELECT revision FROM {owner_table} WHERE id=?',(row[owner_key],)).fetchone()[0]
        if source=='expense':
            data['capital']=[dict(r) for r in conn.execute('SELECT * FROM capital_movements WHERE linked_expense_id=? ORDER BY id',(row['expense_id'],))]
    return data


def state(source,rid):
    with connect() as conn: return _state(conn,source,rid)


def _check(before,expected,reason):
    reason=expenses._text(reason,'Motivo de la corrección',True)
    if token(before)!=expected: raise ValueError('El registro cambió en otra ventana. Cierra y vuelve a abrir la edición.')
    return reason


def _audit(conn,source,rid,reason,before):
    conn.execute('INSERT INTO reconciliation_events(source,record_id,reason,before_json,after_json,created_at) VALUES(?,?,?,?,?,?)',
        (source,rid,reason,_encode(before),_encode(_state(conn,source,rid)),timestamp()))


def history(source,rid):
    with connect() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM reconciliation_events WHERE source=? AND record_id=? ORDER BY id DESC',(source,rid))]


def _day(value,previous):
    if not value and not previous: return ''
    return expenses._date(value,'Fecha del movimiento')


def _sync_partner(conn,eid):
    e=dict(expenses._get(conn,eid))
    partner=conn.execute('SELECT * FROM partner_expense_settlements WHERE expense_id=?',(eid,)).fetchone()
    if partner:
        conn.execute('UPDATE capital_movements SET moved_on=?,concept=?,party=?,amount_cents=?,subtotal_cents=?,tax_cents=?,receipt=? WHERE linked_expense_id=? AND movement=\'Compra pagada por socio\'',
            (partner['paid_on'],e['concept'],e['supplier'],e['total_cents'],e['subtotal_cents'],e['tax_cents'],e['receipt_type'],eid))
    else:
        payments=conn.execute('SELECT * FROM expense_payments WHERE expense_id=? AND voided_at IS NULL',(eid,)).fetchall()
        amount=sum(p['amount_cents'] for p in payments)
        conn.execute("UPDATE capital_movements SET amount_cents=?,reimbursed_cents=? WHERE linked_expense_id=? AND movement='Reembolso al socio'",(amount,amount,eid))
        if len(payments)==1:
            conn.execute("UPDATE capital_movements SET moved_on=? WHERE linked_expense_id=? AND movement='Reembolso al socio'",(payments[0]['paid_on'] or None,eid))


def correct_expense(eid,payload,*,expected,reason,sync_payment=False,partner_day=None):
    with connect(write=True,reconciliation=True) as conn:
        before=_state(conn,'expense_document',eid)
        reason=_check(before,expected,reason)
        if before['status']!='Activo': raise ValueError('El gasto está cancelado.')
        d=expenses.normalize(payload,allow_undated=not bool(before['expense_on']))
        active=[r for r in before['payments'] if not r['voided_at']]
        partner=before['partners']
        if sync_payment and (len(active)!=1 or active[0]['amount_cents']!=before['total_cents'] or partner):
            raise ValueError('Solo se puede ajustar automáticamente un pago único que cubra el gasto completo.')
        paid=sum(p['amount_cents'] for p in active)
        if not sync_payment and not partner and paid>d['total_cents']:
            raise ValueError('El total es menor que lo pagado. Corrige primero los pagos desde Tesorería o selecciona ajustar el pago completo.')
        if partner and active: raise ValueError('Revisa los pagos del socio antes de conciliar.')
        if sync_payment:
            conn.execute('UPDATE expense_payments SET amount_cents=? WHERE id=?',(d['total_cents'],active[0]['id']))
        if partner:
            day=_day(partner_day if partner_day is not None else partner[0]['paid_on'],partner[0]['paid_on'])
            conn.execute('UPDATE partner_expense_settlements SET amount_cents=?,paid_on=? WHERE expense_id=?',(d['total_cents'],day or None,eid))
        conn.execute(f'UPDATE expenses SET {",".join(k+"=?" for k in expenses.FIELDS)},revision=revision+1,updated_at=? WHERE id=?',
            (*[d[k] for k in expenses.FIELDS],timestamp(),eid))
        _sync_partner(conn,eid)
        expenses._audit(conn,eid,'Conciliación: '+reason)
        _audit(conn,'expense_document',eid,reason,before)


def correct_movement(source,rid,payload,*,expected,reason):
    if source not in TABLES: raise ValueError('Tipo de movimiento inválido.')
    with connect(write=True,reconciliation=True) as conn:
        before=_state(conn,source,rid)
        reason=_check(before,expected,reason)
        amount=cents(payload['amount'])
        if amount<=0: raise ValueError('El importe debe ser mayor que cero.')
        aid=payload.get('account_id')
        if aid is None: raise ValueError('Selecciona la cuenta efectiva del movimiento.')
        treasury.validate_account(conn,aid)
        if source=='capital':
            if before['voided_at']: raise ValueError('La aportación está anulada; conserva su historial.')
            if before['sign']!=1 or before['linked_expense_id']:
                raise ValueError('Las compras y reembolsos se concilian desde su gasto vinculado.')
            day=_day(payload.get('paid_on'),before['moved_on'])
            values={k:expenses._text(payload.get(k,before[k]),k,k=='concept') for k in ('partner','concept','party','receipt','notes','reference')}
            conn.execute('UPDATE capital_movements SET moved_on=?,amount_cents=?,account_id=?,partner=?,concept=?,party=?,receipt=?,notes=?,reference=? WHERE id=?',
                (day or None,amount,aid,*values.values(),rid))
        else:
            if before['voided_at']: raise ValueError('El pago está anulado. Conserva su historial.')
            day=_day(payload.get('paid_on'),before['paid_on'])
            table=TABLES[source]
            owner_table,key={'expense':('expenses','expense_id'),'quote':('quotations','quote_id'),'sale':('sales','sale_id')}[source]
            oid=before[key]
            owner=conn.execute(f'SELECT * FROM {owner_table} WHERE id=?',(oid,)).fetchone()
            if owner['status'] in ('Cancelado','Cancelada'): raise ValueError('El documento está cancelado.')
            paid=conn.execute(f'SELECT COALESCE(SUM(amount_cents),0) FROM {table} WHERE {key}=? AND voided_at IS NULL AND id<>?',(oid,rid)).fetchone()[0]
            if paid+amount>owner['total_cents']: raise ValueError('El importe supera el saldo del documento. Concílialo primero en su gasto o venta.')
            linked=None
            if source=='quote':
                linked=conn.execute('SELECT * FROM sales WHERE quote_id=?',(oid,)).fetchone()
                if linked and (linked['status']=='Cancelada' or paid+amount>linked['total_cents']): raise ValueError('Revisa el saldo y estado de la venta vinculada.')
            method=expenses._text(payload.get('method',before['method']),'Método',True)
            reference=expenses._text(payload.get('reference',before['reference']),'Referencia')
            conn.execute(f'UPDATE {table} SET amount_cents=?,paid_on=?,method=?,reference=? WHERE id=?',(amount,day,method,reference,rid))
            if source=='expense':
                name=conn.execute('SELECT name FROM treasury_accounts WHERE id=?',(aid,)).fetchone()[0]
                conn.execute('UPDATE expense_payments SET account=? WHERE id=?',(name,rid))
            else:
                concept=expenses._text(payload.get('concept',before['concept']),'Concepto',True)
                conn.execute(f'UPDATE {table} SET concept=? WHERE id=?',(concept,rid))
            conn.execute('''INSERT INTO payment_accounts(source,payment_id,account_id,created_at) VALUES(?,?,?,?)
                ON CONFLICT(source,payment_id) DO UPDATE SET account_id=excluded.account_id''',(source,rid,aid,timestamp()))
            conn.execute(f'UPDATE {owner_table} SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),oid))
            if linked: conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),linked['id']))
            if source=='expense':
                _sync_partner(conn,oid)
                expenses._audit(conn,oid,'Conciliación de pago '+before['code']+': '+reason)
        _audit(conn,source,rid,reason,before)
