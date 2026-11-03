"""Transactional production rules. No UI dependencies."""
from __future__ import annotations

import sqlite3

from db import connect
from models.constants import JOB_STATUSES, MACHINE_STATUSES, PRIORITIES, PROCESSES
from utils.dates import parse_deadline, parse_end, timestamp
from services.inventory import sync_production, validate_item_change, validate_part_change


class ValidationError(ValueError):
    """An actionable business-rule violation."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} es obligatorio.")
    return value.strip()


def _integer(value: int, label: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"{label} debe ser un entero mayor o igual a {minimum}.")
    return value


def _choice(value: str, options: tuple, label: str) -> str:
    if value not in options:
        raise ValidationError(f"{label} no válido: {value}.")
    return value


def _get(conn: sqlite3.Connection, table: str, record_id: int) -> sqlite3.Row:
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    if row is None:
        raise ValidationError("El registro ya no existe. Actualiza la vista.")
    return row


def _owner(conn: sqlite3.Connection, table: str, record_id: int) -> int:
    row = _get(conn, table, record_id)
    if table == "orders":
        return row["id"]
    if table == "items":
        return row["order_id"]
    if table == "parts":
        return _owner(conn, "items", row["item_id"])
    return _owner(conn, "parts", row["part_id"])


def _editable(conn: sqlite3.Connection, order_id: int) -> sqlite3.Row:
    order = _get(conn, "orders", order_id)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_cancellations'").fetchone() and conn.execute('SELECT 1 FROM order_cancellations WHERE order_id=?',(order_id,)).fetchone():
        raise ValidationError('El pedido está cancelado y conserva su historial.')
    if order["status"] == "Entregado":
        raise ValidationError("El pedido está entregado y se conserva como histórico de solo lectura.")
    return order


def _code(conn: sqlite3.Connection, table: str, prefix: str) -> tuple[int, str]:
    # Caller holds BEGIN IMMEDIATE. sqlite_sequence prevents reuse after deletion.
    seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
    maximum = conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {table}").fetchone()[0]
    number = max(seq[0] if seq else 0, maximum) + 1
    while conn.execute(f"SELECT 1 FROM {table} WHERE code=?", (f"{prefix}-{number:04d}",)).fetchone():
        number += 1
    return number, f"{prefix}-{number:04d}"


def refresh_order(conn: sqlite3.Connection, order_id: int) -> None:
    order = _get(conn, "orders", order_id)
    if order["status"] == "Entregado":
        return
    aggregate = conn.execute("""SELECT COALESCE(SUM(p.quantity_required),0) required,
        COALESCE(SUM((SELECT COALESCE(SUM(j.quantity_completed),0) FROM production_jobs j WHERE j.part_id=p.id)),0) completed
        FROM parts p JOIN items i ON i.id=p.item_id WHERE i.order_id=?""", (order_id,)).fetchone()
    undefined_items = conn.execute("""SELECT COUNT(*) FROM items i WHERE order_id=?
        AND recipe_id IS NULL AND NOT EXISTS(SELECT 1 FROM parts p WHERE p.item_id=i.id)""", (order_id,)).fetchone()[0]
    jobs = conn.execute("""SELECT j.status,j.started_at,j.quantity_completed FROM production_jobs j
        JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id WHERE i.order_id=?""", (order_id,)).fetchall()
    if order['fulfillment'] != 'Personalizado':
        from services.recipes import load_requirements
        needs = [r for r in load_requirements(conn) if r['order_id'] == order_id]
        aggregate = {'required': sum(r['quantity'] for r in needs), 'completed': sum(r['covered'] for r in needs)}
    if order["blocked_manually"] or any(j["status"] == "Bloqueado" for j in jobs):
        status = "Bloqueado"
    elif aggregate["required"] > 0 and aggregate["completed"] == aggregate["required"] and not undefined_items:
        status = "Listo"
    elif any(j["started_at"] or j["quantity_completed"] for j in jobs):
        status = "En producción"
    else:
        status = "Pendiente"
    from services.stock_runs import is_run
    if status == "Listo" and is_run(conn, order_id):
        # A print for inventory has nobody to deliver to: its units are already in Colección.
        status = "Entregado"
    conn.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?", (status,timestamp(),order_id))


def _refresh_machines(conn: sqlite3.Connection, *machine_ids: int | None) -> None:
    for machine_id in set(machine_ids) - {None}:
        machine = _get(conn, "machines", machine_id)
        busy = conn.execute("SELECT 1 FROM production_jobs WHERE machine_id=? AND status='En producción'", (machine_id,)).fetchone()
        status = "Imprimiendo" if busy else (machine["status"] if machine["status"] in ("Mantenimiento", "Fuera de servicio") else "Disponible")
        conn.execute("UPDATE machines SET status=?,updated_at=? WHERE id=?", (status,timestamp(),machine_id))


def create_order(project: str, client: str = "", deadline: str = "", priority: str = "Media", notes: str = "") -> int:
    project = _text(project,"Proyecto")
    _choice(priority,PRIORITIES,"Prioridad")
    due = parse_deadline(deadline)
    with connect(write=True) as conn:
        record_id, code = _code(conn,"orders","ORD")
        now = timestamp()
        conn.execute("""INSERT INTO orders(id,code,project,client,deadline,priority,status,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,'Pendiente',?,?,?)""", (record_id,code,project,client.strip(),due.isoformat() if due else None,priority,notes.strip(),now,now))
        return record_id


def update_order(order_id: int, *, project: str, client: str, deadline: str, priority: str, notes: str) -> None:
    project = _text(project,"Proyecto")
    _choice(priority,PRIORITIES,"Prioridad")
    due = parse_deadline(deadline)
    with connect(write=True) as conn:
        _editable(conn,order_id)
        conn.execute("UPDATE orders SET project=?,client=?,deadline=?,priority=?,notes=?,updated_at=? WHERE id=?",
                     (project,client.strip(),due.isoformat() if due else None,priority,notes.strip(),timestamp(),order_id))


def set_order_blocked(order_id: int, blocked: bool) -> None:
    with connect(write=True) as conn:
        _editable(conn,order_id)
        conn.execute("UPDATE orders SET blocked_manually=? WHERE id=?", (int(blocked),order_id))
        refresh_order(conn,order_id)


def deliver_order(order_id: int) -> None:
    with connect(write=True) as conn:
        _deliver_order(conn, order_id)


def _deliver_order(conn, order_id):
    _editable(conn,order_id)
    from services.commerce import check_order
    check_order(conn,order_id,'delivery')
    refresh_order(conn,order_id)
    if _get(conn,"orders",order_id)["status"] != "Listo":
        raise ValidationError("Solo puedes entregar un pedido listo, sin bloqueos, con su fabricación terminada y todos sus componentes e insumos cubiertos.")
    order = _get(conn, 'orders', order_id)
    lamp=conn.execute('SELECT 1 FROM items i JOIN origin_recipes o ON o.recipe_id=i.recipe_id WHERE i.order_id=?',(order_id,)).fetchone()
    if lamp:
        unchecked=conn.execute('SELECT 1 FROM items i LEFT JOIN item_tracking t ON t.item_id=i.id WHERE i.order_id=? AND t.checked_at IS NULL',(order_id,)).fetchone()
        required=('revision',) if order['fulfillment']=='Stock' else ('revision','packing','dispatch')
        checked={r['stage'] for r in conn.execute('SELECT stage FROM order_stages WHERE order_id=? AND checked_at IS NOT NULL',(order_id,))}
        if unchecked or any(stage not in checked for stage in required):
            raise ValidationError('Confirma el ensamble y revisión de las lámparas y completa la preparación antes de entregar.')
    if order['fulfillment'] != 'Personalizado':
        from services.recipes import complete_recipe_order
        complete_recipe_order(conn, order)
    conn.execute("UPDATE orders SET status='Entregado',updated_at=? WHERE id=?", (timestamp(),order_id))


def create_item(order_id: int, name: str, quantity: int, notes: str = "", *, collection: str = "") -> int:
    name, quantity = _text(name,"Item"), _integer(quantity,"Cantidad")
    _choice(collection, ('', 'Origen'), 'Colección')
    with connect(write=True) as conn:
        if _editable(conn,order_id)['fulfillment'] != 'Personalizado':
            raise ValidationError('El pedido desde receta conserva su despiece. Crea otro pedido para agregar productos.')
        cursor = conn.execute("INSERT INTO items(order_id,name,quantity,notes,created_at,collection) VALUES(?,?,?,?,?,?)", (order_id,name,quantity,notes.strip(),timestamp(),collection))
        refresh_order(conn,order_id)
        return cursor.lastrowid


def update_item(item_id: int, name: str, quantity: int, notes: str = "", *, collection: str | None = None) -> None:
    name, quantity = _text(name,"Item"), _integer(quantity,"Cantidad")
    with connect(write=True) as conn:
        order_id = _owner(conn,"items",item_id)
        _editable(conn,order_id)
        old = _get(conn, 'items', item_id)
        if old['recipe_id'] and (name != old['name'] or quantity != old['quantity'] or (collection is not None and collection != old['collection'])):
            raise ValidationError('La receta del pedido está fijada. Crea otro pedido para cambiar producto o cantidad.')
        if collection is None:
            collection = _get(conn, 'items', item_id)['collection']
        _choice(collection, ('', 'Origen'), 'Colección')
        validate_item_change(conn, item_id, name, collection)
        conn.execute("UPDATE items SET name=?,quantity=?,notes=?,collection=? WHERE id=?", (name,quantity,notes.strip(),collection,item_id))
        refresh_order(conn,order_id)


def create_part(item_id: int, name: str, quantity_required: int, process: str, material: str = "", notes: str = "") -> int:
    name, quantity_required = _text(name,"Pieza"), _integer(quantity_required,"Cantidad requerida")
    _choice(process,PROCESSES,"Proceso")
    with connect(write=True) as conn:
        order_id = _owner(conn,"items",item_id)
        _editable(conn,order_id)
        if _get(conn, 'items', item_id)['recipe_id']:
            raise ValidationError('El despiece de receta está fijado. Publica una nueva versión para pedidos futuros.')
        cursor = conn.execute("""INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at)
            VALUES(?,?,?,?,?,?,?)""", (item_id,name,quantity_required,process,material.strip(),notes.strip(),timestamp()))
        refresh_order(conn,order_id)
        return cursor.lastrowid


def update_part(part_id: int, name: str, quantity_required: int, process: str, material: str = "", notes: str = "") -> None:
    name, quantity_required = _text(name,"Pieza"), _integer(quantity_required,"Cantidad requerida")
    _choice(process,PROCESSES,"Proceso")
    with connect(write=True) as conn:
        order_id = _owner(conn,"parts",part_id)
        _editable(conn,order_id)
        old = _get(conn, 'parts', part_id)
        if old['component_id'] and any(old[k] != v for k, v in (('name', name), ('quantity_required', quantity_required), ('process', process), ('material', material))):
            raise ValidationError('La pieza y el faltante provienen de una receta fijada; modifica solo sus trabajos o notas.')
        validate_part_change(conn, part_id, name, process, material)
        assigned = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM production_jobs WHERE part_id=?", (part_id,)).fetchone()[0]
        if quantity_required < assigned:
            raise ValidationError(f"Hay {assigned} unidades asignadas. Ajusta los trabajos antes de reducir la pieza.")
        conn.execute("UPDATE parts SET name=?,quantity_required=?,process=?,material=?,notes=? WHERE id=?",
                     (name,quantity_required,process,material.strip(),notes.strip(),part_id))
        refresh_order(conn,order_id)


def _validate_job(conn: sqlite3.Connection, part_id: int, quantity: int, quantity_completed: int,
                  machine_id: int | None, status: str, job_id: int = 0) -> int:
    _integer(quantity,"Cantidad del trabajo")
    _integer(quantity_completed,"Terminadas",0)
    _choice(status,JOB_STATUSES,"Estado")
    if quantity_completed > quantity:
        raise ValidationError("Las terminadas no pueden exceder la cantidad del trabajo.")
    if status == "Terminado" and quantity_completed != quantity:
        raise ValidationError("Un trabajo terminado debe tener todas sus unidades completadas.")
    part = _get(conn,"parts",part_id)
    order_id = _owner(conn,"parts",part_id)
    order = _editable(conn,order_id)
    assigned = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM production_jobs WHERE part_id=? AND id<>?", (part_id,job_id)).fetchone()[0]
    if assigned + quantity > part["quantity_required"]:
        raise ValidationError(f"Solo quedan {part['quantity_required']-assigned} unidades disponibles para este trabajo.")
    if status == "En producción" and order["blocked_manually"]:
        current = _get(conn,"production_jobs",job_id) if job_id else None
        if not current or current["status"] != "En producción" or current["machine_id"] != machine_id:
            raise ValidationError("Libera el bloqueo manual del pedido antes de iniciar trabajos.")
    if machine_id is not None:
        machine = _get(conn,"machines",machine_id)
        if machine['archived']:
            raise ValidationError('La máquina está archivada. Reactívala antes de asignar trabajo.')
        if status == "En producción":
            if machine["status"] in ("Mantenimiento","Fuera de servicio"):
                raise ValidationError("La máquina está en mantenimiento o fuera de servicio.")
            other = conn.execute("SELECT code FROM production_jobs WHERE machine_id=? AND id<>? AND status='En producción'", (machine_id,job_id)).fetchone()
            if other:
                raise ValidationError(f"La máquina ya está ocupada por {other['code']}.")
    return order_id


def create_job(part_id: int, quantity: int, machine_id: int | None = None, *, priority: str | None = None,
               expected_end: str = "", notes: str = "", plan: dict | None = None) -> int:
    return create_jobs(part_id, [{"quantity": quantity, "machine_id": machine_id}],
                       priority=priority, expected_end=expected_end, notes=notes, plan=plan)[0]


def create_jobs(part_id: int, allocations: list[dict], *, priority: str | None = None,
                expected_end: str = "", notes: str = "", plan: dict | None = None) -> list[int]:
    """Split a part into several jobs atomically, with the same capacity rules."""
    if not allocations:
        raise ValidationError("Asigna al menos una unidad a una máquina o proceso externo.")
    end = parse_end(expected_end)
    with connect(write=True) as conn:
        order_id = _owner(conn, "parts", part_id)
        _editable(conn, order_id)
        created = _insert_jobs(conn, order_id, part_id, allocations, priority, end, notes, plan)
        refresh_order(conn,order_id)
        return created


def create_order_jobs(order_id: int, allocations: list[dict], *, priority: str | None = None) -> list[int]:
    """Assign several pieces of one order in a single transaction: all jobs are created or none."""
    rows = [a for a in allocations if a["quantity"]]
    if not rows:
        raise ValidationError("Asigna al menos una unidad a una máquina o proceso externo.")
    with connect(write=True) as conn:
        _editable(conn, order_id)
        created = []
        for part_id in dict.fromkeys(a["part_id"] for a in rows):
            if _owner(conn, "parts", part_id) != order_id:
                raise ValidationError("Solo se pueden repartir piezas de este pedido.")
            created += _insert_jobs(conn, order_id, part_id, [a for a in rows if a["part_id"] == part_id], priority, None, "", None)
        refresh_order(conn, order_id)
        return created


def _insert_jobs(conn, order_id, part_id, allocations, priority, end, notes, plan):
    priority = priority or _get(conn,"orders",order_id)["priority"]
    _choice(priority,PRIORITIES,"Prioridad")
    created = []
    for allocation in allocations:
        quantity, machine_id = allocation["quantity"], allocation.get("machine_id")
        _validate_job(conn, part_id, quantity, 0, machine_id, "En cola")
        record_id, code = _code(conn,"production_jobs","JOB")
        now = timestamp()
        conn.execute("""INSERT INTO production_jobs(id,code,part_id,machine_id,quantity,status,priority,expected_end,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,'En cola',?,?,?,?,?)""", (record_id,code,part_id,machine_id,quantity,priority,end.isoformat(timespec="minutes") if end else None,notes.strip(),now,now))
        if plan is not None:
            from services.planning import _write
            _write(conn,record_id,plan)
        if allocation.get("extra"):
            from services.piece_stock import set_extra
            set_extra(conn,record_id,allocation["extra"])
        created.append(record_id)
    return created


def create_parts(item_id: int, names: list[str], units_per_item: int, process: str,
                 material: str = "", notes: str = "") -> list[int]:
    """Build a simple bill of parts in one operation, preserving item total semantics."""
    if not names:
        raise ValidationError("Escribe al menos un nombre de pieza.")
    clean_names = [_text(name, "Nombre de pieza") for name in names]
    if len({name.casefold() for name in clean_names}) != len(clean_names):
        raise ValidationError("Hay nombres repetidos en la lista. Revisa el despiece.")
    _integer(units_per_item, "Unidades por producto")
    _choice(process, PROCESSES, "Proceso")
    with connect(write=True) as conn:
        item = _get(conn, "items", item_id)
        _editable(conn, item["order_id"])
        if item['recipe_id']:
            raise ValidationError('El despiece de este pedido ya está definido por su receta.')
        created = []
        for name in clean_names:
            cursor = conn.execute("""INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at)
                VALUES(?,?,?,?,?,?,?)""", (item_id, name, item["quantity"] * units_per_item,
                                          process, material.strip(), notes.strip(), timestamp()))
            created.append(cursor.lastrowid)
        refresh_order(conn, item["order_id"])
        return created


def create_part_rows(item_id: int, rows: list[dict]) -> list[int]:
    """Create a heterogeneous despiece atomically; quantities are per product."""
    if not rows or len(rows)>100: raise ValidationError('Agrega entre 1 y 100 piezas.')
    prepared=[]
    for row in rows:
        name=_text(row.get('name',''),'Nombre de pieza')
        units=row.get('units')
        if isinstance(units,float) and units.is_integer(): units=int(units)
        _integer(units,'Unidades por producto')
        process=row.get('process','');_choice(process,PROCESSES,'Proceso')
        material=str(row.get('material') or '').strip()
        prepared.append((name,units,process,material))
    identities=[(n.casefold(),p,m.casefold()) for n,u,p,m in prepared]
    if len(set(identities))!=len(identities): raise ValidationError('Hay piezas repetidas con el mismo proceso y material.')
    with connect(write=True) as conn:
        item=_get(conn,'items',item_id);_editable(conn,item['order_id'])
        if item['recipe_id']: raise ValidationError('La receta ya define sus piezas; crea otra versión para cambiarla.')
        existing={(r['name'].casefold(),r['process'],r['material'].casefold()) for r in conn.execute('SELECT * FROM parts WHERE item_id=?',(item_id,))}
        if existing.intersection(identities): raise ValidationError('Esta pieza ya existe en el producto. Edítala o usa otro material.')
        created=[]
        for name,units,process,material in prepared:
            created.append(conn.execute('INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at) VALUES(?,?,?,?,?,?,?)',
                (item_id,name,item['quantity']*units,process,material,'',timestamp())).lastrowid)
        refresh_order(conn,item['order_id'])
        return created


def record_progress(job_id: int, quantity_completed: int, *, expected_revision: str) -> None:
    """Record a total without requiring the operator to re-enter job metadata."""
    with connect(write=True) as conn:
        job = _get(conn, "production_jobs", job_id)
        if job["updated_at"] != expected_revision:
            raise ValidationError("Este trabajo cambió. Cierra el formulario y vuelve a abrirlo.")
        if job["status"] == "Terminado":
            raise ValidationError("Para corregir un trabajo terminado, usa Editar trabajo.")
        _save_job(conn, job, quantity=job["quantity"], quantity_completed=quantity_completed,
                  status=job["status"], machine_id=job["machine_id"], priority=job["priority"],
                  expected_end=job["expected_end"], notes=job["notes"])


def _save_job(conn: sqlite3.Connection, job: sqlite3.Row, *, quantity: int, quantity_completed: int,
              status: str, machine_id: int | None, priority: str, expected_end: str, notes: str) -> None:
    _choice(status,JOB_STATUSES,"Estado")
    _choice(priority,PRIORITIES,"Prioridad")
    _integer(quantity,"Cantidad")
    _integer(quantity_completed,"Terminadas",0)
    from services.piece_stock import is_pulled
    if is_pulled(conn, job["id"]):
        raise ValidationError("Estas piezas salieron de inventario, no de una impresión: no se editan como trabajo.")
    if quantity_completed == quantity:
        status = "Terminado"
    end = parse_end(expected_end)
    order_id = _validate_job(conn,job["part_id"],quantity,quantity_completed,machine_id,status,job["id"])
    if (status=='En producción' and job['status']!='En producción') or (not job['started_at'] and (quantity_completed or status=='Terminado')):
        from services.commerce import check_order
        check_order(conn,order_id,'production')
    now = timestamp()
    started = job["started_at"] or (now if status in ("En producción","Terminado") or quantity_completed else None)
    completed_at = (job["completed_at"] or now) if status == "Terminado" else None
    conn.execute("""UPDATE production_jobs SET quantity=?,quantity_completed=?,status=?,machine_id=?,priority=?,
        expected_end=?,notes=?,started_at=?,completed_at=?,updated_at=? WHERE id=?""",
        (quantity,quantity_completed,status,machine_id,priority,end.isoformat(timespec="minutes") if end else None,
         notes.strip(),started,completed_at,now,job["id"]))
    from services.runtime import transition
    transition(conn,job,status,now)
    sync_production(conn, job['id'], job['quantity_completed'], quantity_completed)
    from services.piece_stock import sync_extras, sync_riders
    sync_extras(conn, job['id'], status == "Terminado")
    sync_riders(conn, job['id'], status, machine_id)
    _refresh_machines(conn,job["machine_id"],machine_id)
    refresh_order(conn,order_id)


def update_job(job_id: int, *, quantity: int, quantity_completed: int, status: str, machine_id: int | None,
               priority: str, expected_end: str = "", notes: str = "", expected_revision: str | None = None, plan: dict | None = None, expected_plan_revision: int | None = None,
               extra: int | None = None) -> None:
    with connect(write=True) as conn:
        job = _get(conn,"production_jobs",job_id)
        if expected_revision is not None and job["updated_at"] != expected_revision:
            raise ValidationError("Este trabajo cambió en otra ventana. Actualiza antes de guardar.")
        if extra is not None:
            # Before saving the job, so finishing it in this same edit already posts the extra.
            from services.piece_stock import set_extra
            set_extra(conn,job_id,extra)
        _save_job(conn,job,quantity=quantity,quantity_completed=quantity_completed,status=status,
                  machine_id=machine_id,priority=priority,expected_end=expected_end,notes=notes)
        if plan is not None:
            from services.planning import _write
            _write(conn,job_id,plan,expected_revision=expected_plan_revision)

        if status=='En producción' or machine_id!=job['machine_id'] or expected_end!=job['expected_end']:
            from services.resources import validate
            validate(conn,job_id)

def job_action(job_id: int, action: str, *, expected_revision: str | None = None) -> None:
    """Quick actions re-read quantities in the same write transaction."""
    with connect(write=True) as conn:
        _job_action(conn, job_id, action, expected_revision=expected_revision)


def _job_action(conn, job_id, action, *, expected_revision=None):
    job = _get(conn,"production_jobs",job_id)
    if expected_revision is not None and job["updated_at"] != expected_revision:
        raise ValidationError("Este trabajo cambió. Actualiza la vista y vuelve a intentar.")
    allowed = {"start": ("En cola","Pausado"), "pause": ("En producción",),
               "block": ("En cola","En producción","Pausado"), "unblock": ("Bloqueado",),
               "finish": ("En cola","En producción","Pausado")}
    if action not in allowed or job["status"] not in allowed[action]:
        raise ValidationError("Esta acción no corresponde al estado actual del trabajo.")
    from services.piece_stock import is_rider
    if action in ("start", "pause") and (host := is_rider(conn, job_id)):
        raise ValidationError(f"Va dentro de la impresión {host}: se inicia y termina con ella.")
    status = {"start":"En producción","pause":"Pausado","block":"Bloqueado","unblock":"En cola","finish":"Terminado"}[action]
    completed = job["quantity"] if action == "finish" else job["quantity_completed"]
    _save_job(conn,job,quantity=job["quantity"],quantity_completed=completed,status=status,machine_id=job["machine_id"],
              priority=job["priority"],expected_end=job["expected_end"],notes=job["notes"])
    if action=='start':
        from services.resources import validate
        validate(conn,job_id)


def update_machine(machine_id: int, status: str, notes: str = "") -> None:
    _choice(status,MACHINE_STATUSES,"Estado de máquina")
    with connect(write=True) as conn:
        _get(conn,"machines",machine_id)
        busy = conn.execute("SELECT 1 FROM production_jobs WHERE machine_id=? AND status='En producción'", (machine_id,)).fetchone()
        if busy and status != "Imprimiendo":
            raise ValidationError("Pausa o termina el trabajo actual antes de cambiar la máquina.")
        if not busy and status == "Imprimiendo":
            raise ValidationError("Inicia un trabajo para marcar la máquina como Imprimiendo.")
        conn.execute("UPDATE machines SET status=?,notes=?,updated_at=? WHERE id=?", (status,notes.strip(),timestamp(),machine_id))


def delete_record(kind: str, record_id: int) -> None:
    """Delete freely, including finished jobs and historical pieces; only what the database itself

    cannot safely undo stays blocked: a job that already moved inventory (its units are physically
    in Colección or beyond) or that has a recorded quality failure (failures keep their history).
    A delivered or cancelled order stays read-only, like everywhere else in the app.
    """
    tables = {"order":"orders","item":"items","part":"parts","job":"production_jobs"}
    if kind not in tables:
        raise ValidationError("Tipo de registro desconocido.")
    table = tables[kind]
    with connect(write=True) as conn:
        order_id = _owner(conn,table,record_id)
        _editable(conn,order_id)
        where = {"order":"i.order_id=?", "item":"i.id=?", "part":"p.id=?", "job":"j.id=?"}[kind]
        jobs = [r[0] for r in conn.execute(f"""SELECT j.id FROM production_jobs j JOIN parts p ON p.id=j.part_id
            JOIN items i ON i.id=p.item_id WHERE {where}""", (record_id,))]
        if jobs:
            marks = ','.join('?' * len(jobs))
            if conn.execute(f'SELECT 1 FROM inventory_movements WHERE job_id IN ({marks}) LIMIT 1', jobs).fetchone():
                raise ValidationError("Ya movió piezas a inventario (Colección, stock o entrega). Se conserva para no descuadrar las existencias.")
            if conn.execute(f'SELECT 1 FROM production_failures WHERE job_id IN ({marks}) LIMIT 1', jobs).fetchone():
                raise ValidationError("Tiene una falla registrada. Las fallas conservan su historial; elimina primero la falla o deja el trabajo.")
            from services.piece_stock import release_riders
            release_riders(conn, jobs)
            # Plain cost/retry bookkeeping of the job: no history guarantee of its own, so it goes with it
            # (unlike production_failures and inventory_movements, which block deletion above).
            conn.execute(f'DELETE FROM job_consumption WHERE job_id IN ({marks})', jobs)
            conn.execute(f'DELETE FROM print_reprints WHERE job_id IN ({marks})', jobs)
        if _get(conn, 'orders', order_id)['fulfillment'] != 'Personalizado':
            if kind in ('item', 'part'):
                raise ValidationError('No elimines líneas de una receta fijada. Puedes eliminar el pedido completo si aún no tiene producción.')
            if kind == 'order':
                from services.recipes import release_draft_order
                release_draft_order(conn, order_id)
        conn.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
        if kind != "order":
            refresh_order(conn,order_id)
