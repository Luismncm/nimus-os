"""One way to put a print in the queue, whatever it is for: an order's piece, a new piece, stock or a prototype.

Every print still lands as a normal job of an order, so reservations, filament demand, costs and
progress keep their rules. This module only decides where it goes and saves it in one transaction.
"""
from db import connect
from services import production
from services.catalog import clean
from services.quotations import cents
from utils.dates import timestamp


# Average filament price when the spool is not priced in Filamento y consumibles: MXN 380 per kg.
DEFAULT_MATERIAL_RATE_CENTS = 38000


def material_rate(material):
    """MXN cents per kg for a print: the filament's own price when registered, else the workshop average."""
    from services import consumables
    return consumables.material_rate(material) or DEFAULT_MATERIAL_RATE_CENTS


def plan_for(material, planned_start, duration_minutes, estimated_grams, machine_rate, material_rate_mxn=None):
    """Booking and cost inputs of a print, captured once when it is assigned.

    Time, grams and the filament price given here are the print's cost: they are not asked again at the end.
    """
    if not any(v is not None for v in (planned_start, duration_minutes, estimated_grams, machine_rate, material_rate_mxn)):
        return None
    return dict(planned_start=planned_start, duration_minutes=duration_minutes, estimated_grams=estimated_grams, actual_grams=None,
                material_rate_cents=cents(material_rate_mxn) if material_rate_mxn is not None else material_rate(material),
                machine_rate_cents=cents(machine_rate) if machine_rate is not None else None)


def insert_print(conn, order_id, piece, quantity, *, material, process, machine_id, plan, notes, extra=0, product=''):
    """New piece (inside `product`, or a product named like the piece) and its job in an open transaction."""
    stamp = timestamp()
    item_id = conn.execute("INSERT INTO items(order_id,name,quantity,notes,created_at,collection) VALUES(?,?,?,?,?,'')",
                           (order_id, product or piece, 1, clean(notes), stamp)).lastrowid
    part_id = conn.execute('''INSERT INTO parts(item_id,name,quantity_required,process,material,notes,created_at)
        VALUES(?,?,?,?,?,?,?)''', (item_id, piece, quantity, process, clean(material), '', stamp)).lastrowid
    job_id = production._insert_jobs(conn, order_id, part_id, [dict(quantity=quantity, machine_id=machine_id, extra=extra)], None, None, clean(notes), plan)[0]
    production.refresh_order(conn, order_id)
    return job_id


def new_print(order_id, *, part_id=None, piece='', quantity, material='', process='Impresión 3D', machine_id=None, planned_start=None,
              duration_minutes=None, estimated_grams=None, machine_rate=None, material_rate=None, notes='', extra=0, request_key):
    """Queue a print for an order: an existing piece with units to assign, or a new piece of a custom order.

    `extra` units are printed on top for inventory; prototypes never send units to stock.
    """
    quantity = production._integer(quantity, 'Cantidad')
    with connect() as conn:
        order = production._get(conn, 'orders', order_id)
        dev = conn.execute('SELECT 1 FROM development_projects WHERE order_id=?', (order_id,)).fetchone()
        part = production._get(conn, 'parts', part_id) if part_id else None
        part_order = production._owner(conn, 'parts', part_id) if part_id else None
    if dev:
        from services import development
        return development.launch_print(order_id, piece or (part['name'] if part else ''), quantity, material=material or (part['material'] if part else ''),
                                        process=process, machine_id=machine_id, planned_start=planned_start, duration_minutes=duration_minutes,
                                        estimated_grams=estimated_grams, machine_rate=machine_rate, material_rate=material_rate, notes=notes, request_key=request_key)
    if part:
        if part_order != order_id:
            raise ValueError('La pieza pertenece a otro pedido.')
        plan = plan_for(part['material'], planned_start, duration_minutes, estimated_grams, machine_rate, material_rate)
        return production.create_jobs(part_id, [dict(quantity=quantity, machine_id=machine_id, extra=extra)], notes=notes, plan=plan)[0]
    if order['fulfillment'] != 'Personalizado':
        raise ValueError('Este pedido viene de una receta: su despiece está fijado. Elige una de sus piezas por asignar.')
    piece = production._text(piece, 'Pieza')
    production._choice(process, production.PROCESSES, 'Proceso')
    plan = plan_for(material, planned_start, duration_minutes, estimated_grams, machine_rate, material_rate)
    with connect(write=True) as conn:
        production._editable(conn, order_id)
        return insert_print(conn, order_id, piece, quantity, material=material, process=process, machine_id=machine_id, plan=plan, notes=notes, extra=extra)


def reschedule_first_free(job_id):
    """One-click fix for an overdue or overlapping booking: same duration, next free slot on its machine."""
    from services import planning, resources
    from services.queries import load_snapshot
    job = next((j for j in load_snapshot()['jobs'] if j['id'] == job_id), None)
    if not job:
        raise ValueError('El trabajo ya no existe.')
    if job['status'] not in ('En cola', 'Pausado'):
        raise ValueError('Solo se reprograman trabajos en cola o pausados.')
    if not job['machine_id'] or not job['duration_minutes']:
        raise ValueError('Asigna máquina y duración para reprogramarlo.')
    start = resources.first_free(job_id, job['machine_id'], job['duration_minutes'])
    if not start:
        raise ValueError('La máquina no tiene horario libre calculable: está fuera de servicio o con una impresión sin fin vigente.')
    plan = planning.get(job_id)
    data = {f: plan.get(f) for f in planning.FIELDS} | dict(planned_start=start.isoformat(timespec='minutes'))
    planning.save(job_id, data, expected_revision=plan['revision'], expected_job_revision=job['updated_at'])
    return start


def schedule_unscheduled(job_ids):
    """Give every print still without a time the first free slot of its machine, one after another.

    The ids come in the queue's own order (priority, then delivery date), so the most urgent print takes the
    earliest slot and each booking pushes the next one later on the same machine. A print that cannot be
    placed (no machine, no duration, machine out of service) is left as it was and reported with its reason;
    nothing else changes. Returns (scheduled [(job_id, start)], skipped [(job_id, reason)]).
    """
    scheduled, skipped = [], []
    for job_id in job_ids:
        try:
            scheduled.append((job_id, reschedule_first_free(job_id)))
        except ValueError as exc:
            skipped.append((job_id, str(exc)))
    return scheduled, skipped
