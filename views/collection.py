"""General inventory: every piece and supply that is not Colección Origen, its purchases, reservations and movements.

Colección Origen keeps its own inventory (pieces, bases by color and supplies) on its page; the ledger is the same.
"""
import streamlit as st
from services.inventory import load_inventory
from services.inventory_view import present
from views.collection_forms import manual_entry_form, found_stock_form
from views.inventory_ui import (overview_help,empty_inventory,stock_panel,reservations_panel,clients_panel,history_panel,reset_filters,
                                incoming_panel,incoming_rows,balance_row,is_origin,take_focus,open_origin_inventory,ORIGIN_PANELS)
from views.inbound_ui import panel as inbound_panel
from views.consumables_ui import orders_panel as consumable_orders_panel
from views.supplies_ui import panel as supplies_panel
from services.inbound import list_orders as inbound_orders
from services.consumables import list_orders as consumable_orders
from services.order_status import FLOW,OPEN,COLORS

data=load_inventory()
if pending_id:=st.session_state.pop('inventory_inbound_focus',None):
    st.session_state['collection_workspace']='Compras'
    st.session_state['inbound_panel_focus']=pending_id
previous_tab=st.session_state.get('collection_workspace')
# Panels that moved to Colección Origen open there; older names of this page's tabs map to today's.
if previous_tab in ORIGIN_PANELS:
    st.session_state['collection_workspace']='Existencias'
    open_origin_inventory(ORIGIN_PANELS[previous_tab])
old_tabs={'Inventario':'Existencias','Reservas por pedido':'Reservas y clientes','Reservas':'Reservas y clientes','Asignaciones B2B':'Reservas y clientes',
          'Clientes B2B':'Reservas y clientes','Pedidos':'Compras','Filamento y consumibles':'Insumos y consumibles'}
if previous_tab in old_tabs: st.session_state['collection_workspace']=old_tabs[previous_tab]
if focus:=take_focus(data,origin=False):
    sku,workspace=focus
    if workspace=='Insumos y consumibles' and sku.get('component_id'):
        st.session_state['restock_focus_component']=sku['component_id']
        st.session_state['collection_workspace']='Insumos y consumibles'
    else:
        reset_filters()
        st.session_state['inventory_selected']=sku['id']
        st.session_state['collection_workspace']=workspace if workspace and workspace not in ORIGIN_PANELS else 'Existencias'
rows=[r for r in present(data['skus']) if not is_origin(r)]
incoming=incoming_rows(st.session_state['snapshot'],origin=False)
from views.shell import actions
from views.common import remembered
from views.emoji import tag
with actions():
    if st.button('💡 Inventario Origen',key='inventory_open_origin',type='tertiary'):open_origin_inventory()
    if st.button('Entrada o pedido',key='inventory_receive',icon=':material/add:',
                 help='Una referencia nueva, filamento y consumibles, o un pedido a proveedor.'): manual_entry_form()
    if st.button('📦 Stock encontrado',key='inventory_found',type='primary',help='Anota varias piezas que encontraste en los estantes, de una vez.'):
        found_stock_form()
balance_row(rows,incoming)
with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
    st.caption(f'{len(rows)} referencias · En taller = Disponibles + Reservadas · Cantidades en piezas')
    overview_help()
SECTIONS={'Existencias':'📦','Insumos y consumibles':'🧵','Compras':'🚚','Reservas y clientes':'🔖','Movimientos':'🧾'}
if st.session_state.get('collection_workspace') not in (None,*SECTIONS):st.session_state['collection_workspace']='Existencias'
section=st.segmented_control('Sección del inventario',list(SECTIONS),default=remembered('collection_workspace','Existencias'),key='collection_workspace',
                             persist_state='session',label_visibility='collapsed',width='stretch',format_func=lambda s:f"{SECTIONS[s]} {s}") or 'Existencias'
if section=='Existencias':
    if rows:stock_panel(rows)
    else:empty_inventory()
    incoming_panel(st.session_state['snapshot'],origin=False)
elif section=='Reservas y clientes':
    reservations_panel(data,st.session_state['snapshot'])
    st.divider()
    clients_panel(data)
elif section=='Movimientos':history_panel(data)
elif section=='Insumos y consumibles':supplies_panel()
else:
    st.subheader('Compras de piezas, insumos y filamento',icon=':material/local_shipping:')
    st.caption('Lo que pediste a proveedores y todavía no llega, de todas las líneas. Al recibirlo entra a su inventario.')
    # Every purchase follows the same status flow, whatever is bought.
    orders=[*inbound_orders(),*consumable_orders()]
    with st.container(horizontal=True,gap='small'):
        for state in FLOW:
            total=sum(o['status']==state for o in orders)
            if total or state in OPEN:st.badge(f'{state} · {total}',color=COLORS[state] if total else 'gray')
        late=sum(o['overdue'] for o in orders)
        if late:st.badge(f'{late} con llegada vencida',color='red',icon=':material/schedule:')
    # Other screens preselect the kind through session state, so the default applies only the first time.
    kind=st.segmented_control('Tipo de pedido',('Piezas e insumos','Filamento y consumibles'),default=remembered('orders_kind', 'Piezas e insumos'),
                              key='orders_kind',persist_state='session', format_func=tag) or 'Piezas e insumos'
    if kind=='Piezas e insumos':inbound_panel()
    else:consumable_orders_panel()
