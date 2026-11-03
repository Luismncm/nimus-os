"""Presentation and draft validation for the recipe workspace."""
import math
from numbers import Real

def product_label(row):
    return ' · '.join(str(row[k]) for k in ('name','variant','collection') if row.get(k))

def product_rows(catalog):
    result=[]
    for product in catalog['products']:
        lines=[r for r in catalog['lines'] if r['recipe_id']==product['recipe_id']]
        result.append(dict(product,parts=len(lines),units=sum(r['quantity'] for r in lines),state='Con receta' if lines else 'Sin receta'))
    return result

def filter_products(rows,search='',line='Todas',state='Todos'):
    needle=search.strip().casefold()
    return [r for r in rows if needle in ' '.join(str(r.get(k) or '') for k in ('code','name','variant','collection')).casefold()
        and (line=='Todas' or r['collection']==line) and (state=='Todos' or r['state']==state)]

def usages(catalog,cid):
    latest={p['recipe_id']:p for p in catalog['products'] if p['recipe_id']}
    return [dict(product_id=latest[r['recipe_id']]['id'],product=product_label(latest[r['recipe_id']]),quantity=r['quantity'],version=latest[r['recipe_id']]['version'])
        for r in catalog['lines'] if r['component_id']==cid and r['recipe_id'] in latest]

def editor_lines(records):
    if not records: raise ValueError('Selecciona al menos una pieza para la receta.')
    lines=[]
    for r in records:
        qty=r.get('quantity')
        if isinstance(qty,bool) or not isinstance(qty,Real) or not math.isfinite(qty) or qty<=0 or int(qty)!=qty:
            raise ValueError('Cada cantidad por producto debe ser un entero positivo. Revisa la tabla.')
        lines.append(dict(component_id=r['component_id'],quantity=int(qty)))
    if len({r['component_id'] for r in lines})!=len(lines): raise ValueError('Una pieza está repetida en la receta.')
    return lines

def differences(current,draft,components):
    before={r['component_id']:r['quantity'] for r in current}
    after={r['component_id']:r['quantity'] for r in draft}
    return [dict(name=components[cid]['name'],variant=components[cid]['variant'],before=before.get(cid,0),after=after.get(cid,0),
        change='Agregar' if cid not in before else 'Quitar' if cid not in after else 'Cambiar cantidad')
        for cid in sorted(before.keys()|after.keys()) if before.get(cid,0)!=after.get(cid,0)]
