"""Internal development projects: an order flagged as prototyping, never as a sale.

Prints, filament, consumables and real cost reuse the order's tables, so the queue, agenda,
reservations and costing work unchanged. This table only marks the order and holds its goal and budget.
"""


def create_development_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS development_projects (
        order_id INTEGER PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
        goal TEXT NOT NULL DEFAULT '', budget_cents INTEGER CHECK(budget_cents IS NULL OR budget_cents>=0),
        status TEXT NOT NULL DEFAULT 'Activo' CHECK(status IN ('Activo','Cerrado')),
        created_at TEXT NOT NULL, closed_at TEXT)''')
    # One prototype launch per form submission: a double click never creates two prints.
    conn.execute('''CREATE TABLE IF NOT EXISTS development_launches (
        request_key TEXT PRIMARY KEY CHECK(length(request_key)>0),
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        job_id INTEGER NOT NULL, created_at TEXT NOT NULL)''')
