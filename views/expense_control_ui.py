"""Daily spending control with optional project cash coverage and detailed plans."""
import streamlit as st
from services import expense_control as control
from services.quotations import money
from utils.dates import now
from views.expense_control_forms import quick_expense_form
from views.expense_forms import expense_form, expense_payment_form
from views.treasury_components import financial_table,opens
from views.common import picks
from views.work_context import open_record
from views.catalog_workspace import workspace_tabs
from services import cash_projection
from views.cash_projection_ui import projection_cards
from views.cash_projection_ui import account_cards,forecast_form
from views.spending_plan_forms import planned_expense_form,materialize_form,cancel_plan_form
from views.emoji import tag


def summary_panel(report):
    st.caption(f"{report['month']} · Registrado {money(report['registered_cents'])[1:]} · Pagado {money(report['paid_cents'])[1:]} MXN")
    st.subheader('En qué se está gastando', icon=':material/receipt_long:')
    columns = {'category':'Categoría','registered_cents':'Registrado MXN','paid_cents':'Pagado MXN','pending_cents':'Por pagar MXN'}
    amounts = ['registered_cents','paid_cents','pending_cents']
    if report['partner_cents']:
        columns['partner_cents']='Cubierto por socios MXN'; amounts.append('partner_cents')
    if report['categories']:
        financial_table(report['categories'], columns, amounts, label='Gastos y pagos reales por categoría del mes')
        st.caption('Registrado usa la fecha del gasto. Pagado usa la fecha del pago, aunque el gasto sea de otro mes. Son lecturas distintas; no se suman entre sí.')
    else:
        st.info('Aún no hay gastos ni pagos en este mes. Empieza con Registrar gasto; no necesitas crear un presupuesto.')
    with st.expander('Pagos por cuenta y efectivo', icon=':material/account_balance_wallet:', key='control_accounts', on_change='rerun') as accounts:
        if accounts.open:
            financial_table(report['accounts'], {'account':'Cuenta o caja','kind':'Tipo','paid_cents':'Pagado MXN'},
                            ['paid_cents'], label='Pagos de gastos por cuenta y efectivo')
            st.caption('Salidas registradas del mes. No representan el saldo actual de tus cuentas.')
    if report['expenses']:
        with st.expander('Gastos registrados este mes', key='control_documents', on_change='rerun') as docs:
            if docs.open:
                financial_table(report['expenses'], {'code':'Gasto','expense_on':'Fecha','concept':'Concepto','total_cents':'Total MXN','balance_cents':'Pendiente actual MXN','payment_status':'Pago'},
                                ['total_cents','balance_cents'], label='Gastos registrados en el mes', open=opens('Gasto'))
                rows={r['id']:r for r in report['expenses']}
                if st.session_state.get('control_document') not in rows: st.session_state['control_document']=next(iter(rows))
                eid=st.selectbox('Gasto para consultar',list(rows),key='control_document',format_func=lambda i:f"{rows[i]['code']} · {rows[i]['concept']}")
                if st.button('Abrir gasto y comprobante',key='control_document_open',icon=':material/open_in_new:'):open_record('Gasto',eid)


def pending_panel(report):
    st.subheader('Lo que falta pagar', icon=':material/payments:')
    st.caption('Saldos actuales de todas las fechas. Los pagos parciales y lo cubierto por socios ya están descontados.')
    search=st.text_input('Buscar pendiente',key='control_pending_search',placeholder='Concepto, proveedor, categoría o folio',icon=':material/search:')
    a,b=st.columns(2)
    attention=a.segmented_control('Atención',('Todos','Vencidos','Sin fecha'),default='Todos',key='control_pending_attention', format_func=tag) or 'Todos'
    names=sorted({r['account'] or 'Por definir' for r in report['pending']})
    if st.session_state.get('control_pending_account') not in ('Todas',*names):st.session_state['control_pending_account']='Todas'
    account=b.selectbox('Cuenta prevista',('Todas',*names),key='control_pending_account')
    rows=[dict(r,due=r['due_on'] or 'Sin fecha',attention='Vencido' if r['overdue'] else 'Pendiente') for r in report['pending']
          if search.strip().casefold() in f"{r['concept']} {r['supplier']} {r['category']} {r['code']}".casefold()
          and (account=='Todas' or (r['account'] or 'Por definir')==account)
          and (attention=='Todos' or attention=='Vencidos' and r['overdue'] or attention=='Sin fecha' and not r['due_on'])]
    if not rows:
        st.success('Sin pendientes para esta consulta.' if search else 'No hay gastos pendientes de pago.');return
    st.caption(str(len(rows))+' pendientes · '+money(sum(r['balance_cents'] for r in rows))+' MXN en esta consulta. Las tarjetas generales conservan el total de todas las cuentas.')
    financial_table(rows,{'code':'Gasto','concept':'Concepto','account':'Cuenta prevista','due':'Vencimiento','balance_cents':'Por pagar MXN','attention':'Estado'},
                    ['balance_cents'],label='Gastos pendientes de pago de todas las fechas',open=opens('Gasto'))
    lookup={r['id']:r for r in rows}
    if st.session_state.get('control_pending_selected') not in lookup: st.session_state['control_pending_selected']=next(iter(lookup))
    eid=st.selectbox('Gasto por atender',list(lookup),key='control_pending_selected',format_func=lambda i:f"{lookup[i]['code']} · {lookup[i]['concept']} · {money(lookup[i]['balance_cents'])}")
    with st.container(horizontal=True):
        if st.button('Registrar pago',type='primary',key='control_pending_pay',icon=':material/payments:'):expense_payment_form(lookup[eid])
        if st.button('Abrir detalle',key='control_pending_open',icon=':material/open_in_new:'):open_record('Gasto',eid)


def planned_panel(projection):
    st.subheader('Lo que aún planeas gastar',icon=':material/event_note:')
    st.caption('Estas previsiones todavía no son deudas ni pagos. Al usar Registrar gasto pasan automáticamente a Gastos y salen de esta lista.')
    search=st.text_input('Buscar previsto',key='control_plan_search',placeholder='Concepto, proveedor o cuenta',icon=':material/search:')
    rows=[r for r in projection['plans']['active'] if search.strip().casefold() in (r['concept']+' '+r['supplier']+' '+r['account_name']).casefold()]
    if rows:
        financial_table(rows,{'concept':'Concepto','due_on':'Fecha prevista','account_name':'Cuenta','amount_cents':'Previsto MXN','category':'Categoría'},['amount_cents'],label='Gastos previstos pendientes de registrar',
                        open=picks('control_plan_selected'),key='control_plan_table')
        lookup={r['id']:r for r in rows}
        if st.session_state.get('control_plan_selected') not in lookup:st.session_state['control_plan_selected']=next(iter(lookup))
        pid=st.selectbox('Previsión por atender',list(lookup),key='control_plan_selected',format_func=lambda i:lookup[i]['concept']+' · '+money(lookup[i]['amount_cents']))
        with st.container(horizontal=True):
            if st.button('Registrar gasto',key='control_plan_materialize',type='primary',icon=':material/receipt_long:'):materialize_form(lookup[pid])
            if st.button('Editar previsión',key='control_plan_edit',icon=':material/edit:'):planned_expense_form(projection['forecast']['month'],lookup[pid])
            with st.popover('Más',icon=':material/more_horiz:'):
                if st.button('Cancelar previsión',key='control_plan_cancel'):cancel_plan_form(lookup[pid])
    else:st.info('Sin previsiones en esta consulta. Usa Agregar previsto para una compra, servicio o gasto futuro.')
    with st.expander('Ajuste general e historial',key='control_plan_history',on_change='rerun'):
        st.caption('Ajuste manual del mes: '+money(projection['forecast']['additional_cents'])+' MXN. Es adicional a las previsiones por concepto.')
        if st.button('Editar ajuste mensual',key='control_forecast'):forecast_form(projection['forecast'])
        history=[r for r in projection['plans']['rows'] if r['status']!='Previsto']
        financial_table(history,{'concept':'Concepto','amount_cents':'Importe MXN','status':'Estado','expense_code':'Gasto vinculado'},['amount_cents'],label='Historial de previsiones registradas o canceladas',
                        open=lambda r:r['expense_id'] and open_record('Gasto',r['expense_id']))
        linked={r['expense_id']:r for r in history if r['expense_id']}
        if linked:
            eid=st.selectbox('Gasto registrado desde previsión',list(linked),format_func=lambda i:linked[i]['expense_code']+' · '+linked[i]['concept'])
            if st.button('Abrir gasto',key='control_plan_open'):open_record('Gasto',eid)

def project_panel(report,projection):
    st.subheader('¿Alcanza para un proyecto o compra?', icon=':material/savings:')
    st.caption('Se usa el total de tus cuentas y se descuentan los gastos proyectados de las tarjetas. Agrega una reserva y el costo del proyecto para ver cuánto quedaría.')
    with st.container(border=True):
        st.text_input('Proyecto o compra · opcional',key='control_project_name',placeholder='Ej. otra impresora, una campaña o un prototipo',persist_state='session')
        available=projection['cash']['total_cents']
        manual=st.toggle('Simular con otro monto',key='control_project_manual')
        if manual:
            available_input=st.number_input('Dinero para simular · MXN',min_value=0.0,value=None,step=100.0,key='control_project_available',placeholder='Sólo para este escenario',persist_state='session')
        else:
            available_input=available/100 if available is not None else None
            st.caption('Total en cuentas: '+(money(available)+' MXN' if available is not None else 'agrega una cuenta en Tesorería.'))
        a,b=st.columns(2)
        reserve=a.number_input('Reserva que quieres conservar · MXN',min_value=0.0,value=0.0,step=100.0,key='control_project_reserve',persist_state='session')
        cost=b.number_input('Costo estimado del proyecto · MXN',min_value=0.01,value=None,step=100.0,key='control_project_cost',placeholder='Por definir',persist_state='session')
        st.caption(f"Gastos proyectados: {money(projection['projected_cents'])} MXN. La reserva es adicional a esos gastos.")
        try: result=control.project_coverage(available=available_input,reserve=reserve,project_cost=cost,pending_cents=projection['projected_cents'],allow_negative_available=True)
        except ValueError as exc: st.error(str(exc));return
        if result['missing']:
            st.caption('Completa: '+', '.join(result['missing'])+'.')
        else:
            with st.container(horizontal=True):
                st.metric('Para el proyecto',money(result['before_project_cents']),border=True)
                st.metric('Después del proyecto',money(result['after_project_cents']),border=True)
            st.badge('Se cubre con el dinero indicado' if result['covered'] else 'Falta '+money(result['shortfall_cents'])+' MXN para cubrirlo',
                     color='green' if result['covered'] else 'orange',icon=':material/check_circle:' if result['covered'] else ':material/pending:')
        st.caption('Total en cuentas − gastos proyectados − reserva − proyecto. Es una simulación de dinero disponible; no registra gastos ni aparta fondos.')


def render():
    from views.shell import actions
    with actions():
        if st.button('Captura completa',key='control_full_expense',icon=':material/receipt_long:'):expense_form()
        if st.button('Registrar gasto',key='control_quick_expense',type='primary',icon=':material/add:'):quick_expense_form()
    day=st.date_input('Mes de previsión y análisis',value=now().date().replace(day=1),key='budget_month',persist_state='session',width=260)
    report,projection=cash_projection.workspace(day.strftime('%Y-%m'))
    projection_cards(projection)
    if report['partner_cents']:st.caption(f"Cubierto por socios en el mes: {money(report['partner_cents'])} MXN; separado de las salidas de banco y caja.")
    overview,pending,planned,projects=workspace_tabs(['Resumen','Por pagar','Previsión','Evaluar proyecto'],'expense_control_tabs')
    if overview.open:
        with overview:
            account_cards(projection)
            summary_panel(report)
    if pending.open:
        with pending:pending_panel(report)
    if planned.open:
        with planned:planned_panel(projection)
    if projects.open:
        with projects:project_panel(report,projection)
    if st.toggle('Ver planeación detallada · opcional',key='budget_advanced_open'):
        with st.container(border=True):
            st.caption('Aquí se conservan los planes por categoría, sus versiones y las proyecciones anteriores. No son necesarios para registrar ni consultar gastos.')
            from views.budget_advanced import render as detailed_plan
            detailed_plan(day)
