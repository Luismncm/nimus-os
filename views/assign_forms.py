"""Assign every pending piece of an order or product to machines in one window."""
import pandas as pd
import streamlit as st
from services import production as service
from services.assign_suggest import same_material
from views.common import managed_dialog, perform

EXTERNAL = 'Sin máquina'


def pending_parts(order, item_id=None):
    """Pieces with units still to assign, grouped by material so shared filaments sit together."""
    rows = [p for i in order['items'] if item_id in (None, i['id']) for p in i['parts'] if p['quantity_unassigned'] > 0]
    return sorted(rows, key=lambda p: ((p['material'] or '').casefold(), p['item_name'], p['id']))


def _columns(machines):
    return [m['code'] for m in machines] + [EXTERNAL]


def _frame(parts, machines, amounts=None):
    amounts = amounts or {}
    return pd.DataFrame([{'Pieza': p['name'], 'Producto': p['item_name'], 'Material': p['material'] or 'Sin material',
                          'Sin asignar': p['quantity_unassigned'],
                          **{c: amounts.get((p['id'], c), 0) for c in _columns(machines)}} for p in parts])


def _auto(parts, machines):
    """Each piece whole to the least loaded available machine, preferring one already on that material.

    Keeping a piece on one machine avoids one-unit jobs; existing pending units count as load.
    """
    available = [m for m in machines if m['status'] == 'Disponible']
    if not available:
        return {(p['id'], EXTERNAL): p['quantity_unassigned'] for p in parts}
    load = {m['code']: m.get('pending_units', 0) for m in available}
    materials = {m['code']: set() for m in available}
    loaded = {m['code']: m.get('loaded_material', '') for m in available}
    amounts = {}
    for p in sorted(parts, key=lambda p: -p['quantity_unassigned']):
        # The filament already mounted is worth the piece's own units of load: it avoids a spool change
        # without piling a whole batch on one printer.
        bonus = lambda c: p['quantity_unassigned'] if same_material(loaded[c], p['material']) else 0
        code = min(load, key=lambda c: (load[c] - bonus(c), p['material'] not in materials[c], c))
        amounts[(p['id'], code)] = p['quantity_unassigned']
        load[code] += p['quantity_unassigned']
        materials[code].add(p['material'])
    return amounts


@managed_dialog('Repartir piezas pendientes', width='large')
def bulk_split_form(order_id: int, item_id: int | None = None) -> None:
    snapshot = st.session_state['snapshot']
    order = next((o for o in snapshot['orders'] if o['id'] == order_id), None)
    parts = pending_parts(order, item_id) if order else []
    if not parts:
        st.success('Todas las piezas ya tienen trabajo asignado.', icon=':material/check_circle:')
        return
    machines = snapshot['machines']
    scope = f"bulk_split_{order_id}_{item_id or 'all'}"
    version = st.session_state.setdefault(scope + '_version', 0)
    st.caption(f"{len(parts)} piezas · {sum(p['quantity_unassigned'] for p in parts)} unidades sin asignar. "
               'Escribe cuántas unidades van a cada máquina. Las piezas del mismo material aparecen juntas.')
    with st.container(horizontal=True, vertical_alignment='center'):
        if st.button('Distribuir automáticamente', icon=':material/grid_view:', key=scope + '_auto',
                     help='Cada pieza completa va a la máquina disponible con menos carga; si no hay, queda sin máquina. Puedes ajustar las cantidades después.'):
            st.session_state[scope + '_amounts'] = _auto(parts, machines)
            st.session_state[scope + '_version'] = version = version + 1
        if st.button('Vaciar', icon=':material/backspace:', key=scope + '_clear', type='tertiary'):
            st.session_state[scope + '_amounts'] = {}
            st.session_state[scope + '_version'] = version = version + 1
        st.caption(' · '.join(f"{m['code']} {m['status'].lower()}" for m in machines))
    columns = _columns(machines)
    config = {c: st.column_config.NumberColumn(c, min_value=0, step=1, format='%d') for c in columns}
    config.update({c: st.column_config.TextColumn(c, disabled=True) for c in ('Pieza', 'Producto', 'Material')})
    config['Sin asignar'] = st.column_config.NumberColumn('Sin asignar', disabled=True, format='%d')
    edited = st.data_editor(_frame(parts, machines, st.session_state.get(scope + '_amounts')), column_config=config,
                            hide_index=True, width='stretch', key=f'{scope}_grid_{version}', num_rows='fixed')
    allocations, errors = [], []
    by_code = {m['code']: m['id'] for m in machines}
    for part, (_, row) in zip(parts, edited.iterrows()):
        total = 0
        for column in columns:
            quantity = 0 if pd.isna(row[column]) else int(row[column])
            if quantity:
                total += quantity
                allocations.append(dict(part_id=part['id'], machine_id=by_code.get(column), quantity=quantity))
        if total > part['quantity_unassigned']:
            errors.append(f"{part['name']} ({part['item_name']}): sobran {total - part['quantity_unassigned']}")
    assigned = sum(a['quantity'] for a in allocations)
    pending = sum(p['quantity_unassigned'] for p in parts) - assigned
    if errors:
        st.error('Reduce el reparto antes de guardar · ' + ' · '.join(errors))
    else:
        st.caption(f"{assigned} unidades en {len(allocations)} trabajos · {pending} quedan sin asignar")
    st.caption('Los trabajos se crean en cola con la prioridad del pedido. Una máquina ocupada puede recibir trabajos para después.')
    if st.button(f'Crear {len(allocations)} trabajos', type='primary', width='stretch', key=scope + '_save',
                 disabled=not allocations or bool(errors)):
        st.session_state.pop(scope + '_amounts', None)
        perform(service.create_order_jobs, order_id, allocations,
                message=f'{len(allocations)} trabajos creados. Ya puedes iniciarlos desde la cola o las máquinas.')
