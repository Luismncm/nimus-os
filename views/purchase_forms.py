"""Inventory purchases share the existing expense and payment workflows."""
import streamlit as st
from services import expenses,treasury,inbound
from services.quotations import money
from utils.dates import now
from views.common import managed_dialog,perform
from views.emoji import tag


def financial_fields(prefix):
    st.markdown('**Gasto de la compra**')
    amount=st.number_input('Total del pedido · MXN *',min_value=0.01,value=None,step=1.0,key=prefix+'_total',placeholder='Total de todas las unidades, con cargos incluidos')
    state=st.segmented_control('Estado del gasto',('Por pagar','Ya pagado'),default='Por pagar',key=prefix+'_payment_state',width='stretch', format_func=tag) or 'Por pagar'
    accounts={r['id']:r for r in treasury.accounts(active_only=True)}
    a,b=st.columns(2)
    account=a.selectbox('Cuenta prevista / de pago',[None,*accounts],format_func=lambda i:accounts[i]['name'] if i else 'Por definir',key=prefix+'_account')
    method=b.selectbox('Forma de pago si ya pagaste',('Transferencia','Efectivo','Tarjeta','Depósito','Otro'),index=None,key=prefix+'_method',placeholder='Sólo para gastos pagados')
    st.caption('Ya pagado requiere cuenta y forma de pago. Recibir el inventario no repetirá el gasto.')
    with st.expander('Fechas y categoría del gasto · opcional'):
        a,b=st.columns(2)
        paid_on=a.date_input('Fecha del pago',value=now().date(),max_value=now().date(),key=prefix+'_paid_on')
        due=b.date_input('Vencimiento del pago',value=None,key=prefix+'_due')
        options=expenses.saved_values('category');default='Producción / materiales'
        if default not in options:options.append(default)
        category=st.selectbox('Categoría del gasto',options,index=options.index(default),accept_new_options=True,key=prefix+'_category')
    return dict(amount=amount,paid=state=='Ya pagado',account_id=account,method=method or '',paid_on=paid_on,due_on=due,category=category)


@managed_dialog('Gasto del pedido de inventario',width='medium')
def purchase_expense_form(row):
    prefix='purchase_'+st.session_state['dialog_request_key']
    st.text(row['code']+' · '+row['part'])
    mode=st.segmented_control('Vinculación',('Crear gasto','Usar gasto existente'),default='Crear gasto',key=prefix+'_mode',width='stretch', format_func=tag) or 'Crear gasto'
    if mode=='Crear gasto':
        with st.form(prefix):
            financial=financial_fields(prefix)
            if st.form_submit_button('Guardar gasto vinculado',type='primary',width='stretch'):
                perform(inbound.attach_expense,row['id'],financial=financial,expected_token=row['token'],request_key=st.session_state['dialog_request_key'],message='Gasto vinculado al pedido.')
    else:
        linked={r['expense_id'] for r in inbound.list_orders() if r['expense_id']}
        rows={r['id']:r for r in expenses.list_expenses() if r['status']=='Activo' and r['id'] not in linked}
        search=st.text_input('Buscar gasto existente',key=prefix+'_search',placeholder='Folio, concepto o proveedor')
        rows={i:r for i,r in rows.items() if search.casefold() in (r['code']+' '+r['concept']+' '+r['supplier']).casefold()}
        if not rows:st.info('No hay gastos disponibles en esta consulta.');return
        with st.form(prefix+'_existing'):
            eid=st.selectbox('Gasto existente',list(rows),key=prefix+'_expense',format_func=lambda i:rows[i]['code']+' · '+rows[i]['concept']+' · '+money(rows[i]['total_cents']))
            st.caption('Se conserva el gasto y sus pagos. Esta acción sólo lo vincula al pedido y no genera otra salida de dinero.')
            if st.form_submit_button('Vincular gasto existente',type='primary',width='stretch'):
                perform(inbound.attach_expense,row['id'],existing_expense_id=eid,expected_expense_revision=rows[eid]['revision'],
                    expected_token=row['token'],request_key=st.session_state['dialog_request_key'],message='Gasto existente vinculado sin duplicar registros.')
