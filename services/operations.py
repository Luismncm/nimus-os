"""Manual checks never create stock, complete jobs or deliver an order."""
from db import connect
from services.catalog import clean
from services.production import _editable, _get
from utils.dates import timestamp

STAGES = {'revision':'Revisión final','packing':'Empacado','dispatch':'Listo para salida'}


def _revision(row, expected):
    if (row['revision'] if row else 0) != expected:
        raise ValueError('Este seguimiento cambió en otra ventana. Actualiza antes de guardar.')


def update_item(item_id, *, expected_revision, label=None, checked=None):
    with connect(write=True) as conn:
        item=_get(conn,'items',item_id)
        _editable(conn,item['order_id'])
        row=conn.execute('SELECT * FROM item_tracking WHERE item_id=?',(item_id,)).fetchone()
        _revision(row,expected_revision)
        old_label=row['label'] if row else ''
        old_checked=row['checked_at'] if row else None
        new_label=old_label if label is None else clean(label)
        if len(new_label)>80:
            raise ValueError('La etiqueta admite hasta 80 caracteres.')
        if checked is not None and not isinstance(checked,bool):
            raise ValueError('El check debe ser verdadero o falso.')
        mark=old_checked if checked is None or bool(old_checked)==checked else timestamp() if checked else None
        if new_label==old_label and mark==old_checked:
            return
        conn.execute('''INSERT INTO item_tracking VALUES(?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE
          SET label=excluded.label,checked_at=excluded.checked_at,revision=excluded.revision,updated_at=excluded.updated_at''',
          (item_id,new_label,mark,expected_revision+1,timestamp()))
        details=[]
        if new_label!=old_label:
            details.append(f'etiqueta: {old_label or "sin etiqueta"} → {new_label or "sin etiqueta"}')
        if mark!=old_checked:
            details.append('revisado' if mark else 'revisión pendiente')
        conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',
                     (item['order_id'],f"{item['name']} · {'; '.join(details)}",timestamp()))


def set_stage(order_id, stage, checked, *, expected_revision):
    if stage not in STAGES or not isinstance(checked,bool):
        raise ValueError('Etapa no válida.')
    with connect(write=True) as conn:
        _editable(conn,order_id)
        row=conn.execute('SELECT * FROM order_stages WHERE order_id=? AND stage=?',(order_id,stage)).fetchone()
        _revision(row,expected_revision)
        if bool(row and row['checked_at']) == checked:
            return
        conn.execute('''INSERT INTO order_stages VALUES(?,?,?,?,?) ON CONFLICT(order_id,stage) DO UPDATE
          SET checked_at=excluded.checked_at,revision=excluded.revision,updated_at=excluded.updated_at''',
          (order_id,stage,timestamp() if checked else None,expected_revision+1,timestamp()))
        conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',
                     (order_id,f"{STAGES[stage]} · {'completado' if checked else 'pendiente'}",timestamp()))


def review_products(order_id, expected):
    """Review all products in one transaction after checking every revision."""
    if not isinstance(expected,dict) or not expected: raise ValueError('Agrega productos antes de revisarlos.')
    with connect(write=True) as conn:
        _editable(conn,order_id)
        items=conn.execute('SELECT * FROM items WHERE order_id=? ORDER BY id',(order_id,)).fetchall()
        if {i['id'] for i in items}!=set(expected): raise ValueError('Los productos del pedido cambiaron. Actualiza antes de revisar.')
        records={i['id']:conn.execute('SELECT * FROM item_tracking WHERE item_id=?',(i['id'],)).fetchone() for i in items}
        for identity,row in records.items(): _revision(row,expected[identity])
        for item in items:
            row=records[item['id']]
            if row and row['checked_at']: continue
            mark=timestamp()
            conn.execute('INSERT INTO item_tracking VALUES(?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET checked_at=excluded.checked_at,revision=excluded.revision,updated_at=excluded.updated_at',
                (item['id'],row['label'] if row else '',mark,expected[item['id']]+1,mark))
            conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',(order_id,f"{item['name']} · revisado",mark))


def annotate(conn, items, orders):
    tracking={r['item_id']:dict(r) for r in conn.execute('SELECT * FROM item_tracking')}
    stages={}
    for row in conn.execute('SELECT * FROM order_stages'):
        stages.setdefault(row['order_id'],{})[row['stage']]=dict(row)
    for item in items:
        row=tracking.get(item['id'],{})
        item.update(label=row.get('label',''),checked_at=row.get('checked_at'),tracking_revision=row.get('revision',0))
    for order in orders:
        order['stages']={key:stages.get(order['id'],{}).get(key,dict(checked_at=None,revision=0)) for key in STAGES}


def history(order_id):
    with connect() as conn:
        return [dict(r) for r in conn.execute('SELECT detail,created_at FROM operation_events WHERE order_id=? ORDER BY id DESC LIMIT 100',(order_id,))]
