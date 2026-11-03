"""Compact tracking and receipt of future inventory orders."""
from datetime import date
import streamlit as st
from services import inbound,expenses
from services.quotations import money
from utils.dates import now
from views.common import managed_dialog,perform,table,picks
from views.collection_forms import manual_entry_form,focus_inbound
from services.inventory_view import location
from views.purchase_forms import purchase_expense_form
from views.expense_forms import expense_payment_form
from views.work_context import open_record
from services.order_status import STAGES,COLORS
from views.consumables_ui import stepper
from views.common import remembered
from views.emoji import tag


def open_order(identity):
    focus_inbound(identity)
    st.switch_page('views/collection.py')


@managed_dialog('Recibir pedido de inventario',width='medium')
def receive_form(row):
    fresh=inbound.get(row['id'])
    prefix='inbound_receive_'+st.session_state['dialog_request_key']
    st.text(f"{fresh['code']} · {fresh['part']} · {fresh['material']}")
    st.badge(f"{fresh['pending']} unidades pendientes",color='blue')
    st.caption('Destino: '+location(fresh['destination'])+'.')
    if not fresh['pending']:st.info('Este pedido ya no tiene unidades pendientes.');return
    with st.form(prefix):
        qty=st.number_input('Unidades recibidas',min_value=1,max_value=fresh['pending'],value=fresh['pending'],step=1,key=prefix+'_qty')
        day=st.date_input('Fecha de recepción',value=now().date(),min_value=date.fromisoformat(fresh['ordered_on']),max_value=now().date(),key=prefix+'_day')
        notes=st.text_input('Nota / comprobante de recepción',key=prefix+'_notes')
        st.caption('Confirma solo las piezas que llegaron físicamente. El resto seguirá pendiente.')
        if st.form_submit_button('Confirmar recepción',type='primary',width='stretch'):
            perform(inbound.receive,row['id'],qty,received_on=day,notes=notes,expected_token=row['token'],
                request_key=st.session_state['dialog_request_key'],after=lambda _:focus_inbound(row['id']),message='Recepción guardada. Inventario actualizado.')


@managed_dialog('Seguimiento del pedido',width='medium')
def follow_form(row):
    st.text(row['code']+' · '+row['part']+' · ahora: '+row['status'])
    prefix='inbound_follow_'+st.session_state['dialog_request_key']
    with st.form(prefix):
        stage=st.radio('Estado',STAGES,index=STAGES.index(row['stage']) if row['stage'] in STAGES else 0,horizontal=True,key=prefix+'_stage',
            help='Solicitado: enviado al proveedor. Confirmado: el proveedor lo aceptó. En camino: ya se envió. Las recepciones marcan el resto.')
        supplier=st.text_input('Proveedor',value=row['supplier'],key=prefix+'_supplier')
        expected=st.date_input('Llegada prevista',value=date.fromisoformat(row['expected_on']) if row['expected_on'] else None,key=prefix+'_expected')
        notes=st.text_area('Nota de seguimiento',placeholder='Confirmación del proveedor, guía o cambio de fecha',key=prefix+'_notes')
        st.caption('Si solo cambias el estado, la nota es opcional.')
        if st.form_submit_button('Guardar seguimiento',type='primary',width='stretch'):
            perform(inbound.follow_up,row['id'],supplier=supplier,expected_on=expected,notes=notes,expected_token=row['token'],
                stage=stage if stage!=row['stage'] else None,
                request_key=st.session_state['dialog_request_key'],after=lambda _:focus_inbound(row['id']),message='Seguimiento guardado.')


@managed_dialog('Cancelar unidades pendientes',width='small')
def cancel_form(row):
    st.text(f"{row['code']} · cancelar {row['pending']} pendientes de {row['part']}")
    st.caption(f"Las {row['received']} unidades recibidas conservan su entrada al inventario.")
    if row['expense_id']:
        st.caption('Si no hay recepción ni pagos, el gasto pendiente también se cancelará. Si ya recibiste unidades o registraste pagos, se conserva el gasto para ajustar el importe o gestionar la devolución desde su detalle.')
    with st.form('inbound_cancel'):
        reason=st.text_input('Motivo de cancelación *',key='inbound_cancel_reason')
        if st.form_submit_button('Confirmar cancelación',type='primary',width='stretch'):
            perform(inbound.cancel,row['id'],reason,expected_token=row['token'],request_key=st.session_state['dialog_request_key'],
                after=lambda _:focus_inbound(row['id']),message='Unidades pendientes canceladas. Revisa el estado del gasto vinculado.')


def panel():
    rows=inbound.list_orders()
    st.subheader('Pedidos de inventario',icon=':material/local_shipping:')
    st.caption('Da seguimiento a lo solicitado y registra la llegada. El inventario físico aumenta al confirmar la recepción.')
    if st.button('Nuevo pedido de inventario',key='inbound_new',type='primary',icon=':material/add:'):
        manual_entry_form(entry_type='Pedido')
    opened=[r for r in rows if r['pending']]
    with st.container(horizontal=True):
        st.badge(f'{len(opened)} pedidos abiertos',color='gray')
        st.badge(f"{sum(r['pending'] for r in opened)} unidades por recibir",color='blue')
        late=sum(r['overdue'] for r in opened)
        if late:st.badge(f'{late} con fecha vencida',color='orange')
    focus=st.session_state.pop('inbound_panel_focus',None)
    if focus is not None:
        st.session_state['inbound_filter']='Todos'
        st.session_state['inbound_search']=''
        st.session_state['inbound_selected']=focus
    a,b=st.columns(2)
    mode=a.segmented_control('Ver pedidos',('Abiertos','Recibidos','Cancelados','Todos'),default=remembered('inbound_filter', 'Abiertos'),key='inbound_filter', format_func=tag) or 'Abiertos'
    search=b.text_input('Buscar pedido de inventario',placeholder='Pieza, proveedor o referencia',key='inbound_search')
    shown=[r for r in rows if (mode=='Todos' or mode=='Abiertos' and r['pending']>0 or r['status']==mode.rstrip('s'))
        and search.casefold() in f"{r['code']} {r['part']} {r['material']} {r['supplier']} {r['reference']}".casefold()]
    table(shown,{'code':'Pedido','part':'Pieza','supplier':'Proveedor','quantity':'Pedidas','received':'Recibidas','pending':'Pendientes','expected_on':'Llegada prevista','status':'Estado','expense_status':'Gasto'},label='Pedidos de inventario, recepción y estado de gasto',
          open=picks('inbound_selected'),key='inbound_table')
    if not shown:st.caption('No hay pedidos en esta consulta.');return
    lookup={r['id']:r for r in shown}
    if st.session_state.get('inbound_selected') not in lookup:st.session_state['inbound_selected']=next(iter(lookup))
    identity=st.selectbox('Pedido para gestionar',list(lookup),key='inbound_selected',format_func=lambda i:lookup[i]['code']+' · '+lookup[i]['part']+' · '+(lookup[i]['supplier'] or 'Sin proveedor'))
    row=lookup[identity]
    with st.container(border=True,gap='small'):
        with st.container(horizontal=True,horizontal_alignment='distribute'):
            st.text(row['code']+' · '+row['part'])
            st.badge(row['status']+(' · llegada vencida' if row['overdue'] else ''),color='red' if row['overdue'] else COLORS[row['status']])
        stepper(row['status'])
        st.caption(f"{row['supplier'] or 'Sin proveedor'} · Referencia: {row['reference']} · Llegada: {row['expected_on'] or 'Sin fecha'} · {location(row['destination'])}")
        for col,label,key in zip(st.columns(3),('Pedidas','Recibidas','Pendientes'),('quantity','received','pending')):col.metric(label,row[key])
        if row['expense_id']:
            st.badge(row['expense_code']+' · '+row['expense_status'],color='green' if row['expense_status']=='Pagado' else 'gray' if row['expense_status']=='Cancelado' else 'orange',icon=':material/receipt_long:')
            st.caption(f"Compra {money(row['expense_total_cents'])[1:]} · Pagado {money(row['expense_paid_cents'])[1:]} · Por pagar {money(row['expense_balance_cents'])[1:]} MXN")
            with st.container(horizontal=True):
                if row['expense_balance_cents']>0 and row['expense_status']!='Cancelado' and st.button('Registrar pago',key='inbound_expense_pay',icon=':material/payments:'):
                    expense_payment_form(expenses.get_expense(row['expense_id']))
                if st.button('Abrir gasto',key='inbound_expense_open',icon=':material/open_in_new:'):open_record('Gasto',row['expense_id'])
        else:
            st.caption('Pedido anterior sin importe de compra vinculado. Registra su gasto o enlaza uno ya existente.')
            if st.button('Vincular gasto',key='inbound_expense_link',icon=':material/link:'):purchase_expense_form(row)
        if row['pending']:
            with st.container(horizontal=True):
                if st.button('Recibir unidades',key='inbound_receive',type='primary',icon=':material/inventory_2:'):receive_form(row)
                if st.button('Estado y seguimiento',key='inbound_follow',icon=':material/sync_alt:'):follow_form(row)
                with st.popover('Más acciones'):
                    if st.button('Cancelar saldo pendiente',key='inbound_cancel'):cancel_form(row)
        if row['cancelled']:st.caption(f"Se cancelaron {row['remaining']} unidades sin recibir.")
    with st.expander('Historial de seguimiento y recepciones',icon=':material/history:'):
        st.caption('Pedido creado: '+row['ordered_on']+(' · '+row['notes'] if row['notes'] else ''))
        events=[dict(e,quantity=e['payload'].get('quantity'),day=e['payload'].get('received_on',e['created_at'][:10]),
            movement=f"MOV-{e['movement_id']:04d}" if e['movement_id'] else '',
            receipt_state=('Revertida' if e['reversed'] else 'Registrada') if e['movement_id'] else '') for e in row['events']]
        table(events,{'day':'Fecha','kind':'Evento','quantity':'Unidades','movement':'Entrada','receipt_state':'Estado de entrada','notes':'Notas'},label='Seguimiento inalterable del pedido de inventario')
