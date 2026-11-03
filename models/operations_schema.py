"""Manual fulfillment tracking, independent from manufactured quantities."""


def create_operations_schema(conn):
    conn.execute('''CREATE TABLE item_tracking (
      item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
      label TEXT NOT NULL DEFAULT '', checked_at TEXT,
      revision INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE order_stages (
      order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
      stage TEXT NOT NULL CHECK(stage IN ('revision','packing','dispatch')),
      checked_at TEXT, revision INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
      PRIMARY KEY(order_id,stage))''')
    conn.execute('''CREATE TABLE operation_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
      detail TEXT NOT NULL, created_at TEXT NOT NULL)''')
    for table, owner in (('item_tracking', '(SELECT o.status FROM orders o JOIN items i ON i.order_id=o.id WHERE i.id={row}.item_id)'),
                         ('order_stages', '(SELECT status FROM orders WHERE id={row}.order_id)')):
        for event in ('INSERT','UPDATE','DELETE'):
            refs = ('OLD','NEW') if event=='UPDATE' else ('OLD',) if event=='DELETE' else ('NEW',)
            condition=' OR '.join(owner.format(row=ref)+"='Entregado'" for ref in refs)
            conn.execute(f"CREATE TRIGGER delivered_{table}_{event.lower()} BEFORE {event} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'El pedido entregado es de solo lectura.'); END")
    conn.execute("INSERT INTO migration_log(created_at,detail) VALUES(datetime('now'),'v0.7: etiquetas de items y checklist manual de revisión, empacado y salida; sin alterar producción.')")
