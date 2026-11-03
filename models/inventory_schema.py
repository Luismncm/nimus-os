"""Additive schema for collection inventory. No existing production is inferred."""
import sqlite3


def create_inventory_schema(conn: sqlite3.Connection, *, item_column: bool = True) -> None:
    if item_column:
        conn.execute("ALTER TABLE items ADD COLUMN collection TEXT NOT NULL DEFAULT '' CHECK(collection IN ('','Origen'))")
    conn.execute("""CREATE TABLE inventory_skus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_key TEXT NOT NULL UNIQUE,
        collection TEXT NOT NULL CHECK(collection IN ('Origen','General')),
        product TEXT NOT NULL CHECK(length(trim(product))>0),
        part TEXT NOT NULL CHECK(length(trim(part))>0),
        material TEXT NOT NULL DEFAULT '', process TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE inventory_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku_id INTEGER NOT NULL REFERENCES inventory_skus(id) ON DELETE RESTRICT,
        job_id INTEGER REFERENCES production_jobs(id) ON DELETE RESTRICT,
        kind TEXT NOT NULL CHECK(kind IN ('Producción','Corrección','Traslado','B2B','Reversión','Entrega')),
        source TEXT NOT NULL CHECK(source IN ('Producción','Colección','Stock','B2B')),
        destination TEXT NOT NULL CHECK(destination IN ('Producción','Colección','Stock','B2B','Entregado')),
        quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
        client TEXT NOT NULL DEFAULT '', client_key TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        reversal_of INTEGER UNIQUE REFERENCES inventory_movements(id) ON DELETE RESTRICT,
        request_key TEXT UNIQUE,
        CHECK(source<>destination),
        CHECK((source='B2B' OR destination IN ('B2B','Entregado')) = (length(trim(client))>0 AND length(client_key)>0)),
        CHECK((kind='Reversión') = (reversal_of IS NOT NULL)),
        CHECK((kind='Producción' AND source='Producción' AND destination='Colección' AND job_id IS NOT NULL)
           OR (kind='Corrección' AND source='Colección' AND destination='Producción' AND job_id IS NOT NULL)
           OR (kind='Traslado' AND source IN ('Colección','Stock') AND destination IN ('Colección','Stock') AND job_id IS NULL)
           OR (kind='B2B' AND source IN ('Colección','Stock') AND destination='B2B' AND job_id IS NULL)
           OR (kind='Entrega' AND source IN ('Colección','Stock') AND destination='Entregado' AND job_id IS NULL)
           OR (kind='Reversión' AND source<>'Producción' AND destination NOT IN ('Producción','Entregado') AND job_id IS NULL)))""")
    conn.execute("CREATE INDEX idx_inventory_sku ON inventory_movements(sku_id)")
    conn.execute("CREATE INDEX idx_inventory_job ON inventory_movements(job_id)")
    conn.execute("""CREATE TRIGGER inventory_balance BEFORE INSERT ON inventory_movements
        WHEN NEW.source<>'Producción' BEGIN
        SELECT CASE WHEN NEW.quantity > COALESCE((SELECT SUM(
            CASE WHEN destination=NEW.source THEN quantity ELSE 0 END
          - CASE WHEN source=NEW.source THEN quantity ELSE 0 END)
          FROM inventory_movements WHERE sku_id=NEW.sku_id
          AND (NEW.source<>'B2B' OR client_key=NEW.client_key)),0)
        THEN RAISE(ABORT,'No hay suficientes unidades en ese origen. Actualiza el inventario.') END;
        END""")
    for event in ('UPDATE', 'DELETE'):
        conn.execute(f"""CREATE TRIGGER inventory_immutable_{event.lower()} BEFORE {event} ON inventory_movements
            BEGIN SELECT RAISE(ABORT,'Los movimientos se conservan. Usa una reversión o corrige el trabajo.'); END""")
