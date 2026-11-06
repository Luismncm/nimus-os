import streamlit as st
from services import development
from services import development_journal as dj
from services.quotations import money
from utils.dates import fmt
from views.development_forms import project_form
from views.development_panel import (RESULT_COLORS, RESULT_ICONS, open_panel, plain, project_menu, project_panel, quick_access,
                                     development_entry_form, result_label)
from views.capture_forms import new_print_form
from views.consumables_ui import consumable_use_form
from views.navigation import open_queue
from views.kind_style import card

snapshot = st.session_state['snapshot']
rows = development.summaries(snapshot)
active = [r for r in rows if r['info']['status'] == 'Activo']

from views.shell import actions
with actions():
    st.page_link('views/queue.py', label='Cola', icon=':material/format_list_bulleted:')
    if st.button('Nuevo proyecto', key='dev_new', icon=':material/add:'):project_form()
    if st.button('Lanzar impresión de prototipo', key='dev_launch', type='primary', icon=':material/rocket_launch:'):new_print_form(purpose='Prototipo')

opened = next((r for r in rows if r['order']['id'] == st.session_state.get('dev_open_project')), None)
if opened:
    project_panel(opened)
    st.stop()
st.session_state.pop('dev_open_project', None)

a, b, c, d = st.columns(4)
a.metric('Proyectos activos', len(active), border=True)
b.metric('Impresiones en marcha · en cola', f"{sum(r['running'] for r in active)} · {sum(r['waiting'] for r in active)}", border=True)
c.metric('Filamento previsto', f"{sum(r['grams_estimated'] for r in active):,.0f} g", border=True,
         help='Gramos estimados de las impresiones de proyectos activos; ya cuentan en Insumos y consumibles.')
d.metric('Costo de desarrollo', money(sum(r['real_cents'] for r in active)), border=True,
         help='Costo real registrado (consumo de impresiones, consumibles y costos adicionales) de proyectos activos, sin IVA.')

if not rows:
    st.info('Aún no hay proyectos. Crea uno para lanzar impresiones de prueba sin mezclarlas con pedidos ni ventas.', icon=':material/science:')
    st.stop()
journals = dj.overview()
show_closed = st.toggle('Mostrar proyectos cerrados', key='dev_show_closed', persist_state='session')
for row in rows:
    order, info = row['order'], row['info']
    if info['status'] != 'Activo' and not show_closed:continue
    oid = order['id']
    journal = journals.get(oid, dict(notes=0, reports=0, links=0, last_result=None, last_report=None, quick=[]))
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
        with st.container(horizontal=True, gap='xsmall'):
            st.badge(f"{journal['notes']} {'nota' if journal['notes'] == 1 else 'notas'}", color='gray', icon=':material/sticky_note_2:')
            st.badge(f"{journal['reports']} {'reporte' if journal['reports'] == 1 else 'reportes'}", color='gray', icon=':material/lab_research:')
            st.badge(f"{journal['links']} {'archivo o enlace' if journal['links'] == 1 else 'archivos y enlaces'}", color='gray', icon=':material/link:')
            if journal['last_report']:
                st.badge(f"Último reporte: {result_label(journal['last_result'])} · {fmt(journal['last_report'])}",
                         color=RESULT_COLORS[journal['last_result']], icon=f":material/{RESULT_ICONS[journal['last_result']]}:")
        costs = [f"Costo estimado {money(row['estimated_cents'])}" if row['estimated_cents'] else 'Costo estimado: faltan gramos, duración o tarifas',
                 f"Costo real {money(row['real_cents'])}"]
        if row['consumables_cents']:costs.append(f"incluye {money(row['consumables_cents'])} de consumibles")
        if info['budget_cents'] is not None:
            costs.append(f"presupuesto {money(info['budget_cents'])}")
            st.progress(min(1.0, row['real_cents'] / info['budget_cents']) if info['budget_cents'] else 1.0,
                        text=plain(f"{money(row['real_cents'])} de {money(info['budget_cents'])} · " + ('presupuesto excedido' if row['budget_left'] < 0 else f"quedan {money(row['budget_left'])}")))
        st.caption(plain(' · '.join(costs) + ' · sin IVA, no es venta'))
        if journal['quick']:
            quick_access(journal['quick'], f'dev_quick_{oid}')
        with st.container(horizontal=True, gap='small'):
            st.button('Abrir panel', key=f'dev_panel_{oid}', icon=':material/open_in_full:', type='primary', on_click=open_panel, args=(oid,))
            if info['status'] == 'Activo':
                if st.button('Lanzar impresión', key=f'dev_launch_{oid}', icon=':material/rocket_launch:'):new_print_form(order_id=oid, purpose='Prototipo')
                if st.button('Registrar consumible', key=f'dev_consumable_{oid}', icon=':material/science:'):consumable_use_form(oid)
            if st.button('Nota', key=f'dev_note_{oid}', icon=':material/sticky_note_2:', type='tertiary'):
                development_entry_form(oid, row['jobs'], kind='Nota')
            if row['waiting'] or row['running']:
                if st.button('Ver en la cola', key=f'dev_queue_{oid}', icon=':material/format_list_bulleted:', type='tertiary'):open_queue(order_id=oid)
            project_menu(row, 'dev')
