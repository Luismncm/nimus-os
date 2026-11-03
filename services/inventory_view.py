"""Read-only inventory labels and filters; the ledger remains the source of truth."""

def model(row):
    """The model a piece belongs to: the catalog variant (CIRRUS, CUMULO, STRATO) or the product it was printed for."""
    return (row.get('variant') or '').strip() or ('' if row.get('component_id') else row.get('product') or '')


def label(row):
    """Piece with its model, so identical parts are told apart: PANTALLA · CIRRUS."""
    name,kind=row['part'],model(row)
    return f"{name} · {kind}" if kind and kind.casefold() not in name.casefold() else name


def present(rows):
    result=[]
    for row in rows:
        free=row['available_collection']+row['available_stock']
        physical=row['unassigned']+row['stock']
        result.append(dict(row,free=free,physical=physical,model=model(row),label=label(row),
            reference='Pieza compartida de catálogo' if row['component_id'] else row['product'],
            state='Disponible' if free>0 else 'Reservada' if row['reserved']>0 else 'En clientes' if row['b2b']>0 else 'Sin saldo'))
    return result


def query(rows, *, search='', model='Todos', line='Todas', state='Todos'):
    term=search.strip().casefold()
    return [r for r in rows if (model=='Todos' or r['product']==model) and (line=='Todas' or r['collection']==line)
        and (state=='Todos' or state=='Con disponibles' and r['free']>0 or state=='Con reservas' and r['reserved']>0
             or state=='Sin saldo' and r['physical']==0 and r['b2b']==0)
        and term in ' '.join(str(r.get(f) or '') for f in ('code','product','reference','part','model','material','process','collection')).casefold()]


def totals(rows):
    return {field:sum(r[field] for r in rows) for field in ('physical','free','reserved','b2b')}


def location(value):
    return {'Colección':'Por distribuir', 'Stock':'Almacén', 'B2B':'Cliente B2B',
            'Producción':'Producción', 'Externo':'Entrada externa', 'Entregado':'Entregado'}.get(value,value)


def movement_state(row):
    return 'Revertido' if row['reversed_by'] else 'Reversión' if row['kind']=='Reversión' else 'Registrado'
