"""Single capture of a print: first what it is for, then what is printed, then the shared print setup.

Pedido: a piece of a customer order (or a new piece of a custom one). Stock: straight to inventory
with no order at all, or a piece of a stock lot made from a recipe. Prototipo: a development project.
Time, filament, printer, start, rate and notes come from views.print_setup, the same block used to
assign a piece, so each datum is captured once and looks the same everywhere.
"""
import streamlit as st
from models.constants import PROCESSES
from services import capture, sales, stock_runs
from services.inventory import PRINT_PROCESSES
from services.queue_review import destinations
from services import piece_stock
from views.common import managed_dialog, perform
from views.piece_stock_ui import stock_notice
from views.print_setup import print_setup, quantity_row, save_label, section
from views.common import request_key as _key

PURPOSES = ('Pedido', 'Stock', 'Prototipo')
PURPOSE_HELP = {'Pedido': 'Para un pedido de cliente, con o sin venta.',
                'Stock': 'Para tener piezas listas en inventario y usarlas después en cualquier pedido.',
                'Prototipo': 'Usa máquina y filamento y tiene costo, pero no es venta ni entrega.'}
PURPOSE_ICONS = {'Pedido': ':material/inventory_2:', 'Stock': ':material/warehouse:', 'Prototipo': ':material/science:'}
STOCK_MODES = ('Directo a inventario', 'Lote de stock')
SOURCES = ('Pieza libre', 'Del catálogo')
NEW_PIECE = 'new'


def _free_piece(prefix):
    """Name, process and material of a piece typed here; returns (piece, process, material)."""
    from views.development_forms import materials
    a, b = st.columns([2, 1])
    piece = a.text_input('Pieza *', key=prefix + '_piece', placeholder='Base, bisagra, pantalla v3, probeta…')
    process = b.selectbox('Proceso', PROCESSES, index=PROCESSES.index('Impresión 3D'), key=prefix + '_process')
    material = st.selectbox('Material', materials(), index=None, accept_new_options=True, key=prefix + '_material', placeholder='Elige el filamento o escribe uno nuevo')
    return piece, process, material


def stock_direct(snapshot, prefix):
    """Stock with no order: a free piece (model optional) or a catalog piece, straight to inventory."""
    from views.properties import property_select
    with section('Qué se imprime', f'what-{prefix}', 'deployed_code'):
        source = st.segmented_control('Pieza', SOURCES, default=SOURCES[0], key=prefix + '_stock_source', label_visibility='collapsed') or SOURCES[0]
        component, models = None, {}
        if source == 'Del catálogo':
            catalog = {c['id']: c for c in stock_runs.components()}
            if not catalog:
                st.info('No hay piezas activas en el catálogo. Usa Pieza libre o crea la pieza en Catálogo y recetas.', icon=':material/info:')
                return
            component = st.selectbox('Pieza del catálogo', list(catalog), key=prefix + '_component', format_func=lambda i: ' · '.join(
                x for x in (catalog[i]['name'], catalog[i]['variant'], catalog[i]['material'] or 'Sin material', catalog[i]['process'],
                            f"{catalog[i]['free']} libres en inventario" if catalog[i]['free'] else '') if x))
            chosen = catalog[component]
            piece, material, process, product = chosen['name'], chosen['material'], chosen['process'], ''
            st.caption(':material/menu_book: Entra a la línea de inventario de esa pieza: los pedidos desde receta la reservan sin imprimirla.')
        else:
            piece, process, material = _free_piece(prefix)
            # A piece the catalog has by model (PANTALLA → CIRRUS, CUMULO, STRATO): the model is picked first and the print
            # takes that catalog piece, so the queue and the inventory say which model it is.
            models = {c['id']: c for c in stock_runs.components() if piece.strip() and c['name'].casefold() == piece.strip().casefold()}
            if models:
                component = st.pills('Modelo *', list(models), key=prefix + '_model_pick',
                                     format_func=lambda i: models[i]['variant'] or models[i]['material'] or f"CMP-{i:04d}")
                if component:
                    chosen = models[component]
                    piece, material, process, product = chosen['name'], chosen['material'], chosen['process'], ''
                    st.caption(f":material/menu_book: {chosen['name']} · {chosen['variant']} del catálogo · {chosen['material'] or 'Sin material'}"
                               + (f" · {chosen['free']} libres en inventario" if chosen['free'] else ''))
                else:
                    st.caption(':orange[Elige el modelo de esta pieza: así se ve en la cola y entra a su inventario.]')
                    product = ''
            else:
                product = property_select('Modelo o producto', 'product', key=prefix + '_product')
            found = piece_stock.free_like(piece, material or '', process)
            if found['stock_free']:
                st.caption(f":material/inventory_2: Ya hay {found['stock_free']} de esta pieza en inventario · "
                           + ' · '.join(f"{q} en {loc}" for loc, q in found['stock_detail'].items()))
        quantity, _ = quantity_row(prefix + '_qty_stock', prefix + '_extra', value=1, extra=False, label='Unidades para inventario')
        st.caption(':material/warehouse: Cada pieza buena entra a **Colección** en Inventario al registrarse. Al terminar, la impresión se cierra sola '
                   'y esas piezas quedan libres para cualquier pedido con la misma pieza y material.')
    with section('Cómo y dónde', f'how-{prefix}', 'print'):
        setup = print_setup(snapshot, material, prefix, process=process, label=f"{piece or 'Pieza'} ×{quantity}")
    if st.button(save_label('Imprimir para inventario', quantity, 0, setup['machine_id'], setup['planned_start'], snapshot),
                 type='primary', width='stretch', key=prefix + '_save', icon=':material/add_task:',
                 disabled=process in PRINT_PROCESSES and not setup['estimated_grams']):
        if models and not component:
            st.error('Elige el modelo de la pieza antes de agregarla a la cola.')
            return
        perform(stock_runs.launch, piece, quantity, product=product, component_id=component, material=material or '', process=process,
                request_key=_key(), **setup, message=f'Impresión para inventario agregada a la cola: {quantity} × {piece or "pieza"}.')


def order_print(snapshot, purpose, orders, labels, order_id, part_id, prefix):
    """A piece of a customer order, stock lot or prototype project: existing piece or a new one."""
    if purpose == 'Prototipo':
        options = {i: o for i, o in orders.items() if o.get('development') and o['development']['status'] == 'Activo'}
        empty = 'No hay proyectos de desarrollo activos. Crea uno para lanzar sus impresiones.'
    elif purpose == 'Stock':
        options = {i: o for i, o in orders.items() if o.get('fulfillment') == 'Stock'}
        empty = 'No hay lotes de stock abiertos. Los lotes se crean desde una receta con destino Stock; para imprimir sin pedido usa Directo a inventario.'
    else:
        options = {i: o for i, o in orders.items() if not o.get('development') and o.get('fulfillment') != 'Stock'}
        empty = 'No hay pedidos activos. Crea el pedido primero.'
    if not options:
        st.info(empty, icon=':material/info:')
        if purpose == 'Prototipo' and st.button('Nuevo proyecto', key=prefix + '_project', icon=':material/add:'):
            from views.development_forms import project_form
            project_form()
        return
    def order_label(i):
        """Prototipo: 'Proyecto · ORD'. Pedido: 'ORD · cliente · venta · proyecto'. Plus units still to assign."""
        o = options[i]
        unassigned = sum(p['quantity_unassigned'] for it in o['items'] for p in it['parts'])
        text = f"{o['project']} · {o['code']}" if purpose == 'Prototipo' else f"{labels[i]['label']} · {o['project']}"
        return text + (f" · {unassigned} por asignar" if unassigned else '')
    with section('Qué se imprime', f'what-{prefix}', 'deployed_code'):
        ids = list(options)
        a, b = st.columns(2)
        target = a.selectbox({'Prototipo': 'Proyecto', 'Stock': 'Lote de stock'}.get(purpose, 'Pedido'), ids,
                             index=ids.index(order_id) if order_id in ids else 0, key=prefix + '_order', format_func=order_label)
        order = options[target]
        pieces = {p['id']: p for it in order['items'] for p in it['parts'] if p['quantity_unassigned'] > 0}
        custom = order.get('fulfillment') == 'Personalizado'
        choices = [*pieces] + ([NEW_PIECE] if custom else [])
        if not choices:
            st.info('Todas sus piezas ya tienen trabajo y su despiece viene de una receta. Revisa la cola o crea otro pedido.', icon=':material/info:')
            return
        piece_id = b.selectbox('Pieza', choices, index=choices.index(part_id) if part_id in choices else 0, key=prefix + '_piece_choice',
                               format_func=lambda i: '+ Pieza nueva' if i == NEW_PIECE else f"{pieces[i]['name']} · {pieces[i]['material'] or 'Sin material'} · {pieces[i]['quantity_unassigned']} por asignar")
        if piece_id == NEW_PIECE:
            piece, process, material = _free_piece(prefix)
            if purpose != 'Prototipo':
                stock_notice(dict(piece_stock.free_like(piece, material or '', process), name=piece), prefix + '_stock_new', allow_take=False)
            quantity, extra = quantity_row(prefix + '_qty_new', prefix + '_extra', value=1, process=process, extra=purpose != 'Prototipo')
        else:
            part = pieces[piece_id]
            piece, process, material = part['name'], part['process'], part['material']
            if purpose != 'Prototipo':
                stock_notice(part, f'{prefix}_stock_{piece_id}')
            quantity, extra = quantity_row(f'{prefix}_qty_{piece_id}', prefix + '_extra', value=part['quantity_unassigned'], top=part['quantity_unassigned'],
                                           process=process, extra=purpose != 'Prototipo')
    with section('Cómo y dónde', f'how-{prefix}', 'print'):
        setup = print_setup(snapshot, material, prefix, process=process, label=f"{piece or 'Pieza'} ×{quantity}")
    if st.button(save_label('Agregar a la cola', quantity, extra, setup['machine_id'], setup['planned_start'], snapshot),
                 type='primary', width='stretch', key=prefix + '_save', icon=':material/add_task:',
                 disabled=process in PRINT_PROCESSES and not setup['estimated_grams']):
        perform(capture.new_print, target, part_id=None if piece_id == NEW_PIECE else piece_id, piece=piece, quantity=quantity,
                material=material or '', process=process, extra=extra, request_key=_key(), **setup,
                message='Impresión agregada a la cola.' + (f' Al terminar, {extra} unidades extra entran a inventario.' if extra else ''))


@managed_dialog('Nueva impresión', width='large')
def new_print_form(order_id=None, part_id=None, purpose=None):
    snapshot = st.session_state['snapshot']
    prefix = 'capture_' + _key()
    # Prints straight to inventory are launched here, never picked as an order to add to.
    orders = {o['id']: o for o in snapshot['orders'] if o['status'] != 'Entregado' and not o.get('commercial_cancelled') and not o.get('stock_run')}
    labels = destinations(snapshot, sales.list_sales())
    chosen = orders.get(order_id)
    default = purpose if purpose in PURPOSES else ('Prototipo' if chosen and chosen.get('development') else
                                                   'Stock' if chosen and chosen.get('fulfillment') == 'Stock' else 'Pedido')
    purpose = st.segmented_control('¿Para qué es esta impresión?', PURPOSES, default=default, key=prefix + '_purpose', width='stretch',
                                   format_func=lambda p: f'{PURPOSE_ICONS[p]} {p}') or default
    with st.container(horizontal=True, vertical_alignment='center', gap='small'):
        st.caption(PURPOSE_HELP[purpose])
        mode = None
        if purpose == 'Stock':
            mode = st.segmented_control('¿Va ligado a un lote?', STOCK_MODES, label_visibility='collapsed',
                                        default='Lote de stock' if chosen and chosen.get('fulfillment') == 'Stock' else STOCK_MODES[0],
                                        key=prefix + '_stock_mode', help='Directo a inventario no necesita pedido. Lote de stock imprime una pieza de un lote creado desde receta.') or STOCK_MODES[0]
    if mode == 'Directo a inventario':
        stock_direct(snapshot, prefix)
        return
    if mode == 'Lote de stock' and not any(o.get('fulfillment') == 'Stock' for o in orders.values()):
        st.info('No hay lotes de stock abiertos. Usa Directo a inventario para imprimir sin pedido.', icon=':material/info:')
        return
    order_print(snapshot, purpose, orders, labels, order_id, part_id, prefix)
