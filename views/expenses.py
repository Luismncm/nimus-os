from views.invoice_forms import invoice_panel
from views.capital import historical_expenses_panel
from views.work_context import remember
import pandas as pd
import streamlit as st
from services import expenses as e, reconciliation
from views.reconciliation_forms import expense_reconciliation_form,movement_form,correction_history
from services.expense_catalog import COST_TYPES
from utils.dates import now
from views.common import table
from views.navigation import select_order
from views.expense_forms import (select_expense,expense_form,expense_payment_form,expense_void_form,
    expense_cancel_form,expense_delete_form,expense_template_form,expense_generate_form)
from views.finance_workspace import money_header
from views.treasury_components import financial_table,opens
from views.catalog_workspace import workspace_tabs
from views.expense_control_forms import quick_expense_form


def expense_table(rows,label):
    # Picking a row opens that expense.
    # The order an expense was bought for reads in its row, so the link shows without opening it.
    financial_table([dict(r,order=r.get('order_code') or '—') for r in rows],{'code':'Folio','expense_on':'Fecha','concept':'Concepto','category':'Categoría','order':'Pedido',
         'total_cents':'Total MXN','balance_cents':'Por pagar MXN','payment_status':'Estado','control':'Comprobante'},['total_cents','balance_cents'],label=label,open=opens('Gasto'))


selected=st.session_state.get('open_expense_id')
if not selected:
    money_header('expense')
    from views.shell import actions
    with actions():
        if st.button('Captura completa',key='expense_new',icon=':material/receipt_long:'): expense_form()
        if st.button('Registrar gasto',key='expense_quick_new',type='primary',icon=':material/add:'):quick_expense_form()
    with st.container(border=True):
        a,b,c=st.columns([1,1,2])
        start=a.date_input('Desde',value=now().date().replace(day=1),key='expense_start',persist_state='session')
        end=b.date_input('Hasta',value=now().date(),key='expense_end',persist_state='session')
        search=c.text_input('Buscar gasto',placeholder='Concepto, proveedor o folio',key='expense_search',icon=':material/search:',persist_state='session')
        with st.expander('Filtros de clasificación y estado',icon=':material/filter_alt:'):
            a,b,c=st.columns(3)
            category=a.selectbox('Categoría',('Todas',*e.saved_values('category')),key='expense_category',persist_state='session')
            subtypes=sorted({r['subtype'] for r in e.list_expenses() if r['subtype'] and (category=='Todas' or r['category']==category)})
            subtype=b.selectbox('Etiqueta específica',('Todos',*subtypes),key='expense_subtype')
            unit=c.selectbox('Unidad',('Todas',*e.saved_values('unit')),key='expense_unit',persist_state='session')
            a,b=st.columns(2)
            nature=a.selectbox('Naturaleza',('Todos',*COST_TYPES),persist_state="session",key='expense_nature')
            status=b.selectbox('Estado',('Todos','Por pagar','Pago parcial','Pagado','Cancelado'),key='expense_status',persist_state='session')
        active=[v for v in (category,subtype,unit,nature,status) if v not in ('Todas','Todos')]
        if active: st.caption('Filtros activos: '+' · '.join(active))
    if start>end:
        st.warning('Desde debe ser anterior o igual a Hasta.')
        st.stop()
    report=e.report(start,end,search=search,category=category,subtype=subtype,unit=unit,cost_type=nature,status=status)
    from views.treasury_components import money_pulse
    money_pulse([
        ('Registrado',e.money(report['total_cents']),'calm'),
        ('Pagado',e.money(report['paid_cents']),'calm'),
        ('Por pagar · consulta',e.money(report['balance_cents']),'orange' if report['balance_cents'] else 'calm'),
        ('Comprobantes por revisar',str(report['missing_receipts']),'orange' if report['missing_receipts'] else 'calm'),
    ],key='expense-pulse')
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.text(f"Por pagar · todas las fechas: {e.money(report['all_balance_cents'])} · Vencido: {e.money(report['overdue_cents'])}")
        with st.popover('Sobre este control',icon=':material/info:'):
            st.write('Gastos y saldo usan la fecha del gasto; Pagado usa la fecha real de cada pago, incluyendo gastos de otros períodos y compras cubiertas por socios. Esas compras no son salidas de caja o banco. Cancelados y pagos anulados no suman.')
            st.write('Por pagar abarca todas las fechas y respeta los filtros de esta consulta. Las tarjetas superiores muestran el saldo global según cuentas y movimientos existentes, junto con la previsión del mes. Conciliar saldos permite ajustar diferencias contra banco y caja.')
            st.caption('Históricos migrados de NIMUS · Control con fila de origen. Los gastos sin fecha están disponibles en Históricos sin fecha y suman al saldo acumulado de Tesorería.')
    movements,payables,costs,analysis,historical=workspace_tabs(['Movimientos','Por pagar','Costos recurrentes','Resumen','Históricos sin fecha'],'expense_tabs')
    with historical: historical_expenses_panel()
    with movements:
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            st.subheader(f"{len(report['rows'])} gastos en la consulta", icon=':material/receipt_long:')
            st.download_button('Exportar CSV',e.export_csv(report['rows']),file_name='NIMUS_gastos.csv',mime='text/csv',icon=':material/download:',disabled=not report['rows'])
        expense_table(report['rows'],'Control de gastos')
        rows={r['id']:r for r in report['rows']}
        if rows:
            a,b=st.columns([4,1],vertical_alignment='bottom')
            eid=a.selectbox('Abrir gasto',list(rows),format_func=lambda i:f"{rows[i]['code']} · {rows[i]['concept']}",key='expense_selected')
            if b.button('Ver detalle',key='expense_open',type='primary',width='stretch'):
                select_expense(eid)
                st.rerun()
        else: st.info('Sin gastos con estos filtros. Consulta otros períodos o Históricos sin fecha.')
    with payables:
        st.caption('Pendientes de todas las fechas. Se aplican los filtros de búsqueda, categoría, unidad, naturaleza y estado.')
        if not report['pending']: st.success('No hay pagos pendientes con estos filtros.')
        for row in report['pending'][:30]:
            with st.container(border=True):
                a,b,c=st.columns([3,1,1],vertical_alignment='center')
                a.write(f"**{row['code']} · {row['concept']}**")
                a.caption(f"{row['supplier'] or 'Sin proveedor'} · Vence {row['due_on'] or 'sin fecha'}")
                b.metric('Por pagar',e.money(row['balance_cents']))
                if row['overdue']: a.badge('Vencido',color='red')
                if c.button('Pagar',key=f'expense_pay_{row["id"]}',type='primary',width='stretch'): expense_payment_form(row)
        if len(report['pending'])>30:
            with st.expander('Ver todos los pendientes'):
                expense_table(report['pending'],'Todos los gastos pendientes de pago')
                all_pending={r['id']:r for r in report['pending']}
                pid=st.selectbox('Pendiente por atender',list(all_pending),format_func=lambda i:all_pending[i]['code']+' · '+all_pending[i]['concept'])
                if st.button('Registrar pago',key='expense_pending_all'):expense_payment_form(all_pending[pid])
    with costs:
        templates=e.templates()
        active_templates=[r for r in templates if r['active']]
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            st.subheader('Estructura de costos', icon=':material/pie_chart:')
            if st.button('Nuevo costo recurrente',key='expense_template_new',icon=':material/add:'): expense_template_form()
        st.caption('Previsión independiente de los movimientos. Estos costos no suman como gasto ni como pago hasta que registres el período. Los filtros de arriba no afectan esta estructura.')
        a,b,c=st.columns(3)
        a.metric('Fijos · equivalente mensual',e.money(sum(r['monthly_cents'] for r in active_templates if r['data']['cost_type']=='Fijo')),border=True)
        b.metric('Variables · equivalente mensual',e.money(sum(r['monthly_cents'] for r in active_templates if r['data']['cost_type']=='Variable')),border=True)
        c.metric('Únicos · importe previsto',e.money(sum(r['total_cents'] for r in active_templates if r['period']=='Único')),border=True)
        for row in templates:
            with st.container(border=True):
                st.write(f"**{row['name']}** · {row['data']['unit']} · {row['period']}"+(' · Archivado' if not row['active'] else ''))
                st.text(f"Importe {e.money(row['total_cents'])} · Equivalente mensual {e.money(row['monthly_cents'])} MXN")
                with st.container(horizontal=True):
                    if st.button('Registrar período',key=f'expense_generate_{row["id"]}',type='primary',disabled=not row['active']): expense_generate_form(row)
                    if st.button('Editar costo',key=f'expense_template_edit_{row["id"]}'): expense_template_form(row)
        if not templates: st.info('Agrega renta, suscripciones, servicios u otros costos para reutilizarlos en cada período.')
    with analysis:
        st.subheader('Gastos por categoría', icon=':material/category:')
        if report['categories']:
            frame=pd.DataFrame([{'Categoría':k,'Total MXN':v/100} for k,v in report['categories'].items()])
            st.bar_chart(frame,x='Categoría',y='Total MXN',horizontal=True,sort='-Total MXN',alt='Gastos del período por categoría')
        else: st.caption('Sin gastos activos en este período.')
        st.subheader('Pagos realizados en el período', icon=':material/payments:')
        by_id={r['id']:r for r in e.list_expenses()}
        table([dict(p,expense=by_id[p['expense_id']]['code'],concept=by_id[p['expense_id']]['concept'],amount=e.money(p['amount_cents'])) for p in report['payments']],
            {'code':'Pago','expense':'Gasto','concept':'Concepto','paid_on':'Fecha','account':'Cuenta de salida','method':'Método','amount':'Pagado MXN'},label='Pagos de gastos del período')
    st.stop()

row=e.get_expense(selected)
from services import inbound
from views.emoji import icon_tabs
purchase=inbound.purchase_for_expense(selected)
if purchase:
    with st.container(horizontal=True,vertical_alignment='center'):
        st.caption('Compra de inventario '+purchase['code']+' · '+purchase['reference'])
        if st.button('Abrir pedido de compra',key='expense_purchase',icon=':material/local_shipping:'):
            from views.inbound_ui import open_order
            open_order(purchase['id'])
remember('Gasto',row['id'],row['code'])
if st.button('Todos los gastos',key='expense_back',icon=':material/arrow_back:',type='tertiary'):
    st.session_state.pop('open_expense_id',None)
    st.rerun()
with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
    st.subheader(f"{row['code']} · {row['concept']}")
    st.badge(row['payment_status'],color='green' if row['payment_status']=='Pagado' else 'red' if row['status']=='Cancelado' else 'orange')
st.caption(f"{row['expense_on']} · {row['category']}"+(f" / {row['subtype']}" if row['subtype'] else '')+f" · {row['cost_type']} · {row['unit']} · {row['supplier'] or 'Sin proveedor'}")
if row['status']=='Cancelado': st.warning('Gasto cancelado: '+row['cancel_reason'])
elif row['overdue']: st.warning(f"Pago vencido desde {row['due_on']}.")
if row['control']!='Completo' and row['status']=='Activo': st.info(row['control']+'. Puedes completarlo en Editar gasto.')
a,b,c=st.columns(3)
a.metric('Total · MXN',e.money(row['total_cents']),border=True)
b.metric('Pagado',e.money(row['paid_cents']),border=True)
c.metric('Saldo de la operación' if row['status']=='Cancelado' else 'Por pagar',e.money(row['balance_cents']),border=True)
with st.container(horizontal=True):
    if st.button('Registrar pago',key='expense_payment',type='primary',icon=':material/payments:',disabled=row['status']!='Activo' or row['balance_cents']<=0): expense_payment_form(row)
    if st.button('Editar gasto',key='expense_edit',icon=':material/edit:',disabled=row['status']!='Activo'): expense_form(row)
    if st.button('Conciliar gasto',key='expense_reconcile',icon=':material/fact_check:',disabled=row['status']!='Activo'):
        expense_reconciliation_form(row,reconciliation.state('expense_document',selected))
    if st.button('Reutilizar gasto',key='expense_reuse',icon=':material/content_copy:'): expense_form(row,reuse=True)
    if row['order_id'] and st.button('Abrir pedido',key='expense_order'):
        select_order(row['order_id'])
        st.switch_page('views/orders.py')
    with st.popover('Más opciones',icon=':material/more_horiz:'):
        if st.button('Cancelar gasto',key='expense_cancel',disabled=row['status']!='Activo' or row['paid_cents']>0): expense_cancel_form(row)
        st.caption('Eliminar lo borra por completo, sin dejar registro; úsalo para duplicados o capturas erróneas.')
        if st.button('Eliminar gasto',key='expense_delete',icon=':material/delete_forever:'): expense_delete_form(row)
detail,payments,history,invoice_tab=icon_tabs(['Detalle','Pagos','Historial','Factura y PDF'],key=f'expense_detail_{selected}',on_change='rerun')
with invoice_tab:
    invoice_panel('expense',selected)
with detail:
    if row['subtotal_cents'] is None: st.caption('Importe capturado sin desglose de IVA.')
    else: st.text(f"Subtotal {e.money(row['subtotal_cents'])} · IVA {e.money(row['tax_cents'])} MXN")
    st.write(f"**Comprobante:** {row['receipt_type']} · {row['receipt_ref'] or 'Sin referencia'}")
    st.write(f"**Cuenta prevista:** {row['account']} · **Vencimiento:** {row['due_on'] or 'Sin fecha'}")
    if row['subtype']: st.write(f"**Tipo de gasto:** {row['subtype']}")
    if row['notes']: st.write(row['notes'])
    st.caption('La cuenta efectiva y la fecha de salida se registran en cada pago. Capturar materiales aquí no aumenta inventario automáticamente.')
with payments:
    if row.get('partner_settlement'):
        settlement=row['partner_settlement']
        st.info(f"Cubierto por {settlement['partner']} · {e.money(settlement['amount_cents'])} MXN · {settlement['paid_on'] or 'Sin fecha'}. Aportación de socio; no hubo salida de caja ni banco.")
    table([dict(p,amount=e.money(p['amount_cents']),state='Anulado' if p['voided_at'] else 'Registrado') for p in row['payments']],
        {'code':'Pago','paid_on':'Fecha','account':'Cuenta','method':'Método','amount':'Monto MXN','reference':'Referencia','state':'Estado','void_reason':'Motivo'},label='Historial de pagos del gasto')
    active={p['id']:p for p in row['payments'] if not p['voided_at']}
    if active:
        with st.expander('Corregir un pago'):
            pid=st.selectbox('Pago a corregir',list(active),format_func=lambda i:f"{active[i]['code']} · {e.money(active[i]['amount_cents'])}")
            if st.button('Conciliar pago',key='expense_reconcile_payment'):
                movement_form('expense',pid,reconciliation.state('expense',pid))
            correction_history('expense',pid)
            if st.button('Anular registro',key='expense_void'): expense_void_form(active[pid])
with history:
    correction_history('expense_document',selected)
    table(row['events'],{'created_at':'Fecha y hora','detail':'Movimiento'},label='Historial del gasto')
