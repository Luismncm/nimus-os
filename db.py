"""SQLite connections, versioned migration and consistent online backups."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from models.constants import JOB_STATUSES, MACHINE_STATUSES, ORDER_STATUSES, PRIORITIES, PROCESSES

BASE_DIR = Path(__file__).resolve().parent
CORE_SCHEMA_VERSION = 11


def database_path() -> Path:
    return Path(os.environ.get("NIMUS_DB_PATH", BASE_DIR / "data" / "nimus_production.db")).resolve()


def postgres_enabled() -> bool:
    """Postgres when DATABASE_URL points at it (the cloud); SQLite on this computer otherwise.

    Read from the environment only, so the local app never needs the Postgres driver installed.
    """
    return os.environ.get('DATABASE_URL', '').startswith(('postgres://', 'postgresql://')) or bool(os.environ.get('NIMUS_PG_PER_PATH'))


@contextmanager
def connect(path: Path | str | None = None, *, write: bool = False, migration: bool = False, reconciliation: bool = False):
    # An explicit path is always a SQLite file (migrations, backups, imports); otherwise the configured database.
    if path is None and postgres_enabled():
        from pgcompat.connection import connect as pg_connect
        with pg_connect(write=write, migration=migration, reconciliation=reconciliation) as conn:
            yield conn
        return
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.create_function('nimus_reconciling',0,lambda:int(write and reconciliation))
    conn.execute("PRAGMA foreign_keys = OFF" if migration else "PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        if migration and conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('La migración produjo relaciones inválidas.')
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def backup_database(path: Path | str | None = None, *, label: str = "manual") -> Path:
    if path is None and postgres_enabled():
        raise OSError('La base en la nube se respalda en Neon (restauración a cualquier momento); no hay archivo local que copiar.')
    source = Path(path) if path is not None else database_path()
    folder = source.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{source.stem}-{label}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dest:
            src.backup(dest)
    return target


def _options(values: tuple[str, ...]) -> str:
    return ",".join("'" + value.replace("'", "''") + "'" for value in values)


def _create_schema(conn: sqlite3.Connection) -> None:
    priorities = _options(PRIORITIES)
    statements = [
        f"""CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            client TEXT NOT NULL DEFAULT '', project TEXT NOT NULL CHECK(length(trim(project)) > 0),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deadline TEXT,
            priority TEXT NOT NULL CHECK(priority IN ({priorities})),
            status TEXT NOT NULL CHECK(status IN ({_options(ORDER_STATUSES)})),
            notes TEXT NOT NULL DEFAULT '', blocked_manually INTEGER NOT NULL DEFAULT 0
                CHECK(blocked_manually IN (0,1)))""",
        """CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            name TEXT NOT NULL CHECK(length(trim(name)) > 0),
            quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity > 0),
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
        f"""CREATE TABLE parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            name TEXT NOT NULL CHECK(length(trim(name)) > 0),
            quantity_required INTEGER NOT NULL CHECK(typeof(quantity_required)='integer' AND quantity_required > 0),
            process TEXT NOT NULL CHECK(process IN ({_options(PROCESSES)})),
            material TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""",
        f"""CREATE TABLE machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL CHECK(length(trim(name)) > 0),
            status TEXT NOT NULL CHECK(status IN ({_options(MACHINE_STATUSES)})),
            notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)""",
        f"""CREATE TABLE production_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
            machine_id INTEGER REFERENCES machines(id) ON DELETE RESTRICT,
            quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity > 0),
            quantity_completed INTEGER NOT NULL DEFAULT 0 CHECK(typeof(quantity_completed)='integer'
                AND quantity_completed >= 0 AND quantity_completed <= quantity),
            status TEXT NOT NULL CHECK(status IN ({_options(JOB_STATUSES)})),
            priority TEXT NOT NULL CHECK(priority IN ({priorities})),
            started_at TEXT, expected_end TEXT, completed_at TEXT,
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK((status='Terminado' AND quantity_completed=quantity AND completed_at IS NOT NULL)
               OR (status<>'Terminado' AND quantity_completed<quantity AND completed_at IS NULL)),
            CHECK(status<>'En producción' OR started_at IS NOT NULL))""",
        "CREATE TABLE migration_log (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, detail TEXT NOT NULL)",
        "CREATE INDEX idx_items_order ON items(order_id)",
        "CREATE INDEX idx_parts_item ON parts(item_id)",
        "CREATE INDEX idx_jobs_part ON production_jobs(part_id)",
        "CREATE INDEX idx_jobs_machine ON production_jobs(machine_id)",
        "CREATE INDEX idx_jobs_status ON production_jobs(status)",
        "CREATE UNIQUE INDEX one_running_job_per_machine ON production_jobs(machine_id) WHERE status='En producción' AND machine_id IS NOT NULL",
    ]
    for statement in statements:
        conn.execute(statement)


def _create_guards(conn: sqlite3.Connection) -> None:
    for event in ("INSERT", "UPDATE"):
        exclusion = "AND id <> OLD.id" if event == "UPDATE" else ""
        conn.execute(f"""CREATE TRIGGER jobs_capacity_{event.lower()} BEFORE {event} ON production_jobs
        BEGIN
          SELECT CASE WHEN NEW.quantity + COALESCE((SELECT SUM(quantity) FROM production_jobs
             WHERE part_id=NEW.part_id {exclusion}),0) > (SELECT quantity_required FROM parts WHERE id=NEW.part_id)
             THEN RAISE(ABORT,'La asignación excede las unidades requeridas de la pieza.') END;
          SELECT CASE WHEN NEW.status='En producción' AND EXISTS(SELECT 1 FROM machines
             WHERE id=NEW.machine_id AND status IN ('Mantenimiento','Fuera de servicio'))
             THEN RAISE(ABORT,'La máquina no está operativa.') END;
        END""")
    conn.execute("""CREATE TRIGGER parts_capacity BEFORE UPDATE OF quantity_required ON parts BEGIN
        SELECT CASE WHEN NEW.quantity_required < COALESCE((SELECT SUM(quantity) FROM production_jobs WHERE part_id=OLD.id),0)
        THEN RAISE(ABORT,'La pieza tiene más unidades asignadas que la cantidad propuesta.') END; END""")
    conn.execute("""CREATE TRIGGER machine_busy BEFORE UPDATE OF status ON machines
        WHEN NEW.status <> 'Imprimiendo' AND EXISTS(SELECT 1 FROM production_jobs
             WHERE machine_id=NEW.id AND status='En producción') BEGIN
        SELECT RAISE(ABORT,'Pausa o termina el trabajo antes de cambiar la máquina.'); END""")
    conn.execute("""CREATE TRIGGER keep_delivered BEFORE DELETE ON orders WHEN OLD.status='Entregado'
        BEGIN SELECT RAISE(ABORT,'Un pedido entregado se conserva en el histórico.'); END""")
    owners = {
        "items": "SELECT status FROM orders WHERE id={row}.order_id",
        "parts": "SELECT o.status FROM orders o JOIN items i ON i.order_id=o.id WHERE i.id={row}.item_id",
        "production_jobs": "SELECT o.status FROM orders o JOIN items i ON i.order_id=o.id JOIN parts p ON p.item_id=i.id WHERE p.id={row}.part_id",
    }
    for table, owner in owners.items():
        for event in ("INSERT", "UPDATE", "DELETE"):
            references = ("OLD", "NEW") if event == "UPDATE" else (("OLD",) if event == "DELETE" else ("NEW",))
            condition = " OR ".join(f"({owner.format(row=row)})='Entregado'" for row in references)
            conn.execute(f"""CREATE TRIGGER delivered_{table}_{event.lower()} BEFORE {event} ON {table}
                WHEN {condition} BEGIN SELECT RAISE(ABORT,'El pedido entregado es de solo lectura.'); END""")


def _init_core_db(path: Path | str | None = None) -> None:
    """Migrate atomically; failures preserve the original schema and a backup."""
    target = Path(path) if path is not None else database_path()
    with connect(target) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        exists = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='orders'").fetchone())
    if version == CORE_SCHEMA_VERSION:
        return
    if version not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        raise RuntimeError(f"Base versión {version} no compatible; no se modificó.")
    backup = backup_database(target, label="pre-v013" if version == 10 else "pre-v012" if version == 9 else "pre-v011" if version == 8 else "pre-v010" if version == 7 else "pre-v09" if version == 6 else "pre-v08" if version == 5 else "pre-v07" if version == 4 else "pre-v06" if version == 3 else "pre-v04" if version == 2 else "pre-v02") if exists else None
    try:
        with connect(target, write=True, migration=True) as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] == CORE_SCHEMA_VERSION:
                return
            from models.inventory_schema import create_inventory_schema
            from models.recipe_schema import create_recipe_schema
            from models.operations_schema import create_operations_schema
            from models.manual_inventory_schema import create_manual_inventory_schema
            from models.quotation_schema import create_quotation_schema
            from models.sales_schema import create_sales_schema
            from models.expense_schema import create_expense_schema
            from models.treasury_schema import create_treasury_schema
            from models.document_schema import create_document_schema
            from models.planning_schema import create_planning_schema
            if conn.execute("PRAGMA user_version").fetchone()[0] == 10:
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 9:
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 8:
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 7:
                create_sales_schema(conn)
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 6:
                create_quotation_schema(conn)
                create_sales_schema(conn)
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 5:
                create_manual_inventory_schema(conn)
                create_quotation_schema(conn)
                create_sales_schema(conn)
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 4:
                create_operations_schema(conn)
                create_manual_inventory_schema(conn)
                create_quotation_schema(conn)
                create_sales_schema(conn)
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 3:
                create_recipe_schema(conn)
                create_operations_schema(conn)
                create_manual_inventory_schema(conn)
                create_quotation_schema(conn)
                create_sales_schema(conn)
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Hay relaciones inválidas en la base.")
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            if conn.execute("PRAGMA user_version").fetchone()[0] == 2:
                create_inventory_schema(conn)
                conn.execute("INSERT INTO migration_log(created_at,detail) VALUES(?,?)",
                             (datetime.now().isoformat(), "v0.4: inventario de Colección Origen; items existentes sin clasificar, sin entradas retroactivas."))
                create_recipe_schema(conn)
                create_operations_schema(conn)
                create_manual_inventory_schema(conn)
                create_quotation_schema(conn)
                create_sales_schema(conn)
                create_expense_schema(conn)
                create_treasury_schema(conn)
                create_document_schema(conn)
                create_planning_schema(conn)
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Hay relaciones inválidas en la base.")
                conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
                return
            old = {}
            old_sequences = {}
            if exists:
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Hay relaciones huérfanas en la base original.")
                for table in ("orders", "items", "parts", "machines", "production_jobs"):
                    old[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                old_sequences = dict(conn.execute("SELECT name,seq FROM sqlite_sequence"))
                for table in ("production_jobs", "parts", "items", "orders", "machines"):
                    conn.execute(f"DROP TABLE {table}")
            _create_schema(conn)
            create_inventory_schema(conn)
            if old:
                _restore_legacy(conn, old)
                for table, seq in old_sequences.items():
                    if table in old:
                        conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name=?", (seq, table))
                        if not conn.execute("SELECT 1 FROM sqlite_sequence WHERE name=?", (table,)).fetchone():
                            conn.execute("INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)", (table,seq))
                over = conn.execute("""SELECT p.id FROM parts p JOIN production_jobs j ON j.part_id=p.id
                    GROUP BY p.id HAVING SUM(j.quantity)>p.quantity_required""").fetchall()
                if over:
                    raise ValueError("Piezas sobreasignadas: " + ", ".join(f"PART-{r[0]:04d}" for r in over))
            now = datetime.now().isoformat(timespec="microseconds")
            for code in ("P1", "P2", "P3", "P4"):
                conn.execute("""INSERT OR IGNORE INTO machines(code,name,status,notes,updated_at)
                    VALUES(?,?,'Disponible','',?)""", (code, f"Impresora {code}", now))
            _create_guards(conn)
            create_recipe_schema(conn)
            create_operations_schema(conn)
            create_manual_inventory_schema(conn)
            create_quotation_schema(conn)
            create_sales_schema(conn)
            create_expense_schema(conn)
            create_treasury_schema(conn)
            create_document_schema(conn)
            create_planning_schema(conn)
            if old:
                from services.production import refresh_order
                for order in old["orders"]:
                    refresh_order(conn, order["id"])
            conn.execute(f"PRAGMA user_version = {CORE_SCHEMA_VERSION}")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("La migración produjo relaciones inválidas.")
    except (sqlite3.DatabaseError, ValueError) as exc:
        raise RuntimeError(f"Migración cancelada sin cambiar tus datos: {exc}. Respaldo: {backup or 'base nueva'}") from exc


def _restore_legacy(conn: sqlite3.Connection, old: dict) -> None:
    now = datetime.now().isoformat(timespec="microseconds")
    order_priority = {o["id"]: o["priority"] for o in old["orders"]}
    item_order = {i["id"]: i["order_id"] for i in old["items"]}
    part_order = {p["id"]: item_order[p["item_id"]] for p in old["parts"]}
    for table in ("orders", "items", "parts", "machines", "production_jobs"):
        for original in old[table]:
            row = dict(original)
            for field in ("notes", "material", "client"):
                if field in row:
                    row[field] = row[field] or ""
            if table == "orders":
                row["status"] = {"Abierto": "Pendiente"}.get(row["status"], row["status"])
                row["blocked_manually"] = int(row["status"] == "Bloqueado")
            elif table == "parts":
                row["process"] = {"Externo": "Producción externa"}.get(row["process"], row["process"])
            elif table == "machines" and row["status"] == "Imprimiendo":
                row["status"] = "Disponible"
            elif table == "production_jobs":
                row["quantity_completed"] = row.pop("completed_quantity")
                row["priority"] = order_priority[part_order[row["part_id"]]]
                previous = row["status"]
                row["status"] = {"Pendiente": "En cola", "Imprimiendo": "En producción", "Postproceso": "Pausado",
                                 "Listo": "Pausado"}.get(previous, previous)
                row["started_at"] = row["created_at"] if previous in ("Imprimiendo", "Postproceso", "Listo") or row["quantity_completed"] else None
                row["completed_at"] = None
                if row["quantity_completed"] == row["quantity"]:
                    row["status"] = "Terminado"
                    row["completed_at"] = row["updated_at"]
                if previous == "Listo" and row["quantity_completed"] < row["quantity"]:
                    row["notes"] += "\nMigración v0.2: antes Listo, con terminadas parciales; revisar cantidad real."
            if row != original:
                conn.execute("INSERT INTO migration_log(created_at,detail) VALUES(?,?)",
                             (now, f"{table} #{row['id']}: estado {original.get('status','')} → {row.get('status','')}; campos normalizados; original en respaldo pre-v02."))
            columns = ",".join(row)
            conn.execute(f"INSERT INTO {table}({columns}) VALUES({','.join('?' for _ in row)})", tuple(row.values()))
    for row in conn.execute("SELECT machine_id FROM production_jobs WHERE status='En producción' AND machine_id IS NOT NULL").fetchall():
        machine = conn.execute("SELECT status FROM machines WHERE id=?", (row[0],)).fetchone()
        if machine[0] in ("Mantenimiento", "Fuera de servicio"):
            raise ValueError(f"Máquina {row[0]} no operativa con un trabajo activo.")
        conn.execute("UPDATE machines SET status='Imprimiendo' WHERE id=?", (row[0],))


SCHEMA_VERSION = 33

def init_db(path=None):
    if path is None and postgres_enabled():
        # Postgres takes this same schema, translated once (pgcompat.schema); SQLite's migrations stay the source.
        from pgcompat.connection import ensure_schema
        ensure_schema()
        return
    target = Path(path) if path is not None else database_path()
    with connect(target) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version < CORE_SCHEMA_VERSION:
        _init_core_db(target)
    elif version not in (11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32):
        raise RuntimeError(f'Base versión {version} no compatible; no se modificó.')
    if version == 32:
        backup_database(target,label='pre-stock-directo-v33')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==32:
                from models.stock_run_schema import create_stock_run_schema
                create_stock_run_schema(conn)
                conn.execute('PRAGMA user_version = 33')
        return
    if version == 31:
        backup_database(target,label='pre-piezas-compartidas-v32')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==31:
                from models.job_extra_schema import create_share_schema
                create_share_schema(conn)
                conn.execute('PRAGMA user_version = 32')
        return init_db(target)
    if version == 30:
        backup_database(target,label='pre-excedentes-v31')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==30:
                from models.job_extra_schema import create_job_extra_schema
                create_job_extra_schema(conn)
                conn.execute('PRAGMA user_version = 31')
        return init_db(target)
    if version == 29:
        backup_database(target,label='pre-filamento-cargado-v30')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==29:
                from models.loadout_schema import create_loadout_schema
                create_loadout_schema(conn)
                conn.execute('PRAGMA user_version = 30')
        return init_db(target)
    if version == 28:
        backup_database(target,label='pre-desarrollo-v29')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==28:
                from models.development_schema import create_development_schema
                create_development_schema(conn)
                conn.execute('PRAGMA user_version = 29')
        return init_db(target)
    if version == 27:
        backup_database(target,label='pre-costos-consumibles-v28')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==27:
                from models.consumable_schema import create_consumable_cost_schema
                create_consumable_cost_schema(conn)
                conn.execute('PRAGMA user_version = 28')
        return init_db(target)
    if version == 26:
        backup_database(target,label='pre-consumibles-v27')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==26:
                from models.consumable_schema import create_consumable_schema
                create_consumable_schema(conn)
                conn.execute('PRAGMA user_version = 27')
        return init_db(target)
    if version == 25:
        backup_database(target,label='pre-compras-gastos-v26')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==25:
                from models.purchase_expense_schema import create_purchase_expense_schema
                create_purchase_expense_schema(conn)
                conn.execute('PRAGMA user_version = 26')
        return init_db(target)
    if version == 24:
        backup_database(target,label='pre-previsiones-v25')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==24:
                from models.spending_plan_schema import create_spending_plan_schema
                create_spending_plan_schema(conn)
                conn.execute('PRAGMA user_version = 25')
        return init_db(target)
    if version == 23:
        backup_database(target,label='pre-saldos-v24')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==23:
                from models.cash_projection_schema import create_cash_projection_schema
                create_cash_projection_schema(conn)
                conn.execute('PRAGMA user_version = 24')
        return init_db(target)
    if version == 22:
        backup_database(target,label='pre-pedidos-inventario-v23')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==22:
                from models.inbound_schema import create_inbound_schema
                create_inbound_schema(conn)
                conn.execute('PRAGMA user_version = 23')
        return init_db(target)
    if version == 21:
        backup_database(target,label='pre-reposicion-v22')
        with connect(target,write=True) as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0]==21:
                from models.restock_schema import create_restock_schema
                create_restock_schema(conn)
                conn.execute('PRAGMA user_version = 22')
        return init_db(target)
    if version == 20:
        backup_database(target,label="pre-control-v21")
        with connect(target,write=True) as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0]==20:
                from models.production_control_schema import create_production_control_schema
                create_production_control_schema(conn)
                from models.restock_schema import create_restock_schema
                create_restock_schema(conn)
                conn.execute("PRAGMA user_version = 22")
        return init_db(target)
    if version == CORE_SCHEMA_VERSION:
        backup_database(target, label="pre-capital-v12")
    from models.capital_schema import create_capital_schema
    from models.reconciliation_schema import create_reconciliation_schema
    from models.costing_schema import create_costing_schema
    from models.budget_schema import create_budget_schema
    from models.partner_capture_schema import create_partner_capture_schema
    from models.visual_schema import create_visual_schema
    from models.origin_schema import create_origin_schema
    from models.commerce_schema import create_commerce_schema
    if version == 19:backup_database(target,label='pre-flujo-comercial-v20')
    if version == 18:
        backup_database(target,label='pre-modelos-origen-v19')
    if version == 17:
        backup_database(target,label='pre-origen-v18')
    if version == 16:
        backup_database(target,label='pre-visual-v17')
    if version == 12:
        backup_database(target,label='pre-conciliacion-v13')
    if version == 13:
        backup_database(target,label='pre-costos-v14')
    if version == 14:
        backup_database(target,label='pre-presupuesto-v15')
    if version == 15:
        backup_database(target,label='pre-socios-v16')
    with connect(target, write=True) as conn:
        version=conn.execute('PRAGMA user_version').fetchone()[0]
        if version==SCHEMA_VERSION:
            return
        if version <= 11:
            create_capital_schema(conn)
        if version <= 12:
            create_reconciliation_schema(conn)
        if version<=13:
            create_costing_schema(conn)
        create_budget_schema(conn)
        create_partner_capture_schema(conn)
        create_visual_schema(conn)
        create_origin_schema(conn)
        from services.origin import bootstrap
        bootstrap(conn)
        create_commerce_schema(conn)
        from models.production_control_schema import create_production_control_schema
        create_production_control_schema(conn)
        from models.restock_schema import create_restock_schema
        create_restock_schema(conn)
        from models.inbound_schema import create_inbound_schema
        create_inbound_schema(conn)
        from models.cash_projection_schema import create_cash_projection_schema
        create_cash_projection_schema(conn)
        from models.spending_plan_schema import create_spending_plan_schema
        create_spending_plan_schema(conn)
        from models.purchase_expense_schema import create_purchase_expense_schema
        create_purchase_expense_schema(conn)
        from models.consumable_schema import create_consumable_schema,create_consumable_cost_schema
        create_consumable_schema(conn)
        create_consumable_cost_schema(conn)
        from models.development_schema import create_development_schema
        create_development_schema(conn)
        from models.loadout_schema import create_loadout_schema
        create_loadout_schema(conn)
        from models.job_extra_schema import create_job_extra_schema, create_share_schema
        create_job_extra_schema(conn)
        create_share_schema(conn)
        from models.stock_run_schema import create_stock_run_schema
        create_stock_run_schema(conn)
        conn.execute("PRAGMA user_version = 33")
