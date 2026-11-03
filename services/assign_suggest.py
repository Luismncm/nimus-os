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
