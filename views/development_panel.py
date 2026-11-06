"""A development project opened wide: its journal of notes and technical reports, its files and its prints.

The list in Desarrollo y prototipos stays a quick overview; "Abrir panel" gives one project the whole page.
"""
from textwrap import shorten

import streamlit as st
from services import development, local_files
from services import development_journal as dj
from services.quotations import money
from services.timeline import slot
from utils.dates import fmt
from views.common import managed_dialog, perform, picks, table
from views.common import request_key as _key
from views.kind_style import card
from views.timeline_ui import slot_line

RESULT_COLORS = {'Aprobado': 'green', 'Ajustar': 'orange', 'Rechazado': 'red', None: 'gray'}
RESULT_ICONS = {'Aprobado': 'check_circle', 'Ajustar': 'tune', 'Rechazado': 'cancel', None: 'pending'}
KIND_LABELS = {'Nota': 'Nota', 'Reporte': 'Reporte técnico'}
KIND_ICONS = {'Nota': 'sticky_note_2', 'Reporte': 'lab_research'}
REPORT_TEMPLATE = ('Qué se probó: tolerancia, ajuste, acabado…\nParámetros: material, capa, relleno, soportes, orientación…\n'
                   'Qué salió: medidas, fallas, fotos…\nSiguiente paso: qué cambia en la próxima iteración…')
PATH_TIP = 'En el Explorador de Windows: Shift + clic derecho sobre el archivo o carpeta → «Copiar como ruta de acceso», y pégala aquí.'
VIEWS = ('Bitácora', 'Reportes técnicos', 'Archivos y enlaces', 'Impresiones')


def plain(text):
    return text.replace('$', '\\$')


def open_panel(order_id):
    st.session_state['dev_open_project'] = order_id


def close_panel():
    st.session_state.pop('dev_open_project', None)


def result_label(result):
    return result or 'Sin resultado'


@managed_dialog('Nota o reporte técnico', width='large')
def development_entry_form(order_id, jobs, entry=None, kind='Nota', job_code=''):
    prefix = 'dev_entry_' + _key()
    if entry:
        kind = entry['kind']
        st.caption(f"{KIND_LABELS[kind]} · creada {fmt(entry['created_at'], time=True)}")
    else:
        kind = st.segmented_control('Tipo', dj.KINDS, default=kind, key=prefix + '_kind', format_func=KIND_LABELS.get, width='stretch') or kind
    codes = [j['code'] for j in jobs]
    names = {j['code']: f"{j['code']} · {j['part_name']} · {j['status']}" for j in jobs}
    with st.form(prefix):
        title = st.text_input('Título *', value=entry['title'] if entry else '', key=prefix + '_title',
                              placeholder='Prueba de ajuste 0.2 mm · bisagra v3' if kind == 'Reporte' else 'Idea, pendiente o acuerdo…')
        result, job = None, ''
        if kind == 'Reporte':
            a, b = st.columns(2)
            options = ('Sin resultado aún', *dj.RESULTS)
            current = entry['result'] if entry and entry['result'] else 'Sin resultado aún'
            picked = a.radio('Resultado', options, index=options.index(current), horizontal=True, key=prefix + '_result')
            result = None if picked == 'Sin resultado aún' else picked
            start = entry['job_code'] if entry else job_code
            job = b.selectbox('Impresión probada', ['', *codes], index=([''] + codes).index(start) if start in codes else 0, key=prefix + '_job',
                              format_func=lambda c: names.get(c, 'Ninguna en particular'))
        body = st.text_area('Contenido', value=entry['body'] if entry else '', height=260, key=prefix + '_body',
                            placeholder=REPORT_TEMPLATE if kind == 'Reporte' else 'Lo que quieres recordar de este proyecto…',
                            help='Admite formato: **negritas**, listas con «-» y enlaces.')
        links = st.text_area('Agregar archivos y enlaces · uno por línea', height=90, key=prefix + '_links',
                             placeholder='Modelo v3 | C:\\Proyectos\\Nimbus\\pantalla_v3.3mf\nFotos de la prueba | https://drive.google.com/…',
                             help='«Nombre | dirección» o solo la dirección. Se abren desde la nota o desde Archivos y enlaces.')
        st.caption(PATH_TIP)
        if st.form_submit_button('Guardar cambios' if entry else f'Guardar {KIND_LABELS[kind].lower()}', type='primary', width='stretch', icon=':material/save:'):
            try:
                parsed = dj.parse_links(links)
            except ValueError as exc:
                st.error(str(exc))
            else:
                perform(dj.save_entry, order_id, kind, title, body, result=result, job_code=job, links=parsed,
                        entry_id=entry['id'] if entry else None, expected_revision=entry['revision'] if entry else None,
                        request_key=_key(), message={'Nota': 'Nota guardada.', 'Reporte': 'Reporte técnico guardado.'}[kind])


@managed_dialog('Archivo o enlace', width='medium')
def development_link_form(order_id, entry=None):
    prefix = 'dev_link_' + _key()
    if entry:
        st.caption(f"Se guarda en «{entry['title']}».")
    with st.form(prefix):
        target = st.text_input('Ruta o enlace *', key=prefix + '_target', placeholder='C:\\Proyectos\\Nimbus\\pantalla_v3.3mf  o  https://…')
        label = st.text_input('Nombre', key=prefix + '_label', placeholder='Si lo dejas vacío, se usa el nombre del archivo')
        pinned = st.checkbox('Mostrar en accesos rápidos del proyecto', value=entry is None, key=prefix + '_pinned')
        st.caption(PATH_TIP)
        if st.form_submit_button('Guardar enlace', type='primary', width='stretch', icon=':material/add_link:'):
            perform(dj.add_link, order_id, target, label, entry_id=entry['id'] if entry else None, pinned=pinned,
                    request_key=_key(), message='Enlace guardado.')


def _open(link, reveal=False):
    try:
        (local_files.reveal if reveal else local_files.open_target)(link['target'])
        st.toast(f"Abriendo {link['label']}…", icon=':material/open_in_new:')
    except ValueError as exc:
        st.toast(str(exc), icon=':material/error:')


def quick_access(links, key):
    """Pinned links as one row of buttons: a click opens the page, the file or the folder."""
    with st.container(horizontal=True, gap='xsmall'):
        for link in links:
            if link['web']:
                st.link_button(link['label'], link['target'], icon=':material/open_in_new:', type='tertiary')
            elif st.button(link['label'], key=f"{key}_{link['id']}", icon=':material/folder_open:', type='tertiary',
                           help=link['target']):
                _open(link)


def link_row(link, key, *, source=False):
    with st.container(horizontal=True, vertical_alignment='center', gap='small', key=f'dev-link-{key}-{link["id"]}'):
        found = 'Web' if link['web'] else local_files.status(link['target'])
        icon = {'Web': 'public', 'Carpeta': 'folder', 'Archivo': 'draft', 'No encontrado': 'link_off'}[found]
        where = f" · en «{shorten(link['entry_title'], 40, placeholder='…')}»" if source and link['entry_title'] else ''
        st.markdown(f":material/{icon}: **{plain(link['label'])}**  \n:gray[{plain(shorten(link['target'], 90, placeholder='…'))}{plain(where)}]")
        if link['web']:
            st.link_button('Abrir', link['target'], icon=':material/open_in_new:')
        elif found == 'No encontrado':
            st.badge('No encontrado', color='red', icon=':material/link_off:')
        else:
            if st.button('Abrir', key=f"{key}_open_{link['id']}", icon=':material/open_in_new:'):
                _open(link)
            if found == 'Archivo' and st.button('Carpeta', key=f"{key}_reveal_{link['id']}", icon=':material/folder_open:', type='tertiary'):
                _open(link, reveal=True)
        pinned = bool(link['pinned'])
        if st.button('Fijado' if pinned else 'Fijar', key=f"{key}_pin_{link['id']}", icon=':material/star:' if pinned else ':material/star_border:',
                     type='tertiary', help='Quitar de accesos rápidos' if pinned else 'Mostrar en accesos rápidos del proyecto'):
            perform(dj.set_pinned, 'link', link['id'], not pinned, message='Accesos rápidos actualizados.')
        if st.button('Quitar', key=f"{key}_drop_{link['id']}", icon=':material/link_off:', type='tertiary', help='Quita el enlace; el archivo no se borra'):
            perform(dj.delete_link, link['id'], message='Enlace quitado. El archivo no se borra.')


def entry_card(entry, order_id, jobs, key):
    with st.container(border=True, gap='xsmall', key=f'dev-entry-{key}-{entry["id"]}'):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            star = ' :orange[:material/star:]' if entry['pinned'] else ''
            st.markdown(f":material/{KIND_ICONS[entry['kind']]}: **{plain(entry['title'])}**{star}")
            with st.container(horizontal=True, gap='xxsmall', width='content'):
                if entry['kind'] == 'Reporte':
                    st.badge(result_label(entry['result']), color=RESULT_COLORS[entry['result']], icon=f":material/{RESULT_ICONS[entry['result']]}:")
                    if entry['job_code']:
                        st.badge(entry['job_code'], color='violet', icon=':material/print:')
                else:
                    st.badge('Nota', color='gray')
        edited = f" · editada {fmt(entry['updated_at'], time=True)}" if entry['updated_at'] != entry['created_at'] else ''
        st.caption(fmt(entry['created_at'], time=True) + edited)
        if entry['body']:
            # Markdown would join single line breaks; keep each typed line apart.
            st.markdown(plain(entry['body']).replace('\n', '  \n'))
        for link in entry['links']:
            link_row(link, f'{key}_e{entry["id"]}')
        with st.container(horizontal=True, gap='xsmall'):
            if st.button('Editar', key=f"{key}_edit_{entry['id']}", icon=':material/edit:', type='tertiary'):
                development_entry_form(order_id, jobs, entry)
            if st.button('Archivo o enlace', key=f"{key}_link_{entry['id']}", icon=':material/add_link:', type='tertiary'):
                development_link_form(order_id, entry)
            pinned = bool(entry['pinned'])
            if st.button('Desfijar' if pinned else 'Fijar arriba', key=f"{key}_pin_{entry['id']}", icon=':material/push_pin:', type='tertiary'):
                perform(dj.set_pinned, 'entry', entry['id'], not pinned, message='Bitácora actualizada.')
            with st.popover('Eliminar', icon=':material/delete:', type='tertiary'):
                st.caption('Se borra con sus enlaces. Los archivos en tu equipo no se tocan.')
                if st.button('Eliminar definitivamente', key=f"{key}_drop_{entry['id']}", type='primary', width='stretch'):
                    perform(dj.delete_entry, entry['id'], expected_revision=entry['revision'], message='Entrada eliminada.')


def project_menu(row, key):
    """The project's less frequent actions, the same in the list and in the panel."""
    order, info = row['order'], row['info']
    oid = order['id']
    from views.navigation import open_order
    from views.development_forms import project_form
    with st.popover('Más', icon=':material/more_horiz:', type='tertiary'):
        if st.button('Costos del proyecto', key=f'{key}_costs_{oid}', width='stretch', icon=':material/payments:'):
            st.session_state.update(control_view='Costos y margen', control_cost_order=oid);st.switch_page('views/control.py')
        if st.button('Abrir detalle de piezas y trabajos', key=f'{key}_open_{oid}', width='stretch'):open_order(oid)
        if info['status'] == 'Activo':
            if st.button('Editar objetivo y presupuesto', key=f'{key}_edit_{oid}', width='stretch'):project_form(order)
            if st.button('Cerrar proyecto', key=f'{key}_close_{oid}', width='stretch'):
                perform(development.close_project, oid, message='Proyecto cerrado; su historial se conserva.')
        elif st.button('Reabrir proyecto', key=f'{key}_reopen_{oid}', width='stretch'):
            perform(development.reopen_project, oid, message='Proyecto reabierto.')


def journal_view(data, oid, jobs):
    entries = data['entries']
    if not entries:
        st.info('Aún no hay notas ni reportes. Anota ideas y acuerdos como notas; cada prueba impresa, como reporte técnico con su resultado.',
                icon=':material/edit_note:')
        return
    a, b = st.columns([2, 1], vertical_alignment='bottom')
    search = a.text_input('Buscar en la bitácora', key=f'dev_journal_search_{oid}', icon=':material/search:', placeholder='Título, contenido o impresión')
    kind = b.segmented_control('Mostrar', ('Todo', 'Notas', 'Reportes'), default='Todo', key=f'dev_journal_kind_{oid}', width='stretch') or 'Todo'
    needle = search.strip().casefold()
    shown = [e for e in entries if (kind == 'Todo' or e['kind'] == {'Notas': 'Nota', 'Reportes': 'Reporte'}[kind])
             and needle in f"{e['title']} {e['body']} {e['job_code']}".casefold()]
    if not shown:
        st.caption('Nada coincide con la búsqueda.')
    limit = st.session_state.get(f'dev_journal_limit_{oid}', 8)
    for entry in shown[:limit]:
        entry_card(entry, oid, jobs, 'dev_journal')
    if len(shown) > limit and st.button(f'Ver más · {len(shown) - limit} restantes', key=f'dev_journal_more_{oid}', width='stretch'):
        st.session_state[f'dev_journal_limit_{oid}'] = limit + 8;st.rerun()


def reports_view(data, oid, jobs):
    reports = data['reports']
    if not reports:
        st.info('Sin reportes técnicos todavía. Registra cada prueba con lo que se probó, sus parámetros y su resultado.', icon=':material/lab_research:')
        return
    filters = ('Todos', *dj.RESULTS, 'Sin resultado')
    counts = {'Todos': len(reports), **{r: data['results'][r] for r in dj.RESULTS}, 'Sin resultado': data['results'][None]}
    picked = st.segmented_control('Resultado', filters, default='Todos', key=f'dev_reports_filter_{oid}', width='stretch',
                                  format_func=lambda f: f'{f} · {counts[f]}') or 'Todos'
    shown = [r for r in reports if picked == 'Todos' or result_label(r['result']) == picked]
    table([dict(r, day=fmt(r['created_at']), shown_result=result_label(r['result']), files=len(r['links']) or '—', job=r['job_code'] or '—') for r in shown],
          {'day': 'Fecha', 'title': 'Reporte', 'job': 'Impresión', 'shown_result': 'Resultado', 'files': 'Archivos'},
          label='Reportes técnicos del proyecto', open=picks(f'dev_report_selected_{oid}'), key=f'dev_reports_table_{oid}')
    lookup = {r['id']: r for r in shown}
    if not lookup:
        return
    if st.session_state.get(f'dev_report_selected_{oid}') not in lookup:
        st.session_state[f'dev_report_selected_{oid}'] = next(iter(lookup))
    selected = st.selectbox('Reporte', list(lookup), key=f'dev_report_selected_{oid}', label_visibility='collapsed',
                            format_func=lambda i: f"{fmt(lookup[i]['created_at'])} · {lookup[i]['title']} · {result_label(lookup[i]['result'])}")
    entry_card(lookup[selected], oid, jobs, 'dev_report')


def files_view(data, oid):
    if st.button('Agregar archivo o enlace', key=f'dev_files_add_{oid}', icon=':material/add_link:'):
        development_link_form(oid)
    if not data['links']:
        st.info('Guarda aquí las rutas de modelos, perfiles de slicer, fotos y carpetas del proyecto, o enlaces de Drive y la web. '
                'Se abren con un clic desde este equipo.', icon=':material/folder_open:')
        return
    for link in data['links']:
        link_row(link, 'dev_files', source=True)


def prints_view(row, data):
    jobs, oid = row['jobs'], row['order']['id']
    if not jobs:
        st.info('Este proyecto aún no tiene impresiones.', icon=':material/print:')
        return
    reported = {}
    for r in data['reports']:
        if r['job_code']:
            reported[r['job_code']] = reported.get(r['job_code'], 0) + 1
    table([dict(j, schedule=slot_line(slot(j)) if j['status'] != 'Terminado' else 'Terminada',
                grams=f"{j.get('estimated_grams') or 0:g} g est. · {j.get('actual_consumed_grams') or 0:g} g reales",
                reports=reported.get(j['code'], '—')) for j in jobs],
          {'code': 'Trabajo', 'part_name': 'Pieza', 'material': 'Material', 'machine_code': 'Máquina', 'status': 'Estado',
           'schedule': 'Horario', 'grams': 'Filamento', 'reports': 'Reportes'}, label=f"Impresiones de {row['order']['project']}")
    names = {j['code']: f"{j['code']} · {j['part_name']} · {j['status']}" for j in jobs}
    with st.container(horizontal=True, vertical_alignment='bottom', gap='small'):
        code = st.selectbox('Impresión', list(names), format_func=names.get, key=f'dev_prints_pick_{oid}')
        if st.button('Reporte de esta impresión', key=f'dev_prints_report_{oid}', icon=':material/lab_research:'):
            development_entry_form(oid, jobs, kind='Reporte', job_code=code)


def project_panel(row):
    order, info = row['order'], row['info']
    oid, jobs = order['id'], row['jobs']
    data = dj.journal(oid)
    st.button('Todos los proyectos', key='dev_panel_back', icon=':material/arrow_back:', type='tertiary', on_click=close_panel)
    with card('Prototipo', f'dev-panel-{oid}', gap='small'):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            st.markdown(f"### {plain(order['project'])} :gray[· {order['code']}]")
            st.badge(info['status'], color='violet' if info['status'] == 'Activo' else 'gray', icon=':material/science:')
        if info['goal']:
            st.markdown(f":material/flag: {plain(info['goal'])}")
        with st.container(horizontal=True, gap='small'):
            if st.button('Nota', key=f'dev_panel_note_{oid}', icon=':material/sticky_note_2:'):
                development_entry_form(oid, jobs, kind='Nota')
            if st.button('Reporte técnico', key=f'dev_panel_report_{oid}', icon=':material/lab_research:', type='primary'):
                development_entry_form(oid, jobs, kind='Reporte')
            if st.button('Archivo o enlace', key=f'dev_panel_link_{oid}', icon=':material/add_link:'):
                development_link_form(oid)
            if info['status'] == 'Activo':
                from views.capture_forms import new_print_form
                if st.button('Lanzar impresión', key=f'dev_panel_launch_{oid}', icon=':material/rocket_launch:'):
                    new_print_form(order_id=oid, purpose='Prototipo')
            project_menu(row, 'dev_panel')
        quick = [l for l in data['links'] if l['pinned']]
        if quick:
            st.caption(':material/bolt: Accesos rápidos')
            quick_access(quick, f'dev_panel_quick_{oid}')
    a, b, c, d = st.columns(4)
    results = data['results']
    a.metric('Reportes', len(data['reports']), border=True,
             help=f"{results['Aprobado']} aprobados · {results['Ajustar']} por ajustar · {results['Rechazado']} rechazados · {results[None]} sin resultado")
    b.metric('Impresiones', f"{row['running']} · {row['waiting']} · {row['finished']}", border=True, help='En marcha · en cola · terminadas')
    c.metric('Filamento', f"{row['grams_used']:,.0f} g", border=True, help=f"Reales; {row['grams_estimated']:,.0f} g previstos en total.")
    budget = info['budget_cents']
    d.metric('Costo real', money(row['real_cents']), border=True,
             help=(f"Presupuesto {money(budget)} · " + ('excedido' if row['budget_left'] < 0 else f"quedan {money(row['budget_left'])}")) if budget is not None
             else 'Sin presupuesto definido. Sin IVA; no es venta.')
    counts = {'Bitácora': len(data['entries']), 'Reportes técnicos': len(data['reports']), 'Archivos y enlaces': len(data['links']), 'Impresiones': len(jobs)}
    view = st.segmented_control('Vista del proyecto', VIEWS, default='Bitácora', key=f'dev_panel_view_{oid}', persist_state='session',
                                label_visibility='collapsed', width='stretch', format_func=lambda v: f'{v} · {counts[v]}') or 'Bitácora'
    if view == 'Bitácora':
        journal_view(data, oid, jobs)
    elif view == 'Reportes técnicos':
        reports_view(data, oid, jobs)
    elif view == 'Archivos y enlaces':
        files_view(data, oid)
    else:
        prints_view(row, data)
