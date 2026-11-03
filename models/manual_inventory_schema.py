"""Expand the existing ledger without changing any historical movement."""
import sqlite3


def create_manual_inventory_schema(conn: sqlite3.Connection) -> None:
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='inventory_movements'").fetchone()[0]
    if "'Entrada manual'" in sql:
        return
    # init_db holds an exclusive write transaction with FK enforcement disabled;
    # all relationships are validated before committing the rebuilt table.
    objects = list(conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='inventory_movements' AND type IN ('index','trigger') AND sql IS NOT NULL"))
    seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='inventory_movements'").fetchone()
    conn.execute('CREATE TEMP TABLE saved_manual_ledger AS SELECT * FROM inventory_movements')
    conn.execute('DROP TABLE inventory_movements')
    sql = sql.replace("'Reversión','Entrega'", "'Reversión','Entrega','Entrada manual'")
    sql = sql.replace("source IN ('Producción','Colección','Stock','B2B')", "source IN ('Producción','Colección','Stock','B2B','Externo')")
    sql = sql.replace("destination IN ('Producción','Colección','Stock','B2B','Entregado')", "destination IN ('Producción','Colección','Stock','B2B','Entregado','Externo')")
    sql = sql.replace("OR (kind='Corrección'", "OR (kind='Entrada manual' AND source='Externo' AND destination IN ('Colección','Stock') AND job_id IS NULL)\n           OR (kind='Corrección'")
    conn.execute(sql)
    conn.execute('INSERT INTO inventory_movements SELECT * FROM saved_manual_ledger ORDER BY id')
    if seq:
        conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='inventory_movements'", (seq[0],))
    conn.execute('DROP TABLE saved_manual_ledger')
    for row in objects:
        conn.execute(row[0].replace("WHEN NEW.source<>'Producción'", "WHEN NEW.source NOT IN ('Producción','Externo')"))
    conn.execute("INSERT INTO migration_log(created_at,detail) VALUES(datetime('now'),'v0.8: entradas manuales de inventario con reversión e historial; valores anteriores conservados.')")
