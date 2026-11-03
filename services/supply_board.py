"""What the workshop must buy or receive, in one list: supplies by piece, consumables and open orders.

Read-only. Each row names its action: "Pedir" when stock is short and nothing covers it yet,
"Recibir" when an order is open. Shortages already covered by open orders say so instead.
"""
from utils.dates import now


def board(jobs):
    from services import restock, consumables, inbound
    today = now().date().isoformat()
    rows = []
    piece_orders = inbound.list_orders()
    for r in restock.rows():
        if not r['attention']:
            continue
        missing = max(0, r['replenish'] - r['on_order'])
        rows.append(dict(kind='Insumo', identity=f"supply:{r['id']}", record_id=r['id'], title=f"{r['name']} · {r['variant']}" if r['variant'] else r['name'],
                         detail=f"Saldo neto {r['net']} · mínimo {r['minimum']}" + (f" · {r['on_order']} en pedido" if r['on_order'] else ''),
                         state=r['state'], color='red' if r['critical'] else 'orange', action='Pedir' if missing else None,
                         quantity=missing, covered=not missing, score=100 if r['critical'] else 60))
    items = consumables.items(jobs)
    for r in items:
        if not r['attention']:
            continue
        short = max(0, -r['free_after'], r['minimum'] - r['balance']) - r['on_order']
        rows.append(dict(kind='Consumible', identity=f"consumable:{r['id']}", record_id=r['id'], title=r['name'],
                         detail=f"Disponible {consumables.quantity_text(r['balance'], r['unit'])}"
                                + (f" · la cola prevé {consumables.quantity_text(r['committed'], r['unit'])}" if r['committed'] else '')
                                + (f" · {consumables.quantity_text(r['on_order'], r['unit'])} en pedido" if r['on_order'] else ''),
                         state=r['state'], color='red' if r['state'] in ('Sin existencias', 'No alcanza para la cola') else 'orange',
                         action='Pedir' if short > 0 else None, quantity=short, covered=short <= 0,
                         score=95 if r['state'] == 'No alcanza para la cola' else 55))
    for o in piece_orders:
        if o['pending']:
            rows.append(dict(kind='Pedido de piezas', identity=f"inbound:{o['id']}", record_id=o['id'], title=f"{o['code']} · {o['part']}",
                             detail=f"{o['pending']} u. por recibir · {o['supplier'] or 'Sin proveedor'} · llegada {o['expected_on'] or 'sin fecha'}",
                             state=o['status'], color='red' if o['overdue'] else 'blue', action='Recibir', expected=o['expected_on'],
                             score=90 if o['overdue'] else 70 if o['expected_on'] == today else 30))
    for o in consumables.list_orders():
        if o['pending']:
            rows.append(dict(kind='Pedido de consumibles', identity=f"consumable_order:{o['id']}", record_id=o['id'], title=f"{o['code']} · {o['item']}",
                             detail=f"{o['pending']} {o['package_label'].lower()}(s) de {consumables.quantity_text(o['package_size'], o['unit'])} · "
                                    f"{o['supplier'] or 'Sin proveedor'} · llegada {o['expected_on'] or 'sin fecha'}",
                             state=o['status'], color='red' if o['overdue'] else 'blue', action='Recibir', expected=o['expected_on'],
                             score=90 if o['overdue'] else 70 if o['expected_on'] == today else 30))
    rows.sort(key=lambda r: (-r['score'], r['title']))
    to_order = [r for r in rows if r['action'] == 'Pedir']
    arriving = [r for r in rows if r['action'] == 'Recibir']
    return dict(rows=rows, to_order=to_order, arriving=arriving,
                overdue=sum(r['color'] == 'red' and r['action'] == 'Recibir' for r in rows),
                attention=len(to_order) + sum(r['color'] == 'red' for r in arriving))
