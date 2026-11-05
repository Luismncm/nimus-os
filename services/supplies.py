"""Insumos and consumibles as one list: both are something you buy and watch run low.

Insumos (cable, foco, empaque — Colección Origen components bought instead of printed) share
the general reserved-unit inventory ledger. Consumibles (filamento, resina, pintura…) keep their
own weight/volume ledger with packages, because they are not counted in whole pieces. The two
stay separate ledgers underneath for that reason, but this module gives them one combined,
searchable list with one shape, so managing "lo que se compra" does not mean learning two systems.
"""
from services import consumables, restock


def rows(jobs=None):
    """Every consumible and insumo, in one list, each tagged with its kind and a display-ready shape."""
    result = []
    for r in consumables.items(jobs):
        result.append(dict(r, kind='Consumible', supply_id=f"c{r['id']}", name=r['name'],
            variant=' · '.join(x for x in (r['spec'], r['color'], r['brand']) if x),
            balance_text=consumables.quantity_text(r['balance'], r['unit']),
            committed_text=consumables.quantity_text(r['committed'], r['unit']) if r['committed'] else '—',
            minimum_text=consumables.quantity_text(r['minimum'], r['unit']) if r['minimum'] else '—',
            on_order_text=consumables.quantity_text(r['on_order'], r['unit']) if r['on_order'] else '—',
            cost_label=consumables.cost_text(r) if r['package_cost_cents'] is not None else 'Sin costo de referencia'))
    for r in restock.rows():
        result.append(dict(r, kind='Insumo', supply_id=f"r{r['id']}", category=r['role'],
            balance_text=f"{r['net']:g} pza" + ('s' if r['net'] != 1 else ''),
            committed_text=f"{r['committed']:g} pza" if r['committed'] else '—',
            minimum_text=f"{r['minimum']:g} pza" if r['minimum'] else '—',
            on_order_text=f"{r['on_order']:g} pza" if r['on_order'] else '—',
            cost_label='Se costea por receta, no por existencia'))
    return result


def categories(jobs=None):
    """Category labels across both kinds, for one combined filter."""
    return sorted({r['category'] for r in rows(jobs)})
