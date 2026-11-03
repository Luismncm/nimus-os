"""Small reusable planned-expense flows with atomic conversion."""
from datetime import date
import streamlit as st
from services import spending_plans,expenses,treasury
from services.quotations import money
from utils.dates import now
from views.common import managed_dialog,perform
from views.emoji import tag


@managed_dialog('Gasto previsto',width='medium')
def planned_expense_form(month,row=None):
    row=row or {};prefix='spending_'+st.session_state['dialog_request_key']
    st.caption('Previsión de '+month+' · Se descontará del saldo estimado. No mueve dinero hasta registrar su pago.')
    with st.form(prefix):
        concept=st.text_input('Concepto *',value=row.get('concept',''),placeholder='Ej. filamento, renta o una compra de equipo')
        a,b=st.columns(2)
        amount=a.number_input('Importe previsto · MXN *',min_value=0.01,value=row['amount_cents']/100 if row else None,step=100.0)
        due=b.date_input('Fecha prevista · opcional',value=date.fromisoformat(row['due_on']) if row.get('due_on') else None)
        accounts={r['id']:r for r in treasury.accounts(active_only=True)}
        options=[None,*accounts]
        selected=row.get('account_id')
        account=st.selectbox('Cuenta prevista',options,index=options.index(selected) if selected in options else 0,
            format_func=lambda i:accounts[i]['name']+' · '+accounts[i]['kind'] if i else 'Por definir')
        with st.expander('Clasificación · opcional'):
            saved=expenses.saved_values('category');category=row.get('category') or 'Sin clasificar'
            if category not in saved:saved.append(category)
            category=st.selectbox('Categoría',saved,index=saved.index(category),accept_new_options=True)
            supplier=st.text_input('Proveedor',value=row.get('supplier',''))
            notes=st.text_area('Notas',value=row.get('notes',''))
        if st.form_submit_button('Guardar previsión',type='primary',width='stretch'):
            if amount is None:st.error('Indica el importe previsto.');return
            perform(spending_plans.save,month,concept,amount,category=category,supplier=supplier,account_id=account,due_on=due,notes=notes,
                plan_id=row.get('id'),expected_revision=row.get('revision'),request_key=st.session_state['dialog_request_key'],message='Gasto previsto guardado.')


@managed_dialog('Registrar gasto previsto',width='medium')
def materialize_form(row):
    prefix='materialize_'+st.session_state['dialog_request_key']
    st.write('**'+row['concept']+' · '+money(row['amount_cents'])+' MXN**')
    st.caption('Al registrarlo, sale automáticamente de Previsión y pasa a Gastos. El saldo estimado no lo descontará dos veces.')
    day=st.date_input('Fecha del gasto',value=now().date(),max_value=now().date(),key=prefix+'_date')
    paid=st.segmented_control('Pago',('Por pagar','Ya pagado'),default='Por pagar',key=prefix+'_state',width='stretch', format_func=tag)=='Ya pagado'
    account=None;method=''
    if paid:
        accounts={r['id']:r for r in treasury.accounts(active_only=True)};options=[None,*accounts]
        default=row['account_id'] if row['account_id'] in options else None
        account=st.selectbox('Cuenta o caja de salida *',options,index=options.index(default),key=prefix+'_account',
            format_func=lambda i:accounts[i]['name'] if i else 'Selecciona una cuenta')
        method=st.selectbox('Forma de pago *',('Transferencia','Efectivo','Tarjeta','Depósito','Otro'),index=None,key=prefix+'_method') or ''
    if st.button('Registrar gasto y pago' if paid else 'Pasar a por pagar',key=prefix+'_save',type='primary',width='stretch',icon=':material/check:'):
        perform(spending_plans.materialize,row['id'],expense_on=day,paid=paid,account_id=account,method=method,
            expected_revision=row['revision'],request_key=st.session_state['dialog_request_key'],message='Previsión registrada como gasto, sin duplicar importes.')


@managed_dialog('Cancelar previsión',width='small')
def cancel_plan_form(row):
    st.write('**'+row['concept']+'**')
    st.caption('Se retirará del saldo proyectado y quedará en el historial. No afecta gastos ni pagos registrados.')
    if st.button('Confirmar cancelación',type='primary',width='stretch'):
        perform(spending_plans.cancel,row['id'],expected_revision=row['revision'],request_key=st.session_state['dialog_request_key'],message='Previsión cancelada.')
