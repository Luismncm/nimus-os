"""Orders for future stock and their immutable receipt/follow-up history."""


def create_inbound_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS inventory_inbound_orders (
        id INTEGER PRIMARY KEY,code TEXT NOT NULL UNIQUE,
        sku_id INTEGER NOT NULL REFERENCES inventory_skus(id),
        quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
        destination TEXT NOT NULL CHECK(destination IN ('Colección','Stock')),
        supplier TEXT NOT NULL,reference TEXT NOT NULL CHECK(length(trim(reference))>0),
        ordered_on TEXT NOT NULL,expected_on TEXT,notes TEXT NOT NULL,
        created_at TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS inventory_inbound_events (
        id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES inventory_inbound_orders(id),
        kind TEXT NOT NULL CHECK(kind IN ('Recepción','Seguimiento','Cancelación')),
        movement_id INTEGER UNIQUE REFERENCES inventory_movements(id),
        payload TEXT NOT NULL CHECK(json_valid(payload)),notes TEXT NOT NULL,
        created_at TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0),
        CHECK((kind='Recepción' AND movement_id IS NOT NULL) OR (kind<>'Recepción' AND movement_id IS NULL)))''')
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS inbound_cancel_once ON inventory_inbound_events(order_id) WHERE kind='Cancelación'")
    conn.execute('CREATE INDEX IF NOT EXISTS inbound_events_order ON inventory_inbound_events(order_id,id)')
    for table in ('inventory_inbound_orders','inventory_inbound_events'):
        for operation in ('UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_immutable
                BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Se conserva el historial del pedido de inventario.'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS inbound_receipt_matches BEFORE INSERT ON inventory_inbound_events
        WHEN NEW.kind='Recepción' BEGIN
        SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM inventory_movements m JOIN inventory_inbound_orders p ON p.id=NEW.order_id
            WHERE m.id=NEW.movement_id AND m.sku_id=p.sku_id AND m.source='Externo'
            AND m.destination=p.destination AND m.kind='Entrada manual')
            THEN RAISE(ABORT,'La recepción no corresponde al pedido de inventario.') END;
        END''')
