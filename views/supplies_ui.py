"""Insumos y consumibles: one table, one search and one detail panel for everything bought and watched.

Insumos (cable, foco, empaque) and consumibles (filamento, resina, pintura…) are different ledgers
underneath — see services/supplies.py — but here they are one list: look for a name, see its
balance, its minimum and whether it is on order, then manage it with the same actions as before.
"""
import streamlit as st
from services import supplies
from views.common import table, picks
from views.consumables_ui import item_panel as consumable_item_panel, consumable_item_form
from views.restock_ui import item_panel as restock_item_panel, minimum_editor


def _open_orders_count():
    from services import consumables, inbound
    open_states = ('Solicitado', 'Confirmado', 'En camino', 'Recibido parcial')
    insumos = sum(o['status'] in open_states for o in inbound.list_orders() if o['component_id'])
    return insumos + sum(o['status'] in open_states for o in consumables.list_orders())


def panel():
    snapshot = st.session_state['snapshot']
    rows = supplies.rows(snapshot['jobs'])
    with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        st.caption('Filamento, resina, pintura y tornillería, junto con el cable, foco y empaque que se compran por pieza: '
                   'todo lo que vigilas para que no falte, en un solo lugar.')
        if st.button('Nuevo consumible', key='supplies_new_consumable', icon=':material/add:', type='primary'):
            consumable_item_form()
    from services import consumables as _consumables
    missing = _consumables.unregistered(snapshot['jobs'])
    if missing:
        with st.container(border=True, gap='xsmall'):
            st.markdown(f":orange[**{len(missing)} filamentos de la cola sin registrar**] :gray[· regístralos para saber si alcanzan]")
            with st.container(horizontal=True, gap='small'):
                for name in missing[:6]:
                    if st.button(name, key='supplies_register_' + _consumables.identity(name), icon=':material/add:', type='tertiary'):
                        consumable_item_form(name=name)
    if not rows:
        st.info('Aún no hay consumibles ni insumos registrados. Un consumible se registra aquí; un insumo se define en '
                'Catálogo y recetas → Componentes → Insumos.', icon=':material/inventory_2:')
        return
    attention = [r for r in rows if r['attention']]
    a, b, c = st.columns(3)
    a.metric('Consumibles e insumos', len(rows), border=True)
    b.metric('Requieren atención', len(attention), border=True, help='Sin existencias, bajo mínimo, en negativo o sin cubrir la cola.')
    c.metric('Pedidos abiertos', _open_orders_count(), border=True)
    left, right = st.columns([1, 1])
    kind = left.segmented_control('Tipo', ('Todos', 'Consumible', 'Insumo'), default='Todos', key='supplies_kind', persist_state='session') or 'Todos'
    search = right.text_input('Buscar insumo o consumible', key='supplies_search', placeholder='Nombre, variante o categoría', icon=':material/search:')
    shown = [r for r in rows if (kind == 'Todos' or r['kind'] == kind)
             and search.strip().casefold() in f"{r['name']} {r['variant']} {r['category']}".casefold()]
    shown.sort(key=lambda r: (not r['attention'], r['kind'], r['category'], r['name']))
    if not shown:
        st.info('No hay resultados para esta búsqueda.')
        return
    table([dict(r, shown_state=f"{r['kind']} · {r['state']}") for r in shown],
          {'shown_state': 'Tipo y estado', 'name': 'Nombre', 'variant': 'Variante', 'category': 'Categoría',
           'balance_text': 'Disponible', 'committed_text': 'Comprometido', 'minimum_text': 'Mínimo', 'on_order_text': 'En pedido'},
          label='Consumibles e insumos: disponible, comprometido, mínimo y en pedido',
          open=picks('supplies_selected', 'supply_id'), key='supplies_table')
    lookup = {r['supply_id']: r for r in shown}
    focus_insumo = st.session_state.get('restock_focus_component')
    if focus_insumo is not None and f"r{focus_insumo}" in lookup:
        st.session_state['supplies_selected'] = f"r{focus_insumo}";st.session_state.pop('restock_focus_component', None)
    if st.session_state.get('supplies_selected') not in lookup:
        st.session_state['supplies_selected'] = next(iter(lookup))
    selected = st.selectbox('Para gestionar', list(lookup), key='supplies_selected',
                            format_func=lambda i: f"{lookup[i]['name']} · {lookup[i]['variant'] or lookup[i]['category']} · {lookup[i]['kind']}")
    row = lookup[selected]
    if row['kind'] == 'Consumible':
        st.session_state['consumables_selected'] = row['id']
        consumable_item_panel(row)
    else:
        st.session_state['restock_selected'] = row['id']
        restock_item_panel(row)
    consumibles = [r for r in rows if r['kind'] == 'Consumible']
    if consumibles:
        with st.expander('Desglose de consumibles: equivale a, valor y costo', icon=':material/table_chart:'):
            from services import consumables as _c
            from services.quotations import money
            def q(value, r):return _c.quantity_text(value, r['unit'])
            full = {r['id']: r for r in _c.items(snapshot['jobs'])}
            detail = [full[r['id']] for r in consumibles if r['id'] in full]
            table([dict(r, balance_text=q(r['balance'], r), committed_text=q(r['committed'], r) if r['committed'] else '—',
                        free_text=q(r['free_after'], r) if r['committed'] else '—', minimum_text=q(r['minimum'], r) if r['minimum'] else '—',
                        order_text=q(r['on_order'], r) if r['on_order'] else '—', packages_text=f"{r['packages']:g} {r['package_label'].lower()}(s)",
                        cost=_c.cost_text(r) if r['package_cost_cents'] is not None else '—',
                        value=money(r['stock_value_cents']) if r['stock_value_cents'] is not None else '—') for r in detail],
                  {'name': 'Consumible', 'category': 'Categoría', 'balance_text': 'Disponible', 'packages_text': 'Equivale a',
                   'committed_text': 'Previsto en cola', 'free_text': 'Libre después', 'minimum_text': 'Mínimo', 'order_text': 'En pedido',
                   'state': 'Estado', 'cost': 'Costo', 'value': 'Valor en existencia'},
                  label='Consumibles por unidad: disponible, previsto, mínimo y en pedido')
    insumos = [r for r in rows if r['kind'] == 'Insumo']
    if insumos:
        with st.expander('Mínimos de insumos por lote', icon=':material/table_chart:'):
            minimum_editor(insumos)
        with st.expander('Desglose de insumos: físico, reservado y sin cubrir', icon=':material/table_chart:'):
            from views.emoji import tag
            mode = st.segmented_control('Ver insumos', ('Todos', 'Por reponer', 'En negativo'), default='Todos',
                                        key='supplies_restock_filter', persist_state='session', format_func=tag) or 'Todos'
            detail = [r for r in insumos if mode == 'Todos' or mode == 'Por reponer' and r['attention'] or mode == 'En negativo' and r['critical']]
            table(detail, {'code': 'Referencia', 'name': 'Insumo', 'variant': 'Especificación', 'physical': 'Físico',
                           'reserved': 'Reservado', 'pending': 'Sin cubrir', 'net': 'Disponible neto', 'minimum': 'Mínimo',
                           'on_order': 'En pedido', 'replenish': 'Reposición sugerida', 'state': 'Atención'},
                  label='Mínimos, faltantes y saldo neto de insumos')
