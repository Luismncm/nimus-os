"""Assignment panel: pick a piece, see every printer ranked for it, and queue the print in one place.

Left, the pieces with units to assign (most urgent first, same material together). Right, the piece
picked: its inventory, units and extra for stock, duration, the printers ranked by loaded filament and
first free slot, and the schedule. Creating a job keeps the panel on the same piece while units remain,
so splitting a piece between printers is just creating a second job.
"""
import streamlit as st
from models.constants import PRIORITY_RANK
from services import capture, production as service
from services.inventory import PRINT_PROCESSES
from views.common import perform
from views.piece_stock_ui import stock_notice
from views.print_setup import _pick, print_setup, quantity_row, save_label


def pending_pieces(snapshot, order_id=None):
    """Pieces of open orders with units to assign: urgent orders first, then by material."""
    orders = {o['id']: o for o in snapshot['orders']}
    rows = [p for p in snapshot['parts'] if p['quantity_unassigned'] > 0 and p['order_status'] != 'Entregado'
            and not p.get('commercial_cancelled') and order_id in (None, p['order_id'])]
    return sorted(rows, key=lambda p: (PRIORITY_RANK[orders[p['order_id']]['priority']], orders[p['order_id']]['deadline'] or '9999-12-31',
                                       (p['material'] or '').casefold(), p['id']))


def _version(key):
    return st.session_state.get(key + '_version', 0)


def _bump(key):
    st.session_state[key + '_version'] = _version(key) + 1


def single_print(snapshot, part, key, *, keep_open=False):
    """Everything to queue one print of this piece on one printer: the shared print setup."""
    order = next(o for o in snapshot['orders'] if o['id'] == part['order_id'])
    # A new version after each job resets the fields for the units still pending.
    base, key = key, f"{key}_{part['id']}_v{_version(key)}"
    stock_notice(part, key + '_stock')
    units, extra = quantity_row(key + '_units', key + '_extra', value=part['quantity_unassigned'], top=part['quantity_unassigned'],
                                process=part['process'], extra=not order.get('development'))
    setup = print_setup(snapshot, part['material'], key, process=part['process'], label=f"{part['name']} ×{units}")
    code = next((m['code'] for m in snapshot['machines'] if m['id'] == setup['machine_id']), 'sin máquina')
    if st.button(save_label('Crear trabajo', units, extra, setup['machine_id'], setup['planned_start'], snapshot),
                 type='primary', width='stretch', key=key + '_save', icon=':material/add_task:',
                 disabled=part['process'] in PRINT_PROCESSES and not setup['estimated_grams']):
        rest = part['quantity_unassigned'] - units
        perform(service.create_jobs, part['id'], [dict(quantity=units, machine_id=setup['machine_id'], extra=extra)], notes=setup['notes'],
                plan=capture.plan_for(part['material'], setup['planned_start'], setup['duration_minutes'], setup['estimated_grams'], setup['machine_rate'], setup['material_rate']),
                keep_open=keep_open, after=lambda _: _bump(base),
                message=f"{part['name']} ×{units} en la cola de {code}." + (f" Quedan {rest} por asignar." if rest else ''))


def piece_list(snapshot, parts, key, *, labels=None):
    """Selectable pieces; returns the one picked."""
    state = key + '_piece'
    ids = [p['id'] for p in parts]
    if st.session_state.get(state) not in ids:
        st.session_state[state] = ids[0]
    orders = {o['id']: o for o in snapshot['orders']}
    shown = parts[:40]
    if st.session_state[state] not in [p['id'] for p in shown]:
        shown = [next(p for p in parts if p['id'] == st.session_state[state]), *shown[:39]]
    for p in shown:
        picked = p['id'] == st.session_state[state]
        o = orders[p['order_id']]
        with st.container(border=True, gap='xxsmall', key=f"pick-{'on' if picked else 'off'}-{key}-piece-{p['id']}"):
            a, b = st.columns([3, 1.2], vertical_alignment='center')
            with a:
                st.markdown(f"**{p['name']}** ×{p['quantity_unassigned']}" + (' :orange-badge[Alta]' if o['priority'] == 'Alta' else '')
                            + (f" :blue-badge[{p['stock_free']} en inventario]" if p.get('stock_free') else '')
                            + (f" :blue-badge[{p['stock_incoming']} en camino]" if p.get('stock_incoming') else ''))
                # In the queue the same piece name repeats across products and orders: say which one.
                where = labels[o['id']]['label'] if labels else ''
                st.caption(' · '.join(x for x in (p['item_name'], p['material'] or 'Sin material', where,
                                                  f"entrega {o['deadline'][8:10]}/{o['deadline'][5:7]}" if o['deadline'] else '') if x))
            b.button('Elegida' if picked else 'Elegir', key=f"{key}_piece_{p['id']}", type='primary' if picked else 'secondary',
                     width='stretch', on_click=_pick, args=(state, p['id']))
    if len(parts) > len(shown):
        st.caption(f'Y {len(parts) - len(shown)} piezas más. Filtra por material o pedido.')
    return next(p for p in parts if p['id'] == st.session_state[state])


def assign_panel(snapshot, key, *, parts=None, order_id=None, labels=None):
    """Full-width panel: pending pieces on the left, the picked piece's print on the right."""
    parts = pending_pieces(snapshot, order_id) if parts is None else parts
    if not parts:
        st.success('Todas las piezas tienen impresión asignada. Revisa la cola para iniciarlas.', icon=':material/check_circle:')
        return
    materials = sorted({p['material'] or 'Sin material' for p in parts}, key=str.casefold)
    with st.container(horizontal=True, vertical_alignment='center', gap='small'):
        st.markdown(f"**Por asignar · {len(parts)} piezas · {sum(p['quantity_unassigned'] for p in parts)} unidades**")
        material = st.pills('Material', materials, key=key + '_material', label_visibility='collapsed') if len(materials) > 1 else None
        if order_id is not None and len(parts) > 1 and st.button('Repartir todo en tabla', key=key + '_bulk', icon=':material/table_view:', type='tertiary',
                                                                 help='Todas las piezas a la vez, con reparto automático por carga y filamento.'):
            from views.assign_forms import bulk_split_form
            bulk_split_form(order_id)
    if material:
        parts = [p for p in parts if (p['material'] or 'Sin material') == material]
    left, right = st.columns([2, 3], gap='medium')
    # A long list scrolls on its own, so the picked piece's form stays beside it.
    with left, st.container(height=720 if len(parts) > 6 else 'content', border=False):
        part = piece_list(snapshot, parts, key, labels=labels)
    with right, st.container(border=True, key=f'panel-{key}'):
        o = next(o for o in snapshot['orders'] if o['id'] == part['order_id'])
        st.markdown(f"#### {part['name']} ×{part['quantity_unassigned']}")
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center', gap='small'):
            st.caption(' · '.join((f"{o['code']} · {o['project']}", part['item_name'], part['process'], part['material'] or 'Sin material')))
            # Several printers at once, with the suggested split: the same place, one more step.
            if part['quantity_unassigned'] > 1 and st.button('Repartir en varias', key=f"{key}_split_{part['id']}", icon=':material/call_split:', type='tertiary',
                                                             help='Reparte las unidades de esta pieza entre varias impresoras en una sola ventana.'):
                from views.common import split_form
                st.session_state[f"split_mode_{part['id']}"] = 'Repartir en varias'
                split_form(part)
        single_print(snapshot, part, key)
