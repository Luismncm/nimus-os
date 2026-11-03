"""A compact count sheet and contextual receipts for each base color."""
import streamlit as st
from services.base_inventory import load_counts, matrix, ROLES
from views.common import table
from views.collection_forms import manual_entry_form
from views.common import remembered

MEASURES = {'Disponibles': 'free', 'Físicas en taller': 'physical', 'Reservadas': 'reserved', 'En B2B': 'b2b'}


def panel(inventory):
    data = load_counts(inventory['skus'])
    st.subheader('Base, CAP y tapa por color', icon=':material/category:')
    st.caption('Cada pieza tiene su propio saldo. Se incluyen los colores registrados aunque todavía estén en cero.')
    if not data['rows']:
        st.info('Primero registra un color de base en Componentes → Base y colores. Sus tres componentes aparecerán aquí para contar e ingresar unidades.')
        return
    search = st.text_input('Buscar color o material', key='base_inventory_search', icon=':material/search:',
                           placeholder='Ej. beige, gris niebla o PLA', persist_state='session')
    rows = [r for r in data['rows'] if search.strip().casefold() in f"{r['color']} {r['material']}".casefold()]
    measure = st.segmented_control('Conteo', tuple(MEASURES), default=remembered('base_inventory_measure', 'Disponibles'),
                                    key='base_inventory_measure', persist_state='session', width='stretch') or 'Disponibles'
    field = MEASURES[measure]
    with st.container(horizontal=True):
        for role in ROLES:
            st.metric(f'{role} · {measure.lower()}', sum(r['pieces'][role][field] for r in rows), border=True)
        if field == 'free':
            st.metric('Juegos de base disponibles', sum(r['kits_available'] for r in rows), border=True)
    columns = dict(color='Color', material='Material', Base='Base', CAP='CAP', Tapa='Tapa')
    if field == 'free':
        columns['kits_available'] = 'Juegos libres'
    table(matrix(rows, field), columns, label=f'Conteo de base, CAP y tapa por color · {measure}')
    st.caption(f"{len(rows)}/{len(data['rows'])} colores y materiales · " +
               {'free':'Disponibles = físicas en taller menos reservas. Un juego requiere 1 base, 1 CAP y 1 tapa del mismo color y material; no confirma ensamble.',
                'physical':'Unidades en Colección y Stock, incluidas las reservadas. Las asignadas a B2B se consultan por separado.',
                'reserved':'Unidades físicas apartadas para pedidos activos. No se suman de nuevo al inventario.',
                'b2b':'Unidades asignadas a clientes B2B; no forman parte de las disponibles en el taller.'}[field])
    if not rows:
        st.info('No hay colores para esta búsqueda. Cambia el color o material.')
        return
    with st.container(border=True):
        st.markdown('**Ingresar piezas de un color**')
        lookup = {r['id']: r for r in rows}
        if st.session_state.get('base_inventory_color') not in lookup:
            st.session_state['base_inventory_color'] = next(iter(lookup))
        a, b = st.columns([2, 1])
        key = a.selectbox('Color y material', list(lookup), format_func=lambda k: f"{lookup[k]['color']} · {lookup[k]['material']}",
                           key='base_inventory_color', persist_state='session')
        group = lookup[key]
        roles = [role for role in ROLES if group['pieces'][role]['ids']]
        if st.session_state.get('base_inventory_role') not in roles:
            st.session_state['base_inventory_role'] = roles[0]
        role = b.segmented_control('Pieza', roles, key='base_inventory_role', persist_state='session') or roles[0]
        ids = group['pieces'][role]['ids']
        cid = ids[0]
        if len(ids) > 1:
            if st.session_state.get('base_inventory_component') not in ids:
                st.session_state['base_inventory_component'] = cid
            cid = st.selectbox('Referencia de la pieza', ids, key='base_inventory_component', persist_state='session',
                               format_func=lambda i: f"CMP-{i:04d} · {data['components'][i]['variant']}")
        counts = data['components'][cid]['counts']
        st.caption(f"{role} · {group['color']} · {counts['physical']} físicas · {counts['reserved']} reservadas · {counts['free']} disponibles")
        with st.container(horizontal=True, gap='small'):
            if st.button('Agregar unidades', key='base_inventory_receive', type='primary', icon=':material/add:'):
                manual_entry_form(component_id=cid, return_workspace='Bases por color')
            if st.button('Pedir unidades', key='base_inventory_order', icon=':material/local_shipping:'):
                manual_entry_form(component_id=cid, entry_type='Pedido', return_workspace='Bases por color')
