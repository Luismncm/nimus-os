"""Signed availability = physical stock - reservations - uncovered open-order needs.

An order may commit more than is on hand. Physical receipts/reservations retain
their existing protections; purchasing debt is derived, never posted as a receipt.
"""
from contextlib import nullcontext
from db import connect
from utils.dates import timestamp


def rows(conn=None):
    with (connect() if conn is None else nullcontext(conn)) as c:
        components=[dict(r) for r in c.execute('''SELECT c.*,o.role,
            COALESCE(m.minimum,0) minimum,COALESCE(m.revision,0) minimum_revision
            FROM catalog_components c JOIN origin_components o ON o.component_id=c.id
            LEFT JOIN restock_minimums m ON m.component_id=c.id
            WHERE o.supply='Comprar' AND NOT EXISTS(
                SELECT 1 FROM catalog_component_retirements t WHERE t.component_id=c.id)
            ORDER BY o.role,c.name,c.variant,c.id''')]
        physical={r['component_id']:r['quantity'] for r in c.execute('''SELECT s.component_id,
            SUM(CASE WHEN m.destination IN ('Stock','Colección') THEN m.quantity ELSE 0 END
                - CASE WHEN m.source IN ('Stock','Colección') THEN m.quantity ELSE 0 END) quantity
            FROM inventory_movements m JOIN inventory_skus s ON s.id=m.sku_id GROUP BY s.component_id''')}
        held={r['component_id']:r['quantity'] for r in c.execute('''SELECT s.component_id,SUM(h.quantity) quantity
            FROM inventory_reservations h JOIN inventory_skus s ON s.id=h.sku_id
            WHERE h.status='Activa' GROUP BY s.component_id''')}
        needs=[dict(r) for r in c.execute('''SELECT r.component_id,r.quantity,o.id order_id,o.code,o.project,o.deadline,
            COALESCE((SELECT SUM(h.quantity) FROM inventory_reservations h
                WHERE h.requirement_id=r.id AND h.status IN ('Activa','Consumida')),0) covered
            FROM recipe_requirements r JOIN items i ON i.id=r.item_id JOIN orders o ON o.id=i.order_id
            JOIN origin_components t ON t.component_id=r.component_id AND t.supply='Comprar'
            WHERE o.status<>'Entregado' AND NOT EXISTS(SELECT 1 FROM order_cancellations x WHERE x.order_id=o.id)''')]
    result=[]
    from services.inbound import list_orders
    incoming={}
    for order in list_orders(conn):
        if order['component_id'] and order['pending']:
            incoming[order['component_id']]=incoming.get(order['component_id'],0)+order['pending']
    for item in components:
        cid=item['id'];pending=sum(max(0,n['quantity']-n['covered']) for n in needs if n['component_id']==cid)
        stock=physical.get(cid,0);reserved=held.get(cid,0);net=stock-reserved-pending
        critical=net<0;low=item['minimum']>0 and net<=item['minimum']
        state='En negativo' if critical else 'Reponer' if low else 'Sin mínimo' if not item['minimum'] else 'En nivel'
        target=item['minimum']+1 if item['minimum'] else 0
        result.append(dict(item,code=f'CMP-{cid:04d}',physical=stock,reserved=reserved,pending=pending,
            committed=reserved+pending,net=net,deficit=max(0,-net),state=state,critical=critical,
            attention=critical or low,score=100 if critical else 30 if low else 0,
            on_order=incoming.get(cid,0),
            replenish=max(0,target-net) if critical or low else 0,
            orders=[n for n in needs if n['component_id']==cid]))
    return sorted(result,key=lambda r:(-r['score'],r['net'],r['name'],r['id']))


def save_minimums(changes):
    """Apply an entire grid with revision checks in one transaction."""
    if not changes or len(changes)>1000:raise ValueError('Selecciona los insumos para actualizar.')
    if len({r['component_id'] for r in changes})!=len(changes):raise ValueError('Hay insumos repetidos.')
    with connect(write=True) as conn:
        lookup={r['id']:r for r in rows(conn)}
        for change in changes:
            row=lookup.get(change['component_id']);minimum=change['minimum']
            if type(minimum) is not int or not 0<=minimum<=1000000:raise ValueError('El mínimo debe ser un entero entre 0 y 1,000,000.')
            if not row or row['minimum_revision']!=change['expected_revision']:raise ValueError('Los mínimos cambiaron en otra ventana. Actualiza la vista antes de guardar.')
        for change in changes:
            row=lookup[change['component_id']]
            if row['minimum']==change['minimum']:continue
            conn.execute('''INSERT INTO restock_minimums(component_id,minimum,updated_at) VALUES(?,?,?)
                ON CONFLICT(component_id) DO UPDATE SET minimum=excluded.minimum,
                revision=restock_minimums.revision+1,updated_at=excluded.updated_at''',
                (row['id'],change['minimum'],timestamp()))


def projection(plan):
    lines=plan.get('lines') or [r for entry in plan.get('entries',[]) for r in entry['lines']]
    demand={}
    for line in lines:
        if line.get('supply')=='Comprar':demand[line['component_id']]=demand.get(line['component_id'],0)+line['needed']
    return [dict(r,needed=demand[r['id']],net_after=r['net']-demand[r['id']]) for r in rows() if r['id'] in demand]
