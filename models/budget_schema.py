"""Monthly plans and immutable revisions, independent of financial documents."""


def create_budget_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS budget_months (
        id INTEGER PRIMARY KEY, month TEXT NOT NULL UNIQUE,
        receipts_cents INTEGER CHECK(receipts_cents>=0),
        net_sales_cents INTEGER CHECK(net_sales_cents>=0),
        margin_bps INTEGER CHECK(margin_bps>0 AND margin_bps<=10000),
        notes TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS budget_lines (
        id INTEGER PRIMARY KEY, month_id INTEGER NOT NULL REFERENCES budget_months(id),
        category TEXT NOT NULL, fixed_cents INTEGER NOT NULL CHECK(fixed_cents>=0),
        variable_cents INTEGER NOT NULL CHECK(variable_cents>=0),
        role TEXT NOT NULL CHECK(role IN ('Operación','Costo directo','Inversión / único')),
        priority TEXT NOT NULL CHECK(priority IN ('Esencial','Ajustable','Opcional')),
        tax_bps INTEGER CHECK(tax_bps IN (0,1600)), notes TEXT NOT NULL DEFAULT '',
        UNIQUE(month_id,category))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS budget_events (
        id INTEGER PRIMARY KEY, month_id INTEGER NOT NULL REFERENCES budget_months(id),
        revision INTEGER NOT NULL, snapshot TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL, UNIQUE(month_id,revision))''')
    for action in ('UPDATE','DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS budget_events_keep_{action.lower()}
            BEFORE {action} ON budget_events BEGIN
            SELECT RAISE(ABORT,'Guarda una nueva versión para conservar el historial del presupuesto.'); END''')
