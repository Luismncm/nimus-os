"""Which printer should take a print: loaded filament first, then the earliest free slot.

Same rule as print-farm managers (match the material already mounted to avoid spool changes),
on top of NIMUS's own reservations: a machine that is down or blocked by a print without end is
never suggested.
"""
from datetime import timedelta
from db import connect
from services.catalog import clean
from utils.dates import now, timestamp

SPOOL_CHANGE_MINUTES = 60


def set_loaded(machine_id, material):
    material = clean(material)
    with connect(write=True) as conn:
        if not conn.execute('SELECT 1 FROM machines WHERE id=?', (machine_id,)).fetchone():
            raise ValueError('La máquina ya no existe.')
        conn.execute('''INSERT INTO machine_loadout(machine_id,material,updated_at) VALUES(?,?,?)
            ON CONFLICT(machine_id) DO UPDATE SET material=excluded.material,updated_at=excluded.updated_at''', (machine_id, material, timestamp()))


def same_material(a, b):
    return bool(a and b) and clean(a).casefold() == clean(b).casefold()


def rank(snapshot, material='', duration=None, *, at=None):
    """Machines ordered by fit for this print, each with when it is free and whether the filament matches."""
    from services import resources
    from services.timeline import machine_timeline
    at = at or now()
    rows = []
    for m in snapshot['machines']:
        if m['status'] in ('Mantenimiento', 'Fuera de servicio'):
            continue
        free = resources.first_free(0, m['id'], duration, at=at) if duration else None
        if not duration:
            a = machine_timeline(m, snapshot['jobs'], at)['availability']
            free = None if a['kind'] == 'bloqueada' else at if a['kind'] == 'libre' else a['since']
        if free is None:
            continue
        match = same_material(m.get('loaded_material'), material)
        rows.append(dict(machine=m, free=free, match=match, change=bool(material) and not match))
    # A loaded match wins unless another printer frees up more than an hour earlier: a spool change costs that much.
    rows.sort(key=lambda r: (r['free'] + (timedelta(minutes=SPOOL_CHANGE_MINUTES) if r['change'] else timedelta()), not r['match'], r['machine']['code']))
    return rows


def best(snapshot, material='', duration=None):
    rows = rank(snapshot, material, duration)
    return rows[0] if rows else None


def reason(row, at=None):
    """'libre ahora · PLA cargado' — why this machine is suggested."""
    from services.timeline import when
    at = at or now()
    timing = 'libre ahora' if row['free'] <= at else f"libre {when(row['free'], at)}"
    loaded = row['machine'].get('loaded_material')
    return timing + (' · material cargado' if row['match'] else f" · cambiar filamento ({loaded or 'sin registrar'})" if row['change'] else '')


def pending_parts(order, item_id=None):
    """Pieces with units still to assign, grouped by material so shared filaments sit together."""
    rows = [p for i in order['items'] if item_id in (None, i['id']) for p in i['parts'] if p['quantity_unassigned'] > 0]
    return sorted(rows, key=lambda p: ((p['material'] or '').casefold(), p['item_name'], p['id']))


def auto_split(parts, machines):
    """Each piece whole to the least loaded available machine, preferring one already on that material.

    Returns {(part_id, machine_id): units}; machine_id None means no machine (nothing available).
    Keeping a piece on one machine avoids one-unit jobs; existing pending units count as load.
    """
    available = [m for m in machines if m['status'] == 'Disponible']
    if not available:
        return {(p['id'], None): p['quantity_unassigned'] for p in parts}
    load = {m['id']: m.get('pending_units', 0) for m in available}
    code = {m['id']: m['code'] for m in available}
    materials = {m['id']: set() for m in available}
    loaded = {m['id']: m.get('loaded_material', '') for m in available}
    amounts = {}
    for p in sorted(parts, key=lambda p: -p['quantity_unassigned']):
        # The filament already mounted is worth the piece's own units of load: it avoids a spool change
        # without piling a whole batch on one printer.
        bonus = lambda m: p['quantity_unassigned'] if same_material(loaded[m], p['material']) else 0
        machine = min(load, key=lambda m: (load[m] - bonus(m), p['material'] not in materials[m], code[m]))
        amounts[(p['id'], machine)] = p['quantity_unassigned']
        load[machine] += p['quantity_unassigned']
        materials[machine].add(p['material'])
    return amounts
