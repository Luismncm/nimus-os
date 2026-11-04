"""Collection receipts and distribution, recorded in an immutable quantity ledger."""
from __future__ import annotations

import json
import sqlite3

from db import connect
from utils.dates import timestamp

PRINT_PROCESSES = ('Impresión 3D', 'Resina')


def _clean(value: str) -> str:
    return ' '.join(value.split())


def balance(conn: sqlite3.Connection, sku_id: int, location: str, client_key: str = '') -> int:
    return conn.execute("""SELECT COALESCE(SUM(
        CASE WHEN destination=? THEN quantity ELSE 0 END - CASE WHEN source=? THEN quantity ELSE 0 END),0)
        FROM inventory_movements WHERE sku_id=? AND (?<>'B2B' OR client_key=?)""",
        (location, location, sku_id, location, client_key)).fetchone()[0]


def sync_production(conn: sqlite3.Connection, job_id: int, previous: int, completed: int) -> None:
    """Called inside the production transaction; a failed correction rolls it all back."""
    delta = completed - previous
    if not delta:
        return
    from services.stock_runs import sync
    if sync(conn, job_id, previous, completed):
        return
    row = conn.execute("""SELECT i.collection,i.name product,p.name part,p.material,p.process,p.component_id
        FROM production_jobs j JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id
        WHERE j.id=?""", (job_id,)).fetchone()
    if row['component_id']:
        from services.recipes import sync_recipe_production
        sync_recipe_production(conn, job_id, previous, completed, row['component_id'])
        return
    if row['collection'] != 'Origen' or row['process'] not in PRINT_PROCESSES:
        return
    values = [_clean(row[field]) for field in ('collection', 'product', 'part', 'material', 'process')]
    identity = json.dumps([value.casefold() for value in values], ensure_ascii=False)
    conn.execute("""INSERT OR IGNORE INTO inventory_skus(identity_key,collection,product,part,material,process,created_at)
        VALUES(?,?,?,?,?,?,?)""", (identity, *values, timestamp()))
    sku_id = conn.execute('SELECT id FROM inventory_skus WHERE identity_key=?', (identity,)).fetchone()[0]
    from services.recipes import available
    if delta < 0 and available(conn, sku_id, 'Colección') < -delta:
        raise ValueError('Estas unidades ya se asignaron a B2B o stock. Devuélvelas a Colección antes de reducir el avance.')
    conn.execute("""INSERT INTO inventory_movements(sku_id,job_id,kind,source,destination,quantity,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?)""", (sku_id, job_id, 'Producción' if delta > 0 else 'Corrección',
        'Producción' if delta > 0 else 'Colección', 'Colección' if delta > 0 else 'Producción', abs(delta),
        f'Avance del trabajo: {previous} → {completed} unidades buenas.', timestamp()))


def validate_item_change(conn: sqlite3.Connection, item_id: int, name: str, collection: str) -> None:
    old = conn.execute('SELECT name,collection FROM items WHERE id=?', (item_id,)).fetchone()
    changed_identity = old['collection'] != collection or (old['collection'] and _clean(old['name']).casefold() != _clean(name).casefold())
    if changed_identity and conn.execute("""SELECT 1 FROM production_jobs j JOIN parts p ON p.id=j.part_id
        WHERE p.item_id=? AND (j.quantity_completed>0 OR EXISTS(SELECT 1 FROM inventory_movements m WHERE m.job_id=j.id)) LIMIT 1""", (item_id,)).fetchone():
        raise ValueError('El modelo o destino del item ya tiene producción registrada. Crea otro item para un modelo o destino diferente.')


def validate_part_change(conn: sqlite3.Connection, part_id: int, name: str, process: str, material: str) -> None:
    row = conn.execute('SELECT p.*,i.collection FROM parts p JOIN items i ON i.id=p.item_id WHERE p.id=?', (part_id,)).fetchone()
    changed = any(_clean(row[field]).casefold() != _clean(value).casefold()
                  for field, value in (('name', name), ('process', process), ('material', material)))
    if row['collection'] and changed and conn.execute("""SELECT 1 FROM production_jobs j WHERE part_id=?
        AND (quantity_completed>0 OR EXISTS(SELECT 1 FROM inventory_movements m WHERE m.job_id=j.id)) LIMIT 1""", (part_id,)).fetchone():
        raise ValueError('La identidad de una pieza con producción registrada se conserva. Crea otra pieza para cambiar nombre, proceso o material.')


def distribute(sku_id: int, source: str, destination: str, quantity: int, *, client: str = '',
               notes: str = '', request_key: str | None = None) -> int:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError('La cantidad debe ser un entero mayor que cero.')
    if source not in ('Colección', 'Stock') or destination not in ('Colección', 'Stock', 'B2B') or source == destination:
        raise ValueError('Selecciona un origen y un destino diferentes.')
    client = _clean(client) if destination == 'B2B' else ''
    if destination == 'B2B' and not client:
        raise ValueError('Escribe el cliente B2B que recibirá la asignación.')
    notes = notes.strip()
    with connect(write=True) as conn:
        if request_key:
            prior = conn.execute('SELECT * FROM inventory_movements WHERE request_key=?', (request_key,)).fetchone()
            if prior:
                if tuple(prior[k] for k in ('sku_id', 'source', 'destination', 'quantity', 'client', 'notes')) != (sku_id, source, destination, quantity, client, notes):
                    raise ValueError('Esta operación ya se guardó con otros datos. Cierra y vuelve a abrir el formulario.')
                return prior['id']
        if not conn.execute('SELECT 1 FROM inventory_skus WHERE id=?', (sku_id,)).fetchone():
            raise ValueError('La pieza de inventario ya no existe.')
        from services.recipes import available
        free = available(conn, sku_id, source)
        if quantity > free:
            raise ValueError(f'Solo hay {free} unidades disponibles en {source}. Las reservas de pedidos no están disponibles.')
        cursor = conn.execute("""INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,client,client_key,notes,created_at,request_key)
            VALUES(?,?,?,?,?,?,?,?,?,?)""", (sku_id, 'B2B' if destination == 'B2B' else 'Traslado', source, destination,
            quantity, client, client.casefold(), notes, timestamp(), request_key))
        return cursor.lastrowid


def receive_manual(quantity: int, destination: str, reason: str, *, sku_id=None, component_id=None,
                   product='', part='', material='', process='Impresión 3D', collection='Origen', request_key: str) -> int:
    with connect(write=True) as conn:
        return _receive_manual(conn,quantity,destination,reason,sku_id=sku_id,component_id=component_id,
            product=product,part=part,material=material,process=process,collection=collection,request_key=request_key)


def _resolve_receipt_sku(conn,*,sku_id=None,component_id=None,product='',part='',material='',process='Impresión 3D',collection='Origen'):
    from models.constants import PROCESSES
    from services.recipes import require_active_component
    if sku_id is not None and component_id is not None:raise ValueError('Selecciona una sola referencia de inventario.')
    if sku_id is not None:
        sku=conn.execute('SELECT component_id FROM inventory_skus WHERE id=?', (sku_id,)).fetchone()
        if not sku:
            raise ValueError('La referencia de inventario ya no existe.')
        if sku['component_id']:require_active_component(conn,sku['component_id'])
    elif component_id is not None:
        comp = conn.execute('SELECT * FROM catalog_components WHERE id=?', (component_id,)).fetchone()
        if not comp:
            raise ValueError('La pieza del catálogo ya no existe.')
        require_active_component(conn,component_id)
        key = f'component:{component_id}'
        conn.execute('''INSERT OR IGNORE INTO inventory_skus(identity_key,collection,product,part,material,process,created_at,component_id)
            VALUES(?,?,?,?,?,?,?,?)''', (key, comp['collection'], f'Compartida · CMP-{component_id:04d}',
            comp['name'], comp['material'], comp['process'], timestamp(), component_id))
        sku_id = conn.execute('SELECT id FROM inventory_skus WHERE identity_key=?', (key,)).fetchone()[0]
    else:
        values = [_clean(v) for v in (collection, product, part, material, process)]
        if not values[1] or not values[2] or values[0] not in ('Origen', 'General') or values[4] not in PROCESSES:
            raise ValueError('Completa el modelo y la pieza, con una colección y proceso válidos.')
        key = json.dumps([v.casefold() for v in values], ensure_ascii=False)
        conn.execute('''INSERT OR IGNORE INTO inventory_skus(identity_key,collection,product,part,material,process,created_at)
            VALUES(?,?,?,?,?,?,?)''', (key, *values, timestamp()))
        sku_id = conn.execute('SELECT id FROM inventory_skus WHERE identity_key=?', (key,)).fetchone()[0]
    return sku_id


def _receive_manual(conn,quantity: int, destination: str, reason: str, *, sku_id=None, component_id=None,
                   product='', part='', material='', process='Impresión 3D', collection='Origen', request_key: str) -> int:
    from models.constants import PROCESSES
    from services.recipes import positive,require_active_component
    positive(quantity)
    reason = _clean(reason)
    if destination not in ('Colección', 'Stock') or not reason:
        raise ValueError('Selecciona la ubicación y escribe el motivo de la entrada.')
    if not request_key or (sku_id is not None and component_id is not None):
        raise ValueError('Selecciona una sola referencia de inventario.')
    sku_id=_resolve_receipt_sku(conn,sku_id=sku_id,component_id=component_id,product=product,part=part,material=material,process=process,collection=collection)
    prior = conn.execute('SELECT * FROM inventory_movements WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if tuple(prior[k] for k in ('kind', 'sku_id', 'destination', 'quantity', 'notes')) != ('Entrada manual', sku_id, destination, quantity, reason):
            raise ValueError('Esta entrada ya se guardó con otros datos. Abre una nueva entrada.')
        return prior['id']
    return conn.execute('''INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,notes,created_at,request_key)
        VALUES(?,'Entrada manual','Externo',?,?,?,?,?)''',
        (sku_id, destination, quantity, reason, timestamp(), request_key)).lastrowid


FOUND_REASON = 'Stock encontrado'


def receive_found(entries, *, reason=FOUND_REASON, request_key: str) -> list[int]:
    """Pieces found on the shelves, several at once: each line adds to its piece as a reversible manual entry.

    entries: [dict(sku_id=… or component_id=…, quantity=int, destination='Colección'|'Stock')]. Lines of the same
    piece and place add up; everything is saved together or not at all, and a repeated request saves once.
    """
    merged = {}
    for entry in entries:
        ref = ('sku', entry['sku_id']) if entry.get('sku_id') is not None else ('component', entry.get('component_id'))
        if ref[1] is None: raise ValueError('Elige la pieza de cada renglón.')
        quantity = entry.get('quantity')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('Cada renglón necesita una cantidad entera mayor que cero.')
        key = (ref, entry.get('destination') or 'Colección')
        merged[key] = merged.get(key, 0) + quantity
    if not merged: raise ValueError('Agrega al menos una pieza encontrada.')
    with connect(write=True) as conn:
        return [_receive_manual(conn, quantity, destination, reason or FOUND_REASON, request_key=f'{request_key}:{i}',
                                **{'sku_id' if kind == 'sku' else 'component_id': identity})
                for i, (((kind, identity), destination), quantity) in enumerate(sorted(merged.items(), key=lambda m: (m[0][0][0], m[0][0][1], m[0][1])))]


def reverse_movement(movement_id: int, reason: str) -> int:
    reason = reason.strip()
    if not reason:
        raise ValueError('Escribe el motivo de la reversión.')
    with connect(write=True) as conn:
        row = conn.execute('SELECT * FROM inventory_movements WHERE id=?', (movement_id,)).fetchone()
        if not row or row['order_id'] or row['kind'] not in ('Traslado', 'B2B', 'Entrada manual'):
            raise ValueError('Puedes revertir entradas manuales, traslados o asignaciones B2B. La producción se corrige desde el trabajo.')
        if prior := conn.execute('SELECT id FROM inventory_movements WHERE reversal_of=?', (movement_id,)).fetchone():
            return prior['id']
        from services.recipes import available
        free = balance(conn, row['sku_id'], row['destination'], row['client_key']) if row['destination'] == 'B2B' else available(conn, row['sku_id'], row['destination'])
        if free < row['quantity']:
            raise ValueError('Las unidades ya se movieron desde ese destino. Revierte primero los movimientos posteriores.')
        cursor = conn.execute("""INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,client,client_key,notes,created_at,reversal_of)
            VALUES(?,'Reversión',?,?,?,?,?,?,?,?)""", (row['sku_id'], row['destination'], row['source'], row['quantity'],
            row['client'], row['client_key'], reason, timestamp(), movement_id))
        return cursor.lastrowid


def load_inventory() -> dict:
    with connect() as conn:
        skus = [dict(row) for row in conn.execute("""SELECT s.*,
            COALESCE(SUM(CASE WHEN m.destination='Colección' THEN m.quantity ELSE 0 END - CASE WHEN m.source='Colección' THEN m.quantity ELSE 0 END),0) unassigned,
            COALESCE(SUM(CASE WHEN m.destination='Stock' THEN m.quantity ELSE 0 END - CASE WHEN m.source='Stock' THEN m.quantity ELSE 0 END),0) stock,
            COALESCE(SUM(CASE WHEN m.destination='B2B' THEN m.quantity ELSE 0 END - CASE WHEN m.source='B2B' THEN m.quantity ELSE 0 END),0) b2b,
            COALESCE(SUM(CASE WHEN m.destination='Entregado' THEN m.quantity ELSE 0 END),0) delivered,
            COALESCE(SUM(CASE WHEN m.source='Producción' THEN m.quantity ELSE 0 END - CASE WHEN m.destination='Producción' THEN m.quantity ELSE 0 END),0) produced
            FROM inventory_skus s LEFT JOIN inventory_movements m ON m.sku_id=s.id GROUP BY s.id ORDER BY s.product,s.part,s.material""")]
        movements = [dict(row) for row in conn.execute("""SELECT m.*,s.collection,s.product,s.part,s.material,s.process,COALESCE(c.variant,'') variant,
            j.code job_code,COALESCE(o.code,d.code) order_code,COALESCE(o.project,d.project) project,
            (SELECT id FROM inventory_movements r WHERE r.reversal_of=m.id) reversed_by
            FROM inventory_movements m JOIN inventory_skus s ON s.id=m.sku_id LEFT JOIN catalog_components c ON c.id=s.component_id
            LEFT JOIN production_jobs j ON j.id=m.job_id LEFT JOIN parts p ON p.id=j.part_id
            LEFT JOIN items i ON i.id=p.item_id LEFT JOIN orders o ON o.id=i.order_id
            LEFT JOIN orders d ON d.id=m.order_id ORDER BY m.id DESC""")]
        clients = [dict(row) for row in conn.execute("""SELECT m.sku_id, m.client_key,
            MIN(m.client) client,s.product,s.part,s.material,s.process,COALESCE(c.variant,'') variant,
            SUM(CASE WHEN m.destination='B2B' THEN m.quantity ELSE 0 END - CASE WHEN m.source='B2B' THEN m.quantity ELSE 0 END) quantity
            FROM inventory_movements m JOIN inventory_skus s ON s.id=m.sku_id LEFT JOIN catalog_components c ON c.id=s.component_id WHERE m.client_key<>''
            GROUP BY m.client_key,m.sku_id,s.id,c.id HAVING SUM(CASE WHEN m.destination='B2B' THEN m.quantity ELSE 0 END
            - CASE WHEN m.source='B2B' THEN m.quantity ELSE 0 END)>0 ORDER BY client,s.product,s.part""")]
        held = [dict(r) for r in conn.execute("""SELECT h.*,o.code order_code,o.project,o.fulfillment,c.name part,c.material,c.variant
          FROM inventory_reservations h JOIN recipe_requirements r ON r.id=h.requirement_id
          JOIN items i ON i.id=r.item_id JOIN orders o ON o.id=i.order_id
          JOIN catalog_components c ON c.id=r.component_id WHERE h.status='Activa' ORDER BY o.id,h.id""")]
    for row in skus:
        row['code'] = f"INV-{row['id']:04d}"
        row['reserved'] = sum(h['quantity'] for h in held if h['sku_id'] == row['id'])
        row['available_collection'] = row['unassigned'] - sum(h['quantity'] for h in held if h['sku_id'] == row['id'] and h['location'] == 'Colección')
        row['available_stock'] = row['stock'] - sum(h['quantity'] for h in held if h['sku_id'] == row['id'] and h['location'] == 'Stock')
    with connect() as conn:
        definitions={r['component_id']:dict(r) for r in conn.execute('SELECT * FROM origin_components')}
        variants={r['id']:r['variant'] for r in conn.execute('SELECT id,variant FROM catalog_components')}
    for row in skus:
        spec=definitions.get(row['component_id'],{})
        row.update(role=spec.get('role','Pieza'),supply=spec.get('supply','Fabricar'),color=spec.get('color',''),shape=spec.get('shape',''),
                   variant=variants.get(row['component_id']) or '')
    for row in movements:
        row['code'] = f"MOV-{row['id']:04d}"
        row['sku_code'] = f"INV-{row['sku_id']:04d}"
    return {'skus': skus, 'movements': movements, 'clients': clients, 'reservations': held}


INVENTORY_FIELDS = ('code','collection','product','part','variant','material','process','produced','unassigned','stock','b2b','reserved','available_collection','available_stock','delivered','component_id')
MOVEMENT_FIELDS = ('code','created_at','sku_code','collection','product','part','material','process','kind','source','destination',
                   'quantity','client','job_code','order_code','project','notes','reversal_of','reversed_by')
