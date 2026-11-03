"""Commercial rules reuse the existing quote, sale, receipt and order ledgers."""
import json
from decimal import Decimal,ROUND_HALF_UP
from db import connect
from services import quotations as q,sales
from utils.dates import timestamp, parse_deadline

def defaults():
    return dict(production_authorized=False,minimum_mode='Sin mínimo',minimum_value=0.0,delivery_paid=False,
        source='',price_segment='Público',sales_owner='',production_owner='',delivery_owner='',
        delivery_method='Por definir',delivery_reference='',promised_on='',hours_per_day=None,
        purchase_days=None,assembly_minutes=None,shipping_cost=None,agreement='')

def normalize(payload,total):
    d=defaults()|payload
    if d['minimum_mode'] not in ('Sin mínimo','Porcentaje','Importe'):raise ValueError('Selecciona la condición de producción.')
    d['minimum_value']=0.0 if d['minimum_mode']=='Sin mínimo' else float(q.number(d['minimum_value'],'Anticipo',maximum=100 if d['minimum_mode']=='Porcentaje' else total/100))
    for key in ('production_authorized','delivery_paid'):
        if type(d[key]) is not bool:raise ValueError('Revisa las autorizaciones comerciales.')
    if d['delivery_method'] not in ('Por definir','Recolección','Entrega local','Paquetería'):raise ValueError('Selecciona la forma de entrega.')
    for key in ('source','price_segment','sales_owner','production_owner','delivery_owner','delivery_reference','agreement'):
        d[key]=str(d[key] or '').strip()[:3000]
    due=parse_deadline(d['promised_on']);d['promised_on']=due.isoformat() if due else ''
    for key,maximum in (('hours_per_day',24),('purchase_days',365),('assembly_minutes',10000)):
        if d[key] is not None:d[key]=float(q.number(d[key],key,maximum=maximum))
    if d['shipping_cost'] is not None:d['shipping_cost']=float(q.number(d['shipping_cost'],'Costo de envío'))
    return {k:d[k] for k in defaults()}

def owner(conn,kind,identity):
    if kind not in ('quote','sale'):raise ValueError('Documento comercial no válido.')
    if kind=='sale':
        row=sales._get(conn,identity)
        if row['quote_id']:return 'quote',row['quote_id']
    else:q._get(conn,identity)
    return kind,identity

def _profile(conn,kind,identity):
    kind,identity=owner(conn,kind,identity);field='quote_id' if kind=='quote' else 'sale_id'
    row=conn.execute(f'SELECT * FROM commercial_terms WHERE {field}=? ORDER BY id DESC LIMIT 1',(identity,)).fetchone()
    return dict(row,data=json.loads(row['payload'])) if row else None

def profile(kind,identity):
    with connect() as conn:return _profile(conn,kind,identity)

def event(conn,kind,identity,detail):
    kind,identity=owner(conn,kind,identity)
    conn.execute('INSERT INTO commercial_events(quote_id,sale_id,detail,created_at) VALUES(?,?,?,?)',
        (identity if kind=='quote' else None,identity if kind=='sale' else None,detail,timestamp()))

def _save(conn,kind,identity,payload,expected_id,reason):
    if not str(reason).strip():raise ValueError('Indica el motivo del cambio comercial.')
    kind,identity=owner(conn,kind,identity);prior=_profile(conn,kind,identity)
    if (prior['id'] if prior else None)!=expected_id:raise ValueError('Las condiciones cambiaron en otra ventana. Actualiza la vista.')
    row=q._get(conn,identity) if kind=='quote' else sales._get(conn,identity)
    data=normalize(payload,row['total_cents'])
    pk=conn.execute('INSERT INTO commercial_terms(quote_id,sale_id,payload,created_at) VALUES(?,?,?,?)',
        (identity if kind=='quote' else None,identity if kind=='sale' else None,json.dumps(data,ensure_ascii=False),timestamp())).lastrowid
    event(conn,kind,identity,'Condiciones actualizadas: '+str(reason).strip())
    return pk

def save(kind,identity,payload,*,expected_id,reason):
    with connect(write=True) as conn:return _save(conn,kind,identity,payload,expected_id,reason)

def _state(conn,kind,identity):
    kind,identity=owner(conn,kind,identity);p=_profile(conn,kind,identity)
    if kind=='quote':
        row=q._get(conn,identity);table='quotation_payments';field='quote_id'
        linked=conn.execute('SELECT status FROM sales WHERE quote_id=?',(identity,)).fetchone()
        active=row['status']!='Cancelada' and not (linked and linked['status']=='Cancelada')
    else:row=sales._get(conn,identity);table='sale_payments';field='sale_id';active=row['status']=='Activa'
    paid=conn.execute(f'SELECT COALESCE(SUM(amount_cents),0) FROM {table} WHERE {field}=? AND voided_at IS NULL',(identity,)).fetchone()[0]
    d=p['data'] if p else None;minimum=0
    if d:
        if d['minimum_mode']=='Porcentaje':minimum=int((Decimal(row['total_cents'])*Decimal(str(d['minimum_value']))/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        elif d['minimum_mode']=='Importe':minimum=q.cents(d['minimum_value'])
    pending=bool(conn.execute(f"SELECT 1 FROM commercial_requests WHERE {field}=? AND kind='Cancelación' AND state='Pendiente'",(identity,)).fetchone())
    return dict(profile=p,total_cents=row['total_cents'],paid_cents=paid,balance_cents=row['total_cents']-paid,minimum_cents=minimum,
        production_allowed=active and not pending and (not d or (d['production_authorized'] and paid>=minimum)),
        delivery_allowed=active and not pending and (not d or not d['delivery_paid'] or paid>=row['total_cents']),pending_cancellation=pending)

def state(kind,identity):
    with connect() as conn:return _state(conn,kind,identity)

def check(conn,kind,identity,stage='production'):
    status=_state(conn,kind,identity)
    if not status[stage+'_allowed']:
        if status['pending_cancellation']:raise ValueError('Hay una solicitud de cancelación pendiente. Revisa el flujo comercial.')
        raise ValueError('Revisa la autorización de producción y el anticipo acordado.' if stage=='production' else 'La condición comercial requiere liquidar el saldo antes de entregar.')

def order_source(conn,order_id):
    quote=conn.execute('SELECT id FROM quotations WHERE order_id=?',(order_id,)).fetchone()
    if quote:return 'quote',quote[0]
    sale=conn.execute('SELECT id FROM sales WHERE order_id=?',(order_id,)).fetchone()
    return ('sale',sale[0]) if sale else None

def check_order(conn,order_id,stage):
    # Early migration stages predate commercial documents and their conditions.
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='commercial_terms'").fetchone():return
    if source:=order_source(conn,order_id):check(conn,*source,stage)

def history(kind,identity):
    with connect() as conn:
        kind,identity=owner(conn,kind,identity);field='quote_id' if kind=='quote' else 'sale_id'
        return dict(events=[dict(r) for r in conn.execute(f'SELECT * FROM commercial_events WHERE {field}=? ORDER BY id DESC',(identity,))],
            requests=[dict(r) for r in conn.execute(f'SELECT * FROM commercial_requests WHERE {field}=? ORDER BY id DESC',(identity,))])

def request(kind,identity,category,detail):
    if category not in ('Cambio','Cancelación') or not str(detail).strip():raise ValueError('Indica el tipo y detalle de la solicitud.')
    with connect(write=True) as conn:
        kind,identity=owner(conn,kind,identity)
        rid=conn.execute('INSERT INTO commercial_requests(quote_id,sale_id,kind,detail,created_at) VALUES(?,?,?,?,?)',
            (identity if kind=='quote' else None,identity if kind=='sale' else None,category,str(detail).strip(),timestamp())).lastrowid
        event(conn,kind,identity,category+' solicitada: '+str(detail).strip());return rid

def resolve(request_id,resolution,*,apply_cancel=False):
    if not str(resolution).strip():raise ValueError('Describe cómo se resolvió la solicitud.')
    with connect(write=True) as conn:
        req=conn.execute('SELECT * FROM commercial_requests WHERE id=?',(request_id,)).fetchone()
        if not req:raise ValueError('La solicitud no existe.')
        if req['state']!='Pendiente':return
        kind,identity=('quote',req['quote_id']) if req['quote_id'] else ('sale',req['sale_id'])
        if apply_cancel:
            if req['kind']!='Cancelación':raise ValueError('Solo aplica la cancelación a una solicitud de ese tipo.')
            status=_state(conn,kind,identity)
            if status['paid_cents']:raise ValueError('Conserva los cobros reales. Documenta la devolución o acuerdo antes de cerrar la cancelación.')
            row=q._get(conn,identity) if kind=='quote' else sales._get(conn,identity)
            oid=row['order_id']
            if oid:
                order=conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
                started=conn.execute('''SELECT 1 FROM production_jobs j JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id
                  WHERE i.order_id=? AND (j.started_at IS NOT NULL OR j.quantity_completed>0)''',(oid,)).fetchone()
                if order['status']=='Entregado' or started:raise ValueError('El pedido ya tiene avance. Resuelve el cambio operativo antes de cancelar.')
                conn.execute('INSERT INTO order_cancellations VALUES(?,?,?)',(oid,resolution,timestamp()))
                conn.execute("UPDATE inventory_reservations SET status='Liberada',closed_at=? WHERE status='Activa' AND requirement_id IN (SELECT r.id FROM recipe_requirements r JOIN items i ON i.id=r.item_id WHERE i.order_id=?)",(timestamp(),oid))
                conn.execute("UPDATE orders SET blocked_manually=1,status='Bloqueado',updated_at=? WHERE id=?",(timestamp(),oid))
                conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',(oid,'Pedido cancelado: '+resolution,timestamp()))
            if kind=='quote':
                linked=conn.execute('SELECT id FROM sales WHERE quote_id=?',(identity,)).fetchone()
                if linked:conn.execute("UPDATE sales SET status='Cancelada',cancel_reason=?,cancelled_at=?,updated_at=?,revision=revision+1 WHERE id=?",(resolution,timestamp(),timestamp(),linked[0]))
                else:conn.execute("UPDATE quotations SET status='Cancelada',revision=revision+1,updated_at=? WHERE id=?",(timestamp(),identity))
            else:conn.execute("UPDATE sales SET status='Cancelada',cancel_reason=?,cancelled_at=?,updated_at=?,revision=revision+1 WHERE id=?",(resolution,timestamp(),timestamp(),identity))
        conn.execute('UPDATE commercial_requests SET state=?,resolution=?,resolved_at=? WHERE id=?',('Aplicada' if apply_cancel else 'Resuelta',resolution,timestamp(),request_id))
        event(conn,kind,identity,('Cancelación aplicada: ' if apply_cancel else 'Solicitud resuelta: ')+resolution)

def create_document(kind,entries,payload,terms,*,request_key):
    """Keep the cart's frozen recipe ids in the existing commercial document."""
    if kind not in ('quote','sale'):raise ValueError('Selecciona cotización o venta.')
    with connect(write=True) as conn:
        lines=[]
        for entry in entries:
            from services.recipes import positive,require_active_component
            positive(entry['quantity']);rid=entry['recipe_id'];positive(rid,'Receta')
            recipe=conn.execute('SELECT p.name FROM recipe_versions r JOIN catalog_products p ON p.id=r.product_id WHERE r.id=?',(rid,)).fetchone()
            if not recipe:raise ValueError('Una receta ya no existe.')
            for row in conn.execute('SELECT component_id FROM recipe_lines WHERE recipe_id=?',(rid,)):require_active_component(conn,row[0])
            if entry.get('price') is None:raise ValueError('Captura el precio de cada combinación para cotizar o vender.')
            lines.append(dict(description=entry.get('label') or recipe['name'],quantity=entry['quantity'],price=entry['price'],produce=True,recipe_id=rid))
        if payload.get('shipping') is not None or terms.get('shipping_cost') is not None:
            lines.append(dict(description='Envío',quantity=1,price=payload.get('shipping') or 0,produce=False))
        data=q.defaults();data.update({k:v for k,v in payload.items() if k in data})
        data.update(lines=lines,payment_terms='Producción sujeta a autorización y condiciones registradas en el flujo comercial.',conditions=terms.get('agreement',''))
        data=q.calculate(data);terms=normalize(terms,data['totals']['total'])
        if not data['client'] or not data['lines']:raise ValueError('Indica cliente y combinaciones.')
        if not request_key:raise ValueError('Abre una captura nueva.')
        signature=json.dumps([data,terms,payload.get('due_on',''),payload.get('channel','Venta al público')],sort_keys=True,ensure_ascii=False)
        prior=conn.execute('SELECT * FROM commercial_document_requests WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['kind']!=kind or prior['signature']!=signature:raise ValueError('Esta captura ya guardó otro documento. Inicia una nueva.')
            return prior['quote_id'] if kind=='quote' else prior['sale_id']
        if kind=='sale':
            identity=sales._insert(conn,data,data['issued_on'],payload.get('due_on',''),payload.get('channel','Venta al público'),request_key)
        else:
            from services.production import _code
            identity,code=_code(conn,'quotations','COT');stamp=timestamp()
            conn.execute('INSERT INTO quotations(id,code,payload,total_cents,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                (identity,code,json.dumps(data,ensure_ascii=False),data['totals']['total'],stamp,stamp))
        prior=_profile(conn,kind,identity)
        if not prior:_save(conn,kind,identity,terms,None,'Condiciones iniciales del carrito')
        if kind=='sale':
            from services.costing import capture_recipe_costs
            capture_recipe_costs(conn,identity)
        conn.execute('INSERT INTO commercial_document_requests VALUES(?,?,?,?,?)',
            (request_key,kind,identity if kind=='quote' else None,identity if kind=='sale' else None,signature))
        event(conn,kind,identity,f'Carrito guardado: {sum(e["quantity"] for e in entries)} lámparas en {len(entries)} combinaciones.')
        return identity


def draft_order(conn, kind, row, data, due, *, project, note, item_note, missing, need_client=False):
    """The order of an accepted quote or a sale, saved with it: its recipes and joint reservations when the
    lines come from the catalog, else a draft with one item per line to make. The document then points to it."""
    from services import recipe_cart
    from services.production import _code
    from utils.dates import parse_deadline
    table = {'quote': 'quotations', 'sale': 'sales'}[kind]
    check(conn, kind, row['id'])
    due = due or parse_deadline((_profile(conn, kind, row['id']) or {}).get('data', {}).get('promised_on', ''))
    deadline = due.isoformat() if due else None
    prepared = recipe_cart.from_commercial(conn, data, code=row['code'], deadline=deadline or '')
    stamp = timestamp()
    if prepared:
        conn.execute(f'UPDATE {table} SET order_id=?,revision=revision+1,updated_at=? WHERE id=?', (prepared, stamp, row['id']))
        conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)', (prepared, f"Pedido desde {row['code']} con recetas y reservas conjuntas.", stamp))
        return prepared
    lines = [line for line in data['lines'] if line['produce']]
    if not lines or (need_client and not data['client']): raise ValueError(missing)
    oid, code = _code(conn, 'orders', 'ORD')
    conn.execute('''INSERT INTO orders(id,code,project,client,deadline,priority,status,notes,created_at,updated_at)
        VALUES(?,?,?,?,?,'Media','Pendiente',?,?,?)''', (oid, code, project, data['client'], deadline, note, stamp, stamp))
    for line in lines:
        conn.execute('INSERT INTO items(order_id,name,quantity,notes,created_at) VALUES(?,?,?,?,?)',
                     (oid, line['description'], int(line['quantity']), item_note(line), stamp))
    conn.execute(f'UPDATE {table} SET order_id=?,revision=revision+1,updated_at=? WHERE id=?', (oid, stamp, row['id']))
    conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)', (oid, f"Pedido creado desde {row['code']}. Despiece pendiente.", stamp))
    return oid
