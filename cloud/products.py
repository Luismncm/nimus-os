"""Products and stock routes of the cloud app: inventory, filament and supplies, purchases, catalog and Origen.

Same services as the local pages (views/collection.py, origin_ui.py, catalog_workspace.py). The inventory
ledger stays the source of truth: entries, moves and reversals are new movements, never edits. Every form
that creates something carries a request key, so a repeated click records it once.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud import auth
from cloud.routes import write

router = APIRouter(prefix='/api')

PLACES = ('Colección', 'Stock')


class Entry(BaseModel):
    sku_id: int | None = None
    component_id: int | None = None
    quantity: int
    destination: str
    reason: str
    request_key: str


class Move(BaseModel):
    sku_id: int
    source: str
    destination: str
    quantity: int
    client: str = ''
    notes: str = ''
    request_key: str


class Reason(BaseModel):
    reason: str


class SupplyMove(BaseModel):
    kind: str
    amount: float
    notes: str = ''
    job_code: str = ''
    request_key: str


class Receipt(BaseModel):
    quantity: int
    notes: str = ''
    expected_token: str
    request_key: str


class Component(BaseModel):
    name: str
    material: str = ''
    process: str = 'Impresión 3D'
    variant: str = ''
    collection: str = 'General'


class Product(BaseModel):
    name: str
    variant: str = ''
    collection: str = 'General'


class RecipeOrder(BaseModel):
    quantity: int
    project: str = ''
    client: str = ''
    deadline: str = ''
    priority: str = 'Media'
    fulfillment: str = 'Cliente'
    use_stock: bool = True
    expected_fingerprint: str | None = None
    request_key: str


def _piece(r):
    return dict(id=r['id'], code=r['code'], label=r['label'], part=r['part'], model=r['model'], product=r['product'],
                reference=r['reference'], collection=r['collection'], material=r['material'] or '', process=r['process'],
                role=r.get('role') or 'Pieza', supply=r.get('supply') or 'Fabricar', component_id=r['component_id'],
                free=r['free'], reserved=r['reserved'], physical=r['physical'], b2b=r['b2b'], delivered=r['delivered'],
                collection_free=r['available_collection'], stock_free=r['available_stock'],
                unassigned=r['unassigned'], stock=r['stock'], state=r['state'])


@router.get('/inventario')
def inventory(user=Depends(auth.current_user)):
    """Pieces with their balances, the latest movements, reservations, B2B clients, supplies and open purchases."""
    from services import consumables, inbound, restock
    from services.inventory import load_inventory
    from services.inventory_view import location, movement_state, present
    data = load_inventory()
    pieces = [_piece(r) for r in present(data['skus'])]
    finances = user['role'] == 'admin'
    movements = [dict(id=m['id'], code=m['code'], sku_id=m['sku_id'], created_at=m['created_at'], kind=m['kind'],
                      source=location(m['source']), destination=location(m['destination']), quantity=m['quantity'],
                      part=m['part'], product=m['product'], client=m['client'] or '', notes=m['notes'] or '',
                      job=m['job_code'] or '', order=m['order_code'] or '', state=movement_state(m),
                      reversible=m['kind'] in ('Traslado', 'B2B', 'Entrada manual') and not m['order_id'] and not m['reversed_by'] and m['kind'] != 'Reversión')
                 for m in data['movements'][:300]]
    supplies = [dict(id=i['id'], name=i['name'], category=i['category'], unit=i['unit'], spec=i['spec'] or '', color=i['color'] or '',
                     balance=i['balance'], minimum=i['minimum'], committed=i['committed'], free_after=i['free_after'],
                     on_order=i['on_order'], state=i['state'], attention=bool(i['attention']),
                     value_cents=i['stock_value_cents'] if finances else None)
                for i in consumables.items()]
    restocks = [dict(id=r['id'], name=r['name'], variant=r['variant'] or '', net=r['net'], minimum=r['minimum'], physical=r['physical'],
                     reserved=r['reserved'], on_order=r['on_order'], replenish=r['replenish'], critical=bool(r['critical']),
                     attention=bool(r['attention'])) for r in restock.rows()]
    purchases = ([dict(kind='Piezas e insumos', id=o['id'], code=o['code'], what=f"{o['part']}" + (f" · {o['material']}" if o['material'] else ''),
                       supplier=o['supplier'] or '', status=o['status'], ordered_on=o['ordered_on'], expected_on=o['expected_on'],
                       overdue=bool(o['overdue']), quantity=o['quantity'], received=o['received'], remaining=o['pending'],
                       unit='piezas', token=o['token'])
                  for o in inbound.list_orders()]
                 + [dict(kind='Filamento y consumibles', id=o['id'], code=o.get('code') or f"CON-{o['id']:04d}", what=o['item'],
                         supplier=o.get('supplier') or '', status=o['status'], ordered_on=o.get('ordered_on'), expected_on=o.get('expected_on'),
                         overdue=bool(o['overdue']), quantity=o['packages'], received=o['received'], remaining=o['remaining'] if not o['cancelled'] else 0,
                         unit='paquetes', token=o['token'])
                    for o in consumables.list_orders()])
    reservations = [dict(id=h['id'], order=h['order_code'], project=h['project'], part=h['part'], variant=h['variant'] or '',
                         location=location(h['location']), quantity=h['quantity']) for h in data['reservations']]
    clients = [dict(client=c['client'], part=c['part'], product=c['product'], quantity=c['quantity']) for c in data['clients']]
    return dict(pieces=pieces, movements=movements, supplies=supplies, restock=restocks, purchases=purchases,
                reservations=reservations, clients=clients)


@router.post('/inventario/entrada')
def entry(body: Entry, user=Depends(auth.current_user)):
    """Pieces found or made outside a print, into Por distribuir or Almacén of an existing reference."""
    from services.inventory import receive_manual
    if body.destination not in PLACES:
        raise HTTPException(status_code=400, detail='Elige Por distribuir o Almacén.')
    movement = write(receive_manual, body.quantity, body.destination, body.reason, sku_id=body.sku_id,
                     component_id=body.component_id, request_key=body.request_key)
    return dict(ok=True, movement_id=movement)


@router.post('/inventario/mover')
def move(body: Move, user=Depends(auth.current_user)):
    from services.inventory import distribute
    movement = write(distribute, body.sku_id, body.source, body.destination, body.quantity, client=body.client,
                     notes=body.notes, request_key=body.request_key)
    return dict(ok=True, movement_id=movement)


@router.post('/inventario/movimientos/{movement_id}/revertir')
def reverse(movement_id: int, body: Reason, user=Depends(auth.current_user)):
    from services.inventory import reverse_movement
    return dict(ok=True, movement_id=write(reverse_movement, movement_id, body.reason))


@router.post('/consumibles/{item_id}/movimiento')
def supply_move(item_id: int, body: SupplyMove, user=Depends(auth.current_user)):
    """Filament or supply in (Entrada), used (Consumo) or counted (Conteo, sets the balance)."""
    from services import consumables as c
    if body.kind == 'Entrada':
        result = write(c.receive, item_id, body.amount, notes=body.notes, request_key=body.request_key)
    elif body.kind == 'Consumo':
        result = write(c.consume, item_id, body.amount, job_code=body.job_code, notes=body.notes, request_key=body.request_key)
    elif body.kind == 'Conteo':
        result = write(c.count, item_id, body.amount, notes=body.notes, request_key=body.request_key)
    else:
        raise HTTPException(status_code=400, detail='Elige Entrada, Consumo o Conteo.')
    return dict(ok=True, id=result)


@router.post('/compras/piezas/{identity}/recibir')
def receive_pieces(identity: int, body: Receipt, user=Depends(auth.current_user)):
    from services import inbound
    return dict(ok=True, movement_id=write(inbound.receive, identity, body.quantity, notes=body.notes,
                                           expected_token=body.expected_token, request_key=body.request_key))


@router.post('/compras/consumibles/{identity}/recibir')
def receive_supplies(identity: int, body: Receipt, user=Depends(auth.current_user)):
    from services import consumables
    write(consumables.receive_order, identity, body.quantity, notes=body.notes, expected_token=body.expected_token, request_key=body.request_key)
    return dict(ok=True)


def _catalog():
    from services.recipes import load_catalog
    catalog = load_catalog()
    lines = {}
    for line in catalog['lines']:
        lines.setdefault(line['recipe_id'], []).append(line)
    used = {}
    for p in catalog['products']:
        for line in lines.get(p['recipe_id'], []):
            used.setdefault(line['component_id'], []).append(p['name'] + (f" · {p['variant']}" if p['variant'] else ''))
    return catalog, lines, used


@router.get('/catalogo')
def catalog(user=Depends(auth.current_user)):
    """Products with their current recipe, and the reusable pieces with the products that use each."""
    catalog, lines, used = _catalog()
    versions = {}
    for v in catalog['versions']:
        versions[v['product_id']] = versions.get(v['product_id'], 0) + 1
    products = [dict(id=p['id'], code=p['code'], name=p['name'], variant=p['variant'] or '', collection=p['collection'],
                     recipe_id=p['recipe_id'], version=p['version'], versions=versions.get(p['id'], 0),
                     retired=bool(p['has_retired_components']),
                     lines=[dict(component_id=l['component_id'], name=l['name'], variant=l['variant'] or '', material=l['material'] or '',
                                 process=l['process'], quantity=l['quantity']) for l in lines.get(p['recipe_id'], [])])
                for p in catalog['products']]
    components = [dict(id=c['id'], code=c['code'], name=c['name'], variant=c['variant'] or '', material=c['material'] or '',
                       process=c['process'], collection=c['collection'], used_in=used.get(c['id'], []))
                  for c in catalog['components']]
    from models.constants import PRIORITIES, PROCESSES
    return dict(products=products, components=components, processes=PROCESSES, priorities=PRIORITIES)


@router.post('/catalogo/componentes')
def component_create(body: Component, user=Depends(auth.current_user)):
    from services import recipes
    return dict(ok=True, id=write(recipes.create_component, body.name, body.material, body.process, body.variant, body.collection))


@router.post('/catalogo/productos')
def product_create(body: Product, user=Depends(auth.current_user)):
    from services import recipes
    return dict(ok=True, id=write(recipes.create_product, body.name, body.variant, body.collection))


@router.get('/catalogo/recetas/{recipe_id}/plan')
def recipe_plan(recipe_id: int, cantidad: int = 1, stock: bool = True, user=Depends(auth.current_user)):
    """What an order of this recipe takes: per component, what is in stock, reserved, to make and to buy."""
    from services import recipes
    if cantidad < 1:
        raise HTTPException(status_code=400, detail='La cantidad debe ser al menos 1.')
    plan = write(recipes.quote_order, recipe_id, cantidad, stock)
    return dict(recipe=dict(id=plan['recipe']['id'], name=plan['recipe']['name'], variant=plan['recipe']['variant'] or '',
                            version=plan['recipe']['version'], collection=plan['recipe']['collection']),
                quantity=cantidad, fingerprint=plan['fingerprint'],
                lines=[dict(component_id=l['component_id'], name=l['name'], variant=l['variant'] or '', supply=l.get('supply') or 'Fabricar',
                            needed=l['needed'], available=l['available'], reserved=l['reserved'], to_make=l['to_make'], to_buy=l.get('to_buy', 0))
                       for l in plan['lines']])


@router.post('/catalogo/recetas/{recipe_id}/pedido')
def recipe_order(recipe_id: int, body: RecipeOrder, user=Depends(auth.current_user)):
    """An order from a recipe: reserves what is in stock and creates parts only for what is missing."""
    from services import recipes
    order = write(recipes.create_recipe_order, recipe_id, body.quantity, project=body.project, client=body.client,
                  deadline=body.deadline, priority=body.priority, fulfillment=body.fulfillment, use_stock=body.use_stock,
                  expected_fingerprint=body.expected_fingerprint, request_key=body.request_key)
    return dict(ok=True, order_id=order)


@router.get('/origen')
def origin(user=Depends(auth.current_user)):
    """Colección Origen: each lamp (shade model × base color) with its recipe, and active lamp orders with what they still need."""
    from services import origin as service
    from services.queries import load_snapshot, piece_label
    data = service.load()
    _, lines, _ = _catalog()
    bases = {b['id']: b for b in data['bases']}
    lamps = []
    for p in data['products']:
        spec = p.get('origin')
        if not spec or p['has_retired_components']:
            continue
        base = bases.get(spec.get('base_set_id')) or {}
        lamps.append(dict(id=p['id'], code=p['code'], name=p['name'], model=spec.get('model') or '', color=base.get('color') or '',
                          recipe_id=p['recipe_id'], version=p['version'],
                          lines=[dict(name=l['name'], variant=l['variant'] or '', material=l['material'] or '', quantity=l['quantity'])
                                 for l in lines.get(p['recipe_id'], [])]))
    specs = data['specs']
    orders = []
    for o in load_snapshot()['orders']:
        if o['status'] == 'Entregado' or o.get('commercial_cancelled') or not any(i['recipe_id'] in specs for i in o['items']):
            continue
        needs = [r for i in o['items'] for r in i.get('requirements', [])]
        orders.append(dict(id=o['id'], code=o['code'], project=o['project'], client=o['client'] or '', status=o['status'],
                           needs=[dict(name=piece_label(r['name'], (r.get('variant') or '').strip()), supply=r.get('supply') or '',
                                       quantity=r['quantity'], covered=r['covered'], pending=r['quantity'] - r['covered']) for r in needs],
                           can_reserve=any(r.get('supply') == 'Comprar' and r['quantity'] > r['covered'] for r in needs)))
    return dict(models=data['shade_models'], colors=sorted({b['color'] for b in data['bases']}), lamps=lamps, orders=orders)


@router.post('/origen/pedidos/{order_id}/reservar')
def origin_reserve(order_id: int, user=Depends(auth.current_user)):
    from services import origin as service
    return dict(ok=True, reserved=write(service.reserve_supplies, order_id))
