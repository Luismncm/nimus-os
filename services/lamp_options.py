"""Model/color choices and component availability, independent of physical assembly."""
from services.recipes import positive

def free_components(ledger):
    free={}
    for sku in ledger['skus']:
        cid=sku['component_id']
        if cid is not None:
            free[cid]=free.get(cid,0)+max(0,sku['available_stock'])+max(0,sku['available_collection'])
    return free

def availability(data,ledger,product,quantity=1):
    positive(quantity)
    definitions={c['id']:c for c in data['components']};free=free_components(ledger)
    rows=[]
    for line in data['catalog']['lines']:
        if line['recipe_id']!=product['recipe_id']:continue
        c=definitions[line['component_id']];needed=line['quantity']*quantity;available=free.get(c['id'],0)
        missing=max(0,needed-available)
        rows.append(dict(role=c['role'],supply=c['supply'],component_id=c['id'],per_product=line['quantity'],
            available=available,needed=needed,to_make=missing if c['supply']=='Fabricar' else 0,to_buy=missing if c['supply']=='Comprar' else 0))
    ready=min((r['available']//r['per_product'] for r in rows),default=0)
    printed=min((r['available']//r['per_product'] for r in rows if r['supply']=='Fabricar'),default=0)
    base=min((r['available']//r['per_product'] for r in rows if r['role'] in ('Base','CAP','Tapa')),default=0)
    status='Para ensamblar' if ready>=quantity else 'Completar insumos' if printed>=quantity else 'Por fabricar'
    return dict(ready=ready,printed=printed,base=base,status=status,
        to_make=sum(r['to_make'] for r in rows),to_buy=sum(r['to_buy'] for r in rows),rows=rows)

def color_options(data,ledger,model,quantity=1):
    positive(quantity)
    rows=[]
    for base in data['bases']:
        products=[p for p in data['products'] if p['origin'] and not p['has_retired_components']
            and p['origin']['model']==model and p['origin']['base_set_id']==base['id']]
        stock=availability(data,ledger,products[0],quantity) if len(products)==1 else None
        rows.append(dict(base=base,products=products,stock=stock))
    return rows
