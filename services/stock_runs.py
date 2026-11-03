"""Prints made only for inventory: no customer order and no stock lot, units straight to Colección.

A stock run is an internal order flagged in stock_runs, as development projects are. Its print is an
ordinary job (machine time, filament, cost, schedule); every good unit is posted to inventory when it
is recorded, and the run closes by itself when its print finishes. With a catalog piece the units
land on that component's inventory line, so recipe orders can reserve them; a free piece lands on
its model + piece + material line, which any order of the same piece can take.
"""
from db import connect
from models.constants import PRIORITIES
from services import production
from services.catalog import clean
from utils.dates import timestamp
from services.guards import has_table

CLIENT = 'Inventario'
GENERAL = 'Stock general'


def _table(conn) -> bool:
    return has_table(conn, 'stock_runs')


def is_run(conn, order_id) -> bool:
    return _table(conn) and bool(conn.execute('SELECT 1 FROM stock_runs WHERE order_id=?', (order_id,)).fetchone())


def runs(conn) -> dict:
    """order_id → stock run row, for the snapshot."""
    return {r['order_id']: dict(r) for r in conn.execute('SELECT * FROM stock_runs')} if _table(conn) else {}


def components() -> list[dict]:
    """Active catalog pieces that can be printed for stock, with their free units in inventory."""
    from services.recipes import _stock
    with connect() as conn:
        rows = [dict(r) for r in conn.execute('''SELECT c.* FROM catalog_components c WHERE NOT EXISTS(
            SELECT 1 FROM catalog_component_retirements r WHERE r.component_id=c.id) ORDER BY c.name,c.material''')]
        for row in rows:
            row['free'] = sum(s['quantity'] for s in _stock(conn, row['id']))
    return rows


def launch(piece='', quantity=1, *, product='', component_id=None, material='', process='Impresión 3D', machine_id=None,
           planned_start=None, duration_minutes=None, estimated_grams=None, machine_rate=None, material_rate=None, priority='Media', notes='', request_key):
    """Order, piece and print of one stock run, saved together or not at all; returns the job id."""
    if not request_key:
        raise ValueError('Vuelve a abrir el formulario.')
    quantity = production._integer(quantity, 'Cantidad')
    production._choice(priority, PRIORITIES, 'Prioridad')
    if component_id is not None:
        from services.recipes import require_active_component
        with connect() as conn:
            comp = conn.execute('SELECT * FROM catalog_components WHERE id=?', (component_id,)).fetchone()
            if not comp:
                raise ValueError('La pieza del catálogo ya no existe.')
            require_active_component(conn, component_id)
        piece, material, process = comp['name'], comp['material'], comp['process']
        product = clean(product) or f"CMP-{component_id:04d}"
    piece = production._text(piece, 'Pieza')
    production._choice(process, production.PROCESSES, 'Proceso')
    product = clean(product) or GENERAL
    from services.capture import plan_for, insert_print
    plan = plan_for(material, planned_start, duration_minutes, estimated_grams, machine_rate, material_rate)
    with connect(write=True) as conn:
        if prior := conn.execute('SELECT job_id FROM stock_runs WHERE request_key=?', (request_key,)).fetchone():
            return prior['job_id']
        order_id, code = production._code(conn, 'orders', 'ORD')
        stamp = timestamp()
        conn.execute("""INSERT INTO orders(id,code,project,client,deadline,priority,status,notes,created_at,updated_at)
            VALUES(?,?,?,?,NULL,?,'Pendiente',?,?,?)""", (order_id, code, f'Stock · {piece}', CLIENT, priority,
            'Impresión directa a inventario, sin pedido de cliente.', stamp, stamp))
        conn.execute('INSERT INTO stock_runs(order_id,component_id,request_key,created_at) VALUES(?,?,?,?)',
                     (order_id, component_id, request_key, stamp))
        job_id = insert_print(conn, order_id, piece, quantity, product=product, material=material, process=process,
                              machine_id=machine_id, plan=plan, notes=notes)
        conn.execute('UPDATE stock_runs SET job_id=? WHERE order_id=?', (job_id, order_id))
        return job_id


def sync(conn, job_id, previous, completed) -> bool:
    """Inside the job's transaction: post (or take back) a stock run's good units. False if not a run."""
    if not _table(conn):
        return False
    row = conn.execute('''SELECT r.component_id,i.name product,p.name part,p.material,p.process,j.code FROM production_jobs j
        JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id JOIN stock_runs r ON r.order_id=i.order_id WHERE j.id=?''', (job_id,)).fetchone()
    if not row:
        return False
    delta = completed - previous
    if not delta:
        return True
    from services.inventory import _resolve_receipt_sku
    from services.recipes import available
    sku_id = (_resolve_receipt_sku(conn, component_id=row['component_id']) if row['component_id'] else
              _resolve_receipt_sku(conn, product=row['product'], part=row['part'], material=row['material'], process=row['process'], collection='General'))
    if delta < 0 and available(conn, sku_id, 'Colección') < -delta:
        raise ValueError('Estas piezas ya se usaron o movieron en inventario. Devuélvelas a Colección antes de reducir el avance.')
    conn.execute('''INSERT INTO inventory_movements(sku_id,job_id,kind,source,destination,quantity,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?)''', (sku_id, job_id, 'Producción' if delta > 0 else 'Corrección',
        'Producción' if delta > 0 else 'Colección', 'Colección' if delta > 0 else 'Producción', abs(delta),
        f"Stock directo de {row['code']}: {previous} → {completed} piezas buenas.", timestamp()))
    return True
