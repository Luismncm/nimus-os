"""Read-only Base/CAP/Tapa counts by compatible color and material.

Catalog definitions make zero-stock colors visible. Only ledger balances supply
quantities; recipe requirements and components shared by recipes add no stock.
"""
from db import connect
from services.recipes import identity

ROLES = ('Base', 'CAP', 'Tapa')
FIELDS = ('physical', 'free', 'reserved', 'b2b')


def summarize(components, skus):
    active = {c['id']: dict(c) for c in components if c['role'] in ROLES}
    balances = {cid: dict.fromkeys(FIELDS, 0) for cid in active}
    for sku in skus:
        count = balances.get(sku['component_id'])
        if count is None:
            continue
        count['physical'] += sku['unassigned'] + sku['stock']
        count['free'] += sku['available_collection'] + sku['available_stock']
        count['reserved'] += sku['reserved']
        count['b2b'] += sku['b2b']
    groups = {}
    for cid, component in active.items():
        key = identity(component['color'], component['material'])
        group = groups.setdefault(key, dict(id=key, color=component['color'] or 'Sin color',
                material=component['material'] or 'Sin material',
                pieces={role: dict(ids=[], **dict.fromkeys(FIELDS, 0)) for role in ROLES}))
        piece = group['pieces'][component['role']]
        piece['ids'].append(cid)
        for field in FIELDS:
            piece[field] += balances[cid][field]
        component['counts'] = balances[cid]
    for group in groups.values():
        group['kits_available'] = max(0, min(group['pieces'][role]['free'] for role in ROLES))
    rows = sorted(groups.values(), key=lambda g: (g['color'].casefold(), g['material'].casefold()))
    return dict(rows=rows, components=active)


def load_counts(skus=None):
    if skus is None:
        from services.inventory import load_inventory
        skus = load_inventory()['skus']
    with connect() as conn:
        components = [dict(r) for r in conn.execute('''SELECT c.*,o.role,o.color
            FROM catalog_components c JOIN origin_components o ON o.component_id=c.id
            WHERE o.role IN ('Base','CAP','Tapa') AND NOT EXISTS(
                SELECT 1 FROM catalog_component_retirements x WHERE x.component_id=c.id)
            ORDER BY o.color,c.material,c.id''')]
    return summarize(components, skus)


def matrix(rows, field):
    if field not in FIELDS:
        raise ValueError('Conteo no válido.')
    return [dict(color=r['color'], material=r['material'], kits_available=r['kits_available'],
                 **{role: r['pieces'][role][field] for role in ROLES}) for r in rows]
