"""Daily priorities from the current snapshot."""
from datetime import timedelta
from services.queries import dashboard
from utils.dates import now, parse_deadline
from services.order_progress import manufacturing, supplies


def daily_board(snapshot, at=None):
    at=at or now()
    today=at.date()
    base=dashboard(snapshot,at)
    orders=base['orders']
    def deadline(order):
        try:
            return parse_deadline(order['deadline'])
        except ValueError:
            return None
    def priority(order):
        due=deadline(order)
        return (0 if due and due<today else 1 if due==today else 2 if order['status']=='Bloqueado' else 3 if order['status']=='Listo' else 4,
                due or today+timedelta(days=36500), 0 if order['priority']=='Alta' else 1,order['id'])
    every=sorted(orders,key=priority)
    # Development projects and prints straight to inventory use machines but are never delivered to a customer.
    ordered=[o for o in every if not o.get('development') and not o.get('stock_run')]
    overdue=[o for o in ordered if deadline(o) and deadline(o)<today]
    due=[o for o in ordered if deadline(o)==today]
    blocked=[o for o in ordered if o['status']=='Bloqueado']
    ready=[o for o in ordered if o['status']=='Listo']
    packing=[o for o in ready if not o['stages']['packing']['checked_at']]
    unassigned=[p for o in every for i in o['items'] for p in i['parts'] if p['quantity_unassigned']>0]
    missing=[o for o in ordered if not o['items'] or o['undefined_items']]
    available=[m for m in snapshot['machines'] if m['status']=='Disponible']
    attention=[]
    for order in ordered:
        reasons=[]
        if order in overdue:reasons.append('Entrega vencida')
        elif order in due:reasons.append('Entrega hoy')
        if order in blocked:reasons.append('Bloqueado')
        if order in ready:reasons.append('Listo para preparar')
        elif manufacturing(order)['complete'] and supplies(order)['remaining']:
            reasons.append('Insumos pendientes')
        if order in missing:reasons.append('Falta definir despiece')
        if not reasons and any(p['quantity_unassigned'] for i in order['items'] for p in i['parts']):reasons.append('Piezas sin asignar')
        if reasons:attention.append(dict(order=order,reasons=reasons))
    return dict(base=base,orders=ordered,overdue=overdue,due=due,blocked=blocked,ready=ready,packing=packing,
                unassigned=unassigned,missing=missing,available=available,attention=attention,
                unassigned_units=sum(p['quantity_unassigned'] for p in unassigned),
                no_date=[o for o in ordered if not o['deadline']])
