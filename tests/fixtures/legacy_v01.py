from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "nimus_production.db"

ORDER_PRIORITIES = ("Alta", "Media", "Baja")
ORDER_STATUSES = ("Abierto", "En producción", "Bloqueado", "Listo", "Entregado")
PART_PROCESSES = ("Impresión 3D", "Resina", "Postproceso", "Ensamble", "Grabado", "Empaque", "Externo")
JOB_STATUSES = ("Pendiente", "En cola", "Imprimiendo", "Postproceso", "Listo", "Bloqueado")
MACHINE_STATUSES = ("Disponible", "Imprimiendo", "Mantenimiento", "Fuera de servicio")


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                client TEXT,
                project TEXT NOT NULL,
                deadline TEXT,
                priority TEXT NOT NULL DEFAULT 'Media',
                status TEXT NOT NULL DEFAULT 'Abierto',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity_required INTEGER NOT NULL CHECK(quantity_required > 0),
                process TEXT NOT NULL DEFAULT 'Impresión 3D',
                material TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Disponible',
                notes TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS production_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                part_id INTEGER NOT NULL,
                machine_id INTEGER,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                completed_quantity INTEGER NOT NULL DEFAULT 0 CHECK(completed_quantity >= 0),
                status TEXT NOT NULL DEFAULT 'Pendiente',
                expected_end TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(part_id) REFERENCES parts(id) ON DELETE CASCADE,
                FOREIGN KEY(machine_id) REFERENCES machines(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_items_order ON items(order_id);
            CREATE INDEX IF NOT EXISTS idx_parts_item ON parts(item_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_part ON production_jobs(part_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_machine ON production_jobs(machine_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON production_jobs(status);
            """
        )

        now = _now()
        for code in ("P1", "P2", "P3", "P4"):
            conn.execute(
                """
                INSERT OR IGNORE INTO machines(code, name, status, notes, updated_at)
                VALUES (?, ?, 'Disponible', '', ?)
                """,
                (code, f"Impresora {code}", now),
            )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _next_code(conn: sqlite3.Connection, table: str, prefix: str) -> str:
    row = conn.execute(f"SELECT MAX(id) AS max_id FROM {table}").fetchone()
    next_id = (row["max_id"] or 0) + 1
    return f"{prefix}-{next_id:04d}"


def create_order(project: str, client: str = "", deadline: str = "", priority: str = "Media", notes: str = "") -> int:
    with connect() as conn:
        code = _next_code(conn, "orders", "ORD")
        now = _now()
        cur = conn.execute(
            """
            INSERT INTO orders(code, client, project, deadline, priority, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'Abierto', ?, ?, ?)
            """,
            (code, client.strip(), project.strip(), deadline or None, priority, notes.strip(), now, now),
        )
        return cur.lastrowid


def create_item(order_id: int, name: str, quantity: int, notes: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO items(order_id, name, quantity, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            (order_id, name.strip(), int(quantity), notes.strip(), _now()),
        )
        _touch_order(conn, order_id)
        return cur.lastrowid


def create_part(item_id: int, name: str, quantity_required: int, process: str, material: str = "", notes: str = "") -> int:
    with connect() as conn:
        order_id = conn.execute("SELECT order_id FROM items WHERE id = ?", (item_id,)).fetchone()["order_id"]
        cur = conn.execute(
            """
            INSERT INTO parts(item_id, name, quantity_required, process, material, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (item_id, name.strip(), int(quantity_required), process, material.strip(), notes.strip(), _now()),
        )
        _touch_order(conn, order_id)
        return cur.lastrowid


def create_job(part_id: int, quantity: int, machine_id: Optional[int], status: str = "En cola", expected_end: str = "", notes: str = "") -> int:
    with connect() as conn:
        code = _next_code(conn, "production_jobs", "JOB")
        now = _now()
        cur = conn.execute(
            """
            INSERT INTO production_jobs(code, part_id, machine_id, quantity, completed_quantity, status, expected_end, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (code, part_id, machine_id, int(quantity), status, expected_end or None, notes.strip(), now, now),
        )
        order_id = conn.execute(
            "SELECT i.order_id FROM parts p JOIN items i ON i.id = p.item_id WHERE p.id = ?", (part_id,)
        ).fetchone()["order_id"]
        _touch_order(conn, order_id)
        return cur.lastrowid


def update_job(job_id: int, status: str, completed_quantity: int, machine_id: Optional[int], expected_end: str = "") -> None:
    with connect() as conn:
        job = conn.execute("SELECT quantity, part_id FROM production_jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return
        completed = max(0, min(int(completed_quantity), int(job["quantity"])))
        conn.execute(
            """
            UPDATE production_jobs
            SET status = ?, completed_quantity = ?, machine_id = ?, expected_end = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, completed, machine_id, expected_end or None, _now(), job_id),
        )
        order_id = conn.execute(
            "SELECT i.order_id FROM parts p JOIN items i ON i.id = p.item_id WHERE p.id = ?", (job["part_id"],)
        ).fetchone()["order_id"]
        _touch_order(conn, order_id)


def update_order_status(order_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), order_id))


def update_machine(machine_id: int, status: str, notes: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE machines SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (status, notes.strip(), _now(), machine_id),
        )


def _touch_order(conn: sqlite3.Connection, order_id: int) -> None:
    conn.execute("UPDATE orders SET updated_at = ? WHERE id = ?", (_now(), order_id))


def list_orders() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            WITH part_progress AS (
                SELECT
                    p.id AS part_id,
                    p.item_id,
                    p.quantity_required,
                    MIN(p.quantity_required, COALESCE(SUM(j.completed_quantity), 0)) AS completed
                FROM parts p
                LEFT JOIN production_jobs j ON j.part_id = p.id
                GROUP BY p.id
            ), order_progress AS (
                SELECT
                    i.order_id,
                    COALESCE(SUM(pp.quantity_required), 0) AS required_total,
                    COALESCE(SUM(pp.completed), 0) AS completed_total
                FROM items i
                LEFT JOIN part_progress pp ON pp.item_id = i.id
                GROUP BY i.order_id
            )
            SELECT
                o.*,
                COALESCE(op.required_total, 0) AS required_total,
                COALESCE(op.completed_total, 0) AS completed_total,
                CASE WHEN COALESCE(op.required_total, 0) = 0 THEN 0
                     ELSE ROUND(100.0 * op.completed_total / op.required_total, 1)
                END AS progress
            FROM orders o
            LEFT JOIN order_progress op ON op.order_id = o.id
            ORDER BY
              CASE o.priority WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END,
              CASE WHEN o.deadline IS NULL OR o.deadline = '' THEN 1 ELSE 0 END,
              o.deadline,
              o.id DESC
            """
        ).fetchall()


def get_order(order_id: int) -> Optional[sqlite3.Row]:
    return next((r for r in list_orders() if r["id"] == order_id), None)


def get_order_tree(order_id: int) -> dict:
    with connect() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return {}
        items = conn.execute("SELECT * FROM items WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()
        result = {"order": dict(order), "items": []}
        for item in items:
            parts = conn.execute(
                """
                SELECT p.*,
                       MIN(p.quantity_required, COALESCE(SUM(j.completed_quantity), 0)) AS completed_quantity
                FROM parts p
                LEFT JOIN production_jobs j ON j.part_id = p.id
                WHERE p.item_id = ?
                GROUP BY p.id
                ORDER BY p.id
                """,
                (item["id"],),
            ).fetchall()
            item_dict = dict(item)
            item_dict["parts"] = []
            for part in parts:
                jobs = conn.execute(
                    """
                    SELECT j.*, m.code AS machine_code, m.name AS machine_name
                    FROM production_jobs j
                    LEFT JOIN machines m ON m.id = j.machine_id
                    WHERE j.part_id = ? ORDER BY j.id
                    """,
                    (part["id"],),
                ).fetchall()
                part_dict = dict(part)
                part_dict["jobs"] = [dict(j) for j in jobs]
                item_dict["parts"].append(part_dict)
            result["items"].append(item_dict)
        return result


def list_jobs(active_only: bool = False) -> list[sqlite3.Row]:
    with connect() as conn:
        where = "WHERE j.status <> 'Listo'" if active_only else ""
        return conn.execute(
            f"""
            SELECT
                j.id, j.code, j.quantity, j.completed_quantity, j.status, j.expected_end, j.notes,
                p.id AS part_id, p.name AS part_name, p.process, p.material,
                i.name AS item_name, o.id AS order_id, o.code AS order_code, o.project, o.priority, o.deadline,
                m.id AS machine_id, m.code AS machine_code
            FROM production_jobs j
            JOIN parts p ON p.id = j.part_id
            JOIN items i ON i.id = p.item_id
            JOIN orders o ON o.id = i.order_id
            LEFT JOIN machines m ON m.id = j.machine_id
            {where}
            ORDER BY
                CASE o.priority WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END,
                CASE j.status WHEN 'Imprimiendo' THEN 1 WHEN 'En cola' THEN 2 WHEN 'Pendiente' THEN 3 WHEN 'Postproceso' THEN 4 WHEN 'Bloqueado' THEN 5 ELSE 6 END,
                CASE WHEN o.deadline IS NULL OR o.deadline = '' THEN 1 ELSE 0 END,
                o.deadline,
                j.id
            """
        ).fetchall()


def list_machines() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT
                m.*,
                GROUP_CONCAT(CASE WHEN j.status = 'Imprimiendo' THEN j.code || ' · ' || p.name END, ', ') AS current_jobs,
                GROUP_CONCAT(CASE WHEN j.status = 'En cola' THEN j.code || ' · ' || p.name END, ', ') AS queued_jobs
            FROM machines m
            LEFT JOIN production_jobs j ON j.machine_id = m.id AND j.status IN ('Imprimiendo', 'En cola')
            LEFT JOIN parts p ON p.id = j.part_id
            GROUP BY m.id
            ORDER BY m.code
            """
        ).fetchall()


def dashboard_metrics() -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM orders WHERE status NOT IN ('Entregado')) AS active_orders,
                (SELECT COUNT(*) FROM production_jobs WHERE status = 'Imprimiendo') AS printing_jobs,
                (SELECT COUNT(*) FROM production_jobs WHERE status = 'Bloqueado') AS blocked_jobs,
                (SELECT COUNT(*) FROM machines WHERE status = 'Disponible') AS available_machines
            """
        ).fetchone()
        return dict(row)


def parts_for_job_creation() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT p.id, p.name AS part_name, p.quantity_required, p.process,
                   i.name AS item_name, o.code AS order_code, o.project
            FROM parts p
            JOIN items i ON i.id = p.item_id
            JOIN orders o ON o.id = i.order_id
            WHERE o.status <> 'Entregado'
            ORDER BY o.id DESC, i.id, p.id
            """
        ).fetchall()


def items_for_order(order_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM items WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()


def export_rows() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT
                o.code AS order_code, o.client, o.project, o.deadline, o.priority, o.status AS order_status,
                i.name AS item, i.quantity AS item_quantity,
                p.name AS part, p.quantity_required, p.process, p.material,
                j.code AS job_code, j.quantity AS job_quantity, j.completed_quantity, j.status AS job_status,
                m.code AS machine, j.expected_end
            FROM orders o
            LEFT JOIN items i ON i.order_id = o.id
            LEFT JOIN parts p ON p.item_id = i.id
            LEFT JOIN production_jobs j ON j.part_id = p.id
            LEFT JOIN machines m ON m.id = j.machine_id
            ORDER BY o.id, i.id, p.id, j.id
            """
        ).fetchall()
