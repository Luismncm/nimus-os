"""Manage machines without losing the production history tied to their IDs."""
from db import connect
from models.constants import MACHINE_STATUSES
from services.catalog import clean
from services.quotations import cents
from utils.dates import timestamp


def save_machine(code, name, status='Disponible', notes='', machine_id=None, *, hourly_rate=None):
    code, name = clean(code).upper(), clean(name)
    if not code or not name:
        raise ValueError('El código y el nombre de la máquina son obligatorios.')
    if status not in MACHINE_STATUSES:
        raise ValueError('Estado de máquina no válido.')
    rate = cents(hourly_rate) if hourly_rate else None
    with connect(write=True) as conn:
        if conn.execute('SELECT 1 FROM machines WHERE lower(code)=lower(?) AND id<>?', (code, machine_id or 0)).fetchone():
            raise ValueError('Ya existe una máquina con ese código.')
        if machine_id is None:
            if status == 'Imprimiendo':
                raise ValueError('Inicia un trabajo después de crear la máquina.')
            return conn.execute('INSERT INTO machines(code,name,status,notes,hourly_rate_cents,updated_at) VALUES(?,?,?,?,?,?)',
                                (code, name, status, notes.strip(), rate, timestamp())).lastrowid
        row = conn.execute('SELECT * FROM machines WHERE id=?', (machine_id,)).fetchone()
        if not row:
            raise ValueError('La máquina ya no existe.')
        busy = conn.execute("SELECT 1 FROM production_jobs WHERE machine_id=? AND status='En producción'", (machine_id,)).fetchone()
        if bool(busy) != (status == 'Imprimiendo'):
            raise ValueError('Pausa o termina el trabajo para cambiar la disponibilidad; inicia un trabajo para marcar Imprimiendo.')
        conn.execute('UPDATE machines SET code=?,name=?,status=?,notes=?,hourly_rate_cents=?,updated_at=? WHERE id=?',
                     (code, name, status, notes.strip(), rate, timestamp(), machine_id))
        return machine_id


def remove_machine(machine_id):
    with connect(write=True) as conn:
        if conn.execute('SELECT 1 FROM production_jobs WHERE machine_id=?', (machine_id,)).fetchone():
            raise ValueError('La máquina tiene trabajos asociados. Conserva su historial y archívala al terminar los pendientes.')
        conn.execute('DELETE FROM machines WHERE id=?', (machine_id,))


def archive_machine(machine_id, archived=True):
    with connect(write=True) as conn:
        if archived and conn.execute("SELECT 1 FROM production_jobs WHERE machine_id=? AND status<>'Terminado'", (machine_id,)).fetchone():
            raise ValueError('Termina o reasigna los trabajos pendientes antes de archivar la máquina.')
        conn.execute("UPDATE machines SET archived=?,updated_at=? WHERE id=?", (int(archived), timestamp(), machine_id))
