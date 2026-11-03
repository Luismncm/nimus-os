import streamlit as st

from services.inventory import PRINT_PROCESSES
from services.quick_print import fingerprint, finish_printing
from views.common import perform


def print_check(item, parts, order, *, part_id=None):
    completed = all(p['quantity_remaining'] == 0 for p in parts)
    blocked = order['blocked_manually'] or any(j['status'] == 'Bloqueado' for p in parts for j in p['jobs'])
    label = f"{parts[0]['name']} · impreso" if part_id else f"{item['name']} · impresión completa"
    token = fingerprint(parts)
    checked = st.checkbox(label, value=completed, key=f'print_{item["id"]}_{part_id}_{token}',
        disabled=completed or blocked or order['status'] == 'Entregado')
    if checked and not completed:
        perform(finish_printing, item['id'], part_id=part_id, expected_fingerprint=token,
                message='Impresión registrada. Cantidades e inventario actualizados.')


def quick_print_panel(order):
    groups = [(i, [p for p in i['parts'] if p['process'] in PRINT_PROCESSES]) for i in order['items']]
    groups = [(i, parts) for i, parts in groups if parts]
    if not groups:
        return
    with st.container(border=True):
        st.subheader('Impresión rápida', icon=':material/print:')
        st.caption('Marca únicamente lo que ya está impreso: completa las unidades pendientes y actualiza el inventario correspondiente. Revisión y empacado se marcan por separado.')
        pending_only = st.toggle('Solo impresión pendiente', value=True, key=f'print_pending_{order["id"]}')
        visible = [(i, parts) for i, parts in groups if not pending_only or any(p['quantity_remaining'] for p in parts)]
        if not visible:
            st.success('Toda la impresión está registrada.', icon=':material/check_circle:')
        for item, parts in visible:
            with st.container(horizontal=True, vertical_alignment='center'):
                print_check(item, parts, order)
                pending = sum(p['quantity_remaining'] for p in parts)
                st.badge(f'{pending} unidades pendientes', color='orange' if pending else 'green')
            with st.expander('Marcar por pieza · ' + item['name'], key=f'print_parts_{item["id"]}', on_change='rerun'):
                for part in parts:
                    if pending_only and not part['quantity_remaining']:
                        continue
                    print_check(item, [part], order, part_id=part['id'])
                    st.caption(f"{part['quantity_completed']}/{part['quantity_required']} · {part['material'] or 'Sin material'} · {part['process']}")
        if order['blocked_manually'] or any(j['status'] == 'Bloqueado' for _, parts in groups for p in parts for j in p['jobs']):
            st.caption('Los checks con bloqueos quedan deshabilitados hasta revisar y liberar sus trabajos.')
