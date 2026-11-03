"""Order identity, current route and contextual action, shared native styling."""
import streamlit as st
from services.order_board import tracking, LANES
from services.workflow import due_label, next_step
from utils.dates import fmt
from views.common import item_form, parts_form, deliver_dialog
from views.assign_forms import bulk_split_form
from views.components import status_badge
from views.kind_style import order_chip, order_kind
from views.navigation import open_queue
from views.progress_ui import production_progress
from services.order_progress import display_status, breakdown


def choose_tab(order_id, tab):
    st.session_state[f'order_detail_tabs_{order_id}'] = tab


def order_header(order):
    if order.get('commercial_cancelled'):
        st.subheader(order['code']+' · '+order['project'])
        st.warning('Pedido cancelado · '+order['cancellation_reason'])
        return
    t = tracking(order)
    b = breakdown(order)
    with st.container(border=True):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                order_chip(order['code'], order['id'], order_kind(order), help='El color identifica este pedido en la cola, las impresiones y el tablero.')
                st.caption('Proyecto de desarrollo' if order.get('development') else 'Lote para stock' if order.get('fulfillment') == 'Stock' else 'Pedido de cliente')
            status_badge(display_status(order))
        identity, action = st.columns([3, 1.25], vertical_alignment='center')
        with identity:
            st.subheader(order['project'])
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                st.text(order['client'] or 'Sin cliente asignado')
                st.badge(f"Prioridad {order['priority'].lower()}", color='orange' if order['priority'] == 'Alta' else 'gray', icon=':material/flag:')
                if not t['delivered']:
                    label, color = due_label(order['deadline'])
                    st.badge(f"{label} · {fmt(order['deadline'])}" if order['deadline'] else label, color=color, icon=':material/event:')
                if order['notes']:
                    with st.popover('Notas', icon=':material/notes:', type='tertiary'): st.text(order['notes'])
        with action:
            # Development projects are never delivered: their next step is managed from their own page.
            if order.get('development'):
                st.page_link('views/development.py', label='Ir a Desarrollo y prototipos', icon=':material/science:')
            elif not t['delivered']: primary_action(order, t)
        stage_stepper(t)
        production_progress(order)
        with st.container(horizontal=True):
            st.metric('Por fabricar', order['manufacturing']['remaining'], help='Piezas de este pedido que faltan por terminar.')
            st.metric('Sin asignar', b['unassigned'], help='Unidades que todavía no tienen trabajo en una máquina.')
            if order['supplies']['required']:
                st.metric('Insumos por reservar', order['supplies']['remaining'], help='Insumos comprados (cable, foco, empaque) que faltan por reservar.')
        if not t['delivered']:
            detail = ('Revisa el bloqueo del pedido y de sus trabajos antes de continuar.' if t['blocked'] else
                      'Pendiente: ' + ' · '.join(t['pending']) if t['complete'] and t['pending'] else
                      next_step(order)['detail'] if not t['complete'] else '')
            st.markdown(f"**Siguiente paso** · {t['action']}" + (f"  \n:gray[{detail}]" if detail else ''))
    if t['delivered']:
        st.info('Pedido cerrado · histórico de solo lectura.', icon=':material/inventory_2:')
        return
    if order['undefined_items']:
        st.warning(f"{order['undefined_items']} producto(s) sin despiece. Define las piezas para completar el pedido.")


def stage_stepper(t):
    """Planificar → Producir → Preparar → Salida: done, current and next in one line."""
    lanes = list(LANES)
    current = len(lanes) if t['delivered'] else lanes.index(t['lane'])
    marks = [(':material/check_circle:', ':gray[{}]') if index < current else
             (':material/radio_button_checked:', '**{}**') if index == current else
             (':material/radio_button_unchecked:', ':gray[{}]') for index in range(len(lanes))]
    steps = [f"{icon} {text.format(lane)}" for lane, (icon, text) in zip(lanes, marks)]
    if t['delivered']: steps.append(':material/task_alt: **Entregado**')
    st.markdown(' :gray[→] '.join(steps))


def primary_action(order, t):
    button = dict(key=f'order_step_next_{order["id"]}', type='primary', width='stretch', wrap=True)
    if t['blocked']:
        if st.button('Revisar bloqueo', icon=':material/block:', **button): open_queue(order_id=order['id'])
    elif t['complete'] and t['pending']:
        st.button('Continuar preparación', icon=':material/package_2:', on_click=choose_tab,
                  args=(order['id'], 'Preparación'), **button)
    elif t['lane'] == 'Salida':
        if st.button('Liberar a stock' if order.get('fulfillment') == 'Stock' else 'Confirmar entrega',
                     icon=':material/task_alt:', **button): deliver_dialog(order)
    else:
        step = next_step(order)
        labels = {'item':'Agregar producto', 'parts':'Definir piezas', 'split':'Repartir piezas', 'queue':'Ver trabajos','supplies':'Gestionar insumos'}
        if st.button(labels.get(step['action'], 'Ver trabajos'), icon=':material/arrow_forward:', **button):
            if step['action'] == 'item': item_form(order['id'])
            elif step['action'] == 'parts': parts_form(step['item'])
            elif step['action'] == 'split': bulk_split_form(order['id'])
            elif step['action'] == 'supplies':
                choose_tab(order['id'], 'Insumos'); st.rerun()
            else: open_queue(order_id=order['id'])


def commercial_trail(order, quote, sale):
    """The order's commercial chain in one line under its header: quotation → sale and what it still owes.

    Each folio opens its record; a balance can be collected from here. An order for a client with no sale
    or quotation says so, since nothing would then remind anyone to bill it.
    """
    from services.quotations import money
    from views.kind_style import order_kind
    kind = order_kind(order)
    undated = not order.get('deadline') and kind != 'Prototipo' and order['status'] != 'Entregado'
    if not (quote or sale or undated or kind in ('Pedido', 'Origen')):
        return
    with st.container(horizontal=True, gap='small', vertical_alignment='center', key=f"order-trail-{order['id']}"):
        st.caption('Rastreo', width='content')
        if quote and st.button(quote['code'], key=f"order_trail_quote_{order['id']}", icon=':material/request_quote:', type='tertiary',
                               help='Abrir la cotización y sus pagos.'):
            st.session_state['open_quote_id'] = quote['id']; st.switch_page('views/quotations.py')
        if sale:
            owed = sale['status'] == 'Activa' and sale['balance_cents'] > 0
            if st.button(f"{sale['code']} · {'por cobrar ' + money(sale['balance_cents']) if owed else sale['payment_status']}",
                         key=f"order_trail_sale_{order['id']}", icon=':material/point_of_sale:', type='tertiary', help='Abrir la venta y su cobranza.'):
                st.session_state['open_sale_id'] = sale['id']; st.switch_page('views/sales.py')
            if owed and st.button('Cobrar', key=f"order_trail_collect_{order['id']}", icon=':material/payments:',
                                  help='Registrar un pago de la venta vinculada sin salir del pedido.'):
                from services import sales as sales_service
                from views.sales_forms import sale_payment_form
                sale_payment_form(sales_service.get_sale(sale['id']))
        elif kind in ('Pedido', 'Origen'):
            st.badge('Sin venta vinculada', color='orange', icon=':material/link_off:',
                     help='Registra su venta en Ventas o su cotización en Cotizaciones para cobrarlo y medir su utilidad.')
        # Without a delivery date the order cannot be ranked, scheduled against or flagged as late.
        if undated:
            st.badge('Sin fecha de entrega', color='orange', icon=':material/event_busy:',
                     help='Ponla en Más acciones → Editar pedido: ordena la cola y avisa de retrasos.')


def documents_panel(order_id, quote, sale):
    from services.quotations import money
    st.subheader('Venta, cobranza y cotización', icon=':material/description:')
    if not quote and not sale:
        st.info('Este pedido no tiene una venta o cotización vinculada.')
        st.caption('Las operaciones comerciales se registran desde Ventas o Cotizaciones y pueden generar su pedido de producción.')
    if sale:
        with st.container(border=True):
            st.subheader(sale['code'])
            st.badge(sale['payment_status'], color='green' if sale['payment_status']=='Liquidada' else 'orange')
            with st.container(horizontal=True):
                st.metric('Total · MXN', money(sale['total_cents']))
                st.metric('Pagado · MXN', money(sale['paid_cents']))
                st.metric('Saldo · MXN', money(sale['balance_cents']))
            if st.button('Ver venta y cobranza', key='order_sale', icon=':material/point_of_sale:'):
                st.session_state['open_sale_id'] = sale['id']; st.switch_page('views/sales.py')
    if quote:
        with st.container(border=True):
            st.subheader(quote['code'])
            st.text(f"Cotizado {money(quote['total_cents'])} MXN · Pagado {money(quote['paid_cents'])} MXN")
            if st.button('Ver cotización y pagos', key='order_quote', icon=':material/request_quote:'):
                st.session_state['open_quote_id'] = quote['id']; st.switch_page('views/quotations.py')
    if quote and sale: st.caption('La venta y cotización vinculadas comparten sus pagos; los importes mostrados no se suman entre sí.')
