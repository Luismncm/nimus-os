"""Versioned estimated recipe costs and frozen per-sale gross margins, in integer cents."""
import hashlib,json
from contextlib import nullcontext
from decimal import Decimal,ROUND_HALF_UP
from db import connect
from services.quotations import number
from utils.dates import timestamp

PRINT_MODE='Impresión por parámetros'
MODES=('Material + fijo','Material + máquina','Costo unitario',PRINT_MODE)
EXTRAS={'kit_cents':'Kit eléctrico','bulb_cents':'Foco','packaging_cents':'Empaque','assembly_cents':'Ensamble / mano de obra','other_cents':'Otros costos directos'}
def rounded(v):return int(Decimal(v).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def encode(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def fingerprint(v):return hashlib.sha256(encode(v).encode()).hexdigest()


def defaults():
    return dict(mode=MODES[0],grams=None,lot_units=1,lot_minutes=None,material_rate_cents=None,
                machine_rate_cents=None,fixed_cents=None,direct_cents=None,notes='')


def gram_rate(price):
    """MXN/g -> canonical cents/kg, preserving five decimals per gram."""
    return None if price is None else rounded(number(price,'Precio por gramo',maximum=10000)*100000)


def printing_inputs(*,grams,price_per_gram,minutes,hourly_rate,units=1,per_lot=False,fixed_cents=0,notes=''):
    if type(units) is not int or not 1<=units<=1000000:raise ValueError('Las piezas por lote deben ser un entero positivo.')
    weight=number(grams,'Gramos',maximum=1000000) if grams is not None else None
    duration=float(number(minutes,'Tiempo de impresión',maximum=1000000)) if minutes is not None else None
    rate=rounded(number(hourly_rate,'Tarifa por hora',maximum=10000000)*100) if hourly_rate is not None else None
    return normalize(dict(defaults(),mode=PRINT_MODE,grams=float(weight/units if per_lot else weight) if weight is not None else None,
        lot_units=units if per_lot else 1,lot_minutes=duration,material_rate_cents=gram_rate(price_per_gram),
        machine_rate_cents=rate,fixed_cents=fixed_cents,notes=notes))


def normalize(payload):
    d=defaults()|payload
    if d['mode'] not in MODES:raise ValueError('Selecciona cómo calcular el costo.')
    for key in ('grams','lot_minutes'):
        d[key]=float(number(d[key],key,maximum=1000000)) if d[key] is not None else None
    for key in ('material_rate_cents','machine_rate_cents','fixed_cents','direct_cents'):
        if d[key] is not None and (type(d[key]) is not int or not 0<=d[key]<=1000000000):raise ValueError('Revisa los importes de costo.')
    if type(d['lot_units']) is not int or not 1<=d['lot_units']<=1000000:raise ValueError('Las piezas por lote deben ser un entero positivo.')
    d['notes']=str(d['notes'] or '').strip()[:5000]
    if d['mode']==PRINT_MODE and d['fixed_cents'] is None:d['fixed_cents']=0
    return {k:d[k] for k in defaults()}


def component_amount(payload):
    d=normalize(payload);missing=[];material=machine=fixed=None
    if d['mode']=='Costo unitario':
        return dict(total_cents=d['direct_cents'],known_cents=d['direct_cents'] or 0,missing=[] if d['direct_cents'] is not None else ['Costo unitario'],material_cents=None,machine_cents=None,fixed_cents=None)
    if d['grams'] is None or d['material_rate_cents'] is None:missing.append('Gramos o precio del filamento')
    else:material=rounded(Decimal(str(d['grams']))*d['material_rate_cents']/1000)
    if d['fixed_cents'] is None:missing.append('Costo fijo por pieza')
    else:fixed=d['fixed_cents']
    if d['mode'] in ('Material + máquina',PRINT_MODE):
        if d['lot_minutes'] is None or d['machine_rate_cents'] is None:missing.append('Tiempo o tarifa de máquina')
        else:machine=rounded(Decimal(str(d['lot_minutes']))*d['machine_rate_cents']/60/d['lot_units'])
    known=sum(v for v in (material,machine,fixed) if v is not None)
    return dict(total_cents=known if not missing else None,known_cents=known,missing=missing,material_cents=material,machine_cents=machine,fixed_cents=fixed)


def _latest(conn,table,key,rid):
    row=conn.execute(f'SELECT * FROM {table} WHERE {key}=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()
    return dict(row,data=json.loads(row['payload'])) if row else None


def component_profile(cid):
    with connect() as conn:return _latest(conn,'component_cost_versions','component_id',cid)

def component_defaults(cid):
    with connect() as conn:
        row=conn.execute('SELECT supply FROM origin_components WHERE component_id=?',(cid,)).fetchone()
        component=conn.execute('SELECT process FROM catalog_components WHERE id=?',(cid,)).fetchone()
    if row and row['supply']=='Comprar':return dict(defaults(),mode='Costo unitario')
    if component and component['process'] in ('Impresión 3D','Resina'):return dict(defaults(),mode=PRINT_MODE,fixed_cents=0)
    return defaults()


def extras_profile(rid):
    with connect() as conn:return _latest(conn,'recipe_cost_extras','recipe_id',rid)


def history(kind,rid):
    tables={'component':('component_cost_versions','component_id'),'recipe':('recipe_cost_extras','recipe_id'),'sale':('sale_cost_versions','sale_id')}
    if kind not in tables:raise ValueError('Tipo de historial inválido.')
    table,key=tables[kind]
    with connect() as conn:
        return [dict(row,data=json.loads(row['payload'])) for row in conn.execute(f'SELECT * FROM {table} WHERE {key}=? ORDER BY id DESC',(rid,))]


def _save_component(conn,cid,payload,source,expected_id):
    if not conn.execute('SELECT 1 FROM catalog_components WHERE id=?',(cid,)).fetchone():raise ValueError('La pieza ya no existe.')
    prior=_latest(conn,'component_cost_versions','component_id',cid)
    if (prior['id'] if prior else None)!=expected_id:raise ValueError('El costo cambió. Vuelve a abrir el formulario.')
    d=normalize(payload)
    if not str(source).strip():raise ValueError('Indica la fuente o motivo de este costo.')
    return conn.execute('INSERT INTO component_cost_versions(component_id,payload,source,created_at) VALUES(?,?,?,?)',(cid,encode(d),str(source).strip(),timestamp())).lastrowid


def save_component(cid,payload,*,source,expected_id):
    with connect(write=True) as conn:return _save_component(conn,cid,payload,source,expected_id)


def save_extras(rid,payload,*,source,expected_id):
    with connect(write=True) as conn:
        if not conn.execute('SELECT 1 FROM recipe_versions WHERE id=?',(rid,)).fetchone():raise ValueError('La receta no existe.')
        prior=_latest(conn,'recipe_cost_extras','recipe_id',rid)
        if (prior['id'] if prior else None)!=expected_id:raise ValueError('Los costos adicionales cambiaron. Actualiza la vista.')
        d={k:payload.get(k) for k in EXTRAS}
        for v in d.values():
            if v is not None and (type(v) is not int or not 0<=v<=1000000000):raise ValueError('Revisa los costos adicionales.')
        d['notes']=str(payload.get('notes') or '').strip()[:5000]
        if not str(source).strip():raise ValueError('Indica la fuente o motivo de los costos.')
        return conn.execute('INSERT INTO recipe_cost_extras(recipe_id,payload,source,created_at) VALUES(?,?,?,?)',(rid,encode(d),str(source).strip(),timestamp())).lastrowid


def _recipe(conn,rid):
    row=conn.execute('''SELECT r.*,p.name,p.variant,p.collection FROM recipe_versions r JOIN catalog_products p ON p.id=r.product_id WHERE r.id=?''',(rid,)).fetchone()
    if not row:raise ValueError('Selecciona una receta publicada.')
    lines=[];missing=[];known=0
    extras=_latest(conn,'recipe_cost_extras','recipe_id',rid)
    extra=extras['data'] if extras else {k:None for k in EXTRAS}
    origin=conn.execute('SELECT * FROM origin_recipes WHERE recipe_id=?',(rid,)).fetchone()
    included={origin[k]:v for k,v in (('cable_id','kit_cents'),('bulb_id','bulb_cents'),('packaging_id','packaging_cents'))} if origin else {}
    for line in conn.execute('''SELECT l.*,c.name,c.material,c.variant,COALESCE(o.supply,'Fabricar') supply
      FROM recipe_lines l JOIN catalog_components c ON c.id=l.component_id
      LEFT JOIN origin_components o ON o.component_id=c.id WHERE l.recipe_id=? ORDER BY c.id''',(rid,)):
        profile=_latest(conn,'component_cost_versions','component_id',line['component_id'])
        fallback=dict(defaults(),mode='Costo unitario') if line['supply']=='Comprar' else defaults()
        amount=component_amount(profile['data'] if profile else fallback)
        source=profile['source'] if profile else 'Sin costeo'
        if line['component_id'] in included and not profile and extra.get(included[line['component_id']]) is not None:
            # Keep an earlier estimate visible once, until the supply is costed explicitly.
            amount=dict(total_cents=None,known_cents=extra[included[line['component_id']]],missing=['Confirmar costo unitario del insumo'],material_cents=None,machine_cents=None,fixed_cents=None)
            source='Referencia anterior de adicionales · confirmar costo del insumo'
        known+=amount['known_cents']*line['quantity']
        if amount['missing']:missing.append(f"{line['name']} · {line['variant']}: "+', '.join(amount['missing']))
        lines.append(dict(line,profile_id=profile['id'] if profile else None,source=source,
                          **amount,line_cents=amount['total_cents']*line['quantity'] if amount['total_cents'] is not None else None))
    for k,label in EXTRAS.items():
        if k in included.values():continue
        if extra.get(k) is None:missing.append(label)
        else:known+=extra[k]
    if not lines:missing.append('Piezas de la receta')
    result=dict(recipe=dict(row),lines=lines,extras=extra,extras_id=extras['id'] if extras else None,known_cents=known,
                total_cents=known if not missing else None,missing=missing,included_extra_keys=list(included.values()))
    result['fingerprint']=fingerprint(result)
    return result


def recipe_cost(rid):
    with connect() as conn:return _recipe(conn,rid)


def _sale(conn,sid):
    row=conn.execute('SELECT * FROM sales WHERE id=?',(sid,)).fetchone()
    if not row:raise ValueError('La venta no existe.')
    d=json.loads(row['payload'])
    # Content only: receipts, invoices and client notes do not invalidate unit-cost snapshots.
    content=dict(lines=d['lines'],totals=d['totals'])
    return dict(row),d,fingerprint(content)


def sale_context(sid,_conn=None):
    with (nullcontext(_conn) if _conn is not None else connect()) as conn:
        sale,d,fp=_sale(conn,sid)
        prior=_latest(conn,'sale_cost_versions','sale_id',sid)
        return dict(sale=sale,data=d,fingerprint=fp,prior=prior)

def capture_recipe_costs(conn,sid):
    """Freeze costs for commercially linked recipe lines once, including incomplete inputs."""
    sale,data,fp=_sale(conn,sid)
    if _latest(conn,'sale_cost_versions','sale_id',sid) or not any(l.get('recipe_id') for l in data['lines']):return
    from services.commerce import _profile
    terms=(_profile(conn,'sale',sid) or {}).get('data',{})
    rows=[]
    for line in data['lines']:
        rid=line.get('recipe_id');report=_recipe(conn,rid) if rid else None
        unit=report['total_cents'] if report else None;known=report['known_cents'] if report else 0
        if not rid and line['description']=='Envío' and terms.get('shipping_cost') is not None:
            from services.quotations import cents
            unit=known=cents(terms['shipping_cost'])
        qty=Decimal(str(line['quantity']))
        rows.append(dict(description=line['description'],quantity=line['quantity'],recipe_id=rid,recipe_snapshot=report,
            unit_cost_cents=unit,cost_cents=rounded(qty*unit) if unit is not None else None,known_cents=rounded(qty*known)))
    snapshot=dict(sale_fingerprint=fp,lines=rows,net_revenue_cents=data['totals']['subtotal']-data['totals']['discount'])
    conn.execute('INSERT INTO sale_cost_versions(sale_id,payload,source,created_at) VALUES(?,?,?,?)',
        (sid,encode(snapshot),'Costos de recetas al confirmar la venta',timestamp()))


def assign_sale(sid,assignments,*,expected_fingerprint,expected_id,source):
    with connect(write=True) as conn:
        sale,d,fp=_sale(conn,sid)
        prior=_latest(conn,'sale_cost_versions','sale_id',sid)
        if fp!=expected_fingerprint or (prior['id'] if prior else None)!=expected_id:raise ValueError('La venta o su costeo cambió. Vuelve a abrir el formulario.')
        if sale['status']!='Activa' or conn.execute('SELECT 1 FROM sales_trash WHERE sale_id=?',(sid,)).fetchone():raise ValueError('Revisa el estado de la venta.')
        if len(assignments)!=len(d['lines']):raise ValueError('Asigna un costo a cada partida.')
        if not str(source).strip():raise ValueError('Indica el motivo o referencia del costeo.')
        rows=[]
        for line,a in zip(d['lines'],assignments):
            rid=a.get('recipe_id');snapshot=None
            if rid:
                snapshot=_recipe(conn,rid)
                if a.get('recipe_fingerprint')!=snapshot['fingerprint']:raise ValueError('El costo de la receta cambió. Revisa y vuelve a guardar.')
                unit=snapshot['total_cents'];known=snapshot['known_cents']
            else:
                unit=a.get('manual_cents');known=unit or 0
                if unit is not None and (type(unit) is not int or unit<0 or unit>1000000000):raise ValueError('Revisa el costo unitario manual.')
            qty=Decimal(str(line['quantity']))
            rows.append(dict(description=line['description'],quantity=line['quantity'],recipe_id=rid,recipe_snapshot=snapshot,
                unit_cost_cents=unit,cost_cents=rounded(qty*unit) if unit is not None else None,known_cents=rounded(qty*known)))
        data=dict(sale_fingerprint=fp,lines=rows,net_revenue_cents=d['totals']['subtotal']-d['totals']['discount'])
        return conn.execute('INSERT INTO sale_cost_versions(sale_id,payload,source,created_at) VALUES(?,?,?,?)',(sid,encode(data),str(source).strip(),timestamp())).lastrowid


def sale_margin(sid,_conn=None):
    context=sale_context(sid,_conn);prior=context['prior'];data=prior['data'] if prior else None
    stale=bool(data and data['sale_fingerprint']!=context['fingerprint'])
    complete=bool(data and not stale and all(x['cost_cents'] is not None for x in data['lines']) and data['lines'])
    net=context['data']['totals']['subtotal']-context['data']['totals']['discount']
    cost=sum(x['cost_cents'] for x in data['lines']) if complete else None
    profit=net-cost if cost is not None else None
    return dict(context=context,rows=data['lines'] if data and not stale else [],stale=stale,complete=complete,
        net_revenue_cents=net,cost_cents=cost,profit_cents=profit,margin_percent=100*profit/net if profit is not None and net else None)


def job_reference(job_id):
    with connect() as conn:
        row=conn.execute('''SELECT j.id,j.code,j.quantity,j.updated_at job_revision,p.component_id,pl.* FROM production_jobs j JOIN parts p ON p.id=j.part_id
            JOIN print_plans pl ON pl.job_id=j.id WHERE j.id=?''',(job_id,)).fetchone()
        if not row or not row['component_id']:return None
        profile=_latest(conn,'component_cost_versions','component_id',row['component_id'])
        return dict(row,profile_id=profile['id'] if profile else None)


def publish_job_cost(job_id,*,expected_revision,expected_job_revision,expected_profile_id,fixed_cents,source):
    with connect(write=True) as conn:
        row=conn.execute('''SELECT j.code,j.quantity,j.updated_at job_revision,p.component_id,pl.* FROM production_jobs j JOIN parts p ON p.id=j.part_id
            JOIN print_plans pl ON pl.job_id=j.id WHERE j.id=?''',(job_id,)).fetchone()
        if not row or not row['component_id'] or row['revision']!=expected_revision or row['job_revision']!=expected_job_revision:raise ValueError('Revisa la impresión y su pieza de catálogo.')
        if any(row[k] is None for k in ('estimated_grams','duration_minutes','material_rate_cents','machine_rate_cents')):raise ValueError('Completa gramos, duración y tarifas del lote antes de reutilizar el costo.')
        payload=dict(defaults(),mode='Material + máquina',grams=row['estimated_grams']/row['quantity'],lot_units=row['quantity'],
            lot_minutes=row['duration_minutes'],material_rate_cents=row['material_rate_cents'],machine_rate_cents=row['machine_rate_cents'],fixed_cents=fixed_cents,
            notes=f"Costo estimado desde {row['code']}: gramos y tiempo del lote repartidos entre {row['quantity']} piezas.")
        return _save_component(conn,row['component_id'],payload,source,expected_profile_id)
