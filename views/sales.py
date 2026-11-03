from services import sale_corrections as corrections, invoices
from views.invoice_forms import invoice_panel
from views.costing_forms import sale_cost_panel
from views.sale_correction_forms import delete_sale_form,remove_lines_form
from views.common import perform
from views.work_context import remember
import streamlit as st
from services import sales as s, quotations as q
from services.quotation_document import document
from utils.dates import now
from views.common import table
from views.treasury_components import opens
from views.navigation import select_order
from views.origin_cart import open_cart
from views.sales_forms import (select_sale,direct_sale_form,quote_sale_form,sale_payment_form,
                               sale_void_form,sale_cancel_form,sale_order_form)
from views.emoji import icon_tabs


selected = st.session_state.get('open_sale_id')
if not selected:
    linked = {r['quote_id'] for r in s.list_sales(include_deleted=True) if r['quote_id']}
    available = {r['id']:r for r in q.list_quotes() if r['status']=='Aceptada' and r['id'] not in linked}
    from views.shell import actions
    with actions():
        # Accepted quotations become sales from here; the count says when there is one waiting.
        with st.popover(f'Desde cotización · {len(available)}',icon=':material/request_quote:'):
            if available:
                qid = st.selectbox('Cotización aceptada',list(available),format_func=lambda i:f"{available[i]['code']} · {available[i]['client']} · {q.money(available[i]['total_cents'])}",key='sale_quote_select')
                if st.button('Registrar esta cotización como venta',key='sale_from_quote',icon=':material/arrow_forward:'):
                    quote_sale_form(q.get_quote(qid))
            else: st.caption('Acepta una cotización para registrarla aquí. Una cotización se registra como venta una sola vez.')
        if st.button('Venta de Origen',key='sale_new_origin',icon=':material/light:'):
            from views.origin_cart import open_cart
            open_cart(mode='Venta confirmada')
        if st.button('Nueva venta directa',key='sale_new',type='primary',icon=':material/add:'):
            direct_sale_form()
    with st.container(border=True):
        a,b,c = st.columns([1,1,2])
        start = a.date_input('Desde',value=now().date().replace(day=1),key='sales_start',persist_state='session')
        end = b.date_input('Hasta',value=now().date(),key='sales_end',persist_state='session')
        search = c.text_input('Buscar venta',placeholder='Cliente, concepto, VEN o COT',key='sales_search',icon=':material/search:',persist_state='session')
        with st.expander('Filtrar por origen, canal y cobranza',icon=':material/filter_alt:'):
            a,b,c = st.columns(3)
            origin = a.selectbox('Origen',('Todos','Directa','Cotización'),key='sales_origin',persist_state='session')
            channel = b.selectbox('Canal',('Todos',*s.CHANNELS),key='sales_channel',persist_state='session')
            status = c.selectbox('Cobranza',('Todos','Por cobrar','Pago parcial','Liquidada','Cancelada'),key='sales_status',persist_state='session')
        applied = [v for v in (origin,channel,status) if v!='Todos']
        if applied: st.caption('Filtros activos: '+' · '.join(applied))
    if start>end:
        st.warning('La fecha Desde debe ser anterior o igual a Hasta.')
        st.stop()
    report = s.report(start,end,search=search,channel=channel,origin=origin,payment_status=status)
    from views.treasury_components import money_pulse
    money_pulse([
        ('Vendido en el período',q.money(report['sold_cents']),'calm'),
        ('Cobrado en el período',q.money(report['collected_cents']),'calm'),
        ('Saldo de estas ventas',q.money(report['balance_cents']),'orange' if report['balance_cents'] else 'calm'),
        ('Ventas activas',str(report['count']),'calm'),
    ],key='sales-pulse')
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.text(f"Cartera total: {q.money(report['total_balance_cents'])} · Vencido: {q.money(report['overdue_cents'])} MXN")
        with st.popover('Sobre los totales',icon=':material/info:'):
            st.write('Vendido y saldo usan la fecha de venta. Cobrado usa la fecha del pago, incluso de ventas anteriores al período. Todos respetan los filtros; cancelaciones y pagos anulados no suman.')
            st.write('Cartera total y vencido abarcan todas las fechas y respetan cliente, origen, canal y cobranza. Los anticipos de cotizaciones sin venta registrada permanecen en Cotizaciones.')
    sales_tab,receipts_tab = icon_tabs(['Registro de ventas','Cobros del período'],key='sales_tabs',on_change='rerun')
    with sales_tab:
        rows = report['rows']
        invoice_states=invoices.statuses('sale')
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            st.subheader(f"{len(rows)} {'venta' if len(rows)==1 else 'ventas'} en la consulta", icon=':material/point_of_sale:')
            st.download_button('Exportar ventas CSV',s.export_csv(rows),file_name='NIMUS_ventas.csv',mime='text/csv',icon=':material/download:',disabled=not rows)
        # Each sale names what it comes from and what it feeds: its quotation's folio (or Directa) and its order's.
        order_codes={o['id']:o['code'] for o in st.session_state['snapshot']['orders']}
        table([dict(r,invoice=invoice_states.get(r['id'],'Por definir'),total=q.money(r['total_cents']),paid=q.money(r['paid_cents']),balance=q.money(r['balance_cents']),due=r['due_on'] or '—',
                    source=r['quote_code'] or r['origin'],order=order_codes.get(r['order_id'],'—') if r['order_id'] else '—') for r in rows],
            {'code':'Venta','sold_on':'Fecha','client':'Cliente','project':'Concepto','source':'Origen','order':'Pedido','channel':'Canal','total':'Total MXN','paid':'Pagado','balance':'Saldo','payment_status':'Cobranza','due':'Vencimiento','invoice':'Factura'},label='Control general de ventas',
            open=opens('Venta'),key='sales_table')
        if rows:
            by_id = {r['id']:r for r in rows}
            # Picking a row above opens the sale; the list below does the same from the keyboard.
            a,b = st.columns([4,1],vertical_alignment='bottom')
            sid = a.selectbox('Abrir venta',list(by_id),format_func=lambda i:f"{by_id[i]['code']} · {by_id[i]['client']} · {by_id[i]['project'] or by_id[i]['payment_status']}",key='sales_selected_row')
            if b.button('Ver detalle',key='sale_open',type='primary',width='stretch',icon=':material/arrow_forward:'):
                select_sale(sid)
                st.rerun()
            # Deleting lives in the sale's own Más opciones, read after its detail, never one click from opening it.
        else: st.info('Registra una venta directa, incorpora una cotización aceptada o ajusta las fechas.')
    with receipts_tab:
        sales = {r['id']:r for r in s.list_sales()}
        table([dict(p,sale=sales[p['sale_id']]['code'],client=sales[p['sale_id']]['client'],amount=q.money(p['amount_cents'])) for p in report['receipts']],
            {'code':'Recibo','sale':'Venta','client':'Cliente','paid_on':'Fecha','method':'Método','account_name':'Cuenta','concept':'Concepto','amount':'Monto MXN','reference':'Referencia'},label='Cobros vigentes del período')
    # Deleted sales wait at the end of the page, out of the way of the day's work.
    removed=corrections.trash_rows()
    with st.expander(f'Papelera de ventas · {len(removed)}',icon=':material/delete:'):
        if not removed: st.caption('No hay ventas eliminadas.')
        for r in removed:
            st.write(f"**{r['code']} · {r['client']}** · {r['reason']}")
            if st.button('Restaurar venta',key=f"sale_restore_{r['sale_id']}"):
                perform(corrections.restore_sale,r['sale_id'],expected_revision=r['revision'],message='Venta restaurada.')
    st.stop()

sale = s.get_sale(selected)
remember('Venta',sale['id'],sale['code'])
if sale['deleted']:
    st.info('Esta venta está en Papelera. Puedes recuperarla desde el listado de ventas.')
    if st.button('Volver al listado',key='deleted_sale_back'):
        st.session_state.pop('open_sale_id',None)
        st.rerun()
    st.stop()
d = sale['data']
# Back on the left of the content, the sale's own action beside the page title.
if st.button('Todas las ventas',key='sale_back',icon=':material/arrow_back:',type='tertiary'):
    st.session_state.pop('open_sale_id',None)
    st.rerun()
from views.shell import actions
with actions():
    if st.button('Reutilizar venta',key='sale_reuse',icon=':material/content_copy:',help='Crea una venta nueva con las mismas partidas.'):
        if any(l.get('recipe_id') for l in sale['data']['lines']):open_cart(mode='Venta confirmada',source=sale)
        else:direct_sale_form(sale)
with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
    st.subheader(f"{sale['code']} · {sale['client']}")
    st.badge(sale['payment_status'],color='green' if sale['payment_status']=='Liquidada' else 'red' if sale['status']=='Cancelada' else 'orange')
st.caption(f"{sale['sold_on']} · {sale['channel']} · {sale['origin']} · {d['project'] or 'Venta sin referencia adicional'}")
owed = sale['status']=='Activa' and sale['balance_cents']>0
with st.container(horizontal=True,vertical_alignment='center',gap='small'):
    if sale['overdue']: st.badge(f"Pago vencido desde {sale['due_on']}",color='red',icon=':material/warning:')
    elif sale['due_on']: st.caption(f"Vencimiento de pago: {sale['due_on']}",width='content')
    # A balance without a due date never turns overdue in Hoy or the portfolio: say so and let it be set here.
    elif owed: st.badge('Saldo sin vencimiento: nunca aparecerá como vencido',color='orange',icon=':material/event_busy:')
    if owed:
        with st.popover('Fijar vencimiento' if not sale['due_on'] else 'Cambiar vencimiento',icon=':material/edit_calendar:'):
            due=st.date_input('Vencimiento de pago',value=sale['due_on'] or None,min_value=sale['sold_on'],key=f"sale_due_{sale['id']}")
            if st.button('Guardar vencimiento',key=f"sale_due_save_{sale['id']}",type='primary',disabled=not due):
                perform(s.set_due_date,sale['id'],due.isoformat(),expected_revision=sale['revision'],message='Vencimiento guardado.')
if sale['status']=='Cancelada': st.warning(f"Venta cancelada: {sale['cancel_reason']}. Excluida de los totales activos.")
a,b,c = st.columns(3)
a.metric('Total · MXN',q.money(sale['total_cents']),border=True)
b.metric('Pagado',q.money(sale['paid_cents']),border=True)
c.metric('Saldo de la operación' if sale['status']=='Cancelada' else 'Por cobrar',q.money(sale['balance_cents']),border=True)
with st.container(horizontal=True,vertical_alignment='center'):
    if st.button('Registrar pago',key='sale_payment',type='primary',icon=':material/payments:',disabled=sale['status']!='Activa' or sale['balance_cents']<=0):
        sale_payment_form(sale)
    if sale['quote_id'] and st.button(f"Ver {sale['quote_code']}",key='sale_quote_open',icon=':material/request_quote:'):
        st.session_state['open_quote_id']=sale['quote_id']
        st.switch_page('views/quotations.py')
    if sale['order_id']:
        if st.button('Abrir pedido',key='sale_order_open',icon=':material/inventory_2:'):
            select_order(sale['order_id'])
            st.switch_page('views/orders.py')
    elif any(r['produce'] for r in d['lines']) and sale['status']=='Activa':
        if st.button('Crear pedido',key='sale_order',icon=':material/inventory_2:'): sale_order_form(sale)
    # A cancelled sale can still go to Papelera, so the menu stays; only cancelling needs an active sale.
    with st.popover('Más opciones',icon=':material/more_horiz:'):
        if st.button('Eliminar venta',key='sale_delete',icon=':material/delete:'): delete_sale_form(sale)
        if sale['status']=='Activa':
            st.caption('Para cancelar, primero revisa los pagos vigentes. No se eliminan registros.')
            if st.button('Cancelar venta',key='sale_cancel',disabled=bool(sale['paid_cents'])): sale_cancel_form(sale)
from views.commerce_ui import panel as commercial_panel
commercial_panel('sale',selected)
if any(l.get('recipe_id') for l in d['lines']) and st.button('Copiar al carrito para otro alcance',key='sale_copy_cart',icon=':material/content_copy:'):
    from views.origin_cart import open_cart
    open_cart(mode='Cotización',source=sale)
detail,payments,invoice_tab,cost_tab = icon_tabs(['Detalle de venta','Pagos e historial','Factura y PDF','Costos y utilidad'],key=f'sale_tabs_{selected}',on_change='rerun')
with cost_tab:
    sale_cost_panel(selected)
with invoice_tab:
    invoice_panel('sale',selected)
with detail:
    lock=corrections.line_lock(sale)
    if st.button('Eliminar partidas',key='sale_remove_lines',icon=':material/delete:',disabled=bool(lock)):
        remove_lines_form(sale)
    if lock:st.caption(lock)
    table([dict(r,unit=q.money(q.cents(r['price'])),amount=q.money(r['amount_cents'])) for r in d['lines']],
        {'description':'Producto / servicio','quantity':'Cantidad','unit':'P. unitario MXN','amount':'Importe MXN','produce':'Para fabricar'},label='Partidas confirmadas de venta')
    t=d['totals']
    st.text(f"Subtotal {q.money(t['subtotal'])} · Descuento −{q.money(t['discount'])} · IVA {q.money(t['tax'])} MXN")
    if d['notes']: st.write(d['notes'])
    st.download_button('Descargar comprobante de venta',document(sale,receipt=True,sale=True),file_name=sale['code']+'.html',mime='text/html',icon=':material/download:',key='sale_download')
    st.caption('Abre el archivo para imprimir o guardar como PDF. Registrar una venta no descuenta inventario ni marca un pedido como entregado.')
with payments:
    if sale['quote_id']: st.info('Estos pagos son los mismos de la cotización. Cualquier abono o anulación se refleja en ambos apartados.')
    table([dict(p,amount=q.money(p['amount_cents']),state='Anulado' if p['voided_at'] else 'Registrado') for p in sale['payments']],
        {'code':'Recibo','paid_on':'Fecha','concept':'Concepto','method':'Método','account_name':'Cuenta','reference':'Referencia','amount':'Monto MXN','state':'Estado','void_reason':'Motivo de anulación'},label='Historial de pagos de venta')
    active={p['id']:p for p in sale['payments'] if not p['voided_at']}
    if active:
        with st.expander('Corregir un registro de pago'):
            pid=st.selectbox('Pago a anular',list(active),format_func=lambda i:f"{active[i]['code']} · {q.money(active[i]['amount_cents'])}")
            if st.button('Anular registro',key='sale_void',icon=':material/undo:'): sale_void_form(sale,active[pid])

    table(corrections.history(selected),{'created_at':'Fecha','detail':'Corrección / documento'},label='Historial de correcciones')
