from views.work_context import remember
from views.order_board import render_board, trace_panel
from views.order_detail import order_header, documents_panel, choose_tab, commercial_trail
from views.progress_ui import production_progress
from views.order_supplies import supplies_panel
from views.assign_forms import bulk_split_form, pending_parts
from services.order_progress import fabrication_label, breakdown, manufacturing, supplies
import re
import streamlit as st

from services import production as service
from views.common import delete_dialog, deliver_dialog, item_form, order_form, part_form, parts_form, perform
from views.navigation import open_queue
from views.operations import order_checklist, item_check, item_label_form
from views.catalog_forms import recipe_order_form, import_recipe_form
from views.quick_print import quick_print_panel
from services.quotations import list_quotes
from services.sales import list_sales
from services.inventory import PRINT_PROCESSES
from views.piece_management import piece_list, visible_rows, order_prints
from services.queue_review import destinations
from views.emoji import icon_tabs

ITEM_STATES = ('Por asignar', 'En producción', 'Completos')
# Recipe orders store this note automatically; the recipe line already says it.
AUTO_NOTE = re.compile(r'Receta v\d+ · componentes')


def item_state(item):
    if not manufacturing(item)['defined'] or breakdown(item)['unassigned']:
        return 'Por asignar'
    return 'Completos' if manufacturing(item)['complete'] else 'En producción'


def item_title(item):
    """Collapsed product row: name, finished units and only the signals that need action."""
    b, m, s = breakdown(item), manufacturing(item), supplies(item)
    words = [f"**{item['name']}** ×{item['quantity']}",
             f"{b['completed']}/{b['required']} terminadas" if m['applicable'] else fabrication_label(item)]
    if b['unassigned']: words.append(f":orange[{b['unassigned']} sin asignar]")
    if b['running']: words.append(f":blue[{b['running']} en curso]")
    if b['blocked']: words.append(':red[trabajo bloqueado]')
    if s['remaining']: words.append(f":orange[faltan {s['remaining']} insumos]")
    if m['complete'] and not s['remaining']: words.append(':green[fabricación completa]')
    return ' · '.join(words + [f":gray[{item['code']}]"])


def product_panel(item):
    """Progress, then this product's actions, then its pieces; review and context close the panel."""
    production_progress(item)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        if not readonly and pending_parts(order, item['id']) and st.button(
                'Repartir pendientes', key=f"item_bulk_split_{item['id']}", icon=':material/call_split:',
                help='Asigna a máquinas todas las piezas sin trabajo de este producto en una sola ventana.'):
            bulk_split_form(selected_id, item['id'])
        if not readonly and not recipe_order:
            if st.button("Despiece rápido", key=f"item_parts_{item['id']}", icon=":material/format_list_bulleted:"):
                parts_form(item)
            if st.button("Agregar pieza", key=f"item_add_part_{item['id']}", icon=":material/add:"):
                part_form(item)
        if item['supplies']['required']:
            st.button('Ver insumos', key=f"item_supplies_{item['id']}", icon=':material/electrical_services:',
                      on_click=choose_tab, args=(selected_id, 'Insumos'), type='tertiary')
        if item["label"]: st.badge(item["label"], color="blue", icon=':material/label:')
        item_label_form(item, readonly, "detail")
        if not readonly and not recipe_order:
            with st.popover("Opciones del producto", icon=":material/more_horiz:", type='tertiary'):
                if st.button("Editar producto", key=f"item_edit_{item['id']}", icon=":material/edit:", width="stretch"):
                    item_form(selected_id, item)
                if item["parts"] and st.button("Guardar como receta", key=f"item_recipe_{item['id']}", icon=":material/bookmark_add:", width="stretch"):
                    import_recipe_form(item)
                if st.button("Eliminar producto", key=f"item_delete_{item['id']}", icon=":material/delete:", width="stretch"):
                    delete_dialog("item", item)
    rows = visible_rows(item, product_search)
    if rows:
        piece_list(item, rows, readonly=readonly, recipe_order=recipe_order, snapshot=snapshot)
    elif not item["parts"] and not recipe_order:
        st.info("Define sus piezas con Despiece rápido o agrega una pieza individual.", icon=':material/edit_note:')
    item_check(item, readonly, "detail")
    context = []
    if item.get("recipe_id"): context.append(f":material/menu_book: Receta v{item['recipe_version']} · {order['fulfillment']}")
    if item["notes"] and not AUTO_NOTE.fullmatch(item["notes"]): context.append(item["notes"])
    if context: st.caption(' · '.join(context))
    if item['collection']:
        st.page_link('views/collection.py', icon=':material/warehouse:',
                     label='Sus piezas entran al inventario de Colección Origen' + ('' if order.get('fulfillment') == 'Stock' else ' y se reservan para este pedido'))


snapshot = st.session_state["snapshot"]
selected_id = st.session_state.get("open_order_id")
order = next((o for o in snapshot["orders"] if o["id"] == selected_id), None)
if order is None:
    st.session_state.pop("open_order_id", None)
    # Creating sits beside the page title, where every page puts its main action.
    from views.shell import actions
    with actions():
        if st.button("Nuevo pedido", icon=":material/add:"):
            order_form()
        if st.button("Desde receta", icon=":material/playlist_add:", type="primary", key="new_recipe_order"):
            recipe_order_form()
    # Customer orders, stock lots and prototyping projects are followed on the same board; prints straight
    # to inventory live in the queue.
    render_board([o for o in snapshot["orders"] if not o.get('stock_run')])
    st.stop()

# One toolbar above the order: back on the left, the order's own actions on the right.
toolbar = st.container(horizontal=True, vertical_alignment="center", gap="small")
with toolbar:
    if st.button("Todos los pedidos", icon=":material/arrow_back:", key="orders_back", type="tertiary"):
        st.session_state.pop("open_order_id", None)
        st.session_state.pop("focus_item_id", None)
        st.rerun()
    st.space("stretch")
readonly = order["status"] == "Entregado" or order.get('commercial_cancelled',False)
recipe_order = order.get("fulfillment") != "Personalizado"
if pending := st.session_state.pop("pending_focus_item", None):
    st.session_state[f"item_panel_{pending}"] = True
    st.session_state[f"order_detail_tabs_{selected_id}"] = "Producción"
    st.session_state[f"order_production_view_{selected_id}"] = "Piezas"
    st.session_state[f"order_products_search_{selected_id}"] = ''
remember('Pedido',order['id'],order['code'])
order_header(order)
if order.get('commercial_cancelled'):
    from views.order_board import trace_panel
    trace_panel(order)
    st.stop()
linked_quote = next((q for q in list_quotes() if q['order_id'] == selected_id), None)
linked_sale = next((s for s in list_sales() if s['order_id'] == selected_id), None)
commercial_trail(order, linked_quote, linked_sale)
with toolbar:
    if not readonly:
        if not recipe_order and st.button("Agregar producto", key=f"order_add_item_{selected_id}", icon=":material/add:"):
            item_form(selected_id)
    with st.popover("Más acciones", icon=":material/more_horiz:"):
        if st.button("Ver trabajos en la cola", key=f"order_jobs_{selected_id}", icon=":material/format_list_bulleted:", width="stretch"):
            open_queue(order_id=selected_id)
        if st.button('Costos reales y margen',key=f'order_real_cost_{selected_id}',icon=':material/payments:', width="stretch"):
            st.session_state.update(control_view='Costos y margen',control_cost_order=selected_id)
            st.switch_page('views/control.py')
        if st.button('Registrar consumible usado',key=f'order_consumable_{selected_id}',icon=':material/science:', width="stretch",
                     help='Pintura, pegamento, tornillería, empaque o filamento usado en este pedido; su costo se suma al pedido.'):
            from views.consumables_ui import consumable_use_form
            consumable_use_form(selected_id)
        if linked_sale or linked_quote:
            st.button('Venta y cotización vinculadas', key=f'order_documents_{selected_id}', icon=':material/description:',
                      on_click=choose_tab, args=(selected_id, 'Documentos'), width="stretch")
        if not readonly:
            st.divider()
            if st.button("Editar pedido", key=f"order_edit_{selected_id}", icon=":material/edit:", width="stretch"):
                order_form(order)
            if st.button("Liberar bloqueo" if order["blocked_manually"] else "Bloquear pedido", key=f"order_block_{selected_id}", icon=":material/block:", width="stretch"):
                perform(service.set_order_blocked, selected_id, not bool(order["blocked_manually"]))
            if order["status"] == "Listo" and st.button("Marcar entregado", key=f"order_deliver_{selected_id}", icon=":material/task_alt:", width="stretch"):
                deliver_dialog(order)
            if st.button("Eliminar pedido", key=f"order_delete_{selected_id}", icon=":material/delete:", width="stretch"):
                delete_dialog("order", order)
has_supplies = bool(order['supplies']['required'])
tabs = icon_tabs(['Producción', *(['Insumos'] if has_supplies else []), 'Preparación', 'Documentos', 'Historial'],
               key=f'order_detail_tabs_{selected_id}', on_change='rerun')
production_tab = tabs[0]
preparation_tab, documents_tab, history_tab = tabs[-3:]
if has_supplies:
    with tabs[1]:
        supplies_panel(order, readonly)
with preparation_tab:
    st.subheader("Preparación y salida", icon=":material/package_2:")
    st.caption('Registra la revisión de productos y la preparación realizada. Confirma la entrega al terminar.')
    if order['supplies']['remaining']:
        st.badge(f"{order['supplies']['remaining']} insumos por reservar antes del ensamble y la entrega", color='orange', icon=':material/electrical_services:')
    if order.get('fulfillment') == 'Stock': st.caption('Para liberar a stock se requiere revisión de productos y revisión final; empaque y salida son opcionales.')
    order_checklist(order,"order",detailed=True,expanded=True,actions=True)
with documents_tab:
    documents_panel(selected_id, linked_quote, linked_sale)
with history_tab:
    trace_panel(order)
with production_tab:
    from views.piece_stock_ui import cover_panel
    view_key = f'order_production_view_{selected_id}'
    cover_panel(order, readonly, view_key)
    unassigned = sum(p['quantity_unassigned'] for i in order['items'] for p in i['parts'])
    views = ('Piezas', 'Inventario', 'Asignar', 'Impresiones') if not readonly else ('Piezas', 'Impresiones')
    if st.session_state.get(view_key) not in (None, *views):st.session_state[view_key] = 'Piezas'
    from views.piece_stock_ui import coverable, availability_panel
    in_stock = len(coverable(order))
    view = st.segmented_control('Vista de producción', views, default=None if view_key in st.session_state else 'Piezas',
                                key=view_key, width='stretch', label_visibility='collapsed',
                                format_func=lambda v: f'Asignar · {unassigned}' if v == 'Asignar' and unassigned
                                else f'Inventario · {in_stock}' if v == 'Inventario' and in_stock else v) or 'Piezas'
    if view == 'Inventario':
        availability_panel(order)
    elif view == 'Asignar':
        from views.assign_panel import assign_panel
        assign_panel(snapshot, f'order_assign_{selected_id}', order_id=order['id'])
    elif view == 'Impresiones':
        dest = destinations(snapshot, list_sales())[order['id']]
        order_prints(order, snapshot, dest, readonly=readonly)
        if not readonly and any(p['process'] in PRINT_PROCESSES for i in order['items'] for p in i['parts']):
            with st.popover('Registrar impresión terminada', icon=':material/print:',
                            help='Marca impresas un producto completo o piezas sueltas, sin abrir cada trabajo.'):
                quick_print_panel(order)
    else:
        # Products are picked like tabs and shown open: no fold-out per product or per piece.
        items = sorted(order['items'], key=lambda i: (ITEM_STATES.index(item_state(i)), i['id']))
        pick_key = f'order_product_pick_{selected_id}'
        if pending:st.session_state[pick_key] = pending
        if st.session_state.get(pick_key) not in ('all', *[i['id'] for i in items]):st.session_state[pick_key] = 'all' if len(items) != 1 else items[0]['id']
        def product_label(choice):
            if choice == 'all':return f"Todos · {len(items)}"
            item = next(i for i in items if i['id'] == choice);b = breakdown(item)
            return f"{item['name']} · {b['completed']}/{b['required']}" + (f" · {b['unassigned']} sin asignar" if b['unassigned'] else ' ✓' if manufacturing(item)['complete'] else '')
        with st.container(horizontal=True, vertical_alignment='bottom'):
            pick = st.pills('Producto', ['all', *[i['id'] for i in items]], key=pick_key, format_func=product_label, label_visibility='collapsed') or 'all'
            product_search = st.text_input('Buscar pieza', placeholder='Pieza o material', key=f'order_products_search_{selected_id}', icon=':material/search:',
                                           label_visibility='collapsed', width=260)
        shown = [i for i in items if pick in ('all', i['id']) and product_search.strip().casefold() in
                 f"{i['name']} {i['label']} {' '.join(p['name']+' '+p['material'] for p in i['parts'])}".casefold()]
        if not shown: st.info('No hay productos en esta consulta. Agrega un producto o ajusta la búsqueda.')
        for item in shown:
            with st.container(border=True, gap='small', key=f"item_section_{item['id']}"):
                st.markdown(f"#### {item_title(item)}")
                product_panel(item)
