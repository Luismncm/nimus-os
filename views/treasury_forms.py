import streamlit as st
from services import treasury
from views.common import managed_dialog,perform


def account_select(prefix):
    rows={r['id']:r for r in treasury.accounts(active_only=True)}
    if not rows:
        st.error('Agrega o activa una cuenta en Tesorería → Cuentas para registrar el cobro.')
        return None
    return st.selectbox('Cuenta donde se recibió *',list(rows),format_func=lambda i:f"{rows[i]['name']} · {rows[i]['kind']}",key=prefix+'_account')


@managed_dialog('Cuenta de tesorería',width='medium')
def account_form(row=None):
    with st.form('treasury_account'):
        name=st.text_input('Nombre *',value=row['name'] if row else '',placeholder='Banco principal, caja del taller…')
        kind=st.selectbox('Tipo de cuenta',treasury.KINDS,index=treasury.KINDS.index(row['kind']) if row else 0)
        active=st.checkbox('Activa para nuevos movimientos',value=bool(row['active']) if row else True)
        st.caption('Las cuentas archivadas conservan su historial. El tipo permite distinguir banco, efectivo y pasarelas.')
        if st.form_submit_button('Guardar cuenta',type='primary',width='stretch'):
            perform(treasury.save_account,name,kind,account_id=row['id'] if row else None,expected_revision=row['revision'] if row else None,active=active,message='Cuenta guardada.')


@managed_dialog('Asignar cuenta al cobro histórico',width='medium')
def assign_account_form(row):
    st.write(f"**{row['code']} · {row['document']}**")
    st.caption('Selecciona dónde se recibió este cobro. La asignación conserva su importe, fecha y saldo.')
    with st.form('treasury_assign'):
        account=account_select('treasury_assign')
        if st.form_submit_button('Confirmar cuenta',type='primary',width='stretch',disabled=account is None):
            perform(treasury.assign_account,row['source'],row['id'],account,message='Cuenta asignada. Importes conservados.')


def received_payment_form(prefix, title, note, balance_cents, save, *, concept='', placeholder=''):
    """Amount, date, method, account, concept and reference of money received; `save` gets them in that order."""
    from services.quotations import money
    from utils.dates import now
    st.write(title)
    st.caption(f"Saldo pendiente: {money(balance_cents)} MXN" + (f". {note}" if note else ''))
    with st.form(prefix):
        a, b = st.columns(2)
        amount = a.number_input('Monto recibido · MXN', min_value=0.01, value=max(0.01, balance_cents/100), step=1.0, key=prefix+'_amount')
        paid_on = b.date_input('Fecha del pago', value=now().date(), max_value=now().date(), key=prefix+'_date')
        method = st.selectbox('Método de pago', ('Transferencia','Efectivo','Depósito','Tarjeta','Pasarela de pago','Otro'), key=prefix+'_method')
        account_id = account_select(prefix)
        concept = st.text_input('Concepto *', value=concept, placeholder=placeholder, key=prefix+'_concept')
        reference = st.text_input('Referencia / folio', key=prefix+'_ref')
        if st.form_submit_button('Guardar pago recibido', type='primary', icon=':material/check:', width='stretch') and account_id is not None:
            save(amount, paid_on.isoformat(), method, concept, reference, account_id)
