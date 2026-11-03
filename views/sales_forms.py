from views.treasury_forms import received_payment_form
import pandas as pd
import streamlit as st

from services import sales as s, quotations as q
from utils.dates import now
from views.common import managed_dialog, perform, reason_form
from views.properties import property_select
from views.navigation import select_order


def select_sale(sale_id):
    st.session_state['open_sale_id'] = sale_id


@managed_dialog('Nueva venta directa', width='large')
def direct_sale_form(source=None):
    d = source["data"] if source else q.defaults()
    st.caption('Registra productos o servicios vendidos sin preparar una cotización. Guarda las partidas juntas y después registra el pago recibido.')
    prefix = 'sale_new_' + st.session_state['dialog_request_key']
    with st.form(prefix):
        a,b = st.columns(2)
        client = property_select('Cliente / empresa *','client',current=d['client'] or 'Público en general',key=prefix+'_client',container=a)
        project = b.text_input('Concepto / referencia',value=d['project'],placeholder='Lámparas Origen · venta de mostrador',key=prefix+'_project')
        a,b,c = st.columns(3)
        sold = a.date_input('Fecha de venta',value=now().date(),max_value=now().date(),key=prefix+'_date')
        channel = b.selectbox('Canal de venta',s.CHANNELS,index=s.CHANNELS.index(source["channel"]) if source else 1,key=prefix+'_channel')
        due = c.date_input('Vencimiento de pago · opcional',value=None,key=prefix+'_due')
        st.caption('Agrega filas al final. Marca Para fabricar solamente si después crearás un pedido de producción.')
        lines = st.data_editor(pd.DataFrame(d['lines'] or [dict(description='',quantity=1.0,price=0.0,produce=False)],columns=['description','quantity','price','produce']),
            key=prefix+'_lines',num_rows='dynamic',hide_index=True,width='stretch',
            column_config={'description':st.column_config.TextColumn('Producto / servicio *',required=True,width='large'),
                'quantity':st.column_config.NumberColumn('Cantidad',min_value=0.001,default=1.0),
                'price':st.column_config.NumberColumn('P. unitario · MXN',min_value=0.0,step=0.01,default=0.0,format='$%.2f'),
                'produce':st.column_config.CheckboxColumn('Para fabricar',default=False)},alt='Partidas de venta directa')
        a,b = st.columns(2)
        discount = a.number_input('Descuento %',min_value=0.0,max_value=100.0,value=float(d['discount']),key=prefix+'_discount')
        iva = b.checkbox('Agregar IVA 16%',value=bool(d['iva']),key=prefix+'_iva')
        notes = st.text_area('Notas',value=d['notes'],key=prefix+'_notes')
        invoice_required = st.checkbox('Lleva factura',key=prefix+'_invoice')
        st.caption('El PDF se puede adjuntar al abrir la venta, en Factura y PDF.')
        st.caption('Los precios se capturan antes del IVA. El registro confirma la venta; el pago y la salida de inventario se registran por separado.')
        a,b = st.columns(2)
        preview = a.form_submit_button('Calcular total',icon=':material/calculate:',width='stretch')
        save = b.form_submit_button('Registrar venta',type='primary',icon=':material/check:',width='stretch')
        if preview or save:
            payload = q.defaults()
            payload.update(client=client,project=project,discount=discount,iva=iva,notes=notes,payment_terms='',conditions='',
                lines=[{k:None if pd.isna(v) else v for k,v in r.items()} for r in lines.to_dict('records')])
            if preview:
                try:
                    totals = q.calculate(payload)['totals']
                    st.text(f"Subtotal {q.money(totals['subtotal'])} · Descuento −{q.money(totals['discount'])} · IVA {q.money(totals['tax'])}")
                    st.success(f"Total calculado: {q.money(totals['total'])} MXN. Pulsa Registrar venta para guardar.")
                except ValueError as exc: st.error(str(exc))
            else:
                perform(s.create_direct,payload,sold.isoformat(),due.isoformat() if due else '',channel,
                    request_key=st.session_state['dialog_request_key'],invoice_required=invoice_required,after=select_sale,navigate='views/sales.py',message='Venta registrada. Puedes capturar el pago recibido.')


@managed_dialog('Registrar venta desde cotización', width='medium')
def quote_sale_form(quote):
    st.write(f"**{quote['code']} · {quote['data']['client']}**")
    st.text(f"Total {q.money(quote['total_cents'])} · Pagado {q.money(quote['paid_cents'])} · Saldo {q.money(quote['balance_cents'])} MXN")
    st.caption('Se conserva el precio aceptado. Los pagos y el pedido existentes se vinculan a la venta sin duplicarse.')
    with st.form('sale_from_quote'):
        sold = st.date_input('Fecha de venta',value=now().date(),max_value=now().date())
        channel = st.selectbox('Canal de venta',s.CHANNELS)
        due = st.date_input('Vencimiento de pago · opcional',value=None)
        invoice_required = st.checkbox('Lleva factura',key='sale_from_quote_invoice')
        if st.form_submit_button('Confirmar y abrir venta',type='primary',icon=':material/check:',width='stretch'):
            perform(s.from_quote,quote['id'],sold.isoformat(),due.isoformat() if due else '',channel,
                request_key=st.session_state['dialog_request_key'],expected_revision=quote['revision'],invoice_required=invoice_required,after=select_sale,
                navigate='views/sales.py',message='Venta registrada. Pagos vinculados sin duplicarlos.')


@managed_dialog('Registrar pago de venta', width='medium')
def sale_payment_form(sale):
    received_payment_form('sale_payment_' + st.session_state['dialog_request_key'], f"**{sale['code']} · {sale['client']}**", '', sale['balance_cents'],
        concept='Liquidación' if not sale['paid_cents'] else 'Abono',
        save=lambda amount, paid_on, method, concept, reference, account_id: perform(s.record_payment, sale['id'], amount, paid_on, method, concept, reference,
            request_key=st.session_state['dialog_request_key'], expected_revision=sale['revision'],
            expected_quote_revision=sale['quote_revision'], account_id=account_id, message='Pago registrado. Saldo actualizado.'))


@managed_dialog('Anular pago de venta', width='small')
def sale_void_form(sale, payment):
    reason_form('sale_void', f"**{payment['code']} · {q.money(payment['amount_cents'])} MXN**", 'Corrige un registro local; no realiza una devolución de dinero. El historial se conserva y, si viene de cotización, también se actualiza allí.', 'Anular registro',
                lambda reason: perform(s.void_payment,sale['id'],payment['id'],reason,message='Pago anulado. Saldo actualizado.'))


@managed_dialog('Cancelar venta', width='medium')
def sale_cancel_form(sale):
    from services import commerce
    if commerce.profile('sale',sale['id']):
        from views.commerce_ui import request_form
        request_form('sale',sale['id']);return
    st.write(f"**{sale['code']} · {sale['client']}**")
    st.caption('La venta dejará de sumar en ventas y saldos. Se conserva el historial; el pedido, la cotización y el inventario requieren su propia gestión.')
    with st.form('sale_cancel'):
        reason = st.text_input('Motivo de cancelación *')
        if st.form_submit_button('Confirmar cancelación',type='primary',width='stretch'):
            perform(s.cancel,sale['id'],reason,expected_revision=sale['revision'],message='Venta cancelada. Historial conservado.')


@managed_dialog('Crear pedido desde venta', width='medium')
def sale_order_form(sale):
    for line in sale['data']['lines']:
        if line['produce']: st.write(f"{line['quantity']:g} × {line['description']}")
    bound=any(l.get('recipe_id') for l in sale['data']['lines'])
    st.caption('Se conservan las recetas y se calculan las reservas juntas. Solo los faltantes fabricados generan piezas de producción.' if bound else 'Se crean los items para fabricar. Después define las piezas o reutiliza una receta en Pedidos.')
    from services import commerce
    if not commerce.state('sale',sale['id'])['production_allowed']:st.info('Edita las condiciones de esta venta para autorizar producción y revisar el anticipo acordado.')
    with st.form('sale_order'):
        due = st.date_input('Fecha comprometida de entrega',value=None)
        if st.form_submit_button('Crear y abrir pedido',type='primary',width='stretch'):
            perform(s.create_order,sale['id'],due.isoformat() if due else '',expected_revision=sale['revision'],
                expected_quote_revision=sale['quote_revision'],after=select_order,navigate='views/orders.py',message='Pedido creado desde la venta.')
