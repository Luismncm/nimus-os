"""One pooled stock plan and one atomic production order for a recipe basket."""
import hashlib,json
from db import connect
from services import recipes as r
from utils.dates import timestamp,parse_deadline

def _quote(conn,entries,use_stock=True):
    if not isinstance(use_stock,bool) or not entries or len(entries)>100:raise ValueError('Agrega entre 1 y 100 combinaciones al pedido.')
    plans=[];pool={}
    for entry in entries:
        rid=entry['recipe_id'];qty=entry['quantity']
        r.positive(rid,'Receta');r.positive(qty,'Lámparas')
        plan=r._quote(conn,rid,qty,use_stock)
        for row in plan['lines']:
            r.require_active_component(conn,row['component_id'])
            remaining=row['needed'];allocations=[]
            for stock in r._stock(conn,row['component_id']):
                key=(stock['sku_id'],stock['location'])
                pool.setdefault(key,stock['quantity'])
                amount=min(remaining,pool[key]) if use_stock else 0
                if amount:
                    allocations.append(dict(stock,quantity=amount));pool[key]-=amount;remaining-=amount
            row.update(reserved=row['needed']-remaining,allocations=allocations,
                to_make=remaining if row['supply']=='Fabricar' else 0,to_buy=remaining if row['supply']=='Comprar' else 0)
        plan.pop('fingerprint',None);plans.append(plan)
    result=dict(entries=plans,use_stock=use_stock)
    result['fingerprint']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result

def quote(entries,use_stock=True):
    with connect() as conn:return _quote(conn,entries,use_stock)

def _item(conn,oid,plan):
    recipe=plan['recipe'];stamp=timestamp()
    spec=conn.execute('SELECT o.model,b.color FROM origin_recipes o JOIN origin_base_sets b ON b.id=o.base_set_id WHERE recipe_id=?',(recipe['id'],)).fetchone()
    label=f"{spec['model']} · {spec['color']}" if spec else recipe['name']
    iid=conn.execute('''INSERT INTO items(order_id,name,quantity,notes,created_at,collection,recipe_id)
      VALUES(?,?,?,?,?,?,?)''',(oid,label,plan['quantity'],f"Receta v{recipe['version']} · componentes",stamp,
        'Origen' if recipe['collection']=='Origen' else '',recipe['id'])).lastrowid
    for row in plan['lines']:
        part=None
        if row['to_make']:
            part=conn.execute('''INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at,component_id)
              VALUES(?,?,?,?,?,?,?,?)''',(iid,row['name'],row['to_make'],row['process'],row['material'],'Faltante de receta · '+row['variant'],stamp,row['component_id'])).lastrowid
        need=conn.execute('INSERT INTO recipe_requirements(item_id,component_id,quantity,production_part_id) VALUES(?,?,?,?)',
            (iid,row['component_id'],row['needed'],part)).lastrowid
        for stock in row['allocations']:r._reserve(conn,need,stock['sku_id'],stock['location'],stock['quantity'])
    return iid

def _create(conn,entries,*,client,project='',deadline='',priority='Media',fulfillment='Cliente',use_stock=True,expected_fingerprint=None,request_key=None):
    from services.production import _code,_choice,refresh_order
    from models.constants import PRIORITIES
    _choice(priority,PRIORITIES,'Prioridad')
    if fulfillment not in ('Cliente','Stock') or (fulfillment=='Cliente' and not str(client).strip()):raise ValueError('Indica cliente y destino del pedido.')
    due=parse_deadline(deadline)
    signature=json.dumps([entries,str(client).strip(),str(project).strip(),deadline,priority,fulfillment,use_stock],sort_keys=True,ensure_ascii=False)
    if request_key:
        prior=conn.execute('SELECT * FROM recipe_order_requests WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['signature']!=signature:raise ValueError('Esta solicitud ya creó otro pedido. Inicia una captura nueva.')
            return prior['order_id']
    plan=_quote(conn,entries,use_stock)
    if expected_fingerprint and expected_fingerprint!=plan['fingerprint']:raise ValueError('Las existencias cambiaron. Actualiza el plan del pedido.')
    oid,code=_code(conn,'orders','ORD');stamp=timestamp()
    conn.execute('''INSERT INTO orders(id,code,project,client,deadline,priority,status,notes,created_at,updated_at,fulfillment)
      VALUES(?,?,?,?,?,?,'Pendiente',?,?,?,?)''',(oid,code,str(project).strip() or f"Lámparas · {sum(e['quantity'] for e in entries)} unidades",
        str(client).strip(),due.isoformat() if due else None,priority,'Pedido conjunto desde recetas. Ensamble y revisión pendientes.',stamp,stamp,fulfillment))
    for entry in plan['entries']:_item(conn,oid,entry)
    refresh_order(conn,oid)
    if request_key:conn.execute('INSERT INTO recipe_order_requests VALUES(?,?,?)',(request_key,oid,signature))
    return oid

def create_order(entries,**kwargs):
    with connect(write=True) as conn:return _create(conn,entries,**kwargs)

def from_commercial(conn,data,*,code,deadline=''):
    """Return None for the legacy free-form path; keep mixed recipe/manual lines together."""
    lines=[l for l in data['lines'] if l['produce']]
    entries=[dict(recipe_id=l['recipe_id'],quantity=int(l['quantity'])) for l in lines if l.get('recipe_id')]
    if not entries:return None
    oid=_create(conn,entries,client=data['client'],project=data['project'] or code,deadline=deadline)
    stamp=timestamp()
    for line in lines:
        if not line.get('recipe_id'):
            conn.execute('INSERT INTO items(order_id,name,quantity,notes,created_at) VALUES(?,?,?,?,?)',
                (oid,line['description'],int(line['quantity']),f'{code} · Despiece pendiente',stamp))
    from services.production import refresh_order
    refresh_order(conn,oid)
    return oid
