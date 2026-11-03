import json
from db import connect
from services import consumption
from services.quotations import cents
from utils.dates import timestamp

COST_TYPES=('Mano de obra','Empaque','Envío','Servicio externo','Inventario utilizado','Otro')

def extras(order_id):
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT c.*,e.code expense_code,e.status expense_status,
            e.subtotal_cents expense_subtotal,e.total_cents expense_total FROM order_extra_costs c
            LEFT JOIN expenses e ON e.id=c.expense_id WHERE c.order_id=? ORDER BY c.id DESC''',(order_id,))]

def add(order_id,concept,cost_type,amount=0,expense_id=None,*,request_key,expected_expense_revision=None):
    concept=str(concept or '').strip()
    if not concept or len(concept)>500 or cost_type not in COST_TYPES or not request_key:raise ValueError('Indica concepto y tipo de costo.')
    money=cents(amount)
    signature=json.dumps([order_id,concept,cost_type,money,expense_id],ensure_ascii=False)
    with connect(write=True) as conn:
        prior=conn.execute('SELECT id,signature FROM order_extra_costs WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['signature']!=signature:raise ValueError('Esta captura ya se guardó con otros datos.')
            return prior['id']
        if not conn.execute('SELECT 1 FROM orders WHERE id=?',(order_id,)).fetchone():raise ValueError('El pedido no está disponible.')
        if expense_id is not None:
            expense=conn.execute('SELECT * FROM expenses WHERE id=?',(expense_id,)).fetchone()
            if not expense or expense['order_id']!=order_id or expense['status']!='Activo' or expense['revision']!=expected_expense_revision:
                raise ValueError('El gasto cambió o no corresponde a este pedido. Actualiza la selección.')
            if conn.execute("SELECT 1 FROM order_extra_costs WHERE expense_id=? AND status='Activo'",(expense_id,)).fetchone():raise ValueError('Este gasto ya está incluido como costo adicional.')
            money=expense['subtotal_cents'] if expense['subtotal_cents'] is not None else expense['total_cents']
        return conn.execute('''INSERT INTO order_extra_costs(order_id,concept,cost_type,amount_cents,expense_id,request_key,signature,created_at)
            VALUES(?,?,?,?,?,?,?,?)''',(order_id,concept,cost_type,money,expense_id,request_key,signature,timestamp())).lastrowid

def void(identity,reason):
    if not str(reason or '').strip():raise ValueError('Indica el motivo de la anulación.')
    with connect(write=True) as conn:
        conn.execute("UPDATE order_extra_costs SET status='Anulado',void_reason=? WHERE id=? AND status='Activo'",(reason.strip(),identity))

def reports(snapshot):
    with connect() as conn:
        actual={j['id']:consumption._get(conn,j['id']) for j in snapshot['jobs']}
        sale_rows=[dict(r) for r in conn.execute('''SELECT s.*,COALESCE(q.order_id,s.order_id) related_order FROM sales s
            LEFT JOIN quotations q ON q.id=s.quote_id WHERE s.status='Activa'
            AND NOT EXISTS(SELECT 1 FROM sales_trash t WHERE t.sale_id=s.id)''')]
        extra_rows=[dict(r) for r in conn.execute('''SELECT c.*,e.status expense_status,e.subtotal_cents expense_subtotal,
            e.total_cents expense_total FROM order_extra_costs c LEFT JOIN expenses e ON e.id=c.expense_id WHERE c.status='Activo' ''')]
        from services import consumables
        supplies=consumables.by_order(conn)
    result=[]
    for order in snapshot['orders']:
        jobs=[j for j in snapshot['jobs'] if j['order_id']==order['id']]
        rows=[r for r in extra_rows if r['order_id']==order['id']]
        # A development project is a cost, never a sale: no revenue is matched, so no margin is shown.
        revenue=0;revenue_known=True;matched=[] if order.get('development') else [r for r in sale_rows if r['related_order']==order['id']]
        for sale in matched:
            total=json.loads(sale['payload']).get('totals',{})
            if 'subtotal' not in total or 'discount' not in total:revenue_known=False
            else:revenue+=total['subtotal']-total['discount']
        extra_total=0;tax_unknown=False;unavailable=0;stock_cost=False
        for row in rows:
            if row['expense_id'] is not None:
                if row['expense_status']!='Activo':unavailable+=1;continue
                value=row['expense_subtotal'] if row['expense_subtotal'] is not None else row['expense_total']
                tax_unknown|=row['expense_subtotal'] is None
            else:value=row['amount_cents']
            extra_total+=value
            if row['cost_type']=='Inventario utilizado':stock_cost=True
        stock_units=sum(r.get('from_stock',0) for i in order['items'] for r in i.get('requirements',[]))
        missing_stock=stock_units>0 and not stock_cost
        known=sum((actual[j['id']]['material_cost_cents'] or 0)+(actual[j['id']]['machine_cost_cents'] or 0) for j in jobs)
        used=supplies.get(order['id'],dict(cost_cents=0,unknown=0,rows=[]))
        complete=all(actual[j['id']]['complete'] for j in jobs) and not tax_unknown and not unavailable and not missing_stock
        # A consumable used without a known cost keeps the margin provisional, like any missing cost.
        complete&=not used['unknown']
        # Orders without a defined scope cannot silently show a complete margin.
        complete&=bool(order['required_total'] and not order['undefined_items'] and order['remaining_total']==0)
        total=known+extra_total+used['cost_cents']
        result.append(dict(order_id=order['id'],code=order['code'],project=order['project'],client=order['client'],status=order['status'],
            development=bool(order.get('development')),
            revenue_cents=revenue if matched and revenue_known else None,production_actual_cents=known,extras_cents=extra_total,actual_known_cents=total,
            consumables_cents=used['cost_cents'],consumables_unknown=used['unknown'],consumables=used['rows'],
            estimated_cents=sum(j['estimated_cost_cents'] or 0 for j in jobs),costed_jobs=sum(actual[j['id']]['complete'] for j in jobs),job_count=len(jobs),
            complete=bool(complete),scope_unfinished=bool(order['remaining_total'] or order['undefined_items'] or not order['required_total']),tax_unknown=tax_unknown,unavailable_expenses=unavailable,stock_units=stock_units,missing_stock_cost=missing_stock,
            margin_cents=revenue-total if complete and matched and revenue_known else None,
            margin_percent=(revenue-total)/revenue*100 if complete and matched and revenue_known and revenue>0 else None,
            jobs=[dict(j,consumption=actual[j['id']]) for j in jobs]))
    return result
