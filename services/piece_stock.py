"""Free inventory of each piece, extra units printed for stock, and taking pieces from stock.

A print may make more units than its order needs. The job keeps the order's quantity (so order
progress and the capacity triggers stay exact) and its extra units are posted to Colección as
production of that job once it finishes. Before printing, every piece shows how many units are
already free in inventory, so a duplicate print is a decision and not an accident.

Extra units still printing count as inventory on its way: another order's same piece can ride in
that print (ride_print) instead of being printed again, and pieces already in hand are taken from
inventory (use_stock) instead of printed.
"""
from __future__ import annotations


from db import connect
from services.inventory import PRINT_PROCESSES, _clean
from utils.dates import timestamp
from services.guards import has_table

LOCATIONS = ('Colección', 'Stock')


def _table(conn) -> bool:
    return has_table(conn, 'job_extras')


def _piece(conn, part_id):
    return conn.execute('''SELECT p.*,i.name product,i.collection,i.recipe_id,i.order_id FROM parts p
        JOIN items i ON i.id=p.item_id WHERE p.id=?''', (part_id,)).fetchone()


def _free_by_sku(conn) -> dict:
    """{sku_id: {location: free units}} with active reservations already subtracted."""
    free = {}
    for row in conn.execute('''SELECT sku_id,loc,SUM(q) qty FROM (
          SELECT sku_id,destination loc,quantity q FROM inventory_movements WHERE destination IN ('Colección','Stock')
          UNION ALL SELECT sku_id,source,-quantity FROM inventory_movements WHERE source IN ('Colección','Stock')
          UNION ALL SELECT sku_id,location,-quantity FROM inventory_reservations WHERE status='Activa')
        GROUP BY sku_id,loc'''):
        if row['qty'] > 0:
            free.setdefault(row['sku_id'], {})[row['loc']] = row['qty']
    return free


def _physical_by_sku(conn) -> dict:
    """{sku_id: units physically in the workshop (Colección + Stock)}, reserved ones included."""
    physical = {}
    for row in conn.execute('''SELECT sku_id,SUM(q) qty FROM (
          SELECT sku_id,quantity q FROM inventory_movements WHERE destination IN ('Colección','Stock')
          UNION ALL SELECT sku_id,-quantity FROM inventory_movements WHERE source IN ('Colección','Stock')) GROUP BY sku_id'''):
        if row['qty'] > 0:
            physical[row['sku_id']] = row['qty']
    return physical


def _matching_skus(skus, piece) -> list[dict]:
    """Inventory lines that hold this piece, its own model first.

    A catalog piece only uses its component's line (recipe reservations count on it). A custom piece
    uses the same model + piece + material, and then the same piece + material + process printed for
    another model or straight for stock: physically it is the same part.
    """
    if piece['component_id']:
        return [s for s in skus if s['component_id'] == piece['component_id']]
    key = [_clean(v or '').casefold() for v in (piece['product'], piece['name'], piece['material'], piece['process'])]
    exact = [s for s in skus if [_clean(s[f]).casefold() for f in ('product', 'part', 'material', 'process')] == key]
    loose = [s for s in skus if s not in exact and [_clean(s[f]).casefold() for f in ('part', 'material', 'process')] == key[1:]]
    return exact + loose


def piece_key(piece) -> tuple:
    """Same physical piece: the same catalog component, or the same model, piece, material and process."""
    if piece['component_id']:
        return ('c', piece['component_id'])
    return ('p', *[_clean(piece[f] or '').casefold() for f in ('product', 'name', 'material', 'process')])


def loose_key(piece) -> tuple:
    """The same physical piece whatever model it was printed for: component, or piece + material + process."""
    if piece['component_id']:
        return ('c', piece['component_id'])
    return ('l', *[_clean(piece[f] or '').casefold() for f in ('name', 'material', 'process')])


def _shares(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='job_riders'").fetchone())


def _eta(job):
    """When a queued or running print should finish, if it is known."""
    from datetime import timedelta
    from utils.dates import parse_end
    if job.get('estimated_finish'):
        return parse_end(job['estimated_finish'])
    start = parse_end(job.get('planned_start'))
    return start + timedelta(minutes=job['duration_minutes']) if start and job.get('duration_minutes') else None


def annotate(conn, parts: list[dict], jobs: list[dict]) -> None:
    """Parts get stock_free / stock_detail (in hand) and stock_incoming / incoming (extras still printing).

    Jobs get extra / extra_posted, rides_on (the print they travel in) and riders (pieces of other
    orders travelling in theirs).
    """
    extras = {r['job_id']: dict(r) for r in conn.execute('SELECT * FROM job_extras')} if _table(conn) else {}
    riders = [dict(r) for r in conn.execute('SELECT * FROM job_riders')] if _shares(conn) else []
    pulls = {r['job_id'] for r in conn.execute('SELECT job_id FROM stock_pulls')} if _shares(conn) else set()
    by_id = {j['id']: j for j in jobs}
    parts_by_id = {p['id']: p for p in parts}
    orders = {r['id']: dict(r) for r in conn.execute('SELECT id,code,status FROM orders')}
    machines = {r['id']: r['code'] for r in conn.execute('SELECT id,code FROM machines')}
    items = {r['id']: dict(r) for r in conn.execute('SELECT id,name,order_id FROM items')}
    for job in jobs:
        row = extras.get(job['id'], {})
        job.update(extra=row.get('extra', 0), extra_posted=row.get('posted', 0), rides_on=None, riders=[], from_stock=job['id'] in pulls)
    for r in riders:
        rider, host = by_id.get(r['job_id']), by_id.get(r['host_job_id'])
        if rider and host:
            rider['rides_on'] = dict(id=host['id'], code=host['code'])
            owner = orders[items[parts_by_id[rider['part_id']]['item_id']]['order_id']]
            host['riders'].append(dict(id=rider['id'], code=rider['code'], order_code=owner['code'], quantity=rider['quantity']))
    keys = {p['id']: piece_key(dict(p, product=items[p['item_id']]['name'])) for p in parts}
    # Extra units of prints not finished yet: inventory on its way, usable before it lands.
    incoming = {}
    for job in jobs:
        if job['extra'] and not job['extra_posted'] and job['status'] != 'Terminado':
            incoming.setdefault(keys[job['part_id']], []).append(dict(job_id=job['id'], code=job['code'], part_id=job['part_id'],
                machine_code=machines.get(job['machine_id']), status=job['status'], free=job['extra'], eta=_eta(job)))
    # Stock printed straight to inventory that has not finished: it will be free too, though nothing can ride in it.
    from services.stock_runs import runs as stock_runs
    direct, soon = set(stock_runs(conn)), {}
    for job in jobs:
        if job['status'] != 'Terminado' and items[parts_by_id[job['part_id']]['item_id']]['order_id'] in direct:
            soon.setdefault(loose_key(parts_by_id[job['part_id']]), []).append(dict(job_id=job['id'], code=job['code'], part_id=job['part_id'], machine_code=machines.get(job['machine_id']),
                status=job['status'], free=job['quantity'] - job['quantity_completed'], eta=_eta(job)))
    free = _free_by_sku(conn)
    physical = _physical_by_sku(conn)
    skus = [dict(r) for r in conn.execute('SELECT * FROM inventory_skus') if r['id'] in physical]
    for part in parts:
        item = items[part['item_id']]
        piece = dict(part, product=item['name'])
        detail, sources, on_hand = {}, [], 0
        # A delivered order has nothing left to print: its history never shows today's inventory.
        open_order = orders[item['order_id']]['status'] != 'Entregado'
        for sku in _matching_skus(skus, piece) if open_order else []:
            on_hand += physical[sku['id']]
            for location, qty in free.get(sku['id'], {}).items():
                detail[location] = detail.get(location, 0) + qty
                sources.append(dict(product=sku['product'], location=location, quantity=qty,
                                    same=_clean(sku['product']).casefold() == _clean(item['name']).casefold() or bool(part['component_id'])))
        coming = [h for h in incoming.get(keys[part['id']], []) if h['part_id'] != part['id']] if open_order else []
        part.update(stock_free=sum(detail.values()), stock_detail=detail, stock_sources=sources, incoming=coming,
                    stock_incoming=sum(h['free'] for h in coming), stock_physical=on_hand,
                    soon=[h for h in soon.get(loose_key(part), []) if h['part_id'] != part['id']] if open_order else [])
        part['stock_soon'] = sum(h['free'] for h in part['soon'])


def availability(order) -> list[dict]:
    """Every piece of an order against inventory: what it needs, what is already covered, what is free to take now.

    States, from most to least actionable: Disponible (inventory covers all the unassigned units), Parcial,
    En camino (only another print's extra), Imprimir (nothing in hand), Asignada (every unit has a print or
    is covered) and Cubierta (the whole piece came from inventory, nothing to make).
    """
    from services.order_progress import piece_rows
    rows = []
    for item in order['items']:
        parts = {p['id']: p for p in item['parts']}
        for r in piece_rows(item):
            part = parts.get(r['part_id'])
            jobs = part['jobs'] if part else []
            unassigned = r['unassigned']
            free = part.get('stock_free', 0) if part else 0
            coming = part.get('stock_incoming', 0) if part else 0
            soon = part.get('stock_soon', 0) if part else 0
            take = min(free, unassigned)
            pulled = sum(j['quantity'] for j in jobs if j.get('from_stock'))
            covered = r['from_stock'] + pulled
            state = ('Disponible' if unassigned and take == unassigned else 'Parcial' if take
                     else 'En camino' if unassigned and (coming or soon) else 'Imprimir' if unassigned
                     else 'Cubierta' if not part else 'Asignada')
            physical = part.get('stock_physical', 0) if part else covered
            rows.append(dict(part_id=r['part_id'], requirement_id=r['requirement_id'], item=item['name'], name=r['name'], material=r['material'],
                             required=r['required'] or r['to_make'], covered=covered,
                             # Own prints by state; covered + done + running + queued + unassigned == required.
                             done=r['completed'] - pulled, running=r['running'], queued=r['queued'], assigned=r['to_make'] - unassigned - pulled,
                             unassigned=unassigned, free=free, coming=coming, take=take, state=state,
                             # Physically in the workshop (reserved included) and how much of it this order holds.
                             physical=physical, reserved=max(physical - free, 0), returnable=r['from_stock'] if r['requirement_id'] else 0,
                             hosts=part.get('incoming', []) if part else [], soon=part.get('soon', []) if part else [],
                             where=(' · '.join(f'libres: {qty} en {loc}' for loc, qty in part['stock_detail'].items())
                                    + (f" (incluye piezas de {', '.join(sorted({s['product'] for s in part['stock_sources'] if not s['same']}))})"
                                       if any(not s['same'] for s in part['stock_sources']) else '')) if part and free else ''))
    return rows


def return_to_stock(order_id: int, quantity: int, *, requirement_id: int | None = None) -> int:
    """Undo taking a catalog piece from inventory: its reservation is released and the order has to make the units again.

    Only reservations can be undone. A custom piece taken from inventory is a finished job whose units were
    consumed in the ledger, and movements are permanent and tied to that job, so it cannot be taken back here.
    """
    from services import production as p
    from services.recipes import positive
    positive(quantity)
    if not requirement_id:
        raise ValueError('Solo se pueden devolver piezas del catálogo reservadas desde inventario.')
    with connect(write=True) as conn:
        p._editable(conn, order_id)
        _release_reserved(conn, order_id, requirement_id, quantity)
        p.refresh_order(conn, order_id)
    return quantity


def _release_reserved(conn, order_id, requirement_id, quantity):
    req = conn.execute('''SELECT r.*,i.order_id FROM recipe_requirements r JOIN items i ON i.id=r.item_id WHERE r.id=?''', (requirement_id,)).fetchone()
    if not req or req['order_id'] != order_id:
        raise ValueError('La pieza ya no pertenece a este pedido.')
    holds = conn.execute('''SELECT * FROM inventory_reservations WHERE requirement_id=? AND job_id IS NULL AND status='Activa'
        ORDER BY id DESC''', (requirement_id,)).fetchall()
    held = sum(h['quantity'] for h in holds)
    if quantity > held:
        raise ValueError(f'Solo hay {held} unidades tomadas de inventario para esta pieza.')
    stamp, remaining = timestamp(), quantity
    for hold in holds:
        amount = min(remaining, hold['quantity'])
        # A reservation can only be released or consumed whole: release it and hold again what stays.
        conn.execute("UPDATE inventory_reservations SET status='Liberada',closed_at=? WHERE id=?", (stamp, hold['id']))
        if amount < hold['quantity']:
            conn.execute('''INSERT INTO inventory_reservations(requirement_id,sku_id,location,quantity,job_id,created_at)
                VALUES(?,?,?,?,NULL,?)''', (requirement_id, hold['sku_id'], hold['location'], hold['quantity'] - amount, stamp))
        remaining -= amount
        if not remaining:
            break
    if req['production_part_id'] and conn.execute('SELECT 1 FROM parts WHERE id=?', (req['production_part_id'],)).fetchone():
        conn.execute('UPDATE parts SET quantity_required=quantity_required+? WHERE id=?', (quantity, req['production_part_id']))
        return
    comp = conn.execute('SELECT * FROM catalog_components WHERE id=?', (req['component_id'],)).fetchone()
    new_part = conn.execute('''INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at,component_id)
        VALUES(?,?,?,?,?,?,?,?)''', (req['item_id'], comp['name'], quantity, comp['process'], comp['material'],
        'Faltante de receta' + (f" · {comp['variant']}" if comp['variant'] else ''), stamp, comp['id'])).lastrowid
    conn.execute('UPDATE recipe_requirements SET production_part_id=? WHERE id=?', (new_part, requirement_id))


def free_like(name: str, material: str, process: str) -> dict:
    """Free units of any model's piece with this name, material and process (for a piece not created yet)."""
    key = [_clean(v).casefold() for v in (name, material, process)]
    if not key[0]:
        return dict(stock_free=0, stock_detail={})
    with connect() as conn:
        free = _free_by_sku(conn)
        detail = {}
        for sku in conn.execute('SELECT * FROM inventory_skus'):
            if sku['id'] in free and [_clean(sku[f]).casefold() for f in ('part', 'material', 'process')] == key:
                for location, qty in free[sku['id']].items():
                    detail[location] = detail.get(location, 0) + qty
    return dict(stock_free=sum(detail.values()), stock_detail=detail)


def stock_text(part: dict) -> str:
    detail = part.get('stock_detail') or {}
    where = ' · '.join(f'{qty} en {loc}' for loc, qty in detail.items())
    coming = f"{part['stock_incoming']} en camino como excedente de " + ', '.join(h['code'] for h in part['incoming']) if part.get('stock_incoming') else ''
    # Units of the same piece made for another model or straight for stock: say where they come from.
    others = sorted({s['product'] for s in part.get('stock_sources') or [] if not s['same']})
    if part.get('stock_free'):
        return (f"Ya hay {part['stock_free']} en inventario ({where})" + (f", incluye piezas de {', '.join(others)}" if others else '')
                + (f" y {coming}" if coming else ''))
    return f"Vienen {coming}" if coming else 'Sin piezas en inventario'


def _receipt_sku(conn, piece) -> int:
    from services.inventory import _resolve_receipt_sku
    if piece['component_id']:
        return _resolve_receipt_sku(conn, component_id=piece['component_id'])
    return _resolve_receipt_sku(conn, product=piece['product'], part=piece['name'], material=piece['material'],
        process=piece['process'], collection='Origen' if piece['collection'] == 'Origen' else 'General')


def set_extra(conn, job_id: int, extra: int) -> None:
    """Extra units of a job that has not finished; they reach inventory when it finishes."""
    if isinstance(extra, bool) or not isinstance(extra, int) or extra < 0 or extra > 10000:
        raise ValueError('Las unidades extra deben ser un entero entre 0 y 10000.')
    job = conn.execute('SELECT * FROM production_jobs WHERE id=?', (job_id,)).fetchone()
    piece = _piece(conn, job['part_id'])
    if extra and piece['process'] not in PRINT_PROCESSES:
        raise ValueError('Solo las impresiones pueden llevar unidades extra para inventario.')
    prior = conn.execute('SELECT * FROM job_extras WHERE job_id=?', (job_id,)).fetchone()
    if prior and prior['posted']:
        raise ValueError('El excedente de este trabajo ya entró a inventario.')
    if extra:
        _receipt_sku(conn, piece)  # Validates now that the piece can be stored, not when it finishes.
        conn.execute('''INSERT INTO job_extras(job_id,extra,posted,updated_at) VALUES(?,?,0,?)
            ON CONFLICT(job_id) DO UPDATE SET extra=excluded.extra,updated_at=excluded.updated_at''', (job_id, extra, timestamp()))
    elif prior:
        conn.execute('DELETE FROM job_extras WHERE job_id=?', (job_id,))


def update_extra(job_id: int, extra: int) -> None:
    with connect(write=True) as conn:
        if not conn.execute('SELECT 1 FROM production_jobs WHERE id=?', (job_id,)).fetchone():
            raise ValueError('El trabajo ya no existe.')
        set_extra(conn, job_id, extra)


def sync_extras(conn, job_id: int, finished: bool) -> None:
    """Inside the job's transaction: post the extra on finish, take it back if the job reopens."""
    if not _table(conn):
        return
    row = conn.execute('SELECT * FROM job_extras WHERE job_id=?', (job_id,)).fetchone()
    if not row:
        return
    target = row['extra'] if finished else 0
    delta = target - row['posted']
    if not delta:
        return
    job = conn.execute('SELECT code,part_id FROM production_jobs WHERE id=?', (job_id,)).fetchone()
    sku_id = _receipt_sku(conn, _piece(conn, job['part_id']))
    if delta < 0:
        from services.recipes import available
        if available(conn, sku_id, 'Colección') < -delta:
            raise ValueError('El excedente de este trabajo ya se movió en inventario. Devuélvelo a Colección antes de reabrirlo.')
    conn.execute('''INSERT INTO inventory_movements(sku_id,job_id,kind,source,destination,quantity,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?)''', (sku_id, job_id, 'Producción' if delta > 0 else 'Corrección',
        'Producción' if delta > 0 else 'Colección', 'Colección' if delta > 0 else 'Producción', abs(delta),
        f"Excedente de {job['code']}: unidades extra para inventario." if delta > 0 else f"Se reabrió {job['code']}: se retira su excedente.",
        timestamp()))
    conn.execute('UPDATE job_extras SET posted=?,updated_at=? WHERE job_id=?', (target, timestamp(), job_id))


def take_from_stock(part_id: int, quantity: int) -> None:
    """Cover a catalog piece with free inventory instead of printing it again.

    The units are reserved for the order's requirement (as when the order was created from its
    recipe) and the piece to make shrinks by the same amount. Only unassigned units can be taken.
    """
    from services.recipes import positive
    positive(quantity)
    with connect(write=True) as conn:
        _take(conn, part_id, quantity)


def _take(conn, part_id, quantity):
    from services.production import _editable, refresh_order
    from services.recipes import _reserve, _stock
    piece = _piece(conn, part_id)
    if not piece:
        raise ValueError('La pieza ya no existe.')
    _editable(conn, piece['order_id'])
    req = conn.execute('SELECT * FROM recipe_requirements WHERE production_part_id=?', (part_id,)).fetchone()
    if not piece['component_id'] or not req:
        raise ValueError('Solo las piezas del catálogo se pueden cubrir desde inventario. Ajusta el pedido si ya tienes estas piezas.')
    assigned = conn.execute('SELECT COALESCE(SUM(quantity),0) FROM production_jobs WHERE part_id=?', (part_id,)).fetchone()[0]
    if quantity > piece['quantity_required'] - assigned:
        raise ValueError(f"Solo {piece['quantity_required'] - assigned} unidades siguen sin asignar a una impresión.")
    sources = _stock(conn, piece['component_id'])
    if quantity > sum(s['quantity'] for s in sources):
        raise ValueError(f"Solo hay {sum(s['quantity'] for s in sources)} unidades libres en inventario.")
    remaining = quantity
    for source in sources:
        amount = min(remaining, source['quantity'])
        _reserve(conn, req['id'], source['sku_id'], source['location'], amount)
        remaining -= amount
        if not remaining:
            break
    left = piece['quantity_required'] - quantity
    if left or assigned:
        conn.execute('UPDATE parts SET quantity_required=? WHERE id=?', (left, part_id))
    else:
        conn.execute('UPDATE recipe_requirements SET production_part_id=NULL WHERE id=?', (req['id'],))
        conn.execute('DELETE FROM parts WHERE id=?', (part_id,))
    refresh_order(conn, piece['order_id'])


def _unassigned(conn, piece):
    assigned = conn.execute('SELECT COALESCE(SUM(quantity),0) FROM production_jobs WHERE part_id=?', (piece['id'],)).fetchone()[0]
    return piece['quantity_required'] - assigned


def pull_from_stock(part_id: int, quantity: int) -> int:
    """Cover a custom piece with units already in inventory: a finished job whose units leave inventory.

    The units leave Colección (moved there first if they sit in Stock) as consumption of that job, so
    no other order can count them. Catalog pieces reserve instead; see take_from_stock.
    """
    from services.recipes import positive
    positive(quantity)
    with connect(write=True) as conn:
        return _pull(conn, part_id, quantity)


def _pull(conn, part_id, quantity):
    from services import production as p
    piece = _piece(conn, part_id)
    if not piece:
        raise ValueError('La pieza ya no existe.')
    p._editable(conn, piece['order_id'])
    if piece['component_id']:
        raise ValueError('Esta pieza es del catálogo: se reserva desde inventario para su pedido.')
    if quantity > _unassigned(conn, piece):
        raise ValueError(f"Solo {_unassigned(conn, piece)} unidades siguen sin asignar.")
    free = _free_by_sku(conn)
    skus = [dict(r) for r in conn.execute('SELECT * FROM inventory_skus') if r['id'] in free]
    # Its own model first, and within each line Stock (the warehouse) first, as recipe reservations do.
    sources = [(s['id'], loc, qty) for s in _matching_skus(skus, dict(piece)) for loc, qty in sorted(free[s['id']].items(), key=lambda kv: kv[0] != 'Stock')]
    if quantity > sum(q for _, _, q in sources):
        raise ValueError(f"Solo hay {sum(q for _, _, q in sources)} unidades libres en inventario.")
    order = conn.execute('SELECT code FROM orders WHERE id=?', (piece['order_id'],)).fetchone()
    jid = p._insert_jobs(conn, piece['order_id'], part_id, [dict(quantity=quantity, machine_id=None)], None, None, 'Tomado de inventario', None)[0]
    stamp = timestamp()
    conn.execute("UPDATE production_jobs SET status='Terminado',quantity_completed=?,started_at=?,completed_at=?,updated_at=? WHERE id=?",
                 (quantity, stamp, stamp, stamp, jid))
    remaining = quantity
    for sku_id, location, qty in sources:
        amount = min(remaining, qty)
        if location == 'Stock':
            conn.execute('''INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,notes,created_at)
                VALUES(?,'Traslado','Stock','Colección',?,?,?)''', (sku_id, amount, f"Para {order['code']}", stamp))
        conn.execute('''INSERT INTO inventory_movements(sku_id,job_id,kind,source,destination,quantity,notes,created_at)
            VALUES(?,?,'Corrección','Colección','Producción',?,?,?)''', (sku_id, jid, amount, f"Tomado de inventario para {order['code']}.", stamp))
        remaining -= amount
        if not remaining:
            break
    conn.execute('INSERT INTO stock_pulls(job_id,quantity,created_at) VALUES(?,?,?)', (jid, quantity, stamp))
    p.refresh_order(conn, piece['order_id'])
    return jid


def use_stock(part_id: int, quantity: int):
    """Take a piece from inventory the way its kind allows: reserve catalog pieces, consume custom ones."""
    with connect() as conn:
        piece = _piece(conn, part_id)
    if piece and piece['component_id']:
        return take_from_stock(part_id, quantity)
    return pull_from_stock(part_id, quantity)


def cover_from_stock(allocations) -> int:
    """Several pieces covered from inventory in one transaction, all or none; returns the units taken.

    `allocations` is [(part_id, units)]; each piece is taken the way its kind allows (see use_stock).
    """
    from services.recipes import positive
    rows = [(part_id, quantity) for part_id, quantity in allocations if quantity]
    if not rows:
        raise ValueError('Indica cuántas piezas tomar de inventario.')
    for _, quantity in rows:
        positive(quantity)
    with connect(write=True) as conn:
        for part_id, quantity in rows:
            piece = _piece(conn, part_id)
            (_take if piece and piece['component_id'] else _pull)(conn, part_id, quantity)
    return sum(q for _, q in rows)


def ride_print(part_id: int, host_job_id: int, quantity: int) -> int:
    """Print units of this piece inside another job's extra instead of a print of its own.

    The host's extra shrinks by the same units and this piece gets a job on the same printer that
    finishes when the host finishes, so nothing is printed twice and inventory never double counts.
    """
    from services import production as p
    from services.commerce import check_order
    from services.recipes import positive
    positive(quantity)
    with connect(write=True) as conn:
        piece = _piece(conn, part_id)
        host = conn.execute('SELECT * FROM production_jobs WHERE id=?', (host_job_id,)).fetchone()
        if not piece or not host:
            raise ValueError('La pieza o la impresión ya no existe.')
        p._editable(conn, piece['order_id'])
        if host['status'] == 'Terminado':
            raise ValueError(f"{host['code']} ya terminó: su excedente está en inventario, tómalo de ahí.")
        if host['part_id'] == part_id or piece_key(piece) != piece_key(_piece(conn, host['part_id'])):
            raise ValueError('Solo se puede sumar la misma pieza: mismo modelo, material y proceso.')
        extra = conn.execute('SELECT * FROM job_extras WHERE job_id=?', (host_job_id,)).fetchone()
        if not extra or extra['posted'] or extra['extra'] < quantity:
            raise ValueError(f"{host['code']} solo lleva {extra['extra'] if extra else 0} unidades extra libres.")
        if quantity > _unassigned(conn, piece):
            raise ValueError(f"Solo {_unassigned(conn, piece)} unidades siguen sin asignar.")
        check_order(conn, piece['order_id'], 'production')
        jid = p._insert_jobs(conn, piece['order_id'], part_id, [dict(quantity=quantity, machine_id=host['machine_id'])], None, None,
                             f"Va en la impresión {host['code']}.", None)[0]
        conn.execute('INSERT INTO job_riders(job_id,host_job_id,created_at) VALUES(?,?,?)', (jid, host_job_id, timestamp()))
        conn.execute('UPDATE job_extras SET extra=extra-?,updated_at=? WHERE job_id=?', (quantity, timestamp(), host_job_id))
        p.refresh_order(conn, piece['order_id'])
        return jid


def _restore(conn, host_job_id, quantity):
    """Give a rider's units back to its host's extra while the host has not finished."""
    conn.execute('UPDATE job_extras SET extra=extra+?,updated_at=? WHERE job_id=? AND posted=0', (quantity, timestamp(), host_job_id))


def release_riders(conn, job_ids) -> None:
    """Before deleting jobs: an unfinished rider whose host stays gets its units back into the host's extra.

    A finished rider already counted inside the host's own production; nothing to give back.
    """
    if not job_ids or not _shares(conn):
        return
    marks = ','.join('?' * len(job_ids))
    for row in conn.execute(f'''SELECT r.host_job_id,j.quantity FROM job_riders r JOIN production_jobs j ON j.id=r.job_id
            WHERE r.job_id IN ({marks}) AND r.host_job_id NOT IN ({marks}) AND j.status<>'Terminado' ''', (*job_ids, *job_ids)).fetchall():
        _restore(conn, row['host_job_id'], row['quantity'])


def detach_rider(job_id: int) -> None:
    """Undo riding: the piece's units go back to unassigned and to the host's extra."""
    from services import production as p
    with connect(write=True) as conn:
        row = conn.execute('''SELECT r.host_job_id,j.* FROM job_riders r JOIN production_jobs j ON j.id=r.job_id
            WHERE r.job_id=?''', (job_id,)).fetchone()
        if not row:
            raise ValueError('Este trabajo no va dentro de otra impresión.')
        if row['status'] == 'Terminado' or row['quantity_completed']:
            raise ValueError('Ya tiene unidades terminadas: corrige su avance antes de separarlo.')
        order_id = p._owner(conn, 'production_jobs', job_id)
        p._editable(conn, order_id)
        _restore(conn, row['host_job_id'], row['quantity'])
        conn.execute('DELETE FROM production_jobs WHERE id=?', (job_id,))
        p.refresh_order(conn, order_id)


def is_rider(conn, job_id) -> str | None:
    """Code of the print this job travels in, if any."""
    if not _shares(conn):
        return None
    row = conn.execute('SELECT h.code FROM job_riders r JOIN production_jobs h ON h.id=r.host_job_id WHERE r.job_id=?', (job_id,)).fetchone()
    return row['code'] if row else None


def is_pulled(conn, job_id) -> bool:
    return _shares(conn) and bool(conn.execute('SELECT 1 FROM stock_pulls WHERE job_id=?', (job_id,)).fetchone())


def sync_riders(conn, job_id: int, status: str, machine_id) -> None:
    """Inside the host's transaction: riders follow its printer and finish when it finishes.

    A rider whose own order cannot record production yet (a commercial hold) stays queued
    instead of blocking the host.
    """
    if not _shares(conn):
        return
    riders = conn.execute('''SELECT j.* FROM job_riders r JOIN production_jobs j ON j.id=r.job_id
        WHERE r.host_job_id=? AND j.status<>'Terminado' ''', (job_id,)).fetchall()
    if not riders:
        return
    from services.production import _save_job
    for rider in riders:
        if status == 'Terminado':
            conn.execute('SAVEPOINT rider')
            try:
                _save_job(conn, rider, quantity=rider['quantity'], quantity_completed=rider['quantity'], status='Terminado',
                          machine_id=machine_id, priority=rider['priority'], expected_end=rider['expected_end'], notes=rider['notes'])
                conn.execute('RELEASE rider')
            except ValueError:
                conn.execute('ROLLBACK TO rider')
                conn.execute('RELEASE rider')
        elif rider['machine_id'] != machine_id:
            conn.execute('UPDATE production_jobs SET machine_id=?,updated_at=? WHERE id=?', (machine_id, timestamp(), rider['id']))
