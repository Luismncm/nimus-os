"""Checks every service repeats: a record that must exist, a revision that must still match, a past date."""
import json
from datetime import date
from utils.dates import now


def fetch(conn, table, record_id, missing):
    row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (record_id,)).fetchone()
    if not row: raise ValueError(missing)
    return row


def same_revision(row, expected, changed):
    if row['revision'] != expected: raise ValueError(changed)


def past_date(value, label, *, future=False):
    """ISO date of a record; never later than today unless `future`."""
    try:
        result = date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f'Revisa {label}.') from None
    if not future and result > now().date().isoformat():
        raise ValueError(f'{label}: no puede ser una fecha futura.')
    return result


def canonical(value):
    """Stable JSON for audit trails and signatures."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def has_table(conn, name):
    return bool(conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (name,)).fetchone())
