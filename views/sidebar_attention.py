"""Quiet footer entry and an on-demand notification drawer."""
import time
import streamlit as st
from textwrap import shorten
from services import notifications
from services.quotations import money


def open_pending():
    close_panel()
    st.session_state.update(control_view='Avisos',control_alert_state='Pendiente')
    st.switch_page('views/control.py')


def open_notification(row):
    close_panel()
    if row['record_kind'] in ('Pedido','Venta','Gasto'):
        from views.work_context import open_record
        open_record(row['record_kind'],row['record_id'])
    elif row['record_kind']=='Insumo':
        from views.restock_ui import open_restock
        open_restock(row['record_id'])
    elif row['record_kind']=='Pedido de inventario':
        from views.inbound_ui import open_order
        open_order(row['record_id'])
    else:open_pending()


def close_panel():st.session_state['notifications_panel_open']=False


def render_panel():
    if st.session_state.get('notifications_panel_open'):panel()


def current_data():
    """Reuse this run's snapshot; the minute refresh, run alone, reads the database again."""
    fresh=time.monotonic()-st.session_state.get('snapshot_loaded_at',0)<2
    data=notifications.load(st.session_state['snapshot'] if fresh and 'snapshot' in st.session_state else None)
    st.session_state['notifications_data']=data
    return data


@st.dialog('Notificaciones',width='medium',position='right',icon=':material/notifications:',on_dismiss=close_panel)
def panel():
    data=st.session_state.get('notifications_data') or current_data()
    st.caption('Pedidos, dinero y taller · primero lo que requiere atención.')
    with st.container(horizontal=True,gap='small'):
        st.badge(f"{data['total']} pendientes",color='gray')
        if data['priority_count']:st.badge(f"{data['priority_count']} prioritarias",color='red')
    category=st.segmented_control('Tipo de notificación',('Todas',)+notifications.GROUPS,default='Todas',
        key='notifications_category',format_func=lambda g:f"{g} · {data['total'] if g=='Todas' else data['counts'][g]}",
        label_visibility='collapsed') or 'Todas'
    with st.container(horizontal=True,vertical_alignment='bottom'):
        search=st.text_input('Buscar notificación',key='notifications_search',placeholder='Cliente, pedido o concepto…',label_visibility='collapsed')
        priority=st.toggle('Solo prioritarias',key='notifications_priority')
    rows=notifications.select(data,category,search,priority)
    if category in ('Cobros','Pagos'):
        st.metric('Saldo de esta vista · MXN',money(sum(r['amount_cents'] for r in rows)),border=True)
    if not rows:
        st.success('Sin pendientes en esta vista.',icon=':material/check_circle:')
    else:
        slot=st.container()
        pages=(len(rows)+3)//4
        filters=(category,search,priority,pages)
        if st.session_state.get('notifications_filters')!=filters:
            st.session_state['notifications_page_version']=st.session_state.get('notifications_page_version',0)+1
            st.session_state['notifications_filters']=filters
        page_key=f"notifications_page_{st.session_state['notifications_page_version']}"
        page=st.pagination(pages,key=page_key,max_visible_pages=5) if pages>1 else 1
        with slot:
            for row in rows[(page-1)*4:page*4]:
                with st.container(border=True,gap='xxsmall'):
                    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
                        st.badge(row['group'],color='gray')
                        st.badge(row['label'],color=row['color'])
                    st.text(shorten(row['title'],width=120,placeholder='…'))
                    if row['detail']:st.caption(shorten(row['detail'],width=220,placeholder='…'))
                    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
                        if row['amount_cents'] is not None:st.markdown(f"**{money(row['amount_cents'])} MXN** por {'cobrar' if row['group']=='Cobros' else 'pagar'}")
                        label={'Pedido':'Ver pedido','Venta':'Revisar cobro','Gasto':'Revisar pago','Insumo':'Reponer insumo','Material':'Revisar material','Pedido de inventario':'Ver recepción'}.get(row['record_kind'],'Revisar producción')
                        if st.button(label,key='notification_open_'+row['identity'],icon=':material/arrow_forward:'):open_notification(row)
        st.caption(f"{len(rows)} registros · hasta 4 por página")
    with st.expander('Accesos rápidos'):
        with st.container(horizontal=True):
            if st.button('Reposición de insumos',key='sidebar_supplies_open'):
                close_panel()
                from views.restock_ui import open_restock
                open_restock()
            if st.button('Avisos de producción',key='sidebar_pending_open'):open_pending()
    st.caption('Los avisos se retiran al resolver su causa. Abre un registro para atenderlo.')


@st.fragment(run_every='60s')
def render():
    data=current_data()
    # One line: the total, and what needs attention today as a red count inside the same button.
    urgent=data['priority_count']
    label=' '.join(x for x in ('Notificaciones',f":red-badge[{urgent} hoy]" if urgent else '',f"· {data['total']}" if data['total'] else '· al día') if x)
    if st.button(label,key='notifications_open',icon=':material/notifications:',width='stretch',
                 help=(f"{urgent} requieren atención hoy · " if urgent else 'Sin urgencias · ')+f"{data['total']} pendientes en total"):
        st.session_state['notifications_panel_open']=True
        st.rerun()
