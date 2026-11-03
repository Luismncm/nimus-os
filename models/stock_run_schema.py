"""Prints made only for inventory, without a customer order or a stock lot.

A stock run is an internal order flagged here, like development projects: its prints are ordinary
jobs and its good units are posted to inventory as they are recorded.
"""


def create_stock_run_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS stock_runs (
        order_id INTEGER PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
        component_id INTEGER REFERENCES catalog_components(id) ON DELETE RESTRICT,
        job_id INTEGER,
        request_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL)''')
