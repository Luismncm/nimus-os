"""Separate actual manufacturing work from purchased inventory coverage.

Recipe parts contain only shortages planned for manufacturing. Reservations of
existing printed pieces and purchased supplies must never advance that work.
The original coverage totals remain the source of truth for delivery/costing.
"""
from utils.calculations import progress


def manufacturing(record):
    items = record.get('items')
    if items is None:
        items = [record]
    parts = [p for item in items for p in item['parts']]
    required = sum(p['quantity_required'] for p in parts)
    completed = sum(p['quantity_completed'] for p in parts)
    defined = bool(items) and all(i.get('recipe_id') or i['parts'] for i in items)
    return dict(required=required, completed=completed, remaining=required-completed,
                progress=progress(required, completed), applicable=required > 0,
                defined=bool(defined), complete=bool(defined and required == completed))


def breakdown(record):
    """Units by work state; completed + running + queued + unassigned == required.

    This is the shared vocabulary of every order, product and piece view:
    Terminadas, En curso, En cola (queued, paused or blocked) and Sin asignar.
    """
    parts = [record] if 'quantity_required' in record else [p for i in record.get('items', [record]) for p in i['parts']]
    jobs = [j for p in parts for j in p['jobs'] if j['status'] != 'Terminado']
    running = sum(j['quantity'] - j['quantity_completed'] for j in jobs if j['status'] == 'En producción')
    queued = sum(j['quantity'] - j['quantity_completed'] for j in jobs if j['status'] != 'En producción')
    return dict(required=sum(p['quantity_required'] for p in parts),
                completed=sum(p['quantity_completed'] for p in parts),
                running=running, queued=queued,
                unassigned=sum(p['quantity_required'] - sum(j['quantity'] for j in p['jobs']) for p in parts),
                blocked=sum(j['status'] == 'Bloqueado' for j in jobs))


def piece_rows(item):
    """One row per piece to make, with the same columns for recipe and custom products."""
    rows = []
    parts = {p['id']: p for p in item['parts']}
    if item.get('recipe_id'):
        for r in item['requirements']:
            if r.get('supply') == 'Comprar':
                continue
            part = parts.pop(r.get('production_part_id'), None)
            from services.queries import piece_label
            rows.append(_piece_row(part, piece_label(r['name'], (r.get('variant') or '').strip()), r['material'], r.get('process') or '', r['quantity'], r['from_stock'], r.get('id')))
    rows += [_piece_row(p, p['name'], p['material'], p['process'], p['quantity_required'], 0) for p in parts.values()]
    return rows


def _piece_row(part, name, material, process, required, from_stock, requirement_id=None):
    b = breakdown(part) if part else dict(required=0, completed=0, running=0, queued=0, unassigned=0, blocked=0)
    return dict(part_id=part['id'] if part else None, requirement_id=requirement_id, code=part['code'] if part else '—', name=name, material=material or 'Sin material', process=process,
                required=required, from_stock=from_stock, to_make=b['required'], completed=b['completed'],
                running=b['running'], queued=b['queued'], unassigned=b['unassigned'],
                progress=progress(b['required'], b['completed']) if b['required'] else 100.0)


def supplies(record):
    items = record.get('items', [record])
    needs = [r for i in items for r in i.get('requirements', []) if r.get('supply') == 'Comprar']
    required = sum(r['quantity'] for r in needs)
    covered = sum(r['covered'] for r in needs)
    return dict(required=required, covered=covered, remaining=required-covered,
                progress=progress(required, covered), complete=required == covered)


def annotate(record):
    m, s = manufacturing(record), supplies(record)
    items = record.get('items', [record])
    stock = sum(r['from_stock'] for i in items for r in i.get('requirements', [])
                if r.get('supply') != 'Comprar')
    record.update(manufacturing=m, supplies=s, manufactured_from_stock=stock,
                  manufacturing_progress=m['progress'] if m['applicable'] else None,
                  manufacturing_remaining=m['remaining'], supplies_remaining=s['remaining'])


def fabrication_label(record):
    m = manufacturing(record)
    if not m['applicable']:
        return 'Fabricación por definir' if not m['defined'] else 'Sin fabricación requerida'
    return f"Fabricación · {m['completed']}/{m['required']} terminadas · {m['progress']:.0f}%"


def display_status(order):
    if order['status'] in ('Entregado', 'Bloqueado'):
        return order['status']
    if order['required_total'] and not order['remaining_total'] and not order['undefined_items']:
        return 'Listo para preparar'
    m = manufacturing(order)
    if m['complete']:
        return 'Insumos pendientes' if supplies(order)['remaining'] else 'Componentes pendientes'
    jobs = [j for i in order['items'] for p in i['parts'] for j in p['jobs']]
    return 'En producción' if m['completed'] or any(j.get('started_at') for j in jobs) else 'Pendiente'
