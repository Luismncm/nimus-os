"""Prototyping and active development projects: prints that use machines, filament and supplies, not sales.

A project is an order flagged in development_projects. Its prints are ordinary jobs, so they reserve
machine time, count in filament demand and get a real cost; the flag keeps them out of sales, margin,
customer deliveries and order notifications.
"""
from db import connect
from services import production
from services.catalog import clean
from services.quotations import cents
from utils.dates import timestamp

PRINT_PROCESSES = ('Impresión 3D', 'Resina')


def create_project(name, *, goal='', budget=None, priority='Media', deadline=None):
    name = production._text(name, 'Proyecto')
    production._choice(priority, production.PRIORITIES, 'Prioridad')
    due = production.parse_deadline(str(deadline) if deadline else '')
    budget_cents = None if budget in (None, '') else cents(budget)
    if budget_cents is not None and budget_cents < 0:
        raise ValueError('El presupuesto no puede ser negativo.')
    with connect(write=True) as conn:
        order_id, code = production._code(conn, 'orders', 'ORD')
        stamp = timestamp()
        conn.execute("""INSERT INTO orders(id,code,project,client,deadline,priority,status,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,'Pendiente',?,?,?)""", (order_id, code, name, 'Desarrollo interno', due.isoformat() if due else None, priority, clean(goal), stamp, stamp))
        conn.execute('INSERT INTO development_projects(order_id,goal,budget_cents,created_at) VALUES(?,?,?,?)', (order_id, clean(goal), budget_cents, stamp))
        return order_id


def _project(conn, order_id):
    row = conn.execute('SELECT * FROM development_projects WHERE order_id=?', (order_id,)).fetchone()
    if not row:
        raise ValueError('El proyecto de desarrollo ya no existe.')
    if row['status'] != 'Activo':
        raise ValueError('El proyecto está cerrado. Ábrelo de nuevo o crea otro para lanzar impresiones.')
    return row


def launch_print(order_id, piece, quantity, *, material='', process='Impresión 3D', machine_id=None, planned_start=None,
                 duration_minutes=None, estimated_grams=None, machine_rate=None, material_rate=None, notes='', request_key):
    """Piece, job, machine and booked time of one prototype print, saved together or not at all."""
    if not request_key:
        raise ValueError('Vuelve a abrir el formulario.')
    production._choice(process, production.PROCESSES, 'Proceso')
    piece, quantity = production._text(piece, 'Pieza'), production._integer(quantity, 'Cantidad')
    from services.capture import plan_for, insert_print
    # The filament's reference cost prices the estimate, so the project shows what this print will cost.
    plan = plan_for(material, planned_start, duration_minutes, estimated_grams, machine_rate, material_rate)
    with connect(write=True) as conn:
        if prior := conn.execute('SELECT job_id FROM development_launches WHERE request_key=?', (request_key,)).fetchone():
            return prior['job_id']
        _project(conn, order_id)
        production._editable(conn, order_id)
        job_id = insert_print(conn, order_id, piece, quantity, material=material, process=process, machine_id=machine_id, plan=plan, notes=notes)
        conn.execute('INSERT INTO development_launches(request_key,order_id,job_id,created_at) VALUES(?,?,?,?)', (request_key, order_id, job_id, timestamp()))
        return job_id


def update_project(order_id, *, goal='', budget=None):
    budget_cents = None if budget in (None, '') else cents(budget)
    with connect(write=True) as conn:
        _project(conn, order_id)
        conn.execute('UPDATE development_projects SET goal=?,budget_cents=? WHERE order_id=?', (clean(goal), budget_cents, order_id))
        conn.execute('UPDATE orders SET notes=?,updated_at=? WHERE id=?', (clean(goal), timestamp(), order_id))


def close_project(order_id):
    """Closing keeps everything as history; it needs no print running or waiting in the queue."""
    with connect(write=True) as conn:
        _project(conn, order_id)
        open_jobs = conn.execute('''SELECT COUNT(*) FROM production_jobs j JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id
            WHERE i.order_id=? AND j.status<>'Terminado' ''', (order_id,)).fetchone()[0]
        if open_jobs:
            raise ValueError(f'Hay {open_jobs} impresión(es) sin terminar. Termínalas o elimina las que ya no se harán antes de cerrar.')
        conn.execute("UPDATE development_projects SET status='Cerrado',closed_at=? WHERE order_id=?", (timestamp(), order_id))


def reopen_project(order_id):
    with connect(write=True) as conn:
        if conn.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()['status'] == 'Entregado':
            raise ValueError('Este proyecto ya está en el histórico.')
        conn.execute("UPDATE development_projects SET status='Activo',closed_at=NULL WHERE order_id=?", (order_id,))


def summaries(snapshot):
    """Per project: prints by state, filament estimated vs used, estimated and real cost against budget."""
    from services import order_costs
    costs = {r['order_id']: r for r in order_costs.reports(snapshot)}
    result = []
    for order in snapshot['orders']:
        info = order.get('development')
        if not info:
            continue
        jobs = [j for j in snapshot['jobs'] if j['order_id'] == order['id']]
        report = costs[order['id']]
        real = report['actual_known_cents']
        result.append(dict(order=order, info=info, jobs=jobs, report=report,
                           running=sum(j['status'] == 'En producción' for j in jobs),
                           waiting=sum(j['status'] in ('En cola', 'Pausado', 'Bloqueado') for j in jobs),
                           finished=sum(j['status'] == 'Terminado' for j in jobs),
                           grams_estimated=sum(j.get('estimated_grams') or 0 for j in jobs),
                           grams_used=sum(j.get('actual_consumed_grams') or 0 for j in jobs),
                           estimated_cents=sum(j.get('estimated_cost_cents') or 0 for j in jobs),
                           real_cents=real, consumables_cents=report['consumables_cents'],
                           budget_left=info['budget_cents'] - real if info['budget_cents'] is not None else None))
    return sorted(result, key=lambda r: (r['info']['status'] != 'Activo', -r['running'], -r['waiting'], -r['order']['id']))
