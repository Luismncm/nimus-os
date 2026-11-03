"""Read-only operational stages derived from production and recorded checks."""
from models.constants import PRIORITY_RANK
from services.workflow import next_step
from services.order_progress import manufacturing, supplies
from utils.dates import now, parse_deadline

LANES = {
    'Planificar': ('playlist_add_check', 'gray', 'Define productos y asigna trabajos.'),
    'Producir': ('precision_manufacturing', 'blue', 'Sigue piezas y trabajos en curso.'),
    'Preparar': ('package_2', 'orange', 'Completa insumos, ensambla y revisa la salida.'),
    'Salida': ('local_shipping', 'green', 'Confirma entrega o libera a stock.'),
}


KINDS = ('Todos', 'Pedidos', 'Prototipos')
# What needs a look, as one-click filters with their count above the board.
FOCUS = ('Todos', 'Atrasados', 'Entrega hoy', 'Bloqueados', 'Insumos pendientes', 'Listos para salida', 'Sin fecha')


def _days(order, today, closed):
    try:
        deadline = parse_deadline(order.get('deadline'))
        return ((deadline - today).days if deadline and not closed else None), False
    except ValueError:
        return None, True


def prototype_tracking(order, today=None):
    """A development project on the same board: it plans, prints and closes; it is never delivered or sold.

    Planificar until a print starts (as an order with queued jobs), Producir once one has started, and closed
    (shown with the delivered history) once the project is closed in Desarrollo y prototipos.
    """
    today = today or now().date()
    items = order['items']
    parts = [p for i in items for p in i['parts']]
    jobs = [j for p in parts for j in p['jobs']]
    closed = (order.get('development') or {}).get('status') != 'Activo'
    running = sum(j['status'] == 'En producción' for j in jobs)
    waiting = sum(j['status'] in ('En cola', 'Pausado', 'Bloqueado') for j in jobs)
    lane = 'Entregados' if closed else 'Producir' if running or any(j.get('started_at') or j['status'] == 'Terminado' for j in jobs) else 'Planificar'
    action = ('Consultar histórico' if closed else 'Lanzar la primera impresión' if not jobs
              else f"Seguir {running} {'impresión' if running == 1 else 'impresiones'} en marcha" if running
              else f"Iniciar {waiting} en cola" if waiting else 'Evaluar y lanzar otra prueba o cerrar el proyecto')
    days, invalid = _days(order, today, closed)
    return dict(lane=lane, blocked=False, delivered=closed, complete=False, manufacturing_complete=False, supplies_remaining=0,
                overdue=days is not None and days < 0, due_today=days == 0, days=days, invalid_date=invalid, pending=[], action=action,
                jobs=len(jobs), running=running, unassigned=sum(p['quantity_unassigned'] for p in parts), checked=0, items=len(items),
                products=sum(i['quantity'] for i in items), prototype=True)


def tracking(order, today=None):
    if order.get('development'):
        return prototype_tracking(order, today)
    today = today or now().date()
    items = order['items']
    parts = [p for i in items for p in i['parts']]
    jobs = [j for p in parts for j in p['jobs']]
    delivered = order['status'] == 'Entregado'
    blocked = not delivered and (order['status'] == 'Bloqueado' or bool(order.get('blocked_manually')))
    complete = bool(order['required_total']) and not order['undefined_items'] and order['remaining_total'] == 0
    required_checks = ('revision',) if order.get('fulfillment') == 'Stock' else ('revision', 'packing', 'dispatch')
    checks = order.get('stages', {})
    pending = [label for key, label in (('revision', 'Revisión final'), ('packing', 'Empaque'), ('dispatch', 'Salida preparada'))
               if key in required_checks and not checks.get(key, {}).get('checked_at')]
    unchecked = sum(not i.get('checked_at') for i in items)
    if unchecked:
        pending.insert(0, f'Revisar {unchecked} producto(s)')
    fabrication = manufacturing(order)
    purchased = supplies(order)
    started = fabrication['completed'] > 0 or any(j.get('started_at') for j in jobs)
    lane = ('Entregados' if delivered else 'Salida' if complete and not pending and not blocked
            else 'Preparar' if complete or fabrication['complete'] else 'Producir' if started else 'Planificar')
    try:
        deadline = parse_deadline(order.get('deadline'))
        days = (deadline - today).days if deadline and not delivered else None
        invalid_date = False
    except ValueError:
        days, invalid_date = None, True
    action = ('Consultar histórico' if delivered else 'Resolver bloqueo' if blocked
              else pending[0] if complete and pending else 'Liberar a stock' if lane == 'Salida' and order.get('fulfillment') == 'Stock'
              else 'Confirmar entrega' if lane == 'Salida' else next_step(order)['label'])
    return dict(lane=lane, blocked=blocked, delivered=delivered, complete=complete,
                manufacturing_complete=fabrication['complete'], supplies_remaining=purchased['remaining'],
                overdue=days is not None and days < 0, due_today=days == 0, days=days,
                invalid_date=invalid_date, pending=pending, action=action, jobs=len(jobs),
                running=sum(j['status'] == 'En producción' for j in jobs),
                unassigned=sum(p['quantity_unassigned'] for p in parts),
                checked=len(items)-unchecked, items=len(items),
                products=sum(i['quantity'] for i in items))


def query(orders, *, scope='Activos', search='', priority='Todas', attention='Todos', lane='Todas', sort='Atención primero', today=None, kind='Todos'):
    result = []
    for order in orders:
        if kind == 'Pedidos' and order.get('development') or kind == 'Prototipos' and not order.get('development'):continue
        if scope=='Cancelados' and not order.get('commercial_cancelled'):continue
        if scope in ('Activos','Entregados') and order.get('commercial_cancelled'):continue
        t = tracking(order, today)
        if scope not in ('Todos','Cancelados') and t['delivered'] != (scope == 'Entregados'):
            continue
        haystack = ' '.join(str(order.get(k) or '') for k in ('code', 'client', 'project'))
        haystack += ' ' + ' '.join(f"{i['name']} {i.get('label', '')}" for i in order['items'])
        if search.strip().casefold() not in haystack.casefold():
            continue
        if priority != 'Todas' and priority != order['priority']:
            continue
        if lane != 'Todas' and lane != t['lane']:
            continue
        if not {'Todos': True, 'Atrasados': t['overdue'], 'Entrega hoy': t['due_today'],
                'Bloqueados': t['blocked'], 'Insumos pendientes': bool(t['supplies_remaining']) and not t['delivered'],
                'Listos para salida': t['lane'] == 'Salida' and not t['delivered'],
                'Sin fecha': not order.get('deadline') and not t['delivered']}.get(attention, False):
            continue
        result.append(dict(order, tracking=t))
    def key(o):
        t = o['tracking']
        due = o['deadline'] or '9999-12-31'
        priority_rank = PRIORITY_RANK[o['priority']]
        if sort == 'Fecha de entrega': return (due, priority_rank, o['id'])
        if sort == 'Prioridad': return (priority_rank, due, o['id'])
        if sort == 'Más recientes': return (-o['id'],)
        return (t['delivered'], not t['blocked'], not t['overdue'], not t['due_today'], priority_rank, due, o['id'])
    return sorted(result, key=key)


def milestones(order, events):
    """Only dates present in the database; no inferred transition timestamps."""
    rows = [dict(at=order['created_at'], event='Pedido creado', detail=order['code'])]
    for item in order['items']:
        for part in item['parts']:
            for job in part['jobs']:
                for key, label in (('started_at', 'Inicio de trabajo'), ('completed_at', 'Trabajo terminado')):
                    if job.get(key):
                        rows.append(dict(at=job[key], event=label, detail=f"{job['code']} · {part['name']}"))
    rows.extend(dict(at=e['created_at'], event='Seguimiento', detail=e['detail']) for e in events)
    if order['status'] == 'Entregado':
        rows.append(dict(at=order['updated_at'], event='Liberado a stock' if order.get('fulfillment') == 'Stock' else 'Pedido entregado', detail=order['code']))
    return sorted(rows, key=lambda r: r['at'], reverse=True)
