from views.treasury_forms import received_payment_form
import streamlit as st
from services import quotations as q
from views.common import managed_dialog, perform, reason_form
from views.navigation import select_order


@managed_dialog('Registrar pago recibido', width='medium')
def payment_form(quote):
    received_payment_form('payment_' + st.session_state['dialog_request_key'], f"**{quote['code']} · {quote['data']['client']}**",
        'Este registro no procesa cobros ni transferencias.', quote['balance_cents'], placeholder='Anticipo, abono o liquidación',
        save=lambda amount, paid_on, method, concept, reference, account_id: perform(q.record_payment, quote['id'], amount, paid_on, method, concept, reference,
            request_key=st.session_state['dialog_request_key'], expected_revision=quote['revision'], account_id=account_id, message='Pago registrado. Saldo actualizado.'))


@managed_dialog('Crear pedido desde cotización', width='medium')
def convert_form(quote):
    lines = [r for r in quote['data']['lines'] if r['produce']]
    st.write(f"**{quote['code']} → {len(lines)} items para fabricar**")
    for line in lines: st.write(f"{line['quantity']:g} × {line['description']}")
    bound=any(l.get('recipe_id') for l in lines)
    st.caption('Las recetas se conservan y las reservas se calculan juntas. Los servicios permanecen en la cotización.' if bound else 'Se crea el pedido con estos items. Después define sus piezas o reutiliza despieces. Los servicios permanecen solo en la cotización.')
    st.text(f"Pagado: {q.money(quote['paid_cents'])} · Saldo: {q.money(quote['balance_cents'])}.")
    st.caption('Revisa las condiciones de anticipo antes de programar producción.')
    with st.form('quote_convert'):
        deadline = st.date_input('Fecha comprometida de entrega', value=None)
        if st.form_submit_button('Crear y abrir pedido', type='primary', icon=':material/arrow_forward:', width='stretch'):
            perform(q.convert_to_order, quote['id'], deadline.isoformat() if deadline else '',
                    expected_revision=quote['revision'], after=select_order, navigate='views/orders.py', message='Pedido creado con sus recetas y faltantes.' if bound else 'Pedido creado. Define el despiece para planificar producción.')


@managed_dialog('Anular registro de pago', width='small')
def void_payment_form(payment):
    reason_form('payment_void', f"**{payment['code']} · {q.money(payment['amount_cents'])} MXN**", 'Corrige el registro local y recupera el saldo. No emite devoluciones de dinero. El pago original permanece en el historial.', 'Anular registro',
                lambda reason: perform(q.void_payment, payment['id'], reason, message='Registro anulado; historial conservado.'))
