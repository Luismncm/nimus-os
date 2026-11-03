"""Per-purchased-component replenishment thresholds; no physical stock is invented."""

def create_restock_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS restock_minimums (
        component_id INTEGER PRIMARY KEY REFERENCES catalog_components(id),
        minimum INTEGER NOT NULL CHECK(typeof(minimum)='integer' AND minimum>=0),
        revision INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL)''')
