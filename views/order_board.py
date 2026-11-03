"""Native, responsive order board and a shared trace panel."""
import streamlit as st
from services import order_board as board, operations
from utils.dates import fmt
from views.common import table, ORDER_COLUMNS
from views.components import order_card
from views.navigation import open_order
from services.order_progress import display_status, fabrication_label
from views.common import remembered
from views.emoji import tag


def reset_filters():
    st.session_state.update(orders_scope='Activos', orders_search='', orders_priority='Todas', orders_type='Todos',
                            orders_attention='Todos', orders_lane='Todas', orders_sort='Atención primero')


def cards(rows, bucket):
    # Bounded rendering; filters reset the slice so no matching card disappears.
    signature = tuple(o['id'] for o in rows)
    state_key = f'orders_slice_{bucket}'
    old = st.session_state.get(state_key, {})
    limit = old.get('limit', 6) if old.get('signature') == signature else 6
    for row in rows[:limit]:
        order_card(row, 'orders_open', controls=True)
    if len(rows) > limit and st.button(f'Ver 6 más · {len(rows)-limit} restantes', key=f'orders_more_{bucket}', width='stretch'):
        st.session_state[state_key] = dict(signature=signature, limit=limit+6)
        st.rerun()
    if not rows: st.caption('Sin pedidos en esta etapa.')


FOCUS_ICONS = {'Todos': 'select_all', 'Atrasados': 'schedule', 'Entrega hoy': 'today', 'Bloqueados': 'block',
               'Insumos pendientes': 'inventory', 'Listos para salida': 'local_shipping', 'Sin fecha': 'event_busy'}
VIEW_ICONS = {'Tablero': 'view_kanban', 'Tarjetas': 'view_module', 'Lista': 'view_list', 'Tabla': 'table_rows'}


def render_board(orders):
    with st.container(border=True, key='panel-orders-filters', gap='small'):
        # One toolbar: search first, then what to show, then the rest of the filters in a menu.
        with st.container(horizontal=True, vertical_alignment='bottom', gap='small'):
            search = st.text_input('Buscar pedido', placeholder='Código, cliente, proyecto, producto o etiqueta',
                                   key='orders_search', icon=':material/search:', persist_state='session', label_visibility='collapsed')
            scope = st.segmented_control('Mostrar', ('Activos', 'Entregados', 'Cancelados', 'Todos'), default=remembered('orders_scope', 'Activos'),
                                         key='orders_scope', persist_state='session', width='content', label_visibility='collapsed', format_func=tag) or 'Activos'
            # Prototypes are followed here too, in their violet; this narrows the board to one kind.
            kind = st.segmented_control('Tipo', board.KINDS, default=remembered('orders_type', 'Todos'), key='orders_type',
                                        persist_state='session', width='content', label_visibility='collapsed',
                                        format_func=lambda k: {'Todos': 'Todo', 'Pedidos': ':material/inventory_2: Pedidos', 'Prototipos': ':material/science: Prototipos'}[k]) or 'Todos'
            with st.popover('Filtros', icon=':material/tune:', width='content'):
                priority = st.selectbox('Prioridad', ('Todas', 'Alta', 'Media', 'Baja'), key='orders_priority', persist_state='session')
                lane = st.selectbox('Etapa', ('Todas', *board.LANES, 'Entregados'), key='orders_lane', persist_state='session')
                sort = st.selectbox('Ordenar por', ('Atención primero', 'Fecha de entrega', 'Prioridad', 'Más recientes'), key='orders_sort', persist_state='session')
        if st.session_state.get('orders_attention') not in (None, *board.FOCUS): st.session_state['orders_attention'] = 'Todos'
        base = board.query(orders, scope=scope, search=search, priority=priority, lane=lane, sort=sort, kind=kind)
        counts = {f: len(board.query(base, attention=f, scope='Todos', kind=kind)) if f != 'Todos' else len(base) for f in board.FOCUS}
        picked = st.session_state.get('orders_attention') or 'Todos'
        # Each count is also its filter; zero counts stay out of the way unless picked.
        options = [f for f in board.FOCUS if f == 'Todos' or counts[f] or f == picked]
        attention = st.pills('Enfoque', options, default=remembered('orders_attention', 'Todos'), key='orders_attention',
                             persist_state='session', label_visibility='collapsed',
                             format_func=lambda f: f":material/{FOCUS_ICONS[f]}: {f} · {counts[f]}") or 'Todos'
        active = [v for v in (priority, lane) if v not in ('Todas', 'Todos')] + ([attention] if attention != 'Todos' else [])
        if active or search:
            with st.container(horizontal=True, vertical_alignment='center', gap='small'):
                st.caption('Filtros activos: ' + ' · '.join(([search] if search else []) + active))
                st.button('Limpiar filtros', key='orders_clear', on_click=reset_filters, icon=':material/filter_alt_off:', type='tertiary')
    rows = board.query(base, attention=attention, scope='Todos', kind=kind, sort=sort) if attention != 'Todos' else base
    prototypes = sum(bool(r.get('development')) for r in rows)
    with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        view = st.segmented_control('Vista', ('Tablero', 'Tarjetas', 'Lista', 'Tabla'), default=remembered('orders_view', 'Tablero'), key='orders_view',
                                    persist_state='session', label_visibility='collapsed', format_func=lambda v: f":material/{VIEW_ICONS[v]}: {v}") or 'Tablero'
        with st.container(horizontal=True, horizontal_alignment='right', vertical_alignment='center', gap='small', width='content'):
            st.caption(f"{len(rows) - prototypes} pedidos" + (f" · {prototypes} prototipos" if prototypes else ''))
            with st.popover('Cómo avanza un pedido', icon=':material/route:', type='tertiary'):
                st.write('Planificar → Producir → Preparar → Salida → Entregados.')
                st.write('Los prototipos van en violeta: Planificar hasta que inicia su primera impresión y Producir desde entonces. Muévelos a Producir para lanzar o iniciar una impresión, a Entregados para terminar sus impresiones y cerrar el proyecto, y de vuelta para reabrirlo. No se preparan ni se entregan.')
                st.write('La barra de fabricación cuenta solo las piezas por producir. Los insumos comprados se muestran por separado. Al terminar la fabricación, el pedido pasa a Preparar para completar insumos, ensamblar y revisar. Para avanzar a Salida debe tener todos sus componentes y checks completos.')
                st.caption('En el Tablero, arrastra una tarjeta a otra etapa o usa Mover: verás la acción y sus requisitos antes de confirmarla. Usa Seguimiento para registrar checks y Abrir para trabajar piezas, revisar el historial o confirmar una entrega.')
    if not rows:
        st.info('No hay pedidos ni prototipos en esta consulta. Ajusta los filtros o crea un pedido con los botones superiores.')
        return
    if view == 'Tablero':
        from views.kanban import render
        render(rows)
    elif view == 'Tabla':
        table([dict(r, lane=r['tracking']['lane'], next=r['tracking']['action'], operational_status=display_status(r), fabrication_label=fabrication_label(r)) for r in rows],
              dict(ORDER_COLUMNS, lane='Etapa operativa', next='Siguiente paso'), label='Seguimiento de pedidos', progress_column='manufacturing_progress',
              open=lambda r: open_order(r['id']), key='orders_table')
        by_id = {r['id']: r for r in rows}
        oid = st.selectbox('Pedido para abrir', list(by_id), format_func=lambda i: f"{by_id[i]['code']} · {by_id[i]['project']}", key='orders_table_selected')
        if st.button('Abrir pedido', key='orders_table_open', icon=':material/arrow_forward:'): open_order(oid)
    elif view == 'Lista' or scope == 'Entregados':
        cards(rows, 'list')
    else:
        with st.container(horizontal=True, wrap=False, gap='small'):
            for label, (icon, color, subtitle) in board.LANES.items():
                with st.container(width=300):
                    selected = [r for r in rows if r['tracking']['lane'] == label]
                    with st.container(border=True, gap='xsmall'):
                        st.badge(f'{label} · {len(selected)}', icon=f':material/{icon}:', color=color)
                        st.caption(subtitle)
                    cards(selected, label)
        closed = [r for r in rows if r['tracking']['delivered']]
        if closed:
            with st.expander(f'Entregados · {len(closed)}', expanded=lane == 'Entregados'):
                cards(closed, 'closed')


def trace_panel(order):
    t = board.tracking(order)
    with st.container(border=True):
        with st.container(horizontal=True, horizontal_alignment='distribute'):
            st.subheader('Ruta del pedido', icon=':material/route:')
            st.badge(t['lane'], color='green' if t['lane'] in ('Salida', 'Entregados') else 'blue')
        st.text(f"Siguiente paso · {t['action']}")
        if t['blocked']: st.warning('Pedido bloqueado. Revisa el pedido y sus trabajos antes de continuar.')
        st.caption('Planificar → Producir → Preparar → Salida → Entregados')
        if t['complete'] and t['pending'] and not t['delivered']:
            st.caption('Por revisar: ' + ' · '.join(t['pending']))
        with st.expander('Hitos e historial del pedido', icon=':material/history:', key=f'order_trace_{order["id"]}', on_change='rerun') as history:
            if history.open:
                events = board.milestones(order, operations.history(order['id']))
                table([dict(e, date=fmt(e['at'], time=True)) for e in events], {'date':'Fecha registrada', 'event':'Hito', 'detail':'Detalle'}, label='Hitos registrados del pedido')
                st.caption('Creación, inicios y cierres de trabajos, hasta 100 cambios recientes de checks y etiquetas, y cierre del pedido. Las fechas corresponden a los registros del sistema.')
