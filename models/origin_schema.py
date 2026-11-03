"""Typed components and immutable complete lamp recipes; existing rows stay intact."""
def create_origin_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS origin_components (
      component_id INTEGER PRIMARY KEY REFERENCES catalog_components(id),
      role TEXT NOT NULL CHECK(role IN ('Pantalla','Base','CAP','Tapa','Cable','Foco','Empaque')),
      supply TEXT NOT NULL CHECK(supply IN ('Fabricar','Comprar')),
      color TEXT NOT NULL DEFAULT '', shape TEXT NOT NULL DEFAULT '',
      CHECK((role IN ('Cable','Foco','Empaque'))=(supply='Comprar')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS origin_base_sets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,color TEXT NOT NULL,material TEXT NOT NULL,
      base_id INTEGER NOT NULL REFERENCES origin_components(component_id),
      cap_id INTEGER NOT NULL REFERENCES origin_components(component_id),
      lid_id INTEGER NOT NULL REFERENCES origin_components(component_id),
      created_at TEXT NOT NULL,UNIQUE(base_id,cap_id,lid_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS origin_recipes (
      recipe_id INTEGER PRIMARY KEY REFERENCES recipe_versions(id),model TEXT NOT NULL,
      shade_id INTEGER NOT NULL REFERENCES origin_components(component_id),
      base_set_id INTEGER NOT NULL REFERENCES origin_base_sets(id),
      cable_id INTEGER NOT NULL REFERENCES origin_components(component_id),
      bulb_id INTEGER NOT NULL REFERENCES origin_components(component_id),
      packaging_id INTEGER NOT NULL REFERENCES origin_components(component_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS origin_base_models (
      id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS origin_base_colors (
      base_set_id INTEGER PRIMARY KEY REFERENCES origin_base_sets(id),
      model_id INTEGER NOT NULL REFERENCES origin_base_models(id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog_component_retirements (
      component_id INTEGER PRIMARY KEY REFERENCES catalog_components(id),reason TEXT NOT NULL,created_at TEXT NOT NULL)''')
    for table in ('origin_components','origin_base_sets','origin_recipes','origin_base_models','origin_base_colors','catalog_component_retirements'):
        for event in ('UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS keep_{table}_{event.lower()} BEFORE {event} ON {table}
              BEGIN SELECT RAISE(ABORT,'La definición Origen se conserva. Crea otra variante o versión.'); END''')
