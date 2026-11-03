"""Complete lamps share shades, matched base sets and purchased supplies."""
from db import connect
from services import recipes
from services.catalog import clean
from utils.dates import timestamp

ROLES=('Pantalla','Base','CAP','Tapa','Cable','Foco','Empaque')
PURCHASED=('Cable','Foco','Empaque')
EXTRA_ROLES={'Cable':'kit_cents','Foco':'bulb_cents','Empaque':'packaging_cents'}
BASE_MODEL='Base Origen'

def _base_model(conn):
    conn.execute('INSERT OR IGNORE INTO origin_base_models(name,created_at) VALUES(?,?)',(BASE_MODEL,timestamp()))
    return conn.execute('SELECT id FROM origin_base_models WHERE name=?',(BASE_MODEL,)).fetchone()[0]

def normalize_definitions(conn):
    """Group existing colors under one base model and retire the shapeless legacy shade."""
    model_id=_base_model(conn)
    conn.execute('''INSERT OR IGNORE INTO origin_base_colors(base_set_id,model_id)
      SELECT id,? FROM origin_base_sets''',(model_id,))
    for row in conn.execute('''SELECT c.id,c.material,c.variant FROM origin_components o
      JOIN catalog_components c ON c.id=o.component_id WHERE o.role='Pantalla' AND trim(o.shape)='' ''').fetchall():
        if 'IVORY' in row['material'].upper() and row['variant'].strip().upper() in ('','IVORY','PLA IVORY'):
            conn.execute('INSERT OR IGNORE INTO catalog_component_retirements VALUES(?,?,?)',
                (row['id'],'Referencia genérica PLA IVORY sustituida por los modelos de pantalla.',timestamp()))

def _register(conn,cid,role,color='',shape=''):
    if role not in ROLES:raise ValueError('Tipo de componente Origen no válido.')
    old=conn.execute('SELECT * FROM origin_components WHERE component_id=?',(cid,)).fetchone()
    values=(role,'Comprar' if role in PURCHASED else 'Fabricar',clean(color),clean(shape))
    if old:
        if recipes.identity(*[old[k] for k in ('role','supply','color','shape')])!=recipes.identity(*values):raise ValueError('Este componente ya tiene otra definición Origen.')
        return
    conn.execute('INSERT INTO origin_components VALUES(?,?,?,?,?)',(cid,*values))

def create_component(role,*,material='',color='',shape='',variant=''):
    if role not in ROLES:raise ValueError('Selecciona un componente Origen.')
    if role not in PURCHASED and not clean(material):raise ValueError('Indica el material de la pieza.')
    if role=='Pantalla' and not clean(shape):raise ValueError('Indica el modelo o forma de la pantalla.')
    if role in ('Base','CAP','Tapa') and not clean(color):raise ValueError('Indica el color de la base.')
    with connect(write=True) as conn:
        label=' · '.join(v for v in (clean(shape),clean(color),clean(variant)) if v) or 'Estándar'
        cid=recipes._component(conn,role.upper(),material,'Empaque' if role=='Empaque' else 'Ensamble' if role in PURCHASED else 'Impresión 3D',label,'Origen')
        _register(conn,cid,role,color,shape);return cid

def _base_set(conn,base_id,cap_id,lid_id,name=''):
    rows=[]
    for cid,role in zip((base_id,cap_id,lid_id),('Base','CAP','Tapa')):
        recipes.require_active_component(conn,cid)
        row=conn.execute('SELECT o.*,c.material FROM origin_components o JOIN catalog_components c ON c.id=o.component_id WHERE component_id=?',(cid,)).fetchone()
        if not row or row['role']!=role:raise ValueError('Selecciona base, CAP y tapa compatibles.')
        rows.append(row)
    if not rows[0]['color'] or len({recipes.identity(r['color'],r['material']) for r in rows})!=1:
        raise ValueError('Base, CAP y tapa deben compartir color y material.')
    old=conn.execute('SELECT id FROM origin_base_sets WHERE base_id=? AND cap_id=? AND lid_id=?',(base_id,cap_id,lid_id)).fetchone()
    bid=old[0] if old else conn.execute('INSERT INTO origin_base_sets(name,color,material,base_id,cap_id,lid_id,created_at) VALUES(?,?,?,?,?,?,?)',
        (clean(name) or rows[0]['color'],rows[0]['color'],rows[0]['material'],base_id,cap_id,lid_id,timestamp())).lastrowid
    conn.execute('INSERT OR IGNORE INTO origin_base_colors VALUES(?,?)',(bid,_base_model(conn)))
    return bid

def create_base_set(color,material):
    color=clean(color);material=clean(material)
    if not color or not material:raise ValueError('Indica color y material de la base.')
    with connect(write=True) as conn:
        ids=[]
        for role in ('Base','CAP','Tapa'):
            cid=recipes._component(conn,role.upper(),material,'Impresión 3D',color,'Origen')
            _register(conn,cid,role,color);ids.append(cid)
        return _base_set(conn,*ids)

def spec_from_lines(conn,lines,*,required=False):
    ids={line['component_id']:line['quantity'] for line in lines}
    for cid in ids:recipes.require_active_component(conn,cid)
    rows=[dict(r) for r in conn.execute('SELECT * FROM origin_components') if r['component_id'] in ids]
    if not required and len(rows)!=7:return None
    if len(ids)!=7 or len(rows)!=7 or set(r['role'] for r in rows)!=set(ROLES) or any(q!=1 for q in ids.values()):
        raise ValueError('Una lámpara lleva 1 pantalla, 1 base, 1 CAP, 1 tapa, 1 cable, 1 foco y 1 empaque.')
    by_role={r['role']:r for r in rows}
    if not by_role['Pantalla']['shape']:raise ValueError('Selecciona un modelo de pantalla con forma definida.')
    base_set=_base_set(conn,*[by_role[k]['component_id'] for k in ('Base','CAP','Tapa')])
    return dict(model=by_role['Pantalla']['shape'] or 'Lámpara',shade_id=by_role['Pantalla']['component_id'],base_set_id=base_set,
        cable_id=by_role['Cable']['component_id'],bulb_id=by_role['Foco']['component_id'],packaging_id=by_role['Empaque']['component_id'])

def attach(conn,rid,spec):
    conn.execute('INSERT INTO origin_recipes VALUES(?,?,?,?,?,?,?)',(rid,*[spec[k] for k in ('model','shade_id','base_set_id','cable_id','bulb_id','packaging_id')]))

def publish_lamp(product_id,*,name,shade_id,base_set_id,cable_id,bulb_id,packaging_id,expected_recipe_id,notes=''):
    with connect(write=True) as conn:
        return _publish_lamp(conn,product_id,name=name,shade_id=shade_id,base_set_id=base_set_id,cable_id=cable_id,
            bulb_id=bulb_id,packaging_id=packaging_id,expected_recipe_id=expected_recipe_id,notes=notes)

def _publish_lamp(conn,product_id,*,name,shade_id,base_set_id,cable_id,bulb_id,packaging_id,expected_recipe_id,notes=''):
    base=conn.execute('SELECT * FROM origin_base_sets WHERE id=?',(base_set_id,)).fetchone()
    if not base:raise ValueError('Selecciona un juego de base.')
    ids=[shade_id,base['base_id'],base['cap_id'],base['lid_id'],cable_id,bulb_id,packaging_id]
    lines=[dict(component_id=cid,quantity=1) for cid in ids]
    spec=spec_from_lines(conn,lines,required=True)
    if product_id is None:
        for row in conn.execute('''SELECT r.id FROM recipe_versions r JOIN origin_recipes o ON o.recipe_id=r.id
          WHERE r.id=(SELECT id FROM recipe_versions WHERE product_id=r.product_id ORDER BY version DESC LIMIT 1)''').fetchall():
            existing={r['component_id']:r['quantity'] for r in conn.execute('SELECT component_id,quantity FROM recipe_lines WHERE recipe_id=?',(row[0],))}
            if existing=={cid:1 for cid in ids}:raise ValueError('Esta combinación ya tiene receta. Selecciónala en Colección Origen.')
        if conn.execute('SELECT 1 FROM catalog_products WHERE identity_key=?',(recipes.identity(name,base['color'],'Origen'),)).fetchone():
            raise ValueError('Ya existe ese producto y color. Selecciónalo para publicar otra versión.')
        product_id=recipes._product(conn,name,base['color'],'Origen')
    product=conn.execute('SELECT * FROM catalog_products WHERE id=?',(product_id,)).fetchone()
    if not product or product['collection']!='Origen':raise ValueError('Selecciona un producto de Colección Origen.')
    prior=conn.execute('SELECT id FROM recipe_versions WHERE product_id=? ORDER BY version DESC LIMIT 1',(product_id,)).fetchone()
    old=prior[0] if prior else None
    if old!=expected_recipe_id:raise ValueError('La receta cambió en otra ventana. Abre nuevamente su configuración.')
    previous=conn.execute('SELECT base_set_id FROM origin_recipes WHERE recipe_id=?',(old,)).fetchone() if old else None
    if previous and previous[0]!=base_set_id:raise ValueError('Para otro juego de base crea una lámpara nueva y conserva la variante anterior.')
    rid=recipes._publish(conn,product_id,lines,notes or 'Lámpara completa · pantalla, juego de base e insumos.')
    if not conn.execute('SELECT 1 FROM origin_recipes WHERE recipe_id=?',(rid,)).fetchone():attach(conn,rid,spec)
    if old:copy_extras(conn,old,rid)
    return product_id

def complete_combinations():
    """Explicit, atomic and repeatable setup of missing screen/base recipes, without stock."""
    with connect(write=True) as conn:
        components=[dict(r) for r in conn.execute('''SELECT o.*,c.variant FROM origin_components o
          JOIN catalog_components c ON c.id=o.component_id
          WHERE NOT EXISTS(SELECT 1 FROM catalog_component_retirements x WHERE x.component_id=c.id)''')]
        shades=[c for c in components if c['role']=='Pantalla' and c['shape']]
        bases=[dict(r) for r in conn.execute('SELECT * FROM origin_base_sets ORDER BY id')]
        pairs={(r['shade_id'],r['base_set_id']) for r in conn.execute('''SELECT o.* FROM origin_recipes o
          JOIN recipe_versions r ON r.id=o.recipe_id WHERE r.id=(SELECT id FROM recipe_versions
          WHERE product_id=r.product_id ORDER BY version DESC LIMIT 1)''')}
        missing=[(shade,base) for shade in shades for base in bases if (shade['component_id'],base['id']) not in pairs]
        supplies={}
        if missing:
            for role,field in (('Cable','cable_id'),('Foco','bulb_id'),('Empaque','packaging_id')):
                choices=[c for c in components if c['role']==role]
                standard=[c for c in choices if c['variant'].casefold()=='estándar']
                selected=choices if len(choices)==1 else standard
                if len(selected)!=1:raise ValueError(f'Define una referencia estándar de {role.lower()} para completar las combinaciones.')
                supplies[field]=selected[0]['component_id']
        created=[]
        for shade,base in missing:
            pid=_publish_lamp(conn,None,name=f"{shade['shape']} · {base['color']}",shade_id=shade['component_id'],
                base_set_id=base['id'],expected_recipe_id=None,notes='Receta para pedido por modelo y color de base.',**supplies)
            created.append(pid)
        return dict(created=created,total=len(shades)*len(bases))

def copy_extras(conn,old,new):
    if conn.execute('SELECT 1 FROM recipe_cost_extras WHERE recipe_id=?',(new,)).fetchone():return
    prior=conn.execute('SELECT payload,source FROM recipe_cost_extras WHERE recipe_id=? ORDER BY id DESC LIMIT 1',(old,)).fetchone()
    if prior:conn.execute('INSERT INTO recipe_cost_extras(recipe_id,payload,source,created_at) VALUES(?,?,?,?)',(new,prior['payload'],'Referencia anterior · '+prior['source'],timestamp()))

def bootstrap(conn):
    """Bridge only unambiguous existing four-piece Origen lamps, append-only."""
    aliases={'BASE':'Base','CAP':'CAP','TAPA':'Tapa','PANTALLA':'Pantalla'}
    for row in conn.execute("SELECT * FROM catalog_components WHERE collection='Origen'").fetchall():
        if conn.execute('SELECT 1 FROM origin_components WHERE component_id=?',(row['id'],)).fetchone():continue
        role=aliases.get(row['name'].strip().upper())
        if role:
            shape=row['variant'] if role=='Pantalla' and row['variant'].strip().upper() not in ('','IVORY') else ''
            _register(conn,row['id'],role,'IVORY' if role=='Pantalla' and 'IVORY' in row['material'].upper() else row['variant'] if role!='Pantalla' else '',shape)
    normalize_definitions(conn)
    components=[dict(r) for r in conn.execute('SELECT o.*,c.material FROM origin_components o JOIN catalog_components c ON c.id=o.component_id')]
    for base in (r for r in components if r['role']=='Base'):
        caps=[r for r in components if r['role']=='CAP' and recipes.identity(r['color'],r['material'])==recipes.identity(base['color'],base['material'])]
        lids=[r for r in components if r['role']=='Tapa' and recipes.identity(r['color'],r['material'])==recipes.identity(base['color'],base['material'])]
        if len(caps)==len(lids)==1:_base_set(conn,base['component_id'],caps[0]['component_id'],lids[0]['component_id'])
    eligible=[]
    for product in conn.execute("SELECT * FROM catalog_products WHERE collection='Origen'").fetchall():
        latest=conn.execute('SELECT id FROM recipe_versions WHERE product_id=? ORDER BY version DESC LIMIT 1',(product['id'],)).fetchone()
        if not latest:continue
        rows=[dict(r) for r in conn.execute('''SELECT l.*,o.role FROM recipe_lines l
          LEFT JOIN origin_components o ON o.component_id=l.component_id WHERE recipe_id=?
          AND NOT EXISTS(SELECT 1 FROM catalog_component_retirements x WHERE x.component_id=l.component_id)''',(latest[0],))]
        if len(rows)!=4 or {r['role'] for r in rows}!={'Pantalla','Base','CAP','Tapa'} or any(r['quantity']!=1 for r in rows):continue
        by={r['role']:r['component_id'] for r in rows}
        base=conn.execute('SELECT * FROM origin_base_sets WHERE base_id=? AND cap_id=? AND lid_id=?',(by['Base'],by['CAP'],by['Tapa'])).fetchone()
        if base:eligible.append((product['id'],latest[0],rows))
    if not eligible:return
    supplies=[]
    for role in PURCHASED:
        cid=recipes._component(conn,role.upper(),'Insumo eléctrico' if role!='Empaque' else 'Empaque','Empaque' if role=='Empaque' else 'Ensamble','Estándar','Origen')
        _register(conn,cid,role);supplies.append(dict(component_id=cid,quantity=1))
    for pid,old,rows in eligible:
        lines=[dict(component_id=r['component_id'],quantity=1) for r in rows]+supplies
        spec=spec_from_lines(conn,lines,required=True)
        rid=recipes._publish(conn,pid,lines,'Colección Origen · receta completa con cable, foco y empaque. Se conserva la receta anterior.')
        attach(conn,rid,spec);copy_extras(conn,old,rid)

def load():
    with connect() as conn:
        components=[dict(r) for r in conn.execute('''SELECT c.*,o.role,o.supply,o.color,o.shape
          FROM origin_components o JOIN catalog_components c ON c.id=o.component_id
          WHERE NOT EXISTS(SELECT 1 FROM catalog_component_retirements x WHERE x.component_id=c.id)
          ORDER BY o.role,c.material,c.variant''')]
        bases=[dict(r) for r in conn.execute('''SELECT b.*,m.id model_id,m.name model_name FROM origin_base_sets b
          JOIN origin_base_colors v ON v.base_set_id=b.id JOIN origin_base_models m ON m.id=v.model_id ORDER BY b.color''')]
        base_models=[dict(r) for r in conn.execute('SELECT * FROM origin_base_models ORDER BY name')]
        specs={r['recipe_id']:dict(r) for r in conn.execute('SELECT * FROM origin_recipes')}
    catalog=recipes.load_catalog()
    products=[dict(p,origin=specs.get(p['recipe_id'])) for p in catalog['products'] if p['collection']=='Origen']
    shade_models=sorted({c['shape'] for c in components if c['role']=='Pantalla' and c['shape']})
    return dict(components=components,bases=bases,base_models=base_models,shade_models=shade_models,specs=specs,products=products,catalog=catalog)

def reserve_supplies(order_id):
    from services.production import _editable,refresh_order
    with connect(write=True) as conn:
        _editable(conn,order_id);total=0
        for need in recipes.load_requirements(conn):
            if need['order_id']!=order_id or need['supply']!='Comprar':continue
            remaining=need['quantity']-need['covered']
            for stock in recipes._stock(conn,need['component_id']):
                amount=min(remaining,stock['quantity'])
                if amount:recipes._reserve(conn,need['id'],stock['sku_id'],stock['location'],amount);total+=amount;remaining-=amount
        if total:
            refresh_order(conn,order_id)
            conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',(order_id,f'Origen · {total} insumos reservados desde existencias',timestamp()))
        return total
