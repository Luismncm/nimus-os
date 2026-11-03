"""Purchased requirements are inventory tasks, separate from production work."""
import streamlit as st
from services.origin import reserve_supplies
from views.common import table, perform


def supplies_panel(order, readonly):
    st.subheader('Insumos del pedido', icon=':material/electrical_services:')
    st.caption('Cables, focos y otros componentes comprados se reciben y reservan desde inventario. No cuentan como piezas por fabricar.')
    s = order['supplies']
    a, b, c = st.columns(3)
    a.metric('Necesarios', s['required'], border=True)
    b.metric('Cubiertos' if readonly else 'Reservados', s['covered'], border=True)
    c.metric('Por reservar', s['remaining'], border=True)
    rows = [dict(r, product=i['name'], pending=r['quantity']-r['covered'])
            for i in order['items'] for r in i['requirements'] if r['supply'] == 'Comprar']
    table(rows, {'product':'Producto', 'name':'Insumo', 'variant':'Variante', 'quantity':'Necesarios',
                 'covered':'Cubiertos', 'pending':'Por reservar'}, label='Insumos comprados del pedido')
    with st.container(horizontal=True, gap='small'):
        if not readonly and s['remaining'] and st.button('Reservar insumos disponibles', key=f"order_supplies_{order['id']}",
                type='primary', icon=':material/bookmark_add:'):
            perform(reserve_supplies, order['id'], message='Reserva revisada. Los insumos con existencias disponibles se asignaron al pedido.')
        st.page_link('views/collection.py', label='Abrir inventario y compras pendientes', icon=':material/warehouse:')
    if s['remaining']:
        st.caption('Recibe las compras cuando lleguen y después reserva sus unidades aquí. La fabricación puede estar al 100% y mantener insumos pendientes; la entrega sigue bloqueada hasta cubrirlos.')
    else:
        st.badge('Insumos cubiertos', color='green', icon=':material/check_circle:')
        st.caption('Continúa con el ensamble, la revisión y la preparación de salida.')
