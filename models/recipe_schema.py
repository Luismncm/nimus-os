"""Versioned product recipes and reservations; no historical stock is inferred."""
import sqlite3


def create_recipe_schema(conn: sqlite3.Connection) -> None:
    # Rebuild the two ledger tables to allow general components and explicit deliveries.
    # Copy every existing value/ID; deferred FK checks include reversal self-references.
    conn.execute('PRAGMA defer_foreign_keys=ON')
    seq = dict(conn.execute("SELECT name,seq FROM sqlite_sequence WHERE name IN ('inventory_skus','inventory_movements')"))
    conn.execute('CREATE TEMP TABLE saved_skus AS SELECT * FROM inventory_skus')
    conn.execute('CREATE TEMP TABLE saved_movements AS SELECT * FROM inventory_movements')
    conn.execute('DROP TABLE inventory_movements')
    conn.execute('DROP TABLE inventory_skus')
    from models.inventory_schema import create_inventory_schema
    create_inventory_schema(conn, item_column=False)
    conn.execute('INSERT INTO inventory_skus SELECT * FROM saved_skus')
    conn.execute('INSERT INTO inventory_movements SELECT * FROM saved_movements ORDER BY id')
    for name, value in seq.items():
        conn.execute('UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name=?', (value, name))
    conn.execute('DROP TABLE saved_movements')
    conn.execute('DROP TABLE saved_skus')
    statements = [
        """CREATE TABLE catalog_components (
          id INTEGER PRIMARY KEY AUTOINCREMENT, identity_key TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL, material TEXT NOT NULL, process TEXT NOT NULL, variant TEXT NOT NULL DEFAULT '',
          collection TEXT NOT NULL CHECK(collection IN ('Origen','General')), created_at TEXT NOT NULL)""",
        """CREATE TABLE catalog_products (
          id INTEGER PRIMARY KEY AUTOINCREMENT, identity_key TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL, variant TEXT NOT NULL DEFAULT '', collection TEXT NOT NULL CHECK(collection IN ('Origen','General')),
          created_at TEXT NOT NULL)""",
        """CREATE TABLE recipe_versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES catalog_products(id),
          version INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
          UNIQUE(product_id,version))""",
        """CREATE TABLE recipe_lines (
          recipe_id INTEGER NOT NULL REFERENCES recipe_versions(id),
          component_id INTEGER NOT NULL REFERENCES catalog_components(id),
          quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
          PRIMARY KEY(recipe_id,component_id))""",
        "ALTER TABLE orders ADD COLUMN fulfillment TEXT NOT NULL DEFAULT 'Personalizado' CHECK(fulfillment IN ('Personalizado','Cliente','Stock'))",
        "ALTER TABLE items ADD COLUMN recipe_id INTEGER REFERENCES recipe_versions(id)",
        "ALTER TABLE parts ADD COLUMN component_id INTEGER REFERENCES catalog_components(id)",
        "ALTER TABLE machines ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))",
        "ALTER TABLE inventory_skus ADD COLUMN component_id INTEGER REFERENCES catalog_components(id)",
        """CREATE TABLE recipe_requirements (
          id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
          component_id INTEGER NOT NULL REFERENCES catalog_components(id),
          quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
          production_part_id INTEGER UNIQUE REFERENCES parts(id) ON DELETE RESTRICT,
          UNIQUE(item_id,component_id))""",
        """CREATE TABLE inventory_reservations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          requirement_id INTEGER NOT NULL REFERENCES recipe_requirements(id) ON DELETE CASCADE,
          sku_id INTEGER NOT NULL REFERENCES inventory_skus(id),
          location TEXT NOT NULL CHECK(location IN ('Colección','Stock')),
          quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
          job_id INTEGER REFERENCES production_jobs(id) ON DELETE RESTRICT,
          status TEXT NOT NULL DEFAULT 'Activa' CHECK(status IN ('Activa','Liberada','Consumida')),
          created_at TEXT NOT NULL, closed_at TEXT,
          CHECK((status='Activa')=(closed_at IS NULL)))""",
        "ALTER TABLE inventory_movements ADD COLUMN order_id INTEGER REFERENCES orders(id)",
        "CREATE TABLE recipe_order_requests (request_key TEXT PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, signature TEXT NOT NULL)",
        "CREATE INDEX idx_reservation_sku ON inventory_reservations(sku_id,location,status)",
        "CREATE INDEX idx_reservation_requirement ON inventory_reservations(requirement_id)",
        "CREATE INDEX idx_sku_component ON inventory_skus(component_id)",
        """CREATE TRIGGER reservation_available BEFORE INSERT ON inventory_reservations BEGIN
          SELECT CASE WHEN NEW.status<>'Activa' OR NEW.quantity >
            COALESCE((SELECT SUM(CASE WHEN destination=NEW.location THEN quantity ELSE 0 END
            - CASE WHEN source=NEW.location THEN quantity ELSE 0 END) FROM inventory_movements WHERE sku_id=NEW.sku_id),0)
            - COALESCE((SELECT SUM(quantity) FROM inventory_reservations WHERE sku_id=NEW.sku_id AND location=NEW.location AND status='Activa'),0)
            THEN RAISE(ABORT,'Las existencias disponibles cambiaron. Actualiza y vuelve a calcular.') END;
          SELECT CASE WHEN (SELECT component_id FROM inventory_skus WHERE id=NEW.sku_id) IS NOT
            (SELECT component_id FROM recipe_requirements WHERE id=NEW.requirement_id)
            THEN RAISE(ABORT,'La pieza reservada no coincide con la receta.') END;
          SELECT CASE WHEN NEW.quantity + COALESCE((SELECT SUM(quantity) FROM inventory_reservations
            WHERE requirement_id=NEW.requirement_id AND status IN ('Activa','Consumida')),0) >
            (SELECT quantity FROM recipe_requirements WHERE id=NEW.requirement_id)
            THEN RAISE(ABORT,'La reserva excede la necesidad del pedido.') END;
          END""",
        """CREATE TRIGGER reservation_update BEFORE UPDATE ON inventory_reservations WHEN
          OLD.status<>'Activa' OR NEW.status NOT IN ('Liberada','Consumida') OR NEW.closed_at IS NULL OR
          NEW.requirement_id<>OLD.requirement_id OR NEW.sku_id<>OLD.sku_id OR NEW.location<>OLD.location OR
          NEW.quantity<>OLD.quantity OR NEW.job_id IS NOT OLD.job_id OR NEW.created_at<>OLD.created_at
          BEGIN SELECT RAISE(ABORT,'La reserva solo puede liberarse o consumirse.'); END""",
        """CREATE TRIGGER reservation_keep_active BEFORE DELETE ON inventory_reservations
          WHEN OLD.status='Activa' BEGIN SELECT RAISE(ABORT,'Libera la reserva antes de eliminar el pedido.'); END""",
    ]
    for statement in statements:
        conn.execute(statement)
    conn.execute('DROP TRIGGER inventory_balance')
    conn.execute("""CREATE TRIGGER inventory_balance BEFORE INSERT ON inventory_movements
      WHEN NEW.source<>'Producción' BEGIN
      SELECT CASE WHEN NEW.quantity > COALESCE((SELECT SUM(
        CASE WHEN destination=NEW.source THEN quantity ELSE 0 END - CASE WHEN source=NEW.source THEN quantity ELSE 0 END)
        FROM inventory_movements WHERE sku_id=NEW.sku_id AND (NEW.source<>'B2B' OR client_key=NEW.client_key)),0)
        - COALESCE((SELECT SUM(quantity) FROM inventory_reservations
          WHERE sku_id=NEW.sku_id AND location=NEW.source AND status='Activa'),0)
        THEN RAISE(ABORT,'No hay suficientes piezas libres; revisa las reservas del pedido.') END; END""")
    for table in ('recipe_versions', 'recipe_lines', 'catalog_components', 'catalog_products'):
        for event in ('UPDATE', 'DELETE'):
            conn.execute(f"""CREATE TRIGGER keep_{table}_{event.lower()} BEFORE {event} ON {table}
              BEGIN SELECT RAISE(ABORT,'El catálogo publicado se conserva. Crea otra variante o versión.'); END""")
    conn.execute("""INSERT INTO migration_log(created_at,detail) VALUES(datetime('now'),
      'v0.6: catálogo, recetas versionadas y reservas. Pedidos e inventario anteriores conservados sin vinculación automática.')""")
