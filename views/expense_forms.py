from datetime import date
import streamlit as st
from services import expenses as e
from services.expense_catalog import CATEGORIES, COST_TYPES, PERIODS, RECEIPTS, TAX_MODES
from utils.dates import now
from views.common import managed_dialog, perform, reason_form


def select_expense(eid):
    st.session_state['open_expense_id']=eid


def choice(container,label,field,current,key):
    values=list(dict.fromkeys([current or '',*e.saved_values(field)]))
    return container.selectbox(label,values,index=0,key=key,accept_new_options=True,placeholder='Elige o escribe un valor')


def expense_category(container, current, prefix):
    categories=list(dict.fromkeys([current['category'],*CATEGORIES]))
    return container.selectbox('Categoría *',categories,key=prefix+'_category')


def expense_subtype(current, category, prefix):
    known=CATEGORIES.get(category,[])
    previous=current['subtype'] if current['category']==category else ''
    options=list(dict.fromkeys(['',*known,*([previous] if previous else [])]))
    key=prefix+'_subtype'
    if key in st.session_state and st.session_state[key] not in options:
        st.session_state[key]=''
    return st.selectbox('Etiqueta específica',options,key=key,
        format_func=lambda value:value or 'Sin etiqueta específica')


def fields(d,prefix,*,locked=False,template=False,labels):
    data=dict(d)
    data['category'],data['subtype']=labels
    data['concept']=st.text_input('Concepto *',value=d['concept'],key=prefix+'_concept',placeholder='Filamento PLA, renta, servicio de diseño…')
    data['supplier']=choice(st,'Proveedor / contraparte','supplier',d['supplier'],prefix+'_supplier')
    a,b,c=st.columns(3)
    data['unit']=choice(a,'Unidad / negocio *','unit',d['unit'],prefix+'_unit')
    data['cost_type']=b.selectbox('Naturaleza',COST_TYPES,index=COST_TYPES.index(d['cost_type']),key=prefix+'_type')
    data['account']=choice(c,'Cuenta prevista *','account',d['account'],prefix+'_account')
    if not template:
        a,b=st.columns(2)
        expense_day=a.date_input('Fecha del gasto',value=date.fromisoformat(d['expense_on']) if d['expense_on'] else None,max_value=now().date(),key=prefix+'_date')
        data['expense_on']=expense_day.isoformat() if expense_day else ''
        due=b.date_input('Vencimiento · opcional',value=date.fromisoformat(d['due_on']) if d['due_on'] else None,key=prefix+'_due')
        data['due_on']=due.isoformat() if due else ''
    a,b,c=st.columns([2,1,1])
    data['tax_mode']=a.selectbox('Captura del importe',TAX_MODES,index=TAX_MODES.index(d['tax_mode']),key=prefix+'_taxmode',disabled=locked)
    data['amount']=b.number_input('Importe · MXN',min_value=0.0,value=float(d['amount']),step=1.0,key=prefix+'_amount',disabled=locked)
    data['tax']=c.number_input('IVA manual · MXN',min_value=0.0,value=float(d['tax']),step=1.0,key=prefix+'_tax',disabled=locked)
    st.caption('Sin desglose / Total con IVA: captura el total. Subtotal + IVA / Desglose manual: captura el subtotal. IVA manual solo aplica al desglose manual.')
    with st.expander('Comprobante y notas' if not template else 'Notas',key=prefix+'_details',on_change='ignore'):
        if not template:
            a,b=st.columns(2)
            data['receipt_type']=a.selectbox('Comprobante',RECEIPTS,index=RECEIPTS.index(d['receipt_type']),key=prefix+'_receipt')
            data['receipt_ref']=b.text_input('Folio o referencia del comprobante',value=d['receipt_ref'],key=prefix+'_ref')
            orders={r['id']:r for r in st.session_state['snapshot']['orders']}
            options=[None,*orders]
            data['order_id']=st.selectbox('Pedido relacionado · opcional',options,index=options.index(d['order_id']) if d['order_id'] in options else 0,
                format_func=lambda i:'Sin pedido' if i is None else f"{orders[i]['code']} · {orders[i]['project']}",key=prefix+'_order')
        data['notes']=st.text_area('Notas',value=d['notes'],height=80,key=prefix+'_notes')
    return data


@managed_dialog('Capturar gasto',width='large')
def expense_form(row=None,*,reuse=False):
    editing=bool(row and not reuse)
    d=e.editable(row) if row else e.defaults()
    if reuse: d.update(expense_on=now().date().isoformat(),due_on='',receipt_type='Pendiente',receipt_ref='',order_id=None)
    prefix='expense_'+st.session_state['dialog_request_key']
    st.caption(f"Editar {row['code']}" if editing else 'Captura un gasto nuevo. Puedes calcular el total antes de registrarlo.')
    locked=bool(editing and row['money_locked'])
    if locked: st.info('Puedes actualizar clasificación, comprobante, notas y vencimiento. Para corregir importes o IVA con historial, abre Conciliar gasto desde el detalle.')
    category=expense_category(st,d,prefix)
    subtype=expense_subtype(d,category,prefix)
    with st.form(prefix):
        data=fields(d,prefix,locked=locked,labels=(category,subtype))
        paid=False
        if not editing:
            a,b=st.columns(2)
            paid=a.checkbox('Pagado completo en la fecha del gasto',key=prefix+'_paid')
            method=b.selectbox('Método si ya está pagado',('Transferencia','Efectivo','Tarjeta','Depósito','Otro'),key=prefix+'_method')
            st.caption('Si dejas el check vacío, se registra Por pagar. Para abonos o pagos en otra fecha, abre el gasto y pulsa Registrar pago.')
        a,b=st.columns(2)
        preview=a.form_submit_button('Calcular total',icon=':material/calculate:',width='stretch')
        save=b.form_submit_button('Guardar cambios' if editing else 'Registrar gasto',key=prefix+'_save',type='primary',icon=':material/check:',width='stretch')
        if preview or save:
            try: normalized=e.normalize(data,allow_undated=bool(editing and not row['expense_on']))
            except ValueError as exc:
                st.error(str(exc))
                return
            if preview:
                st.success(f"Total: {e.money(normalized['total_cents'])} MXN")
            elif editing:
                perform(e.update,row['id'],data,expected_revision=row['revision'],message='Gasto actualizado. Historial conservado.')
            else:
                if paid:
                    from services import treasury
                    active={a['name'] for a in treasury.accounts(active_only=True)}
                    if data['account'] not in active:
                        st.error('Para un gasto pagado, selecciona una cuenta o caja activa existente. Puedes crearla en Tesorería → Cuentas.');return
                payment=dict(amount=normalized['total_cents']/100,paid_on=data['expense_on'],account=data['account'],method=method) if paid else None
                perform(e.create,data,payment=payment,request_key=st.session_state['dialog_request_key'],after=select_expense,
                    navigate='views/expenses.py',message='Gasto registrado y pago guardado.' if paid else 'Gasto registrado. Pendiente de pago.')


@managed_dialog('Registrar pago de gasto',width='medium')
def expense_payment_form(row):
    st.write(f"**{row['code']} · {row['concept']}**")
    st.caption(f"Saldo: {e.money(row['balance_cents'])} MXN. Registra únicamente pagos realizados.")
    prefix='expense_pay_'+st.session_state['dialog_request_key']
    with st.form(prefix):
        a,b=st.columns(2)
        amount=a.number_input('Monto pagado · MXN',min_value=0.01,value=max(.01,row['balance_cents']/100),step=1.0,key=prefix+'_amount')
        paid=b.date_input('Fecha del pago',value=now().date(),max_value=now().date(),key=prefix+'_date')
        from services import treasury
        active=[a['name'] for a in treasury.accounts(active_only=True)]
        account=st.selectbox('Cuenta de salida *',active,index=active.index(row['account']) if row['account'] in active else None,
            key=prefix+'_account',placeholder='Selecciona banco, efectivo o pasarela')
        method=st.selectbox('Método de pago',('Transferencia','Efectivo','Tarjeta','Depósito','Otro'),key=prefix+'_method')
        ref=st.text_input('Referencia / folio',key=prefix+'_ref')
        if st.form_submit_button('Guardar pago',type='primary',width='stretch'):
            if account is None:st.error('Selecciona la cuenta o caja desde la que pagaste.');return
            perform(e.record_payment,row['id'],amount,paid.isoformat(),account,method,ref,request_key=st.session_state['dialog_request_key'],
                expected_revision=row['revision'],message='Pago registrado. Saldo actualizado.')


@managed_dialog('Anular registro de pago',width='small')
def expense_void_form(payment):
    reason_form('expense_void', f"**{payment['code']} · {e.money(payment['amount_cents'])} MXN**", 'Corrige la captura y recupera el saldo pendiente. No realiza una devolución de dinero.', 'Anular pago',
                lambda reason: perform(e.void_payment,payment['id'],reason,message='Registro anulado; historial conservado.'))


@managed_dialog('Cancelar gasto',width='small')
def expense_cancel_form(row):
    reason_form('expense_cancel', f"**{row['code']} · {row['concept']}**", 'El gasto dejará de sumar en el control. Se conserva su historial.', 'Confirmar cancelación',
                lambda reason: perform(e.cancel,row['id'],reason,expected_revision=row['revision'],message='Gasto cancelado.'))


@managed_dialog('Costo recurrente / previsto',width='large')
def expense_template_form(row=None):
    prefix='expense_template_'+st.session_state['dialog_request_key']
    d=row['data'] if row else dict(e.defaults(),cost_type='Fijo')
    st.caption('Define una vez y registra cada período cuando corresponda. Guardar un costo no registra gastos ni pagos automáticamente.')
    category=expense_category(st,d,prefix)
    subtype=expense_subtype(d,category,prefix)
    with st.form(prefix):
        a,b=st.columns([2,1])
        name=a.text_input('Nombre del costo *',value=row['name'] if row else '',key=prefix+'_name')
        period=b.selectbox('Periodicidad',list(PERIODS),index=list(PERIODS).index(row['period']) if row else 0,key=prefix+'_period')
        data=fields(d,prefix,template=True,labels=(category,subtype))
        active=st.checkbox('Activo',value=bool(row['active']) if row else True,key=prefix+'_active')
        if st.form_submit_button('Guardar costo',type='primary',width='stretch'):
            perform(e.save_template,name,data,period,request_key=st.session_state['dialog_request_key'],template_id=row['id'] if row else None,
                expected_revision=row['revision'] if row else None,active=active,message='Costo guardado. No se generaron pagos.')


@managed_dialog('Registrar gasto del período',width='medium')
def expense_generate_form(row):
    st.write(f"**{row['name']} · {row['period']}**")
    st.text(f"Total previsto: {e.money(row['total_cents'])} MXN")
    st.caption('Se crea un gasto Por pagar con los datos de este costo. Mensual, bimestral, trimestral, semestral y anual usan períodos de calendario; Único permite un solo registro.')
    with st.form('expense_generate'):
        issued=st.date_input('Fecha del gasto',value=now().date(),max_value=now().date())
        due=st.date_input('Vencimiento · opcional',value=None)
        if st.form_submit_button('Registrar y abrir gasto',type='primary',width='stretch'):
            perform(e.generate,row['id'],issued.isoformat(),due.isoformat() if due else '',expected_revision=row['revision'],
                request_key=st.session_state['dialog_request_key'],after=select_expense,message='Gasto del período registrado. Pendiente de pago.')
