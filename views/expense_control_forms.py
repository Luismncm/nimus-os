"""A short expense capture, backed by the existing expense/payment ledger."""
import streamlit as st
from services import expense_control, expenses, treasury
from services.expense_catalog import COST_TYPES
from utils.dates import now
from views.common import managed_dialog, perform
from views.emoji import tag


@managed_dialog('Registrar gasto', width='medium')
def quick_expense_form():
    prefix = 'quick_expense_' + st.session_state['dialog_request_key']
    st.caption('Registra lo básico. El comprobante, IVA y demás datos se pueden completar después desde el gasto.')
    concept = st.text_input('Concepto *', key=prefix+'_concept', placeholder='Ej. filamento, renta o envío')
    a, b = st.columns(2)
    amount = a.number_input('Importe total · MXN *', min_value=0.01, value=None, step=1.0, key=prefix+'_amount', placeholder='Total del gasto')
    day = b.date_input('Fecha del gasto', value=now().date(), max_value=now().date(), key=prefix+'_date')
    category = st.selectbox('Categoría · opcional', expenses.saved_values('category'), index=None,
                            accept_new_options=True, key=prefix+'_category', placeholder='Selecciona, escribe o completa después')
    state = st.segmented_control('Pago', ('Por pagar','Ya pagado'), default='Por pagar', key=prefix+'_state', width='stretch', format_func=tag) or 'Por pagar'
    paid = state == 'Ya pagado'
    account_id = None; method = ''; paid_on = day
    if paid:
        accounts = {r['id']: r for r in treasury.accounts(active_only=True)}
        account_id = st.selectbox('Cuenta o caja de salida *', list(accounts), index=None, key=prefix+'_account',
                                  format_func=lambda i: accounts[i]['name']+' · '+accounts[i]['kind'], placeholder='Con qué cuenta o efectivo pagaste')
        a, b = st.columns(2)
        method = a.selectbox('Forma de pago *', ('Transferencia','Efectivo','Tarjeta','Depósito','Otro'), index=None, key=prefix+'_method')
        paid_on = b.date_input('Fecha del pago', value=day, max_value=now().date(), key=prefix+'_paid_on')
        if not accounts:
            st.caption('Agrega una cuenta bancaria o caja desde Tesorería antes de registrar un pago.')
    supplier = st.session_state.get(prefix+'_supplier','')
    nature = st.session_state.get(prefix+'_nature','Variable')
    due = st.session_state.get(prefix+'_due') if not paid else None
    notes = st.session_state.get(prefix+'_notes','')
    with st.expander('Más datos · opcional', key=prefix+'_more', on_change='rerun'):
        supplier = st.text_input('Proveedor', key=prefix+'_supplier',persist_state='session')
        nature = st.selectbox('Naturaleza', COST_TYPES, key=prefix+'_nature',persist_state='session')
        if not paid:
            due = st.date_input('Vencimiento', value=None, key=prefix+'_due',persist_state='session')
            accounts={r['id']:r for r in treasury.accounts(active_only=True)}
            account_id=st.selectbox('Cuenta prevista · opcional',[None,*accounts],key=prefix+'_planned_account',
                format_func=lambda i:accounts[i]['name'] if i else 'Por definir',persist_state='session')
        notes = st.text_input('Notas', key=prefix+'_notes',persist_state='session')
    if st.button('Guardar gasto y pago' if paid else 'Guardar gasto por pagar', type='primary', width='stretch',
                  icon=':material/check:', key=prefix+'_save'):
        if amount is None:
            st.error('Indica el importe del gasto.'); return
        perform(expense_control.register, concept=concept, amount=amount, expense_on=day, category=category or '',
                paid=paid, account_id=account_id, method=method or '', paid_on=paid_on, supplier=supplier,
                cost_type=nature, due_on=due, notes=notes, request_key=st.session_state['dialog_request_key'],
                message='Gasto y pago registrados.' if paid else 'Gasto registrado como pendiente de pago.')
