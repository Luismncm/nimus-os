"""One row per supply need or incoming order, with the action that resolves it."""
import streamlit as st

ICONS = {'Insumo': 'electrical_services', 'Consumible': 'science', 'Pedido de piezas': 'local_shipping', 'Pedido de consumibles': 'local_shipping'}


def act(row):
    from views.collection_forms import manual_entry_form
    if row['kind'] == 'Insumo':
        manual_entry_form(component_id=row['record_id'], entry_type='Pedido', default_quantity=max(1, int(row['quantity'])))
    elif row['kind'] == 'Consumible':
        manual_entry_form(kind='Filamento y consumibles', consumable_id=row['record_id'], entry_type='Pedido')
    elif row['kind'] == 'Pedido de piezas':
        from services import inbound
        from views.inbound_ui import receive_form
        receive_form(inbound.get(row['record_id']))
    else:
        from services import consumables
        from views.consumables_ui import consumable_receive_order_form
        consumable_receive_order_form(next(o for o in consumables.list_orders() if o['id'] == row['record_id']))


def open_inventory(row):
    if row['kind'] == 'Insumo':
        # Supplies are Colección Origen components: they are replenished from its inventory.
        from views.restock_ui import open_restock
        open_restock(row['record_id'])
    workspace = {'Consumible': 'Filamento y consumibles'}.get(row['kind'], 'Compras')
    st.session_state['collection_workspace'] = workspace
    if row['kind'] == 'Pedido de consumibles':st.session_state['orders_kind'] = 'Filamento y consumibles'
    elif row['kind'] == 'Pedido de piezas':
        st.session_state.update(orders_kind='Piezas e insumos', inbound_panel_focus=row['record_id'])
    elif row['kind'] == 'Consumible':st.session_state['consumables_selected'] = row['record_id']
    else:st.session_state['restock_focus_component'] = row['record_id']
    st.switch_page('views/collection.py')


def supply_row(row, key, *, compact=False):
    with st.container(border=True, gap='xxsmall'):
        info, actions = st.columns([3, 1.3], vertical_alignment='center')
        with info:
            st.markdown(f":material/{ICONS[row['kind']]}: **{row['title']}**")
            with st.container(horizontal=True, gap='xxsmall'):
                st.badge(row['kind'], color='gray')
                st.badge(row['state'], color=row['color'])
                if row.get('covered'):st.badge('Cubierto por pedido abierto', color='green', icon=':material/check:')
            if not compact:st.caption(row['detail'])
        with actions, st.container(horizontal=True, horizontal_alignment='right', gap='xsmall'):
            if row['action'] and st.button(row['action'], key=f"{key}_{row['identity']}", type='primary' if row['color'] == 'red' else 'secondary',
                                           icon=':material/local_shipping:' if row['action'] == 'Pedir' else ':material/inventory_2:'):
                act(row)
            if st.button('Abrir', key=f"{key}_open_{row['identity']}", type='tertiary', icon=':material/open_in_new:'):open_inventory(row)
