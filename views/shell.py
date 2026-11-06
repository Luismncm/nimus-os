"""Native application navigation and shared page hierarchy."""
import sqlite3
import streamlit as st
from db import backup_database
from services.queries import csv_bytes,export_rows,PART_EXPORT_FIELDS
from utils.dates import now

VERSION='0.71'
AREAS=('Taller','Negocio')
# Path and full title stay stable for existing links, dialogs and saved context.
# The label is what people read: sidebar entry, search result and page heading.
PAGES=(
    ('today','Hoy','Hoy','today','Taller','Trabajo diario','Prioridades, capacidad y próximos cobros y pagos.'),
    ('orders','Pedidos','Pedidos','inventory_2','Taller','Trabajo diario','Sigue cada pedido desde la planificación hasta la entrega.'),
    # The print agenda now lives in the queue (Calendario view): one place to capture, schedule and run prints.
    ('queue','Cola de producción','Cola de producción','format_list_bulleted','Taller','Producción','Captura, horario y operación de cada impresión, por máquina o en calendario.'),
    ('development','Desarrollo y prototipos','Desarrollo y prototipos','science','Taller','Producción','Impresiones de prototipo con su filamento, insumos y costo; no son ventas.'),
    ('control','Control de producción','Control de producción','fact_check','Taller','Producción','Capacidad, fallas, costos reales y avisos del taller.'),
    ('origen','Colección Origen','Colección Origen','light','Taller','Productos y existencias','Modelos, variantes, recetas y pedidos en un solo espacio.'),
    ('collection','Inventario','Inventario','warehouse','Taller','Productos y existencias','Piezas, insumos y filamento fuera de Colección Origen: existencias, compras, reservas y movimientos.'),
    ('catalog','Catálogo y recetas','Catálogo y recetas','menu_book','Taller','Productos y existencias','Define productos y piezas para reutilizar sus recetas.'),
    ('machines','Máquinas','Máquinas','precision_manufacturing','Taller','Equipo','Equipos, disponibilidad y carga; sus impresiones se operan en la cola.'),
    ('sales','Ventas','Ventas y cobranza','point_of_sale','Negocio','Comercial','Ventas confirmadas, cobros y seguimiento comercial.'),
    ('quotations','Cotizaciones','Cotizaciones','request_quote','Negocio','Comercial','Precios, acuerdos y alcance antes de confirmar la venta.'),
    # The three money pages in the order money moves: what is coming, what was spent, where it sits.
    ('budget','Control de gastos','Resumen y previsión','savings','Negocio','Control financiero','Saldo en cuentas, pagos pendientes y previsión de gastos.'),
    ('expenses','Gastos','Gastos y comprobantes','receipt_long','Negocio','Control financiero','Detalle de gastos, comprobantes, pagos y costos recurrentes.'),
    ('treasury','Resumen y cuentas','Tesorería','account_balance','Negocio','Control financiero','Banco, caja, movimientos y conciliación.'),
    ('partners','Socios','Socios y aportaciones','group','Negocio','Control financiero','Capital recibido, compras del socio y reembolsos.'),
    ('costs','Costos y utilidad','Costos y utilidad','calculate','Negocio','Rentabilidad','Costos de recetas y utilidad bruta estimada por venta.'),
    ('performance','Estado de rendimiento','Estado de rendimiento','monitoring','Negocio','Rentabilidad','Ventas, cobros, gastos, entregas y producción del período, comparados con el anterior.'),
)

def registry():
    return [dict(zip(('key','title','label','icon','area','group','description'),row),path=f'views/{row[0]}.py') for row in PAGES]

def navigation():
    return st.navigation([st.Page(row['path'],title=row['title'],icon=f":material/{row['icon']}:",default=row['key']=='today') for row in registry()],position='hidden')

def sidebar(page,snapshot):
    rows=registry();current=next(r for r in rows if r['title']==page.title)
    if st.session_state.get('shell_last_page')!=page.title:
        st.session_state.update(shell_area=current['area'],shell_last_page=page.title,shell_jump=None)
    if st.session_state.pop('shell_jump_reset',False):st.session_state['shell_jump']=None
    with st.sidebar:
        # Fixed order: attention, search, area, pages, tools. Switching areas never moves the first three.
        from views.sidebar_attention import render as render_attention
        render_attention()
        by_key={r['key']:r for r in rows}
        jump=st.selectbox('Buscar sección',list(by_key),index=None,key='shell_jump',placeholder='Ir a una sección…',
            format_func=lambda k:f"{by_key[k]['label']} · {by_key[k]['area']}",label_visibility='collapsed')
        if jump:
            st.session_state['shell_jump_reset']=True
            st.switch_page(by_key[jump]['path'])
        area=st.segmented_control('Área de navegación',AREAS,key='shell_area',width='stretch',label_visibility='collapsed',
            format_func=lambda a:f":material/{'construction' if a=='Taller' else 'storefront'}: {a}") or current['area']
        from views.nav_status import badges,render_printers
        counts=badges(snapshot)
        with st.container(gap='xxsmall',key='nav-pages'):
            for group in dict.fromkeys(r['group'] for r in rows if r['area']==area):
                st.caption(group)
                for row in rows:
                    if row['area']==area and row['group']==group:
                        # A live count beside the page: what needs a look there now, in gray when nothing does.
                        badge,why=counts.get(row['key'],('',None))
                        # The page you are on sits in a keyed slot, so the theme marks it with the area's accent.
                        with st.container(key='nav-current') if row['key']==current['key'] else st.container():
                            st.page_link(row['path'],label=f"{row['label']} {badge}".strip(),icon=f":material/{row['icon']}:",width='stretch',help=why)
        if area!=current['area']:
            st.caption(f"Estás en {current['label']} · {current['area']}")
        # Hoy, the queue and Máquinas already show every printer: the sidebar list would repeat them.
        if area=='Taller' and current['key'] not in ('today','queue','machines'):
            with st.container(key='nav-floor'):render_printers()
        tools(snapshot)
    return current

def tools(snapshot):
    # An inline expander keeps the sidebar's colors; a popover here renders dark text on the dark panel.
    with st.expander('Herramientas',icon=':material/tune:'):
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            st.caption(f"Datos leídos {now():%H:%M}")
            if st.button('Actualizar',key='shell_refresh',icon=':material/refresh:',type='tertiary'):st.rerun()
        st.toggle('Reducir movimiento del tablero',key='ui_reduce_motion')
        st.caption('Exportar')
        # Built only when downloaded; downloading does not rerun the page.
        st.download_button('CSV de producción',lambda:csv_bytes(export_rows(snapshot)),file_name='nimus_production_export.csv',
            mime='text/csv',width='stretch',icon=':material/download:',on_click='ignore')
        st.download_button('CSV de piezas',lambda:csv_bytes(snapshot['parts'],PART_EXPORT_FIELDS),file_name='nimus_parts.csv',
            mime='text/csv',width='stretch',icon=':material/download:',on_click='ignore')
        st.caption('Respaldo')
        if st.button('Crear respaldo',icon=':material/backup:',width='stretch'):
            try:
                path=backup_database()
                st.success(f'Respaldo creado: {path.name}',icon=':material/check_circle:')
                st.caption(f'Carpeta: {path.parent}. Cópialo a otro disco de vez en cuando.')
            except (OSError,sqlite3.DatabaseError) as exc:
                st.error(f'No se pudo respaldar: {exc}')
        st.caption(f'NIMUS OS v{VERSION} · datos guardados en este equipo')

def actions():
    """The page's actions, at the right of its title, so every page creates from the same place."""
    slot=st.session_state.get('_page_actions')
    return slot if slot is not None else st.container(horizontal=True,horizontal_alignment='right',vertical_alignment='center',gap='small')


def header(page,current,snapshot):
    """Title and date on one line; where you are and what the page is for on the line below."""
    detail=page.title=='Pedidos' and any(o['id']==st.session_state.get('open_order_id') for o in snapshot['orders'])
    trail=' / '.join((current['area'],current['group'],current['label'])+(('Detalle',) if detail else ()))
    with st.container(gap='xxsmall'):
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            if detail:st.caption(trail)
            else:st.header(current['label'],icon=page.icon,width='content')
            with st.container(horizontal=True,horizontal_alignment='right',vertical_alignment='center',gap='small',width='content'):
                # Every page puts its own actions here, beside its title: create first, the main one filled.
                st.session_state['_page_actions']=st.container(horizontal=True,horizontal_alignment='right',vertical_alignment='center',gap='small',width='content')
        # Where you are is already marked in the sidebar: the line under the title only says what the page is for.
        if not detail:
            st.caption(current['description'])
