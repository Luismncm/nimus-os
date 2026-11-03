import streamlit as st
from services import development
from services.quotations import money
from services.timeline import slot
from views.common import table, perform
from views.development_forms import project_form
from views.capture_forms import new_print_form
from views.consumables_ui import consumable_use_form
from views.navigation import open_order, open_queue
from views.timeline_ui import slot_line
from views.kind_style import card

snapshot = st.session_state['snapshot']
rows = development.summaries(snapshot)
active = [r for r in rows if r['info']['status'] == 'Activo']

from views.shell import actions
with actions():
    st.page_link('views/queue.py', label='Cola', icon=':material/format_list_bulleted:')
    if st.button('Nuevo proyecto', key='dev_new', icon=':material/add:'):project_form()
    if st.button('Lanzar impresión de prototipo', key='dev_launch', type='primary', icon=':material/rocket_launch:'):new_print_form(purpose='Prototipo')

a, b, c, d = st.columns(4)
a.metric('Proyectos activos', len(active), border=True)
b.metric('Impresiones en marcha · en cola', f"{sum(r['running'] for r in active)} · {sum(r['waiting'] for r in active)}", border=True)
c.metric('Filamento previsto', f"{sum(r['grams_estimated'] for r in active):,.0f} g", border=True,
         help='Gramos estimados de las impresiones de proyectos activos; ya cuentan en Filamento y consumibles.')
d.metric('Costo de desarrollo', money(sum(r['real_cents'] for r in active)), border=True,
         help='Costo real registrado (consumo de impresiones, consumibles y costos adicionales) de proyectos activos, sin IVA.')

if not rows:
    st.info('Aún no hay proyectos. Crea uno para lanzar impresiones de prueba sin mezclarlas con pedidos ni ventas.', icon=':material/science:')
    st.stop()
show_closed = st.toggle('Mostrar proyectos cerrados', key='dev_show_closed', persist_state='session')
for row in rows:
    order, info = row['order'], row['info']
    if info['status'] != 'Activo' and not show_closed:continue
    oid = order['id']
    with card('Prototipo', f'dev-project-{oid}', gap='small'):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            st.markdown(f"**{order['project']}** :gray[· {order['code']}]")
            st.badge(info['status'], color='violet' if info['status'] == 'Activo' else 'gray', icon=':material/science:')
        if info['goal']:st.caption(info['goal'])
        with st.container(horizontal=True, gap='xsmall'):
            if row['running']:st.badge(f"{row['running']} en marcha", color='blue', icon=':material/autorenew:')
            if row['waiting']:st.badge(f"{row['waiting']} en cola", color='gray', icon=':material/schedule:')
            st.badge(f"{row['finished']} terminadas", color='green' if row['finished'] else 'gray', icon=':material/check:')
            st.badge(f"Filamento {row['grams_estimated']:,.0f} g previstos · {row['grams_used']:,.0f} g reales", color='gray', icon=':material/science:')
        costs = [f"Costo estimado {money(row['estimated_cents'])}" if row['estimated_cents'] else 'Costo estimado: faltan gramos, duración o tarifas',
                 f"Costo real {money(row['real_cents'])}"]
        if row['consumables_cents']:costs.append(f"incluye {money(row['consumables_cents'])} de consumibles")
        if info['budget_cents'] is not None:
            costs.append(f"presupuesto {money(info['budget_cents'])}")
            st.progress(min(1.0, row['real_cents'] / info['budget_cents']) if info['budget_cents'] else 1.0,
                        text=f"{money(row['real_cents'])} de {money(info['budget_cents'])} · " + ('presupuesto excedido' if row['budget_left'] < 0 else f"quedan {money(row['budget_left'])}"))
        st.caption(' · '.join(costs) + ' · sin IVA, no es venta')
        with st.container(horizontal=True, gap='small'):
            if info['status'] == 'Activo':
                if st.button('Lanzar impresión', key=f'dev_launch_{oid}', icon=':material/rocket_launch:'):new_print_form(order_id=oid, purpose='Prototipo')
                if st.button('Registrar consumible', key=f'dev_consumable_{oid}', icon=':material/science:'):consumable_use_form(oid)
            if row['waiting'] or row['running']:
                if st.button('Ver en la cola', key=f'dev_queue_{oid}', icon=':material/format_list_bulleted:', type='tertiary'):open_queue(order_id=oid)
            if st.button('Costos', key=f'dev_costs_{oid}', icon=':material/payments:', type='tertiary'):
                st.session_state.update(control_view='Costos y margen', control_cost_order=oid);st.switch_page('views/control.py')
            with st.popover('Más', icon=':material/more_horiz:', type='tertiary'):
                if st.button('Abrir detalle de piezas y trabajos', key=f'dev_open_{oid}', width='stretch'):open_order(oid)
                if info['status'] == 'Activo':
                    if st.button('Editar objetivo y presupuesto', key=f'dev_edit_{oid}', width='stretch'):project_form(order)
                    if st.button('Cerrar proyecto', key=f'dev_close_{oid}', width='stretch'):perform(development.close_project, oid, message='Proyecto cerrado; su historial se conserva.')
                elif st.button('Reabrir proyecto', key=f'dev_reopen_{oid}', width='stretch'):perform(development.reopen_project, oid, message='Proyecto reabierto.')
        if row['jobs']:
            with st.expander(f"Impresiones · {len(row['jobs'])}", key=f'dev_jobs_{oid}', expanded=bool(row['running'] or row['waiting']), on_change='ignore'):
                table([dict(j, schedule=slot_line(slot(j)) if j['status'] != 'Terminado' else 'Terminada',
                            grams=f"{j.get('estimated_grams') or 0:g} g est. · {j.get('actual_consumed_grams') or 0:g} g reales") for j in row['jobs']],
                      {'code': 'Trabajo', 'part_name': 'Pieza', 'material': 'Material', 'machine_code': 'Máquina', 'status': 'Estado',
                       'schedule': 'Horario', 'grams': 'Filamento'}, label=f"Impresiones de {order['project']}")
