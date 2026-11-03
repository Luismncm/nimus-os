from datetime import date
from db import connect
from services.catalog import clean
from services.quotations import number
from utils.dates import timestamp

def readings():
    with connect() as conn:return [dict(r) for r in conn.execute('SELECT * FROM material_availability ORDER BY name')]

def save_material(name,available,minimum=0):
    # Readings are counts in the consumables ledger, which also keeps material_availability current.
    name=clean(name)
    if not name or len(name)>160:raise ValueError('Indica un material válido.')
    grams=float(number(available,'Gramos disponibles',maximum=1000000))
    low=float(number(minimum,'Mínimo deseado',maximum=1000000))
    from services import consumables
    consumables.save_reading(name,grams,low)

def maintenance():
    with connect() as conn:return {r['machine_id']:dict(r) for r in conn.execute('SELECT * FROM machine_maintenance_due')}

def save_maintenance(machine_id,due_on=None,notes=''):
    day=date.fromisoformat(str(due_on)).isoformat() if due_on else None
    with connect(write=True) as conn:
        if not conn.execute('SELECT 1 FROM machines WHERE id=?',(machine_id,)).fetchone():raise ValueError('La máquina no está disponible.')
        conn.execute('''INSERT INTO machine_maintenance_due VALUES(?,?,?,?) ON CONFLICT(machine_id) DO UPDATE SET
            due_on=excluded.due_on,notes=excluded.notes,updated_at=excluded.updated_at''',(machine_id,day,str(notes or '').strip(),timestamp()))
