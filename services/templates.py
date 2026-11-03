"""Reuse complete definitions without copying production or inventory movements."""
from db import connect
from services.production import _editable, _get, _integer, refresh_order, ValidationError
from utils.dates import timestamp
import hashlib
import json


def reusable_items():
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT i.*,o.code order_code,
          (SELECT COUNT(*) FROM parts WHERE item_id=i.id) part_count
          FROM items i JOIN orders o ON o.id=i.order_id WHERE i.recipe_id IS NULL
          AND EXISTS(SELECT 1 FROM parts WHERE item_id=i.id)
          AND NOT EXISTS(SELECT 1 FROM parts WHERE item_id=i.id AND quantity_required % i.quantity <> 0)
          ORDER BY i.id DESC''')]


def reusable_parts():
    with connect() as conn:
        rows = [dict(r) for r in conn.execute('''SELECT p.name,p.material,p.process,p.notes,
          CASE WHEN p.quantity_required % i.quantity=0 THEN p.quantity_required/i.quantity ELSE 1 END units
          FROM parts p JOIN items i ON i.id=p.item_id WHERE p.component_id IS NULL ORDER BY p.id DESC''')]
        rows += [dict(r) for r in conn.execute("SELECT name,material,process,variant notes,1 units FROM catalog_components ORDER BY id DESC")]
    unique = {}
    for row in rows:
        identity = tuple(row[k].strip().casefold() for k in ('name', 'material', 'process', 'notes'))
        row['key'] = hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:20]
        unique.setdefault(identity, row)
    return list(unique.values())


def clone_item(order_id, source_item_id, quantity):
    _integer(quantity, 'Cantidad de producto')
    with connect(write=True) as conn:
        if _editable(conn, order_id)['fulfillment'] != 'Personalizado':
            raise ValidationError('Crea un pedido personalizado para reutilizar este despiece.')
        source = _get(conn, 'items', source_item_id)
        parts = conn.execute('SELECT * FROM parts WHERE item_id=? ORDER BY id', (source_item_id,)).fetchall()
        if source['recipe_id'] or not parts or any(p['quantity_required'] % source['quantity'] for p in parts):
            raise ValidationError('Este despiece necesita una receta por unidad. Revísalo desde Catálogo.')
        iid = conn.execute('''INSERT INTO items(order_id,name,quantity,notes,created_at,collection)
          VALUES(?,?,?,?,?,?)''', (order_id, source['name'], quantity, source['notes'], timestamp(), source['collection'])).lastrowid
        for part in parts:
            conn.execute('''INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at)
              VALUES(?,?,?,?,?,?,?)''', (iid, part['name'], part['quantity_required']//source['quantity']*quantity,
                                       part['process'], part['material'], part['notes'], timestamp()))
        refresh_order(conn, order_id)
        return iid
