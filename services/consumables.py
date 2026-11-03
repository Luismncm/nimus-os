"""Consumables by unit: filament, resin, paint, adhesive, hardware… and their package orders.

Each item keeps one base unit: g, ml or pza. kg and L are converted on entry and shown when
quantities are large. The balance is the sum of movements. Filament (unit g) is also compared with
the grams that open print jobs estimate, and every write refreshes material_availability, which
Control's material alerts already read.
"""
from contextlib import nullcontext
from db import connect
from services.catalog import clean
from services.order_status import STAGES, status
from services.quotations import number, cents
from utils.dates import now, timestamp

CATEGORIES = ('Filamento', 'Resina', 'Pintura', 'Adhesivo', 'Tornillería', 'Limpieza', 'Empaque', 'Otro')
UNITS = {'g': 'Masa · gramos', 'ml': 'Volumen · mililitros', 'pza': 'Piezas'}
# Entry units and their factor to the base unit.
ENTRY = {'g': {'g': 1, 'kg': 1000}, 'ml': {'ml': 1, 'L': 1000}, 'pza': {'pza': 1}}
PACKAGES = ('Carrete', 'Botella', 'Bote', 'Bolsa', 'Caja', 'Rollo', 'Pieza', 'Otro')
DEFAULTS = {'Filamento': ('g', 'Carrete', 1000), 'Resina': ('ml', 'Botella', 1000), 'Pintura': ('ml', 'Bote', 250),
            'Adhesivo': ('ml', 'Bote', 100), 'Tornillería': ('pza', 'Bolsa', 100), 'Limpieza': ('ml', 'Botella', 1000),
            'Empaque': ('pza', 'Caja', 50), 'Otro': ('pza', 'Pieza', 1)}


def identity(name):
    return clean(name).casefold()


def to_base(value, entry_unit, unit):
    if entry_unit not in ENTRY[unit]:
        raise ValueError(f'Usa {", ".join(ENTRY[unit])} para este consumible.')
    return float(value) * ENTRY[unit][entry_unit]


def quantity_text(value, unit):
    """1 250 g → '1.25 kg', 800 ml → '800 ml', 12 pza → '12 pzas'."""
    if unit == 'pza':
        return f"{value:,.0f} pza" + ('s' if abs(value) != 1 else '')
    big, label = ('kg', 'g') if unit == 'g' else ('L', 'ml')
    return f"{value / 1000:,.2f} {big}" if abs(value) >= 1000 else f"{value:,.0f} {label}"


def unit_cost(row):
    """Cents per base unit (g, ml or pza) from the reference cost of one package, or None if unknown."""
    cost = row.get('package_cost_cents')
    return cost / row['package_size'] if cost is not None else None


def cost_text(row):
    """'$420.00 por carrete · $0.42/g' — the package price and what one unit costs."""
    from services.quotations import money
    if row.get('package_cost_cents') is None:
        return 'Sin costo de referencia'
    per = unit_cost(row) * (1000 if row['unit'] in ('g', 'ml') else 1)
    unit = {'g': 'kg', 'ml': 'L', 'pza': 'pza'}[row['unit']]
    return f"{money(row['package_cost_cents'])} por {row['package_label'].lower()} · {money(round(per))}/{unit}"


def _amount(value, label, unit, *, positive=True):
    amount = float(number(value, label, maximum=100000000))
    if unit == 'pza' and amount != int(amount):
        raise ValueError(f'{label}: las piezas se cuentan en números enteros.')
    if positive and amount <= 0:
        raise ValueError(f'{label}: indica una cantidad mayor que cero.')
    return round(amount, 1)


def _balances(conn):
    return {r[0]: r[1] for r in conn.execute('SELECT consumable_id,SUM(quantity) FROM consumable_movements GROUP BY consumable_id')}


def _sync(conn, item_id):
    """Filament only: keep the reading used by production alerts equal to the ledger balance."""
    row = conn.execute('SELECT * FROM consumables WHERE id=?', (item_id,)).fetchone()
    if row['unit'] != 'g':
        return
    balance = _balances(conn).get(item_id, 0) or 0
    conn.execute('''INSERT INTO material_availability VALUES(?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET
        name=excluded.name,available_grams=excluded.available_grams,minimum_grams=excluded.minimum_grams,updated_at=excluded.updated_at''',
        (row['identity'], row['name'], max(0.0, balance), row['minimum'], timestamp()))


def demand(jobs):
    """Estimated grams of open print jobs by material: what the queue will still use."""
    result = {}
    for job in jobs:
        if job['status'] == 'Terminado' or job['order_status'] == 'Entregado' or job.get('commercial_cancelled'):
            continue
        if job.get('estimated_grams') and job.get('material'):
            row = result.setdefault(identity(job['material']), dict(quantity=0.0, jobs=0))
            row['quantity'] += job['estimated_grams'];row['jobs'] += 1
    return result


def items(jobs=None, conn=None):
    if jobs is None:
        from services.queries import load_snapshot
        jobs = load_snapshot()['jobs']
    with (connect() if conn is None else nullcontext(conn)) as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM consumables ORDER BY category,name')]
        balances = _balances(c)
        orders = list_orders(c)
    need = demand(jobs)
    for r in rows:
        r['balance'] = round(balances.get(r['id'], 0) or 0, 1)
        use = need.get(r['identity'], dict(quantity=0.0, jobs=0)) if r['unit'] == 'g' else dict(quantity=0.0, jobs=0)
        r['committed'], r['committed_jobs'] = round(use['quantity'], 1), use['jobs']
        r['free_after'] = round(r['balance'] - r['committed'], 1)
        r['on_order'] = round(sum(o['pending'] * o['package_size'] for o in orders if o['consumable_id'] == r['id']), 1)
        r['packages'] = round(r['balance'] / r['package_size'], 1)
        r['unit_cost'] = unit_cost(r)
        r['stock_value_cents'] = round(max(0, r['balance']) * r['unit_cost']) if r['unit_cost'] is not None else None
        r['state'] = ('Sin existencias' if r['balance'] <= 0 else 'No alcanza para la cola' if r['free_after'] < 0
                      else 'Bajo mínimo' if r['minimum'] and r['balance'] < r['minimum'] else 'Suficiente')
        r['attention'] = r['state'] != 'Suficiente' and (r['committed'] > 0 or r['minimum'] > 0)
    return rows


def unregistered(jobs):
    """Filament named by open jobs that has no stock record yet."""
    with connect() as conn:
        known = {r[0] for r in conn.execute('SELECT identity FROM consumables')}
    names = {}
    for job in jobs:
        if job['status'] != 'Terminado' and job.get('material') and identity(job['material']) not in known:
            names.setdefault(identity(job['material']), clean(job['material']))
    return sorted(names.values())


def save_item(name, *, category='Filamento', unit=None, spec='', color='', brand='', package_label=None, package_size=None,
              minimum=0, notes='', package_cost=None, item_id=None, expected_revision=None):
    name = clean(name)
    if not name or len(name) > 160:
        raise ValueError('Indica el nombre. Para filamento usa el mismo nombre de material que tienen las piezas.')
    if category not in CATEGORIES:
        raise ValueError('Elige una categoría válida.')
    default_unit, default_label, default_size = DEFAULTS[category]
    unit = unit or default_unit
    if unit not in UNITS:
        raise ValueError('Elige la unidad: gramos, mililitros o piezas.')
    values = dict(identity=identity(name), name=name, category=category, unit=unit, spec=clean(spec), color=clean(color), brand=clean(brand),
                  package_label=clean(package_label or default_label), package_size=_amount(package_size or default_size, 'Contenido por envase', unit),
                  minimum=_amount(minimum, 'Mínimo', unit, positive=False), notes=str(notes or '').strip()[:2000],
                  package_cost_cents=None if package_cost in (None, '') else cents(package_cost))
    if values['package_cost_cents'] is not None and values['package_cost_cents'] < 0:
        raise ValueError('El costo por envase no puede ser negativo.')
    with connect(write=True) as conn:
        other = conn.execute('SELECT id FROM consumables WHERE identity=?', (values['identity'],)).fetchone()
        if other and other['id'] != item_id:
            raise ValueError('Ya existe un consumible con ese nombre.')
        stamp = timestamp()
        if item_id is None:
            item_id = conn.execute('''INSERT INTO consumables(identity,name,category,unit,spec,color,brand,package_label,package_size,minimum,notes,package_cost_cents,created_at,updated_at)
                VALUES(:identity,:name,:category,:unit,:spec,:color,:brand,:package_label,:package_size,:minimum,:notes,:package_cost_cents,:stamp,:stamp)''',
                dict(values, stamp=stamp)).lastrowid
        else:
            current = conn.execute('SELECT unit FROM consumables WHERE id=?', (item_id,)).fetchone()
            if current and current['unit'] != unit and conn.execute('SELECT 1 FROM consumable_movements WHERE consumable_id=?', (item_id,)).fetchone():
                raise ValueError('La unidad no se puede cambiar cuando ya hay movimientos; crea otro consumible.')
            updated = conn.execute('''UPDATE consumables SET identity=:identity,name=:name,category=:category,unit=:unit,spec=:spec,color=:color,
                brand=:brand,package_label=:package_label,package_size=:package_size,minimum=:minimum,notes=:notes,
                package_cost_cents=:package_cost_cents,revision=revision+1,updated_at=:stamp
                WHERE id=:id AND revision=:revision''', dict(values, stamp=stamp, id=item_id, revision=expected_revision)).rowcount
            if not updated:
                raise ValueError('El consumible cambió en otra ventana. Actualiza antes de guardar.')
        _sync(conn, item_id)
        return item_id


def _unit(conn, item_id):
    row = conn.execute('SELECT unit FROM consumables WHERE id=?', (item_id,)).fetchone()
    if not row:
        raise ValueError('El consumible ya no existe.')
    return row['unit']


def _movement(conn, item_id, kind, quantity, notes, request_key, *, job_code='', order_id=None, production_order=None):
    if not request_key:
        raise ValueError('Vuelve a abrir el formulario.')
    prior = conn.execute('SELECT * FROM consumable_movements WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if (prior['consumable_id'], prior['kind'], prior['quantity']) != (item_id, kind, quantity):
            raise ValueError('Este movimiento ya se guardó con otros datos. Abre el formulario otra vez.')
        return prior['id']
    item = dict(conn.execute('SELECT * FROM consumables WHERE id=?', (item_id,)).fetchone() or {})
    if not item:
        raise ValueError('El consumible ya no existe.')
    balance = _balances(conn).get(item_id, 0) or 0
    if balance + quantity < -0.05:
        raise ValueError(f"El saldo quedaría negativo: hay {quantity_text(balance, item['unit'])} registrados. Registra primero la entrada o haz un conteo.")
    # A consumption keeps the cost it had when it happened; later price changes do not rewrite it.
    cost = round(-quantity * unit_cost(item)) if kind == 'Consumo' and unit_cost(item) is not None else None
    created = conn.execute('''INSERT INTO consumable_movements(consumable_id,kind,quantity,job_code,order_id,notes,created_at,request_key,
        production_order_id,order_code,cost_cents) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (item_id, kind, quantity, clean(job_code), order_id, str(notes or '').strip()[:2000], timestamp(), request_key,
         production_order['id'] if production_order else None, production_order['code'] if production_order else '', cost)).lastrowid
    _sync(conn, item_id)
    return created


def _production_order(conn, order_id, job_code):
    """The order a consumption belongs to: chosen directly, or the one that owns the print job."""
    if job_code:
        row = conn.execute('''SELECT o.id,o.code FROM production_jobs j JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id
            JOIN orders o ON o.id=i.order_id WHERE j.code=?''', (clean(job_code),)).fetchone()
        if not row:
            raise ValueError('El trabajo ya no existe.')
        if order_id is not None and row['id'] != order_id:
            raise ValueError('El trabajo pertenece a otro pedido.')
        return dict(row)
    if order_id is None:
        return None
    row = conn.execute('SELECT id,code FROM orders WHERE id=?', (order_id,)).fetchone()
    if not row:
        raise ValueError('El pedido ya no existe.')
    return dict(row)


def receive(item_id, quantity, *, notes='', request_key):
    """Physical entry without a purchase order (return, gift, stock found)."""
    with connect(write=True) as conn:
        return _movement(conn, item_id, 'Entrada', _amount(quantity, 'Cantidad recibida', _unit(conn, item_id)), notes, request_key)


def consume(item_id, quantity, *, job_code='', order_id=None, notes='', request_key):
    """Use of a consumable, optionally for a production order (or a print job, which names its order)."""
    with connect(write=True) as conn:
        amount = -_amount(quantity, 'Cantidad usada', _unit(conn, item_id))
        return _movement(conn, item_id, 'Consumo', amount, notes, request_key, job_code=job_code,
                         production_order=_production_order(conn, order_id, job_code))


def by_order(conn=None):
    """Consumables charged to each production order.

    Uses tied to a print job are listed for traceability but not added: that filament is already
    costed in the job's real consumption (grams × MXN/kg), and counting it twice would hide margin.
    """
    with (connect() if conn is None else nullcontext(conn)) as c:
        rows = [dict(r) for r in c.execute('''SELECT m.*,i.name item,i.unit FROM consumable_movements m JOIN consumables i ON i.id=m.consumable_id
            WHERE m.kind='Consumo' AND m.production_order_id IS NOT NULL ORDER BY m.id''')]
    result = {}
    for r in rows:
        own = result.setdefault(r['production_order_id'], dict(cost_cents=0, unknown=0, rows=[]))
        r['charged'] = not r['job_code']
        if r['charged']:
            if r['cost_cents'] is None:own['unknown'] += 1
            else:own['cost_cents'] += r['cost_cents']
        own['rows'].append(r)
    return result


def material_rate(material):
    """Reference filament cost in cents per kg, to suggest as the material rate of a print job."""
    with connect() as conn:
        row = conn.execute('SELECT * FROM consumables WHERE identity=? AND unit=?', (identity(material or ''), 'g')).fetchone()
    return round(unit_cost(dict(row)) * 1000) if row and unit_cost(dict(row)) is not None else None


def count(item_id, counted, *, notes='', request_key, conn=None):
    """A weighing or count sets the balance: the difference is stored as an adjustment."""
    with (connect(write=True) if conn is None else nullcontext(conn)) as c:
        unit = _unit(c, item_id)
        counted = _amount(counted, 'Cantidad contada', unit, positive=False)
        balance = _balances(c).get(item_id, 0) or 0
        diff = round(counted - balance, 1)
        if not diff:
            prior = c.execute('SELECT id FROM consumable_movements WHERE request_key=?', (request_key,)).fetchone()
            if prior:
                return prior['id']
            raise ValueError(f'El conteo coincide con el saldo registrado ({quantity_text(balance, unit)}). No hay nada que ajustar.')
        return _movement(c, item_id, 'Ajuste', diff, notes or 'Conteo físico', request_key)


def save_reading(name, available, minimum=0):
    """Control's "Material disponible" form records into the same ledger, as a count of filament."""
    name = clean(name)
    with connect() as conn:
        row = conn.execute('SELECT * FROM consumables WHERE identity=?', (identity(name),)).fetchone()
    if row:
        item_id = save_item(row['name'], category=row['category'], unit=row['unit'], spec=row['spec'], color=row['color'], brand=row['brand'],
                            package_label=row['package_label'], package_size=row['package_size'], minimum=minimum, notes=row['notes'],
                            package_cost=row['package_cost_cents'] / 100 if row['package_cost_cents'] is not None else None,
                            item_id=row['id'], expected_revision=row['revision'])
    else:
        item_id = save_item(name, minimum=minimum)
    try:
        count(item_id, available, notes='Lectura desde Control de producción', request_key=f'reading:{item_id}:{timestamp()}')
    except ValueError as exc:
        if 'coincide' not in str(exc):
            raise
    return item_id


def movements(item_id):
    with connect() as conn:
        rows = [dict(r) for r in conn.execute('''SELECT m.*,o.code purchase_code FROM consumable_movements m
            LEFT JOIN consumable_orders o ON o.id=m.order_id WHERE m.consumable_id=? ORDER BY m.id DESC''', (item_id,))]
    running = sum(r['quantity'] for r in rows)
    for r in rows:
        r['balance_after'] = round(running, 1);running -= r['quantity']
    return rows


# Package purchase orders ------------------------------------------------------------------

def list_orders(conn=None):
    with (connect() if conn is None else nullcontext(conn)) as c:
        rows = [dict(r) for r in c.execute('''SELECT o.*,i.name item,i.unit,i.category,i.package_label FROM consumable_orders o
            JOIN consumables i ON i.id=o.consumable_id ORDER BY o.id DESC''')]
        events = [dict(e) for e in c.execute('SELECT * FROM consumable_order_events ORDER BY id')]
    today = now().date().isoformat()
    for r in rows:
        own = [e for e in events if e['order_id'] == r['id']]
        r['events'] = own
        r['received'] = sum(e['packages'] for e in own if e['kind'] == 'Recepción')
        r['cancelled'] = any(e['kind'] == 'Cancelación' for e in own)
        r['stage'] = next((e['stage'] for e in reversed(own) if e['kind'] == 'Estado'), 'Solicitado')
        r['remaining'] = r['packages'] - r['received']
        r['pending'] = 0 if r['cancelled'] else r['remaining']
        r['status'] = status(r['stage'], r['packages'], r['received'], r['cancelled'])
        r['overdue'] = bool(r['pending'] and r['expected_on'] and r['expected_on'] < today)
        r['token'] = f"{own[-1]['id'] if own else 0}:{r['received']}"
    return rows


def _order(conn, order_id):
    row = next((r for r in list_orders(conn) if r['id'] == order_id), None)
    if not row:
        raise ValueError('El pedido de consumibles ya no existe.')
    return row


def create_order(item_id, packages, *, package_size=None, supplier='', ordered_on=None, expected_on=None, notes='', financial=None, request_key):
    from services.inbound import _day, _financial, _text
    if type(packages) is not int or packages <= 0:
        raise ValueError('Indica cuántos envases pides.')
    ordered = _day(ordered_on or now().date(), 'la fecha del pedido')
    expected = _day(expected_on, 'la fecha prevista', optional=True)
    if ordered > now().date().isoformat():
        raise ValueError('La fecha del pedido no puede ser futura.')
    if expected and expected < ordered:
        raise ValueError('La llegada prevista no puede ser anterior al pedido.')
    payload = _financial(financial, ordered) if financial is not None else None
    with connect(write=True) as conn:
        item = conn.execute('SELECT * FROM consumables WHERE id=?', (item_id,)).fetchone()
        if not item:
            raise ValueError('Elige un consumible registrado.')
        size = _amount(package_size or item['package_size'], 'Contenido por envase', item['unit'])
        if prior := conn.execute('SELECT id FROM consumable_orders WHERE request_key=?', (request_key,)).fetchone():
            return prior['id']
        from services.production import _code
        order_id, code = _code(conn, 'consumable_orders', 'CON')
        expense_id = None
        if payload is not None:
            from services import expense_control
            expense_id = expense_control.register(concept=f"{code} · {item['name']} ×{packages} {item['package_label'].lower()}",
                amount=payload['amount_cents'] / 100, expense_on=ordered, supplier=_text(supplier), category=payload['category'],
                paid=payload['paid'], account_id=payload['account_id'], method=payload['method'], paid_on=payload['paid_on'],
                due_on=payload['due_on'], notes=f'Compra de consumibles {code}', request_key='consumable:' + request_key, _conn=conn)
        conn.execute('''INSERT INTO consumable_orders(id,code,consumable_id,packages,package_size,supplier,ordered_on,expected_on,notes,expense_id,created_at,request_key)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (order_id, code, item_id, packages, size, _text(supplier), ordered, expected, _text(notes), expense_id, timestamp(), request_key))
        return order_id


def _event(conn, order_id, kind, notes, request_key, *, stage=None, packages=None, movement_id=None):
    prior = conn.execute('SELECT * FROM consumable_order_events WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if (prior['order_id'], prior['kind'], prior['stage'], prior['packages']) != (order_id, kind, stage, packages):
            raise ValueError('La operación ya se guardó con otros datos. Abre el formulario otra vez.')
        return prior['id']
    return conn.execute('''INSERT INTO consumable_order_events(order_id,kind,stage,packages,movement_id,notes,created_at,request_key)
        VALUES(?,?,?,?,?,?,?,?)''', (order_id, kind, stage, packages, movement_id, str(notes or '').strip()[:2000], timestamp(), request_key)).lastrowid


def _open(row, token):
    if row['token'] != token:
        raise ValueError('El pedido cambió en otra ventana. Actualiza antes de continuar.')
    if not row['pending']:
        raise ValueError('El pedido ya no tiene envases pendientes.')


def _replayed(conn, request_key):
    return conn.execute('SELECT 1 FROM consumable_order_events WHERE request_key=?', (request_key,)).fetchone()


def set_stage(order_id, stage, *, notes='', expected_token, request_key):
    if stage not in STAGES:
        raise ValueError('Elige un estado válido.')
    with connect(write=True) as conn:
        if not _replayed(conn, request_key):
            row = _order(conn, order_id);_open(row, expected_token)
            if row['stage'] == stage:
                raise ValueError(f'El pedido ya está en «{stage}».')
        return _event(conn, order_id, 'Estado', notes, request_key, stage=stage)


def receive_order(order_id, packages, *, notes='', expected_token, request_key):
    if type(packages) is not int or packages <= 0:
        raise ValueError('Indica cuántos envases llegaron.')
    with connect(write=True) as conn:
        if _replayed(conn, request_key):
            return _event(conn, order_id, 'Recepción', notes, request_key, packages=packages)
        row = _order(conn, order_id);_open(row, expected_token)
        if packages > row['pending']:
            raise ValueError(f"Solo faltan {row['pending']} envases de este pedido.")
        if row['expense_id']:
            # The price actually paid becomes the reference cost (before VAT when the bill has a breakdown).
            from services import expenses
            e = next((x for x in expenses._rows(conn) if x['id'] == row['expense_id']), None)
            if e and e['status'] == 'Activo':
                amount = e['subtotal_cents'] if e['subtotal_cents'] is not None else e['total_cents']
                conn.execute('UPDATE consumables SET package_cost_cents=?,revision=revision+1,updated_at=? WHERE id=?',
                             (round(amount / row['packages']), timestamp(), row['consumable_id']))
        movement = _movement(conn, row['consumable_id'], 'Entrada', round(packages * row['package_size'], 1),
                             f"{row['code']} · {packages} {row['package_label'].lower()}" + (f' · {notes}' if notes else ''),
                             'consumable-order:' + request_key, order_id=order_id)
        return _event(conn, order_id, 'Recepción', notes, request_key, packages=packages, movement_id=movement)


def cancel_order(order_id, reason, *, expected_token, request_key):
    reason = str(reason or '').strip()
    if not reason:
        raise ValueError('Escribe el motivo de cancelación.')
    with connect(write=True) as conn:
        if not _replayed(conn, request_key):
            row = _order(conn, order_id);_open(row, expected_token)
            # Same rule as inventory orders: an unpaid bill with nothing received is cancelled too.
            if row['expense_id'] and not row['received']:
                from services import expenses
                e = next((x for x in expenses._rows(conn) if x['id'] == row['expense_id']), None)
                if e and e['status'] == 'Activo' and not e['paid_cents']:
                    expenses.cancel(e['id'], f"Compra {row['code']} cancelada sin recepción ni pagos: {reason}", expected_revision=e['revision'], _conn=conn)
        return _event(conn, order_id, 'Cancelación', reason, request_key)
