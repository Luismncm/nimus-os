from services import treasury, invoices
"""Sales register with explicit recognition, shared quote receipts and atomic direct payments."""
import json
from datetime import date

from db import connect
from services import quotations as q
from services.production import _code
from utils.dates import now, timestamp, parse_deadline
from services.guards import fetch, past_date as _date, same_revision
from utils.csv_export import amount, csv_bytes

CHANNELS = ('B2B', 'Venta al público', 'Online', 'Distribuidor', 'Otro')


def _get(conn, sale_id): return fetch(conn, 'sales', sale_id, 'La venta no está disponible.')


def _revision(row, expected): same_revision(row, expected, 'La venta cambió en otra ventana. Actualiza antes de guardar.')


def _insert(conn, data, sold_on, due_on, channel, request_key, quote_id=None):
    if not request_key: raise ValueError('Abre un nuevo formulario de venta.')
    sold_on = _date(sold_on, 'Fecha de venta')
    due_on = _date(due_on, 'Vencimiento', future=True) if due_on else None
    if due_on and due_on < sold_on: raise ValueError('El vencimiento no puede ser anterior a la venta.')
    channel = str(channel or '').strip()
    if channel not in CHANNELS: raise ValueError('Selecciona un canal de venta.')
    if not data['client'] or not data['lines']: raise ValueError('Indica cliente y al menos un producto o servicio.')
    payload = json.dumps(data, ensure_ascii=False)
    prior = conn.execute('SELECT * FROM sales WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if (prior['payload'],prior['sold_on'],prior['due_on'],prior['channel'],prior['quote_id']) != (payload,sold_on,due_on,channel,quote_id):
            raise ValueError('Esta captura ya se guardó con otros datos. Abre una venta nueva.')
        return prior['id']
    sid, code = _code(conn, 'sales', 'VEN')
    stamp = timestamp()
    conn.execute('''INSERT INTO sales(id,code,quote_id,payload,total_cents,sold_on,due_on,channel,request_key,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (sid,code,quote_id,payload,data['totals']['total'],sold_on,due_on,channel,request_key,stamp,stamp))
    return sid


def create_direct(payload, sold_on, due_on='', channel='Venta al público', *, request_key, invoice_required=None):
    payload = dict(payload, issued_on=str(sold_on), valid_until=str(sold_on))
    data = q.calculate(payload)
    with connect(write=True) as conn:
        sid = _insert(conn, data, sold_on, due_on, channel, request_key)
        if invoice_required is not None: invoices.initial(conn,'sale',sid,invoice_required)
        return sid


def from_quote(quote_id, sold_on, due_on='', channel='B2B', *, request_key, expected_revision, invoice_required=None):
    with connect(write=True) as conn:
        prior = conn.execute('SELECT id FROM sales WHERE quote_id=?', (quote_id,)).fetchone()
        if prior:
            if conn.execute('SELECT 1 FROM sales_trash WHERE sale_id=?',(prior['id'],)).fetchone():
                raise ValueError('La venta está en Papelera. Restáurala para continuar.')
            return prior['id']
        quote = q._get(conn, quote_id)
        q._revision(quote, expected_revision)
        if quote['status'] != 'Aceptada': raise ValueError('Acepta la cotización antes de registrar su venta.')
        sid = _insert(conn, q.calculate(json.loads(quote['payload'])), sold_on, due_on, channel, request_key, quote_id)
        from services.costing import capture_recipe_costs
        capture_recipe_costs(conn,sid)
        conn.execute('UPDATE quotations SET revision=revision+1,updated_at=? WHERE id=?', (timestamp(),quote_id))
        if invoice_required is not None: invoices.initial(conn,'sale',sid,invoice_required)
        return sid


def _rows(conn,include_deleted=False):
    return [dict(r) for r in conn.execute('''SELECT s.id,s.code,s.quote_id,s.revision,s.status,s.total_cents,
        s.sold_on,s.due_on,s.channel,s.cancel_reason,s.cancelled_at,
        json_extract(s.payload,'$.client') client,json_extract(s.payload,'$.project') project,
        q.code quote_code,q.revision quote_revision,COALESCE(q.order_id,s.order_id) order_id,
        COALESCE((SELECT SUM(amount_cents) FROM sales_payment_ledger p
            WHERE p.sale_id=s.id AND p.voided_at IS NULL),0) paid_cents
        FROM sales s LEFT JOIN quotations q ON q.id=s.quote_id
        WHERE (? OR NOT EXISTS(SELECT 1 FROM sales_trash t WHERE t.sale_id=s.id))
        ORDER BY s.sold_on DESC,s.id DESC''',(include_deleted,))]


def _decorate(row):
    row['origin'] = 'Cotización' if row['quote_id'] else 'Directa'
    row['balance_cents'] = row['total_cents'] - row['paid_cents']
    row['payment_status'] = 'Cancelada' if row['status']=='Cancelada' else 'Liquidada' if row['balance_cents']==0 else 'Pago parcial' if row['paid_cents'] else 'Por cobrar'
    row['overdue'] = bool(row['status']=='Activa' and row['balance_cents']>0 and row['due_on'] and row['due_on'] < now().date().isoformat())
    return row


def list_sales(*,include_deleted=False):
    with connect() as conn: return [_decorate(r) for r in _rows(conn,include_deleted)]


def get_sale(sale_id):
    with connect() as conn:
        stored = _get(conn, sale_id)
        row = next(r for r in _rows(conn,True) if r['id']==sale_id)
        row['deleted'] = bool(conn.execute('SELECT 1 FROM sales_trash WHERE sale_id=?',(sale_id,)).fetchone())
        row['data'] = json.loads(stored['payload'])
        row['payments'] = [dict(p) for p in conn.execute('SELECT * FROM sales_payment_ledger WHERE sale_id=? ORDER BY created_at,id', (sale_id,))]
        treasury.payment_labels(conn,'quote' if row['quote_id'] else 'sale',row['payments'])
    return _decorate(row)


def record_payment(sale_id, amount, paid_on, method, concept, reference='', *, request_key, expected_revision, expected_quote_revision=None, account_id=None):
    sale = get_sale(sale_id)
    if sale['quote_id']:
        # The quote's transaction checks its revision and the sale cancellation trigger.
        return q.record_payment(sale['quote_id'],amount,paid_on,method,concept,reference,
                                request_key=request_key,expected_revision=expected_quote_revision,account_id=account_id)
    amount = q.cents(amount)
    paid_on = _date(paid_on, 'Fecha del pago')
    if amount<=0 or not method.strip() or not concept.strip() or not request_key:
        raise ValueError('Indica monto positivo, método y concepto del pago recibido.')
    values = (sale_id,amount,paid_on,method.strip(),reference.strip(),concept.strip())
    with connect(write=True) as conn:
        prior = conn.execute('SELECT * FROM sale_payments WHERE request_key=?', (request_key,)).fetchone()
        if prior:
            if tuple(prior[k] for k in ('sale_id','amount_cents','paid_on','method','reference','concept')) != values:
                raise ValueError('Este pago ya se guardó con otros datos. Abre un registro nuevo.')
            treasury.check_retry(conn,'sale',prior['id'],account_id)
            return prior['id']
        row = _get(conn,sale_id)
        _revision(row,expected_revision)
        if row['status']!='Activa': raise ValueError('La venta está cancelada.')
        pid, code = _code(conn,'sale_payments','PAG')
        conn.execute('''INSERT INTO sale_payments(id,code,sale_id,amount_cents,paid_on,method,reference,concept,request_key,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',(pid,code,*values,request_key,timestamp()))
        conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),sale_id))
        treasury.link_payment(conn,'sale',pid,account_id)
        return pid


def void_payment(sale_id, payment_id, reason):
    if not reason.strip(): raise ValueError('Indica el motivo de la anulación.')
    sale = get_sale(sale_id)
    if not any(p['id']==payment_id for p in sale['payments']): raise ValueError('El pago no pertenece a esta venta.')
    if sale['quote_id']: return q.void_payment(payment_id,reason)
    with connect(write=True) as conn:
        row = conn.execute('SELECT * FROM sale_payments WHERE id=? AND sale_id=?',(payment_id,sale_id)).fetchone()
        if row['voided_at']: return
        conn.execute('UPDATE sale_payments SET void_reason=?,voided_at=? WHERE id=?',(reason.strip(),timestamp(),payment_id))
        conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),sale_id))


def cancel(sale_id, reason, *, expected_revision):
    if not reason.strip(): raise ValueError('Indica el motivo de cancelación.')
    with connect(write=True) as conn:
        row = _get(conn,sale_id)
        if row['status']=='Cancelada': return
        _revision(row,expected_revision)
        from services import commerce
        if commerce._profile(conn,'sale',sale_id):
            raise ValueError('Registra y resuelve la cancelación en Flujo comercial para revisar reservas y producción.')
        conn.execute("UPDATE sales SET status='Cancelada',cancel_reason=?,cancelled_at=?,updated_at=?,revision=revision+1 WHERE id=?",
                     (reason.strip(),timestamp(),timestamp(),sale_id))


def create_order(sale_id, deadline='', *, expected_revision, expected_quote_revision=None):
    sale = get_sale(sale_id)
    if sale['quote_id']:
        return q.convert_to_order(sale['quote_id'],deadline,expected_revision=expected_quote_revision)
    due = parse_deadline(deadline)
    with connect(write=True) as conn:
        row = _get(conn,sale_id)
        if row['order_id']: return row['order_id']
        _revision(row,expected_revision)
        if row['status']!='Activa': raise ValueError('La venta está cancelada.')
        d = json.loads(row['payload'])
        from services import commerce
        return commerce.draft_order(conn, 'sale', row, d, due, project=d['project'] or row['code'], note=f"Origen: {row['code']}. {d['notes']}",
            item_note=lambda line: f"{row['code']} · Define el despiece o reutiliza una receta.", missing='Esta venta no tiene partidas para fabricar.')


def report(start, end, *, search='', channel='Todos', origin='Todos', payment_status='Todos'):
    start, end = _date(start,'Desde',future=True), _date(end,'Hasta',future=True)
    if start>end: raise ValueError('Desde no puede ser posterior a Hasta.')
    with connect() as conn:
        rows = [_decorate(r) for r in _rows(conn)]
        rows = [r for r in rows if search.casefold() in f"{r['code']} {r['client']} {r['project']} {r['quote_code'] or ''}".casefold()
                and (channel=='Todos' or r['channel']==channel) and (origin=='Todos' or r['origin']==origin)
                and (payment_status=='Todos' or r['payment_status']==payment_status)]
        ids = {r['id'] for r in rows}
        receipts = [dict(p) for p in conn.execute('SELECT * FROM sales_payment_ledger WHERE voided_at IS NULL AND paid_on BETWEEN ? AND ?',(start,end)) if p['sale_id'] in ids]
        for source,label in [('quote','Cotización'),('sale','Directa')]:
            treasury.payment_labels(conn,source,[p for p in receipts if p['source']==label])
    period = [r for r in rows if start<=r['sold_on']<=end]
    active = [r for r in period if r['status']=='Activa']
    return dict(rows=period, receipts=receipts, count=len(active), sold_cents=sum(r['total_cents'] for r in active),
        paid_cents=sum(r['paid_cents'] for r in active), balance_cents=sum(r['balance_cents'] for r in active),
        collected_cents=sum(p['amount_cents'] for p in receipts),
        total_balance_cents=sum(r['balance_cents'] for r in rows if r['status']=='Activa'),
        overdue_cents=sum(r['balance_cents'] for r in rows if r['overdue']))


def export_csv(rows):
    return csv_bytes(['Folio','Fecha','Cliente','Concepto','Origen','Cotización','Canal','Estado','Cobranza','Vencimiento','Total MXN','Pagado MXN','Saldo MXN'], ([r['code'], r['sold_on'], r['client'], r['project'], r['origin'], r['quote_code'] or '', r['channel'], r['status'],
                             r['payment_status'], r['due_on'] or '', amount(r['total_cents']), amount(r['paid_cents']), amount(r['balance_cents'])] for r in rows))


def set_due_date(sale_id, due_on, *, expected_revision):
    """Set or correct when an active sale's balance is due. Without a date a balance never shows as overdue;
    the previous date stays in the sale's history."""
    with connect(write=True) as conn:
        row = _get(conn, sale_id)
        _revision(row, expected_revision)
        if row['status'] != 'Activa': raise ValueError('Solo una venta activa tiene vencimiento de pago.')
        due = _date(due_on, 'Vencimiento', future=True) if due_on else None
        if due and due < row['sold_on']: raise ValueError('El vencimiento no puede ser anterior a la venta.')
        if due == row['due_on']: return due
        stamp = timestamp()
        conn.execute('UPDATE sales SET due_on=?,revision=revision+1,updated_at=? WHERE id=?', (due, stamp, sale_id))
        conn.execute('INSERT INTO sale_events(sale_id,detail,created_at) VALUES(?,?,?)',
                     (sale_id, f"Vencimiento de pago: {row['due_on'] or 'sin fecha'} → {due or 'sin fecha'}", stamp))
        return due


def link_existing_order(sale_id,order_id,*,expected_revision,expected_quote_revision=None):
    with connect(write=True) as conn:
        row=_get(conn,sale_id)
        quote=q._get(conn,row['quote_id']) if row['quote_id'] else None
        linked=quote['order_id'] if quote else row['order_id']
        if linked==order_id:return order_id
        _revision(row,expected_revision)
        if row['status']!='Activa' or linked:raise ValueError('La venta no está activa o ya tiene otro pedido vinculado.')
        if not conn.execute('SELECT 1 FROM orders WHERE id=?',(order_id,)).fetchone():raise ValueError('El pedido no está disponible.')
        if conn.execute('SELECT 1 FROM sales WHERE order_id=?',(order_id,)).fetchone() or conn.execute('SELECT 1 FROM quotations WHERE order_id=?',(order_id,)).fetchone():
            raise ValueError('El pedido ya tiene un origen comercial vinculado.')
        if quote:
            q._revision(quote,expected_quote_revision)
            if quote['status']!='Aceptada':raise ValueError('La cotización debe estar aceptada.')
            conn.execute('UPDATE quotations SET order_id=?,revision=revision+1,updated_at=? WHERE id=?',(order_id,timestamp(),quote['id']))
        else:conn.execute('UPDATE sales SET order_id=? WHERE id=?',(order_id,sale_id))
        conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),sale_id))
        conn.execute('INSERT INTO sale_events(sale_id,detail,created_at) VALUES(?,?,?)',(sale_id,f'Venta vinculada al pedido #{order_id} para costeo y operación',timestamp()))
        return order_id
