"""Small session-only continuation links; no business state is changed here."""
import streamlit as st

TARGETS={'Pedido':('open_order_id','views/orders.py'),'Venta':('open_sale_id','views/sales.py'),
         'Gasto':('open_expense_id','views/expenses.py'),'Cotización':('open_quote_id','views/quotations.py')}


def remember(kind,identity,label):
    st.session_state['last_work_record']={'kind':kind,'id':identity,'label':label}


def open_record(kind,identity):
    key,page=TARGETS[kind]
    st.session_state[key]=identity
    if kind=='Pedido': st.session_state.pop('focus_item_id',None)
    st.switch_page(page)


def continue_button():
    record=st.session_state.get('last_work_record')
    if record and st.button(f"Continuar · {record['label']}",key='today_continue',icon=':material/history:',type='tertiary'):
        open_record(record['kind'],record['id'])
