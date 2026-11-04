"""Profitability routes of the cloud app: recipe costs, profit by sale and by order, and the performance report.

Read-only, administration only: the same figures as views/costs.py, views/control.py (Costos y margen) and
views/performance.py. Editing cost profiles and assigning sale costs stay in the local app for now.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from cloud import auth
from cloud.routes import write

router = APIRouter(prefix='/api')
PERIODS = ('Este mes', 'Mes anterior', 'Últimos 90 días', 'Este año')
EXTRAS = (('kit_cents', 'Kit eléctrico'), ('bulb_cents', 'Foco'), ('packaging_cents', 'Empaque'), ('assembly_cents', 'Ensamble'), ('other_cents', 'Otros directos'))


@router.get('/costos')
def costs(user=Depends(auth.admin)):
    """Per recipe: cost per component and per lamp; per active sale: net revenue, cost and gross profit; per order: real cost and margin."""
    from services import costing, order_costs, recipes, sales
    from services.queries import load_snapshot
    catalog = recipes.load_catalog()
    recipe_rows = []
    for p in catalog['products']:
        if not p['recipe_id']:
            continue
        c = costing.recipe_cost(p['recipe_id'])
        extras = c.get('extras') or {}
        recipe_rows.append(dict(
            product_id=p['id'], recipe_id=p['recipe_id'], name=p['name'], variant=p['variant'] or '', collection=p['collection'],
            total_cents=c['total_cents'], known_cents=c['known_cents'], missing=c['missing'],
            lines=[dict(name=l['name'], variant=l['variant'] or '', quantity=l['quantity'], supply=l.get('supply') or '',
                        material_cents=l.get('material_cents'), machine_cents=l.get('machine_cents'), fixed_cents=l.get('fixed_cents'),
                        line_cents=l.get('line_cents'), missing=l.get('missing') or []) for l in c['lines']],
            extras=[dict(label=label, cents=extras.get(key)) for key, label in EXTRAS if extras.get(key)]))
    sale_rows = []
    for s in sales.list_sales():
        if s['status'] != 'Activa':
            continue
        m = costing.sale_margin(s['id'])
        sale_rows.append(dict(id=s['id'], code=s['code'], client=s['client'] or '', project=s['project'] or '', sold_on=s['sold_on'],
                              net_cents=m['net_revenue_cents'], cost_cents=m['cost_cents'], profit_cents=m['profit_cents'],
                              margin_percent=m['margin_percent'],
                              state='Revisar cambios' if m['stale'] else 'Completo' if m['complete'] else 'Pendiente'))
    order_rows = [dict(order_id=r['order_id'], code=r['code'], project=r['project'], client=r['client'] or '', status=r['status'],
                       development=bool(r['development']), revenue_cents=r['revenue_cents'], cost_cents=r['actual_known_cents'],
                       estimated_cents=r['estimated_cents'], margin_cents=r['margin_cents'], margin_percent=r['margin_percent'],
                       complete=bool(r['complete']), costed_jobs=r['costed_jobs'], job_count=r['job_count'],
                       consumables_cents=r['consumables_cents'], extras_cents=r['extras_cents'])
                  for r in order_costs.reports(load_snapshot())]
    return dict(recipes=recipe_rows, sales=sale_rows, orders=order_rows)


@router.get('/rendimiento')
def performance(periodo: str = 'Este mes', user=Depends(auth.admin)):
    """The period against the one before: sales, collections, expenses, deliveries on time, production and quality."""
    from services import performance as perf
    if periodo not in PERIODS:
        raise HTTPException(status_code=400, detail='Elige un periodo.')
    data = perf.load()
    start, end = perf.period(periodo)
    compared = write(perf.compare, data, start, end)
    return dict(period=periodo, periods=PERIODS, start=start.isoformat(), end=end.isoformat(),
                prior_start=compared['prior_start'].isoformat(), prior_end=compared['prior_end'].isoformat(),
                current=compared['current'], prior=compared['prior'], months=perf.months(data, end),
                machines=perf.by_machine(data, start, end), clients=perf.top_clients(data, start, end))
