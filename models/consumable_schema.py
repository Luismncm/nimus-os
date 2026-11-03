"""Consumables by unit (filament, resin, paint, hardware…): an immutable ledger plus package orders.

Quantities are stored in a base unit per item: g (mass), ml (volume) or pza (pieces). kg and L are
entry/display conveniences. Balances are the sum of movements; nothing is edited in place.
Tracking each spool or bottle later (code/QR) adds a consumable_packages table and an optional
package_id on movements, without changing how balances are computed today.
"""


def create_consumable_cost_schema(conn):
    """v28: reference cost per package, and the production order and frozen cost of each consumption."""
    def columns(table):return {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
    if 'package_cost_cents' not in columns('consumables'):
        conn.execute('ALTER TABLE consumables ADD COLUMN package_cost_cents INTEGER CHECK(package_cost_cents IS NULL OR package_cost_cents>=0)')
    if 'production_order_id' not in columns('consumable_movements'):
        # No foreign key: an order can still be deleted before production starts; the code keeps the trace.
        conn.execute('ALTER TABLE consumable_movements ADD COLUMN production_order_id INTEGER')
        conn.execute("ALTER TABLE consumable_movements ADD COLUMN order_code TEXT NOT NULL DEFAULT ''")
        conn.execute('ALTER TABLE consumable_movements ADD COLUMN cost_cents INTEGER CHECK(cost_cents IS NULL OR cost_cents>=0)')
    conn.execute('CREATE INDEX IF NOT EXISTS consumable_movements_order ON consumable_movements(production_order_id)')


GENERIC_FILAMENTS =(('PLA Genérico', 'PLA', 'Blanco'), ('PETG Genérico', 'PETG', 'Negro'), ('TPU Genérico', 'TPU 95A', 'Natural'))


def seed_generic(conn):
    """Start an empty catalog with three generic filaments: 1 kg spools and no stock until it is counted."""
    if conn.execute('SELECT 1 FROM consumables').fetchone():
        return
    from utils.dates import timestamp
    stamp = timestamp()
    for name, spec, color in GENERIC_FILAMENTS:
        conn.execute('''INSERT INTO consumables(identity,name,spec,color,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?)''',
                     (name.casefold(), name, spec, color, 'Filamento genérico de inicio. Cuenta o pesa el material real.', stamp, stamp))


def create_consumable_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS consumables (
        id INTEGER PRIMARY KEY, identity TEXT NOT NULL UNIQUE, name TEXT NOT NULL CHECK(length(trim(name))>0),
        category TEXT NOT NULL DEFAULT 'Filamento', unit TEXT NOT NULL DEFAULT 'g' CHECK(unit IN ('g','ml','pza')),
        spec TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '', brand TEXT NOT NULL DEFAULT '',
        package_label TEXT NOT NULL DEFAULT 'Carrete', package_size REAL NOT NULL DEFAULT 1000 CHECK(package_size>0),
        minimum REAL NOT NULL DEFAULT 0 CHECK(minimum>=0),
        notes TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS consumable_orders (
        id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
        consumable_id INTEGER NOT NULL REFERENCES consumables(id),
        packages INTEGER NOT NULL CHECK(typeof(packages)='integer' AND packages>0),
        package_size REAL NOT NULL CHECK(package_size>0),
        supplier TEXT NOT NULL, ordered_on TEXT NOT NULL, expected_on TEXT, notes TEXT NOT NULL,
        expense_id INTEGER, created_at TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS consumable_movements (
        id INTEGER PRIMARY KEY, consumable_id INTEGER NOT NULL REFERENCES consumables(id),
        kind TEXT NOT NULL CHECK(kind IN ('Saldo inicial','Entrada','Consumo','Ajuste')),
        quantity REAL NOT NULL CHECK(quantity<>0), job_code TEXT NOT NULL DEFAULT '',
        order_id INTEGER REFERENCES consumable_orders(id), notes TEXT NOT NULL,
        created_at TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0),
        CHECK((kind IN ('Saldo inicial','Entrada') AND quantity>0) OR (kind='Consumo' AND quantity<0) OR kind='Ajuste'))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS consumable_order_events (
        id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES consumable_orders(id),
        kind TEXT NOT NULL CHECK(kind IN ('Estado','Recepción','Cancelación')),
        stage TEXT CHECK(stage IS NULL OR stage IN ('Solicitado','Confirmado','En camino')),
        packages INTEGER, movement_id INTEGER UNIQUE REFERENCES consumable_movements(id), notes TEXT NOT NULL,
        created_at TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0),
        CHECK((kind='Recepción' AND movement_id IS NOT NULL AND packages>0) OR (kind<>'Recepción' AND movement_id IS NULL)),
        CHECK(kind<>'Estado' OR stage IS NOT NULL))''')
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS consumable_cancel_once ON consumable_order_events(order_id) WHERE kind='Cancelación'")
    conn.execute('CREATE INDEX IF NOT EXISTS consumable_movements_item ON consumable_movements(consumable_id,id)')
    for table in ('consumable_movements', 'consumable_orders', 'consumable_order_events'):
        for operation in ('UPDATE', 'DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_immutable
                BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Se conserva el historial de consumibles.'); END''')
    # Existing filament readings become each material's opening balance, so production alerts keep their numbers.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='material_availability'").fetchone():
        from utils.dates import timestamp
        stamp = timestamp()
        for row in conn.execute('SELECT * FROM material_availability').fetchall():
            if conn.execute('SELECT 1 FROM consumables WHERE identity=?', (row['identity'],)).fetchone():
                continue
            cid = conn.execute('''INSERT INTO consumables(identity,name,minimum,created_at,updated_at)
                VALUES(?,?,?,?,?)''', (row['identity'], row['name'], row['minimum_grams'], stamp, stamp)).lastrowid
            if row['available_grams'] > 0:
                conn.execute('''INSERT INTO consumable_movements(consumable_id,kind,quantity,notes,created_at,request_key)
                    VALUES(?,'Saldo inicial',?,?,?,?)''', (cid, row['available_grams'], 'Lectura anterior de material disponible',
                    row['updated_at'], f'migration:consumable:{cid}'))
    # Only when nothing was carried over: an empty catalog starts with generic filaments.
    seed_generic(conn)
