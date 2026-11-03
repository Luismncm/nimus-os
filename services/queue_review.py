"""Who each print is for, and the queue inconsistencies with the one action that fixes each.

Read-only. Fix codes are interpreted by the queue page:
  reschedule  move to the first free slot with the same duration (one click)
  plan        open the scheduling dialog (duration or start missing)
  machine     assign a machine (print process without one)
  progress    record progress or finish (printing past its end)
"""
from services.timeline import slot, issues

PRINT_PROCESSES = ('Impresión 3D', 'Resina')


def destinations(snapshot, sales=()):
    """order_id → what the print is for: Pedido (client, sale), Stock or Prototipo (project)."""
    sale_by_order = {}
    for s in sales:
        if s.get('order_id') and s['status'] == 'Activa':sale_by_order.setdefault(s['order_id'], s['code'])
    result = {}
    for o in snapshot['orders']:
        base = dict(order_id=o['id'], code=o['code'], project=o['project'], client=o['client'], sale=None)
        if o.get('development'):
            result[o['id']] = base | dict(kind='Prototipo', label=f"Prototipo · {o['project']}", color='violet', icon='science')
        elif o.get('stock_run'):
            result[o['id']] = base | dict(kind='Stock', label='Directo a inventario', color='blue', icon='warehouse', direct=True)
        elif any(i.get('collection') == 'Origen' or i.get('is_origin_lamp') for i in o['items']):
            # Colección Origen keeps its own color in the queue, for a client or for its stock.
            sale = sale_by_order.get(o['id'])
            result[o['id']] = base | dict(kind='Origen', label=' · '.join(x for x in ('Origen', o['code'], o['client'] or ('Stock' if o.get('fulfillment') == 'Stock' else 'Sin cliente'), sale) if x),
                                          color='orange', icon='light', sale=sale)
        elif o.get('fulfillment') == 'Stock':
            result[o['id']] = base | dict(kind='Stock', label=f"Lote de stock · {o['code']}", color='blue', icon='warehouse')
        else:
            sale = sale_by_order.get(o['id'])
            result[o['id']] = base | dict(kind='Pedido', label=' · '.join(x for x in (o['code'], o['client'] or 'Sin cliente', sale) if x),
                                          color='green' if sale else 'gray', icon='point_of_sale' if sale else 'inventory_2', sale=sale)
    return result


def review(jobs):
    """Open jobs that need a decision, the most blocking first."""
    rows = []
    for job in jobs:
        # A piece riding in another print has no time of its own: its host carries it.
        if job['status'] == 'Terminado' or job['order_status'] == 'Entregado' or job.get('commercial_cancelled') or job.get('rides_on'):
            continue
        s = slot(job)
        text = issues(s)
        if s['state'] == 'Sin fin':
            rows.append(dict(job=job, text=text[0], fix='progress', label='Avance o terminar', rank=0))
        elif s['conflicts'] or (s['late'] and job['status'] in ('En cola', 'Pausado')):
            rows.append(dict(job=job, text=text[0], fix='reschedule' if job['machine_id'] and job['duration_minutes'] else 'plan',
                             label='Pasar al primer horario libre' if job['machine_id'] and job['duration_minutes'] else 'Corregir horario', rank=1))
        elif job['machine_id'] is None and job['process'] in PRINT_PROCESSES:
            rows.append(dict(job=job, text='Impresión sin máquina: no reserva horario ni aparece en ninguna impresora.', fix='machine', label='Asignar máquina', rank=2))
        elif s['state'] == 'Sin duración' or (s['state'] == 'Sin horario' and not job['duration_minutes']):
            rows.append(dict(job=job, text='Sin duración: no se puede reservar la máquina ni estimar cuándo termina.', fix='plan', label='Capturar duración', rank=3))
        elif s['state'] == 'Sin horario' and job['machine_id']:
            rows.append(dict(job=job, text='Tiene duración pero no horario: no reserva la máquina.', fix='reschedule', label='Programar en el primer horario libre', rank=4))
    return sorted(rows, key=lambda r: (r['rank'], r['job']['id']))
