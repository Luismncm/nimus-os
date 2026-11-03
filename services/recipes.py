"""Catalog, frozen recipes, shortage planning and physical inventory reservations."""
import hashlib
import json

from db import connect
from models.constants import PROCESSES
from services.catalog import clean
from utils.dates import timestamp


def positive(value, label='Cantidad'):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{label} debe ser un entero mayor que cero.')
    return value


def identity(*values):
    return json.dumps([clean(value).casefold() for value in values], ensure_ascii=False)


def require_active_component(conn,component_id):
    if conn.execute('SELECT 1 FROM catalog_component_retirements WHERE component_id=?',(component_id,)).fetchone():
        raise ValueError('Esta referencia fue retirada. Selecciona un componente activo del catálogo.')


def _component(conn, name, material, process, variant='', collection='General'):
    name, material, variant = clean(name), clean(material), clean(variant)
    if not name or process not in PROCESSES or collection not in ('General', 'Origen'):
        raise ValueError('Revisa el nombre, proceso y colección de la pieza.')
    key = identity(name, material, process, variant)
    existing = conn.execute('SELECT id FROM catalog_components WHERE identity_key=?', (key,)).fetchone()
    if existing:
        require_active_component(conn,existing['id'])
        return existing['id']
    return conn.execute('''INSERT INTO catalog_components(identity_key,name,material,process,variant,collection,created_at)
        VALUES(?,?,?,?,?,?,?)''', (key, name, material, process, variant, collection, timestamp())).lastrowid


def create_component(name, material, process, variant='', collection='General'):
    with connect(write=True) as conn:
        return _component(conn, name, material, process, variant, collection)


def _product(conn, name, variant='', collection='General'):
    name, variant = clean(name), clean(variant)
    if not name or collection not in ('General', 'Origen'):
        raise ValueError('Escribe el nombre del producto y una colección válida.')
    key = identity(name, variant, collection)
    prior = conn.execute('SELECT id FROM catalog_products WHERE identity_key=?', (key,)).fetchone()
    if prior:
        return prior['id']
    return conn.execute('''INSERT INTO catalog_products(identity_key,name,variant,collection,created_at)
        VALUES(?,?,?,?,?)''', (key, name, variant, collection, timestamp())).lastrowid


def create_product(name, variant='', collection='General'):
    with connect(write=True) as conn:
        return _product(conn, name, variant, collection)


def _publish(conn, product_id, lines, notes=''):
    if not conn.execute('SELECT 1 FROM catalog_products WHERE id=?', (product_id,)).fetchone():
        raise ValueError('El producto no existe.')
    if not lines:
        raise ValueError('Agrega al menos una pieza a la receta.')
    ids = [line['component_id'] for line in lines]
    if len(ids) != len(set(ids)):
        raise ValueError('Cada pieza debe aparecer una vez. Ajusta su cantidad por producto.')
    for line in lines:
        positive(line['quantity'], 'Unidades por producto')
        if not conn.execute('SELECT 1 FROM catalog_components WHERE id=?', (line['component_id'],)).fetchone():
            raise ValueError('Una pieza seleccionada ya no existe.')
        require_active_component(conn,line['component_id'])
    managed=conn.execute('''SELECT r.id FROM origin_recipes o JOIN recipe_versions r ON r.id=o.recipe_id
      WHERE r.id=(SELECT id FROM recipe_versions WHERE product_id=? ORDER BY version DESC LIMIT 1)''',(product_id,)).fetchone()
    spec=None
    if managed:
        from services.origin import spec_from_lines
        spec=spec_from_lines(conn,lines,required=True)
    version = conn.execute('SELECT COALESCE(MAX(version),0)+1 FROM recipe_versions WHERE product_id=?', (product_id,)).fetchone()[0]
    rid = conn.execute('INSERT INTO recipe_versions(product_id,version,notes,created_at) VALUES(?,?,?,?)',
                       (product_id, version, notes.strip(), timestamp())).lastrowid
    conn.executemany('INSERT INTO recipe_lines VALUES(?,?,?)', [(rid, line['component_id'], line['quantity']) for line in lines])
    if spec:
        from services.origin import attach,copy_extras
        attach(conn,rid,spec);copy_extras(conn,managed[0],rid)
    return rid


_UNSET=object()


def publish_recipe(product_id, lines, notes='', *, expected_recipe_id=_UNSET):
    with connect(write=True) as conn:
        if expected_recipe_id is not _UNSET:
            current=conn.execute('SELECT id FROM recipe_versions WHERE product_id=? ORDER BY version DESC LIMIT 1',(product_id,)).fetchone()
            if (current[0] if current else None)!=expected_recipe_id:
                raise ValueError('La receta vigente cambió en otra ventana. Actualiza antes de publicar.')
        return _publish(conn, product_id, lines, notes)


def duplicate_product(product_id,name,variant,collection,*,copy_recipe,expected_recipe_id):
    """Create a separate variant without changing the original or its orders."""
    if not isinstance(copy_recipe,bool): raise ValueError('Revisa la opción de copiar receta.')
    with connect(write=True) as conn:
        if not conn.execute('SELECT 1 FROM catalog_products WHERE id=?',(product_id,)).fetchone():
            raise ValueError('El producto original ya no existe.')
        current=conn.execute('SELECT id FROM recipe_versions WHERE product_id=? ORDER BY version DESC LIMIT 1',(product_id,)).fetchone()
        rid=current[0] if current else None
        if rid!=expected_recipe_id: raise ValueError('La receta de origen cambió. Abre nuevamente Crear variante.')
        if conn.execute('SELECT 1 FROM catalog_products WHERE identity_key=?',(identity(name,variant,collection),)).fetchone():
            raise ValueError('Ya existe ese producto y variante. Elige otro nombre o variante.')
        new_id=_product(conn,name,variant,collection)
        if copy_recipe and rid:
            lines=[dict(r) for r in conn.execute('SELECT component_id,quantity FROM recipe_lines WHERE recipe_id=?',(rid,))]
            new_rid=_publish(conn,new_id,lines,f'Copiada desde PRO-{product_id:04d}. Ajusta las piezas de esta variante antes de producir.')
            if conn.execute('SELECT 1 FROM origin_recipes WHERE recipe_id=?',(rid,)).fetchone():
                from services.origin import attach,spec_from_lines,copy_extras
                attach(conn,new_rid,spec_from_lines(conn,lines,required=True));copy_extras(conn,rid,new_rid)
        return new_id


def import_item_recipe(item_id):
    """Explicit conversion of an existing breakdown; never guesses fractional quantities."""
    with connect(write=True) as conn:
        item = conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
        parts = conn.execute('SELECT * FROM parts WHERE item_id=? ORDER BY id', (item_id,)).fetchall()
        if not item or not parts:
            raise ValueError('El producto necesita un despiece antes de guardarlo como receta.')
        if item['recipe_id']:
            raise ValueError('Este producto ya proviene de una receta. Publica una nueva versión desde Catálogo.')
        if any(p['quantity_required'] % item['quantity'] for p in parts):
            raise ValueError('Las cantidades no son múltiplos de la cantidad de producto. Define la receta por unidad desde Catálogo.')
        collection = item['collection'] or 'General'
        product_id = _product(conn, item['name'], collection=collection)
        quantities = {}
        for part in parts:
            cid = _component(conn, part['name'], part['material'], part['process'], collection=collection)
            quantities[cid] = quantities.get(cid, 0) + part['quantity_required'] // item['quantity']
        return _publish(conn, product_id, [{'component_id': cid, 'quantity': qty} for cid, qty in quantities.items()],
                        f"Creada desde ITEM-{item_id:04d}. El pedido original se conserva.")


def load_catalog():
    with connect() as conn:
        components = [dict(r) for r in conn.execute('''SELECT * FROM catalog_components c
          WHERE NOT EXISTS(SELECT 1 FROM catalog_component_retirements x WHERE x.component_id=c.id)
          ORDER BY name,material,variant''')]
        products = [dict(r) for r in conn.execute('''SELECT p.*,
          (SELECT id FROM recipe_versions WHERE product_id=p.id ORDER BY version DESC LIMIT 1) recipe_id,
          (SELECT MAX(version) FROM recipe_versions WHERE product_id=p.id) version
          FROM catalog_products p ORDER BY name,variant''')]
        versions = [dict(r) for r in conn.execute('SELECT * FROM recipe_versions ORDER BY product_id,version DESC')]
        lines = [dict(r) for r in conn.execute('''SELECT l.*,c.name,c.material,c.process,c.variant
          FROM recipe_lines l JOIN catalog_components c ON c.id=l.component_id ORDER BY c.name''')]
        retired={r[0] for r in conn.execute('SELECT component_id FROM catalog_component_retirements')}
    for row in components:
        row['code'] = f"CMP-{row['id']:04d}"
    for row in products:
        row['code'] = f"PRO-{row['id']:04d}"
        row['has_retired_components']=any(l['component_id'] in retired for l in lines if l['recipe_id']==row['recipe_id'])
    return dict(components=components, products=products, versions=versions, lines=lines)


def available(conn, sku_id, location):
    from services.inventory import balance
    held = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM inventory_reservations WHERE sku_id=? AND location=? AND status='Activa'",
                        (sku_id, location)).fetchone()[0]
    return balance(conn, sku_id, location) - held


def _stock(conn, component_id):
    result = []
    for sku in conn.execute('SELECT id FROM inventory_skus WHERE component_id=? ORDER BY id', (component_id,)):
        for location in ('Stock', 'Colección'):
            qty = available(conn, sku['id'], location)
            if qty > 0:
                result.append(dict(sku_id=sku['id'], location=location, quantity=qty))
    return result


def _quote(conn, recipe_id, quantity, use_stock=True):
    positive(quantity, 'Cantidad de producto')
    recipe = conn.execute('''SELECT r.*,p.name,p.variant,p.collection FROM recipe_versions r
      JOIN catalog_products p ON p.id=r.product_id WHERE r.id=?''', (recipe_id,)).fetchone()
    if not recipe:
        raise ValueError('Selecciona una receta publicada.')
    lines = []
    for line in conn.execute('''SELECT l.component_id,l.quantity per_product,c.name,c.material,c.process,c.variant,
      COALESCE(o.role,'Pieza') role,COALESCE(o.supply,'Fabricar') supply
      FROM recipe_lines l JOIN catalog_components c ON c.id=l.component_id
      LEFT JOIN origin_components o ON o.component_id=c.id WHERE recipe_id=? ORDER BY l.component_id''', (recipe_id,)):
        row = dict(line)
        needed = line['per_product'] * quantity
        stock = _stock(conn, line['component_id'])
        free = sum(r['quantity'] for r in stock)
        remaining, allocations = needed, []
        if use_stock:
            for source in stock:
                amount = min(remaining, source['quantity'])
                if amount:
                    allocations.append({**source, 'quantity': amount})
                    remaining -= amount
        row.update(needed=needed, available=free, reserved=needed-remaining,
            to_make=remaining if row['supply']=='Fabricar' else 0,to_buy=remaining if row['supply']=='Comprar' else 0,allocations=allocations)
        lines.append(row)
    result = dict(recipe=dict(recipe), quantity=quantity, use_stock=use_stock, lines=lines)
    result['fingerprint'] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result


def quote_order(recipe_id, quantity, use_stock=True):
    with connect() as conn:
        return _quote(conn, recipe_id, quantity, use_stock)


def _reserve(conn, requirement_id, sku_id, location, quantity, job_id=None):
    if quantity:
        conn.execute('''INSERT INTO inventory_reservations(requirement_id,sku_id,location,quantity,job_id,created_at)
          VALUES(?,?,?,?,?,?)''', (requirement_id, sku_id, location, quantity, job_id, timestamp()))


def create_recipe_order(recipe_id, quantity, *, project='', client='', deadline='', priority='Media',
                        fulfillment='Cliente', use_stock=True, expected_fingerprint=None, request_key=None):
    from services.production import _code, _choice, refresh_order
    from models.constants import PRIORITIES
    from utils.dates import parse_deadline
    _choice(priority, PRIORITIES, 'Prioridad')
    if fulfillment not in ('Cliente', 'Stock'):
        raise ValueError('Selecciona pedido de cliente o producción para stock.')
    client = clean(client)
    if fulfillment == 'Cliente' and not client:
        raise ValueError('Selecciona o escribe el cliente de este pedido.')
    due = parse_deadline(deadline)
    signature = json.dumps([recipe_id,quantity,clean(project),client,deadline,priority,fulfillment,use_stock],ensure_ascii=False)
    with connect(write=True) as conn:
        if request_key:
            prior = conn.execute('SELECT * FROM recipe_order_requests WHERE request_key=?',(request_key,)).fetchone()
            if prior:
                if prior['signature'] != signature:
                    raise ValueError('Esta solicitud ya creó un pedido. Cierra el formulario para iniciar otro.')
                return prior['order_id']
        plan = _quote(conn, recipe_id, quantity, use_stock)
        for line in plan['lines']:require_active_component(conn,line['component_id'])
        if expected_fingerprint and expected_fingerprint != plan['fingerprint']:
            raise ValueError('Las existencias cambiaron. Pulsa Recalcular antes de confirmar el pedido.')
        recipe = plan['recipe']
        oid, code = _code(conn, 'orders', 'ORD')
        now = timestamp()
        project = clean(project) or f"{recipe['name']} ×{quantity}"
        conn.execute('''INSERT INTO orders(id,code,project,client,deadline,priority,status,notes,created_at,updated_at,fulfillment)
          VALUES(?,?,?,?,?,?,'Pendiente',?,?,?,?)''',
          (oid, code, project, client, due.isoformat() if due else None, priority,
           'Pedido desde receta. Fabricación e insumos se controlan por separado; no confirma ensamble.', now, now, fulfillment))
        label = recipe['name'] + (f" · {recipe['variant']}" if recipe['variant'] else '')
        iid = conn.execute('''INSERT INTO items(order_id,name,quantity,notes,created_at,collection,recipe_id)
          VALUES(?,?,?,?,?,?,?)''', (oid, label, quantity, f"Receta v{recipe['version']} · componentes",
          now, 'Origen' if recipe['collection'] == 'Origen' else '', recipe_id)).lastrowid
        for row in plan['lines']:
            part_id = None
            if row['to_make']:
                part_id = conn.execute('''INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at,component_id)
                  VALUES(?,?,?,?,?,?,?,?)''', (iid, row['name'], row['to_make'], row['process'], row['material'],
                  'Faltante de receta' + (f" · {row['variant']}" if row['variant'] else ''), now, row['component_id'])).lastrowid
            rid = conn.execute('''INSERT INTO recipe_requirements(item_id,component_id,quantity,production_part_id)
              VALUES(?,?,?,?)''', (iid, row['component_id'], row['needed'], part_id)).lastrowid
            for allocation in row['allocations']:
                _reserve(conn, rid, allocation['sku_id'], allocation['location'], allocation['quantity'])
        refresh_order(conn, oid)
        if request_key:
            conn.execute('INSERT INTO recipe_order_requests VALUES(?,?,?)',(request_key,oid,signature))
        return oid


def link_inventory(sku_id, component_id):
    """An explicit compatibility decision by the operator; never auto-merge old models."""
    with connect(write=True) as conn:
        sku = conn.execute('SELECT * FROM inventory_skus WHERE id=?', (sku_id,)).fetchone()
        comp = conn.execute('SELECT * FROM catalog_components WHERE id=?', (component_id,)).fetchone()
        if not sku or not comp:
            raise ValueError('Selecciona una existencia y una pieza del catálogo.')
        require_active_component(conn,component_id)
        if sku['component_id'] and sku['component_id'] != component_id:
            raise ValueError('Esta existencia ya está vinculada a otra pieza.')
        if identity(sku['part'], sku['material'], sku['process']) != identity(comp['name'], comp['material'], comp['process']):
            raise ValueError('Nombre de pieza, material y proceso deben coincidir. Verifica también que la variante sea compatible.')
        conn.execute('UPDATE inventory_skus SET component_id=? WHERE id=?', (component_id, sku_id))


def sync_recipe_production(conn, job_id, previous, completed, component_id):
    from services.inventory import balance
    req = conn.execute('''SELECT r.* FROM recipe_requirements r JOIN production_jobs j ON j.part_id=r.production_part_id WHERE j.id=?''', (job_id,)).fetchone()
    if not req:
        raise ValueError('La pieza de catálogo no tiene una necesidad de pedido asociada.')
    comp = conn.execute('SELECT * FROM catalog_components WHERE id=?', (component_id,)).fetchone()
    key = f'component:{component_id}'
    conn.execute('''INSERT OR IGNORE INTO inventory_skus(identity_key,collection,product,part,material,process,created_at,component_id)
      VALUES(?,?,?,?,?,?,?,?)''', (key, comp['collection'], f'Compartida · CMP-{component_id:04d}', comp['name'], comp['material'], comp['process'], timestamp(), component_id))
    sku_id = conn.execute('SELECT id FROM inventory_skus WHERE identity_key=?', (key,)).fetchone()[0]
    delta = completed-previous
    if delta < 0:
        holds = conn.execute("SELECT * FROM inventory_reservations WHERE job_id=? AND status='Activa'", (job_id,)).fetchall()
        if sum(r['quantity'] for r in holds) != previous:
            raise ValueError('No se puede corregir producción que ya se entregó o liberó.')
        conn.execute("UPDATE inventory_reservations SET status='Liberada',closed_at=? WHERE job_id=? AND status='Activa'", (timestamp(), job_id))
        _reserve(conn, req['id'], sku_id, 'Colección', completed, job_id)
        if available(conn, sku_id, 'Colección') < -delta:
            raise ValueError('No hay unidades libres para corregir el avance.')
    conn.execute('''INSERT INTO inventory_movements(sku_id,job_id,kind,source,destination,quantity,notes,created_at)
      VALUES(?,?,?,?,?,?,?,?)''', (sku_id, job_id, 'Producción' if delta > 0 else 'Corrección',
      'Producción' if delta > 0 else 'Colección', 'Colección' if delta > 0 else 'Producción', abs(delta),
      f'Avance del trabajo: {previous} → {completed}. Reserva para su pedido.', timestamp()))
    if delta > 0:
        _reserve(conn, req['id'], sku_id, 'Colección', delta, job_id)


def load_requirements(conn):
    return [dict(r) for r in conn.execute('''SELECT r.*,c.name,c.material,c.process,c.variant,i.order_id,
      COALESCE(o.role,'Pieza') role,COALESCE(o.supply,'Fabricar') supply,
      COALESCE((SELECT SUM(quantity) FROM inventory_reservations WHERE requirement_id=r.id AND status IN ('Activa','Consumida')),0) covered,
      COALESCE((SELECT SUM(quantity) FROM inventory_reservations WHERE requirement_id=r.id AND job_id IS NULL AND status IN ('Activa','Consumida')),0) from_stock
      FROM recipe_requirements r JOIN catalog_components c ON c.id=r.component_id JOIN items i ON i.id=r.item_id
      LEFT JOIN origin_components o ON o.component_id=c.id''')]


def complete_recipe_order(conn, order):
    holds = conn.execute('''SELECT h.* FROM inventory_reservations h JOIN recipe_requirements r ON r.id=h.requirement_id
      JOIN items i ON i.id=r.item_id WHERE i.order_id=? AND h.status='Activa' ORDER BY h.id''', (order['id'],)).fetchall()
    if order['fulfillment'] == 'Cliente' and not clean(order['client']):
        raise ValueError('El pedido necesita un cliente antes de entregar sus piezas.')
    for hold in holds:
        is_stock = order['fulfillment'] == 'Stock'
        conn.execute("UPDATE inventory_reservations SET status='Consumida',closed_at=? WHERE id=?", (timestamp(), hold['id']))
        if is_stock and hold['location'] == 'Stock':
            continue
        conn.execute('''INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,client,client_key,notes,created_at,order_id)
          VALUES(?,?,?,?,?,?,?,?,?,?)''', (hold['sku_id'], 'Traslado' if is_stock else 'Entrega', hold['location'],
          'Stock' if is_stock else 'Entregado', hold['quantity'], '' if is_stock else clean(order['client']),
          '' if is_stock else clean(order['client']).casefold(), f"Cierre de {order['code']}", timestamp(), order['id']))


def release_draft_order(conn, order_id):
    conn.execute('''UPDATE inventory_reservations SET status='Liberada',closed_at=? WHERE status='Activa'
      AND requirement_id IN (SELECT r.id FROM recipe_requirements r JOIN items i ON i.id=r.item_id WHERE i.order_id=?)''', (timestamp(), order_id))
    # Requirements reference manufacturing parts; remove them before the normal order cascade.
    conn.execute('DELETE FROM recipe_requirements WHERE item_id IN (SELECT id FROM items WHERE order_id=?)', (order_id,))
