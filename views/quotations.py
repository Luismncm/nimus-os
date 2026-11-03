from views.work_context import remember
import base64
from datetime import date
import pandas as pd
import streamlit as st

from services import quotations as q
from services.quotation_document import document
from utils.dates import now
from views.common import perform, table
from views.properties import property_select
from views.quotation_forms import payment_form, convert_form, void_payment_form
from views.navigation import select_order
from views.sales_forms import quote_sale_form, select_sale


def select_quote(qid):
    st.session_state['open_quote_id'] = qid


def records(frame):
    return [{k: None if pd.isna(v) else v for k, v in row.items()} for row in frame.to_dict('records')]


selected = st.session_state.get('open_quote_id')
if not selected:
    from views.shell import actions
    with actions():
        if st.button('Cotizar Origen',key='quote_new_origin',icon=':material/light:'):
            from views.origin_cart import open_cart
            open_cart(mode='Cotización')
        if st.button('Nueva cotización', key='quote_new', type='primary', icon=':material/add:'):
            perform(q.create_quote, after=select_quote, message='Cotización creada. Completa cliente y partidas.')
    rows = q.list_quotes()
    active = [r for r in rows if r['status'] != 'Cancelada']
    a, b, c = st.columns(3)
    a.metric('Cotizaciones activas', len(active), border=True)
    b.metric('Saldo cotizado · MXN', q.money(sum(r['total_cents']-r['paid_cents'] for r in active)), border=True)
    c.metric('Con pedido de producción', sum(bool(r['order_id']) for r in rows), border=True)
    a, b = st.columns([2, 1])
    search = a.text_input('Buscar cotización', placeholder='Cliente, proyecto o folio', key='quote_search', icon=':material/search:',persist_state='session')
    status = b.selectbox('Estado', ('Todas','Borrador','Enviada','Aceptada','Cancelada'), persist_state="session",key='quote_filter')
    filtered = [r for r in rows if search.casefold() in f"{r['code']} {r['client']} {r['project']}".casefold() and (status == 'Todas' or status == r['status'])]
    if not filtered: st.info('Crea una cotización o ajusta los filtros para comenzar.')
    for row in filtered:
        with st.container(border=True):
            st.write(f"**{row['code']} · {row['project'] or 'Proyecto sin definir'}**")
            st.caption(row['client'] or 'Cliente pendiente')
            with st.container(horizontal=True, vertical_alignment='center'):
                st.badge(row['status'], color='green' if row['status']=='Aceptada' else 'gray')
                st.text(f"{q.money(row['total_cents'])} MXN · saldo {q.money(row['total_cents']-row['paid_cents'])}")
                if row['valid_until'] < now().date().isoformat() and row['status'] in ('Borrador','Enviada'):
                    st.badge('Vigencia vencida', color='orange')
                if st.button('Abrir cotización', key=f'quote_open_{row["id"]}', icon=':material/arrow_forward:'):
                    select_quote(row['id'])
                    st.rerun()
    st.stop()

quote = q.get_quote(selected)
remember('Cotización',quote['id'],quote['code'])
d = quote['data']
prefix = f'quote_{selected}_{quote["revision"]}'
if st.button('Todas las cotizaciones', key='quote_back', icon=':material/arrow_back:', type='tertiary'):
    st.session_state.pop('open_quote_id', None)
    st.rerun()
with st.container(horizontal=True, vertical_alignment='center', horizontal_alignment='distribute'):
    st.subheader(f"{quote['code']} · {d['project'] or 'Nueva cotización'}")
    st.badge(quote['status'], color='green' if quote['status']=='Aceptada' else 'blue')
a, b, c = st.columns(3)
a.metric('Total · MXN', q.money(quote['total_cents']), border=True)
b.metric('Pagado', q.money(quote['paid_cents']), border=True)
c.metric('Saldo pendiente', q.money(quote['balance_cents']), border=True)
from views.commerce_ui import panel as commercial_panel
from views.emoji import icon_tabs
commercial_panel('quote',selected)
if any(l.get('recipe_id') for l in d['lines']) and st.button('Copiar al carrito para otro alcance',key='quote_copy_cart',icon=':material/content_copy:'):
    from views.origin_cart import open_cart
    open_cart(mode='Cotización',source=quote)
with st.container(horizontal=True, vertical_alignment='center'):
    if quote['sale_id']:
        if st.button('Abrir venta vinculada', key='quote_sale_open', icon=':material/point_of_sale:'):
            select_sale(quote['sale_id'])
            st.switch_page('views/sales.py')
    elif st.button('Registrar venta', key='quote_sale', icon=':material/point_of_sale:', disabled=quote['status']!='Aceptada'):
        quote_sale_form(quote)
    if st.button('Duplicar', key='quote_duplicate', icon=':material/content_copy:'):
        perform(q.create_quote, selected, after=select_quote, message='Copia creada con nuevo folio, sin pagos ni pedido vinculado.')
    if quote['order_id']:
        if st.button('Abrir pedido vinculado', key='quote_order_open', icon=':material/inventory_2:'):
            select_order(quote['order_id'])
            st.switch_page('views/orders.py')
    elif st.button('Crear pedido', key='quote_convert', type='primary', icon=':material/inventory_2:', disabled=quote['status']!='Aceptada' or quote['sale_status']=='Cancelada' or not any(r['produce'] for r in d['lines'])):
        convert_form(quote)
    with st.popover('Estado comercial', icon=':material/sell:'):
        with st.form(prefix+'_status'):
            status = st.selectbox('Estado de cotización', ('Borrador','Enviada','Aceptada','Cancelada'), index=('Borrador','Enviada','Aceptada','Cancelada').index(quote['status']))
            if st.form_submit_button('Actualizar estado'):
                perform(q.set_status, selected, status, expected_revision=quote['revision'])
st.caption('Para crear un pedido: guarda las partidas, marca Para fabricar en los productos y cambia el estado a Aceptada. Enviada es un registro manual; no envía mensajes al cliente.')
edit_tab, preview_tab, payments_tab = icon_tabs(['Editar cotización', 'Vista para cliente', 'Pagos y recibos'], key=f'quote_tabs_{selected}', on_change='rerun')

with edit_tab:
    if quote['locked']:
        st.info('El alcance está fijado porque ya tiene venta, pedido o historial de pagos. Duplica la cotización para preparar una modificación.')
    else:
        st.caption('Edita varias celdas y guarda todo junto. Los importes de arriba muestran la última versión guardada. Salir sin guardar descarta los cambios.')
        with st.form(prefix+'_editor', border=False):
            a, b = st.columns(2)
            client = property_select('Cliente / empresa', 'client', current=d['client'], key=prefix+'_client', container=a)
            project = b.text_input('Proyecto', value=d['project'], key=prefix+'_project')
            a, b = st.columns(2)
            issued = a.date_input('Emisión', value=date.fromisoformat(d['issued_on']), key=prefix+'_issued')
            valid = b.date_input('Válida hasta', value=date.fromisoformat(d['valid_until']), key=prefix+'_valid')
            with st.expander('Contacto y alcance comercial', key=f'quote_scope_{selected}', on_change='ignore'):
                details = {}
                labels = {'contact':'Contacto','contact_channel':'Correo / WhatsApp','rfc':'RFC (si aplica)','solution':'Tipo de solución / producto',
                    'context':'Contexto comercial','level':'Nivel de solución','material':'Material / tecnología / acabado','objective':'Objetivo / uso',
                    'reference':'Referencia / campaña','lead_time':'Tiempo de entrega estimado','owner':'Responsable NIMUS'}
                suggestions = {'solution':['Merch / producto de marca','Tap Bar','Tap Board','Smart Link físico','Señalética NFC / QR','Producto conectado NFC / QR','Nimus Link','Campaña / activación','Evento','Proyecto especial','Desarrollo personalizado'],
                    'context':['Operación del negocio','Merch / comunidad','Campaña / lanzamiento','Evento / activación','Proyecto especial','Multi-sucursal / despliegue'],
                    'level':['Producto físico','Producto conectado','Sistema / Nimus Link','Proyecto híbrido'],
                    'owner':['Dirección','Comercial','Producto / Lab','Desarrollo','Dirección + Desarrollo','Dirección + Producto / Lab','Externo / Partner']}
                cols = st.columns(2)
                for i, (field, label) in enumerate(labels.items()):
                    if field in suggestions:
                        opts = list(dict.fromkeys([d[field], *suggestions[field]]))
                        details[field] = cols[i%2].selectbox(label, opts, key=prefix+'_'+field, accept_new_options=True)
                    elif field == 'material':
                        details[field] = property_select(label, 'material', current=d[field], key=prefix+'_'+field, container=cols[i%2])
                    else:
                        details[field] = cols[i%2].text_input(label, value=d[field], key=prefix+'_'+field)
            st.subheader('Partidas', icon=':material/format_list_bulleted:')
            st.caption('Agrega filas al final; selecciona una fila para eliminarla. Para fabricar crea un item en el pedido; los servicios pueden quedar solo como partidas comerciales.')
            line_fields = ['description','quantity','price','produce']
            if any(l.get('recipe_id') for l in d['lines']):line_fields.append('recipe_id')
            frame = pd.DataFrame(d['lines'] or [dict(description='',quantity=1.0,price=0.0,produce=True)], columns=line_fields)
            lines = st.data_editor(frame, key=prefix+'_lines', num_rows='dynamic', hide_index=True, width='stretch',
                disabled=['recipe_id'],
                column_config={'description':st.column_config.TextColumn('Producto / servicio', required=True, width='large'),
                    'recipe_id':None,
                    'quantity':st.column_config.NumberColumn('Cantidad', min_value=0.001, default=1.0),
                    'price':st.column_config.NumberColumn('P. unitario · MXN', min_value=0.0, step=0.01, default=0.0, format='$%.2f'),
                    'produce':st.column_config.CheckboxColumn('Para fabricar', default=False)}, alt='Partidas editables de cotización')
            with st.expander('Precios por volumen', expanded=bool(d['tiers']), key=f'quote_volume_{selected}', on_change='ignore'):
                st.caption('Rangos sin superposición. Deja Hasta vacío para un rango abierto. El descuento de referencia no se vuelve a descontar del precio.')
                tiers = st.data_editor(pd.DataFrame(d['tiers'], columns=['minimum','maximum','price','reference_discount','note']).astype({'minimum':'float64','maximum':'float64','price':'float64','reference_discount':'float64','note':'object'}),
                    key=prefix+'_tiers', num_rows='dynamic', hide_index=True, width='stretch',
                    column_config={'minimum':st.column_config.NumberColumn('Desde', min_value=1, step=1, default=1),
                        'maximum':st.column_config.NumberColumn('Hasta', min_value=1, step=1),
                        'price':st.column_config.NumberColumn('P. unitario · MXN', min_value=0.0, default=0.0, step=0.01, format='$%.2f'),
                        'reference_discount':st.column_config.NumberColumn('Desc. ref. %',min_value=0.0,max_value=100.0,default=0.0),
                        'note':st.column_config.TextColumn('Etiqueta / nota')}, alt='Rangos de precios por volumen')
                volume_line = st.number_input('Número de partida para aplicar volumen', min_value=1, value=1, step=1, key=prefix+'_volume_line')
            a, b = st.columns(2)
            discount = a.number_input('Descuento global %', min_value=0.0, max_value=100.0, value=float(d['discount']), step=1.0, key=prefix+'_discount')
            iva = b.checkbox('Agregar IVA 16%', value=d['iva'], key=prefix+'_iva')
            with st.expander('Notas, condiciones e imágenes', key=f'quote_notes_{selected}', on_change='ignore'):
                for field, label in [('notes','Notas y especificaciones'),('payment_terms','Condiciones de pago'),('conditions','Condiciones comerciales')]:
                    details[field] = st.text_area(label, value=d[field], key=prefix+'_'+field)
                details['issuer'] = st.text_input('Emisor / datos de contacto NIMUS', value=d['issuer'], key=prefix+'_issuer')
                details['footer'] = st.text_input('Pie del documento', value=d['footer'], key=prefix+'_footer')
                keep = st.multiselect('Conservar imágenes guardadas', range(len(d['images'])), default=list(range(len(d['images']))),
                    format_func=lambda i: d['images'][i]['caption'], key=prefix+'_keep_images')
                captions = [st.text_input(f'Descripción de imagen {i+1}', value=pic['caption'], key=prefix+f'_caption_{i}') for i, pic in enumerate(d['images'])]
                uploads = st.file_uploader('Agregar imágenes de prototipo · hasta 4, 3 MB cada una', type=['png','jpg','jpeg','webp'], accept_multiple_files=True, key=prefix+'_images')
            a, b = st.columns(2)
            save = a.form_submit_button('Calcular y guardar', type='primary', icon=':material/save:', width='stretch')
            apply = b.form_submit_button('Aplicar volumen y guardar', icon=':material/calculate:', width='stretch')
            if save or apply:
                images = [dict(d['images'][i],caption=captions[i]) for i in keep] + [dict(data=base64.b64encode(f.getvalue()).decode(), caption=f.name) for f in uploads]
                payload = dict(d, **details)
                payload.update(client=client,project=project,issued_on=issued.isoformat(),valid_until=valid.isoformat(),
                    lines=records(lines),tiers=records(tiers),discount=discount,iva=iva,images=images)
                perform(q.save_quote, selected, payload, expected_revision=quote['revision'], status=quote['status'],
                    volume_line=int(volume_line)-1 if apply else None, message='Cotización guardada. Totales actualizados.')

with preview_tab:
    st.subheader(d['client'] or 'Cliente pendiente')
    st.caption(f"Emisión {d['issued_on']} · Vigencia {d['valid_until']} · {d['lead_time']}")
    table([dict(r, amount=q.money(r['amount_cents']),unit_price=q.money(q.cents(r['price']))) for r in d['lines']],
          {'description':'Producto / servicio','quantity':'Cantidad','unit_price':'P. unitario · MXN','amount':'Importe · MXN'}, label='Partidas de la cotización guardada')
    if d['tiers']:
        st.caption('Precios por volumen · antes de IVA')
        table(d['tiers'], {'minimum':'Desde','maximum':'Hasta','price':'P. unitario','reference_discount':'Desc. ref. %','note':'Etiqueta'}, label='Precios por volumen')
    t = d['totals']
    st.text(f"Subtotal {q.money(t['subtotal'])} · Descuento −{q.money(t['discount'])} · IVA {q.money(t['tax'])}")
    st.subheader(f"Total {q.money(t['total'])} MXN")
    for pic in d['images']: st.image(base64.b64decode(pic['data']), caption=pic['caption'], alt=pic['caption'], width=350)
    st.write(d['notes'])
    st.write(d['payment_terms'])
    st.download_button('Descargar cotización para imprimir / PDF', document(quote), file_name=quote['code']+'.html', mime='text/html', icon=':material/download:', key='quote_download')
    st.caption('Abre el archivo descargado y pulsa Imprimir / guardar como PDF. Incluye el alcance, las condiciones, los rangos y las imágenes guardadas.')

with payments_tab:
    with st.container(horizontal=True, vertical_alignment='center'):
        status = 'Liquidado' if quote['balance_cents']==0 and quote['paid_cents']>0 else 'Pago parcial' if quote['paid_cents'] else 'Pendiente de pago'
        st.badge(status, color='green' if status=='Liquidado' else 'orange')
        if st.button('Registrar pago', key='quote_payment', type='primary', icon=':material/add:', disabled=quote['balance_cents']<=0 or quote['status']=='Cancelada' or quote['sale_status']=='Cancelada' or not d['client']):
            payment_form(quote)
    table([dict(p,amount=q.money(p['amount_cents']),state='Anulado' if p['voided_at'] else 'Registrado') for p in quote['payments']],
        {'code':'Recibo','paid_on':'Fecha','concept':'Concepto','method':'Método','account_name':'Cuenta','reference':'Referencia','amount':'Monto · MXN','state':'Estado','void_reason':'Motivo de anulación'}, label='Historial de pagos')
    if quote['payments']:
        st.download_button('Descargar recibo / estado de pagos', document(quote, receipt=True), file_name=quote['code']+'_pagos.html', mime='text/html', icon=':material/download:', key='quote_receipt')
        active_payments = {p['id']:p for p in quote['payments'] if not p['voided_at']}
        if active_payments:
            with st.expander('Corregir un registro de pago'):
                pid = st.selectbox('Pago a anular', list(active_payments), format_func=lambda i: f"{active_payments[i]['code']} · {q.money(active_payments[i]['amount_cents'])}")
                if st.button('Anular registro', key='quote_void', icon=':material/undo:'):
                    void_payment_form(active_payments[pid])
    st.caption('Los recibos reflejan los pagos capturados. No confirman empaque, entrega ni movimientos de inventario.')
