"""Filament mounted on each printer, so assignment can prefer a machine that needs no spool change."""


def create_loadout_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS machine_loadout (
        machine_id INTEGER PRIMARY KEY REFERENCES machines(id) ON DELETE CASCADE,
        material TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)''')
