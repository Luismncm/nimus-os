"""Explicit cost completeness and capacity scenarios; neither promises delivery nor posts money."""
import math
from datetime import timedelta
from db import connect
from services import costing,quotations as q,recipe_cart
from utils.dates import now

def prices(entries,*,discount=0,iva=False,shipping=None,shipping_cost=None):
    lines=[];cost_rows=[]
    for e in entries:
        report=costing.recipe_cost(e['recipe_id'])
        cost_rows.append(dict(recipe_id=e['recipe_id'],quantity=e['quantity'],unit_cents=report['total_cents'],missing=report['missing']))
        lines.append(dict(description=e.get('label') or 'Lámpara',quantity=e['quantity'],price=e.get('price') or 0,produce=True))
    if shipping is not None or shipping_cost is not None:lines.append(dict(description='Envío',quantity=1,price=shipping or 0,produce=False))
    data=q.calculate(dict(q.defaults(),lines=lines,discount=discount,iva=iva))
    priced=all(e.get('price') is not None for e in entries)
    complete=priced and bool(entries) and all(r['unit_cents'] is not None for r in cost_rows) and (shipping is None or shipping_cost is not None)
    total_cost=sum(r['unit_cents']*r['quantity'] for r in cost_rows)+q.cents(shipping_cost or 0) if complete else None
    net=data['totals']['subtotal']-data['totals']['discount']
    profit=net-total_cost if total_cost is not None else None
    return dict(totals=data['totals'],priced=priced,cost_rows=cost_rows,cost_cents=total_cost,net_cents=net,
        profit_cents=profit,margin=100*profit/net if profit is not None and net else None)

def forecast(entries,terms,plan=None):
    plan=plan or recipe_cart.quote(entries);missing=[];minutes=0;queue_minutes=0;unknown_queue=0
    with connect() as conn:
        machines=conn.execute("SELECT COUNT(*) FROM machines WHERE archived=0 AND status NOT IN ('Mantenimiento','Fuera de servicio')").fetchone()[0]
        for entry in plan['entries']:
            for row in entry['lines']:
                if not row['to_make']:continue
                profile=costing._latest(conn,'component_cost_versions','component_id',row['component_id'])
                d=profile['data'] if profile else {}
                if d.get('lot_minutes') is None or not d.get('lot_units'):missing.append(row['name']+' · '+row['variant'])
                else:minutes+=row['to_make']*d['lot_minutes']/d['lot_units']
        for job in conn.execute('''SELECT j.*,p.duration_minutes FROM production_jobs j JOIN parts t ON t.id=j.part_id JOIN items i ON i.id=t.item_id
          JOIN orders o ON o.id=i.order_id LEFT JOIN print_plans p ON p.job_id=j.id
          WHERE j.status<>'Terminado' AND o.status<>'Entregado' AND o.blocked_manually=0'''):
            if job['duration_minutes'] is None:unknown_queue+=1
            else:queue_minutes+=job['duration_minutes']*(job['quantity']-job['quantity_completed'])/job['quantity']
    buy=sum(r['to_buy'] for p in plan['entries'] for r in p['lines'])
    if not terms.get('hours_per_day'):missing.append('Horas de trabajo por día')
    if terms.get('assembly_minutes') is None:missing.append('Tiempo de ensamble por lámpara')
    if buy and terms.get('purchase_days') is None:missing.append('Plazo para recibir insumos')
    if unknown_queue:missing.append(f'{unknown_queue} trabajos en cola sin duración')
    if (minutes or queue_minutes) and not machines:missing.append('Máquinas operativas')
    estimated=None;days=None
    if not missing:
        available=terms['hours_per_day']*60
        production_days=(minutes+queue_minutes)/(available*machines) if minutes+queue_minutes else 0
        assembly_days=sum(e['quantity'] for e in entries)*terms['assembly_minutes']/available
        days=math.ceil(production_days+assembly_days)+(math.ceil(terms['purchase_days']) if buy else 0)
        estimated=(now().date()+timedelta(days=days)).isoformat()
    return dict(estimated_on=estimated,days=days,known_print_minutes=minutes,queue_minutes=queue_minutes,
        machines=machines,missing=list(dict.fromkeys(missing)))
