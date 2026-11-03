import streamlit as st
from services import partners, treasury, reconciliation
from services.quotations import money
from utils.dates import now
from views.common import managed_dialog,perform, reason_form


def focus_injection(cid):
    st.session_state['partner_focus_id']=cid
    for key,value in (('partner_filter','Todos'),('partner_movement','Todos'),('partner_status','Vigentes'),('partner_search','')):
        st.session_state[key]=value
    st.session_state.pop('partner_injection',None)


@managed_dialog('Nueva aportación de socio',width='large')
def injection_form():
    prefix='partner_new_'+st.session_state['dialog_request_key']
    accounts={r['id']:r for r in treasury.accounts(active_only=True)}
    if not accounts:
        st.info('Agrega una cuenta activa en Tesorería → Cuentas antes de registrar la aportación.'); return
    options=sorted(accounts,key=lambda i:(accounts[i]['name']!='Cuenta bancaria NIMUS',accounts[i]['kind']!='Banco',i))
    st.caption('Registra el dinero recibido del socio. La entrada aparecerá una vez en la cuenta elegida y en la relación de Socios.')
    saved=partners.saved_partners()
    if saved:
        def reuse_partner(): st.session_state[prefix+'_partner']=st.session_state[prefix+'_existing'] or ''
        st.selectbox('Reutilizar nombre de socio',saved,index=None,placeholder='Opcional',key=prefix+'_existing',on_change=reuse_partner)
    with st.form(prefix):
        partner=st.text_input('Socio *',key=prefix+'_partner',placeholder='Nombre del socio que aportó')
        a,b=st.columns(2)
        amount=a.number_input('Dinero recibido · MXN *',min_value=.01,value=None,step=100.0,key=prefix+'_amount',placeholder='Importe recibido')
        day=b.date_input('Fecha de recepción *',value=now().date(),max_value=now().date(),key=prefix+'_date')
        account=st.selectbox('Cuenta donde entró el dinero *',options,format_func=lambda i:f"{accounts[i]['name']} · {accounts[i]['kind']}",key=prefix+'_account')
        concept=st.text_input('Concepto *',value='Inyección a cuenta NIMUS',key=prefix+'_concept')
        reference=st.text_input('Referencia bancaria / folio',key=prefix+'_reference',placeholder='Referencia del depósito o transferencia')
        with st.expander('Comprobante y notas'):
            receipt=st.text_input('Comprobante',key=prefix+'_receipt',placeholder='Estado de cuenta, recibo, pendiente…')
            notes=st.text_area('Notas',key=prefix+'_notes',height=80)
        st.caption('Una compra pagada directamente por el socio se registra como gasto cubierto por socio; esta captura corresponde a dinero que entró a una cuenta del negocio.')
        if st.form_submit_button('Registrar aportación',type='primary',width='stretch',icon=':material/add:'):
            perform(partners.register_injection,partner,amount,day.isoformat(),account,concept=concept,reference=reference,receipt=receipt or 'Pendiente',notes=notes,
                request_key=st.session_state['dialog_request_key'],after=focus_injection,navigate='views/partners.py',message='Aportación registrada. Entrada de capital incorporada a la cuenta.')


@managed_dialog('Anular registro de aportación',width='medium')
def void_injection_form(row):
    reason_form('partner_void', f"**SOC-{row['id']:04d} · {row['partner'] or 'Sin identificar'} · {money(row['amount_cents'])} MXN**", 'La captura dejará de sumar en Tesorería y conservará su historial. Esto corrige un registro; una devolución real requiere su movimiento de salida.', 'Confirmar anulación',
                lambda reason: perform(partners.void_injection,row['id'],reason,expected=reconciliation.token(row),message='Registro anulado; historial conservado.'),
                placeholder='Captura duplicada, entrada no realizada…')
