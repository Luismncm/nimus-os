"""Manual partner entries coexist with immutable spreadsheet provenance."""
import re


def create_partner_capture_schema(conn):
    info=list(conn.execute('PRAGMA table_info(capital_movements)'))
    if next(r for r in info if r[1]=='origin')[3]:
        original=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='capital_movements'").fetchone()[0]
        schema=re.sub(r'\borigin\s+TEXT\s+UNIQUE\s+NOT\s+NULL\s+REFERENCES',
            'origin TEXT UNIQUE REFERENCES',original,flags=re.I)
        if schema==original: raise ValueError('La estructura de procedencia de Socios no coincide con la versión esperada.')
        schema=re.sub(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?capital_movements',
            'CREATE TABLE capital_movements_capture',schema,count=1,flags=re.I)
        extras=[r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='capital_movements' AND type IN ('index','trigger') AND sql IS NOT NULL")]
        columns=','.join('"'+r[1]+'"' for r in info)
        conn.execute(schema)
        conn.execute(f'INSERT INTO capital_movements_capture({columns}) SELECT {columns} FROM capital_movements')
        conn.execute('DROP TABLE capital_movements')
        conn.execute('ALTER TABLE capital_movements_capture RENAME TO capital_movements')
        for sql in extras: conn.execute(sql)
    columns={r[1] for r in conn.execute('PRAGMA table_info(capital_movements)')}
    for name,kind in (
        ('reference',"TEXT NOT NULL DEFAULT ''"),('request_key','TEXT'),('request_payload','TEXT'),
        ('created_at','TEXT'),('voided_at','TEXT'),('void_reason','TEXT')):
        if name not in columns: conn.execute(f'ALTER TABLE capital_movements ADD COLUMN {name} {kind}')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS capital_request_key ON capital_movements(request_key)')
