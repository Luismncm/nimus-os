"""Pure composition helpers for the continuous recipe configurator."""
from services import origin

SUPPLIES=(('Cable','cable_id'),('Foco','bulb_id'),('Empaque','packaging_id'))

def new_draft(data,*,product=None,template=None,shade_id=None,base_set_id=None):
    source=product or template or {};spec=source.get('origin') or {}
    shade_id=spec.get('shade_id',shade_id)
    shade=next((c for c in data['components'] if c['id']==shade_id),None)
    result=dict(product_id=product['id'] if product else None,expected_recipe_id=product['recipe_id'] if product else None,
        product_name=product['name'] if product else '',version=product['version'] if product else None,
        model=shade['shape'] if shade else None,shade_id=shade_id,base_set_id=spec.get('base_set_id',base_set_id),
        name='',notes='')
    for role,field in SUPPLIES:
        ids=[c['id'] for c in data['components'] if c['role']==role]
        result[field]=spec.get(field,ids[0] if len(ids)==1 else None)
    return result

def composition(data,draft):
    components={c['id']:c for c in data['components']};bases={b['id']:b for b in data['bases']}
    shade=components.get(draft['shade_id']);base=bases.get(draft['base_set_id'])
    if shade and (shade['role']!='Pantalla' or shade['shape']!=draft['model']):shade=None
    ids={'Pantalla':shade['id'] if shade else None,
        **{role:base[field] if base else None for role,field in (('Base','base_id'),('CAP','cap_id'),('Tapa','lid_id'))},
        **{role:draft[field] for role,field in SUPPLIES}}
    rows=[]
    for role in origin.ROLES:
        component=components.get(ids[role])
        if component and component['role']!=role:component=None
        rows.append(dict(role=role,component=component,quantity=1))
    complete=all(r['component'] for r in rows)
    matches=[]
    if complete:
        selected={r['component']['id'] for r in rows}
        for p in data['products']:
            if p['origin'] and not p['has_retired_components']:
                existing={r['component_id'] for r in data['catalog']['lines'] if r['recipe_id']==p['recipe_id']}
                if existing==selected:matches.append(p)
    suggested=f"{shade['shape']} · {base['color']}" if shade and base else 'Tu nueva lámpara'
    return dict(rows=rows,shade=shade,base=base,complete=complete,matches=matches,
        name=draft['product_name'] or draft['name'].strip() or suggested,
        count=sum(bool(r['component']) for r in rows))
