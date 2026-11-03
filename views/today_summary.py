"""Actionable overview using the same route as the order board."""
import streamlit as st
from services.order_board import tracking
from services.workbench import visible, urgency
from services.quotations import money
from views.navigation import open_order, open_queue, open_assign
from views.common import deliver_dialog
from views.kind_style import order_chip, order_kind, order_tone
from views.progress_ui import production_progress
from views.supply_ui import supply_row
from services.timeline import machine_timeline, availability_text
from views.today_brief import choose_front


def summary(board, snapshot, search, scope, limit, supply):
    daily = board['daily']
    left, right = st.columns([1.35, 1], gap='medium')
    with left:
        from views.today_brief import agenda
        agenda(snapshot, board)
        rows = [e for e in daily['attention'] if visible(e['order'], search, scope, date_field='deadline', fields=('code','client','project'))]
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            st.subheader('Pedidos por atender', icon=':material/flag:', width='content')
            st.caption(f'{len(rows)} · vencidos, entregas de hoy y bloqueos primero')
        for entry in rows[:min(limit, 3)]:
            order = entry['order']; t = tracking(order)
            kind = order_kind(order)
            with st.container(border=True, gap='xsmall', key=f"panel-order-{order_tone(order['id'], kind)[0]}-today-{order['id']}"):
                with st.container(horizontal=True, gap='xxsmall', vertical_alignment='center'):
                    order_chip(order['code'], order['id'], kind, help=order['project'])
                    for reason in entry['reasons']:
                        st.badge(reason, color='red' if reason in ('Entrega vencida','Bloqueado') else 'orange')
                    st.space('stretch')
                    st.badge(t['lane'], color='green' if t['lane']=='Salida' else 'blue', icon=':material/route:')
                st.markdown(f"**{_escape(order['project'])}** :gray[· {_escape(order['client'] or 'Sin cliente')}]")
                production_progress(order)
                st.markdown(f":material/arrow_right_alt: **{_escape(t['action'])}**")
                # The order's next move from here: assign its pieces or deliver it, besides opening it.
                part = next((p for p in daily['unassigned'] if p['order_id'] == order['id']), None)
                with st.container(horizontal=True, gap='small'):
                    if part and order['status'] != 'Bloqueado':
                        if st.button('Repartir piezas', key=f'today_split_{order["id"]}', icon=':material/call_split:', width='stretch', type='primary',
                                     help='Abre el pedido en su vista Asignar con la pieza elegida.'):open_assign(part)
                    elif order['status'] == 'Listo':
                        if st.button('Cerrar lote' if order['fulfillment'] == 'Stock' else 'Entregar', key=f'today_deliver_{order["id"]}', icon=':material/task_alt:', width='stretch', type='primary'):
                            deliver_dialog(order)
                    if st.button('Abrir pedido', key=f'today_focus_{order["id"]}', icon=':material/arrow_forward:', width='stretch'):
                        open_order(order['id'])
        if not rows:
            st.success('Sin pedidos por atender con estos filtros.' if daily['attention'] else 'Sin alertas de pedidos. Revisa Producir para continuar los trabajos abiertos.', icon=':material/check_circle:')
        with st.container(horizontal=True, gap='small', vertical_alignment='center'):
            if len(rows) > 3: st.caption(f'Y {len(rows)-3} más.')
            st.page_link('views/orders.py', label='Ver tablero de pedidos', icon=':material/view_kanban:')
    with right:
        from views.tags import printer_html
        running, free = len(daily['base']['running']), len(daily['available'])
        with st.container(border=True, gap='xsmall', key='panel-today-floor'):
            with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
                st.markdown('**Taller ahora**', width='content')
                with st.container(horizontal=True, gap='xxsmall', width='content'):
                    st.badge(f'{running} en marcha', color='blue', icon=':material/autorenew:')
                    st.badge(f'{free} disponibles', color='green', icon=':material/check_circle:')
            # Same availability sentence as the queue and the agenda; record filters apply to orders and money only.
            for machine in snapshot['machines']:
                t = machine_timeline(machine, snapshot['jobs'])
                with st.container(horizontal=True, vertical_alignment='center', gap='small', wrap=False):
                    st.html(printer_html(machine, material=False), width='content')
                    st.caption(availability_text(t['availability']), width='stretch')
                    if st.button('Cola', key=f'today_summary_machine_{machine["id"]}', type='tertiary', icon=':material/arrow_forward:', icon_position='right'):
                        open_queue(machine_id=machine['id'])
            st.button('Atender producción', key='today_summary_produce', on_click=choose_front, args=('Producir',), icon=':material/play_arrow:', width='stretch')
        with st.container(border=True, gap='xsmall', key='panel-today-supply'):
            with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
                st.markdown('**Insumos y materiales**', width='content')
                st.caption(f"{len(supply['to_order'])} por pedir · {len(supply['arriving'])} por recibir" + (f" · :red[{supply['overdue']} vencidas]" if supply['overdue'] else ''))
            for row in supply['rows'][:3]:
                supply_row(row, 'today_summary_supply', compact=True)
            if not supply['rows']:st.caption('Sin faltantes ni pedidos de compra abiertos.')
            st.button('Abastecer', key='today_summary_supply', on_click=choose_front, args=('Abastecer',), icon=':material/arrow_forward:', type='tertiary')
    for col, front, label, source, fields, icon in zip(st.columns(2), ('Cobrar','Pagar'),
            ('Cobros prioritarios','Pagos prioritarios'), ('collections','payables'),
            (('code','client','project'), ('code','concept','supplier')), ('south_west', 'north_east')):
        with col.container(border=True, gap='xsmall', key=f'panel-today-{front.lower()}'):
            rows = [r for r in board[source] if visible(r, search, scope, date_field='due_on', fields=fields)]
            with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
                st.markdown(f"**:material/{icon}: {label}**", width='content')
                st.caption(f"{len(rows)} · {money(sum(r['balance_cents'] for r in rows))} MXN")
            # Each line: folio and who, how urgent, and the amount at the right where amounts are compared.
            for row in rows[:3]:
                due, color = urgency(row['due_on'])
                with st.container(horizontal=True, vertical_alignment='center', gap='small', key=f"money-row-{front.lower()}-{row['id']}"):
                    st.markdown(f"**{row['code']}** :gray[· {_escape(row['client'] if front=='Cobrar' else row['concept'])}]", width='stretch')
                    st.badge(due, color=color)
                    st.markdown(f"**{money(row['balance_cents'])}**", width='content')
            if not rows: st.caption('Sin pendientes con estos filtros.')
            st.button('Ver cobranza' if front=='Cobrar' else 'Ver pagos pendientes', key=f'today_summary_{front}',
                      on_click=choose_front, args=(front,), icon=':material/arrow_forward:', type='tertiary')


def _escape(text):
    import re
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', str(text or '').replace('\n', ' '))
