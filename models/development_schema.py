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


def create_development_journal_schema(conn):
    """v36: a project's notes, technical reports and links to its files.

    A report may name the print it tested by job code (no foreign key: deleting a print keeps the report).
    A link belongs to the project, or to one entry when it documents that note or report.
    """
    conn.execute('''CREATE TABLE IF NOT EXISTS development_entries (
        id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('Nota','Reporte')),
        title TEXT NOT NULL CHECK(length(trim(title))>0),
        body TEXT NOT NULL DEFAULT '',
        result TEXT CHECK(result IS NULL OR result IN ('Aprobado','Ajustar','Rechazado')),
        job_code TEXT NOT NULL DEFAULT '',
        pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
        revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0),
        CHECK(kind='Reporte' OR result IS NULL))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS development_links (
        id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        entry_id INTEGER REFERENCES development_entries(id) ON DELETE CASCADE,
        label TEXT NOT NULL CHECK(length(trim(label))>0),
        target TEXT NOT NULL CHECK(length(trim(target))>0),
        pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
        created_at TEXT NOT NULL,
        request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0))''')
    conn.execute('CREATE INDEX IF NOT EXISTS development_entries_order ON development_entries(order_id,created_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS development_links_order ON development_links(order_id,entry_id)')
