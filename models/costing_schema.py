def create_costing_schema(conn):
    for table,owner in [('component_cost_versions','component_id INTEGER NOT NULL REFERENCES catalog_components(id)'),
                        ('recipe_cost_extras','recipe_id INTEGER NOT NULL REFERENCES recipe_versions(id)'),
                        ('sale_cost_versions','sale_id INTEGER NOT NULL REFERENCES sales(id)')]:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY, {owner}, payload TEXT NOT NULL, source TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        for event in ('UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_keep_{event.lower()} BEFORE {event} ON {table}
                BEGIN SELECT RAISE(ABORT,'Guarda una nueva versión para conservar el costo anterior.'); END''')
