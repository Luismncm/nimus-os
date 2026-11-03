from datetime import timedelta
import streamlit as st
from services import treasury, expenses, reconciliation
from services.quotations import money
from utils.dates import now
from views.sales_forms import direct_sale_form
from views.treasury_forms import account_form,assign_account_form
from views.reconciliation_forms import movement_form,correction_history,expense_reconciliation_form
from views.work_context import open_record
from views.capital import review_panel
from views.treasury_components import financial_table
from views.cash_projection_ui import balance_form,balance_details
from views.finance_workspace import money_header,open_account
from views.expense_control_forms import quick_expense_form

projection=money_header('treasury')
cash_snapshot=projection['cash']

# The same actions, with the same names, as on Ventas and Gastos y comprobantes.
from views.shell import actions
from views.emoji import icon_tabs
with actions():
    if st.button('Nueva venta directa',key='treasury_sale',icon=':material/point_of_sale:'): direct_sale_form()
    if st.button('Registrar gasto',key='treasury_expense',type='primary',icon=':material/add:'): quick_expense_form()

today=now().date()
account_rows=treasury.accounts()
accounts={r['id']:r for r in account_rows}
with st.expander('Filtros del historial',icon=':material/filter_alt:',expanded=st.session_state.pop('treasury_filters_open',False)):
    a,b,c=st.columns([2,2,1])
    period=a.selectbox('Período',('Todo el historial','Este mes','Mes anterior','Este año','Personalizado'),key='treasury_period',persist_state='session')
    selected=b.selectbox('Cuenta',['all',None,*accounts],format_func=lambda i:'Todas las cuentas' if i=='all' else 'Sin cuenta asignada' if i is None else accounts[i]['name'],key='treasury_account_filter',persist_state='session')
    kind=c.selectbox('Tipo',('Todas',*treasury.KINDS,'Sin asignar'),key='treasury_kind',persist_state='session')
    if period=='Todo el historial': start,end='0001-01-01','9999-12-31'
    elif period=='Este mes': start,end=today.replace(day=1),today
    elif period=='Mes anterior':
        end=today.replace(day=1)-timedelta(days=1); start=end.replace(day=1)
    elif period=='Este año': start,end=today.replace(month=1,day=1),today
    else:
        a,b=st.columns(2)
        start=a.date_input('Desde',value=today.replace(day=1),key='treasury_start',persist_state='session')
        end=b.date_input('Hasta',value=today,key='treasury_end',persist_state='session')
    st.caption('Estos filtros afectan el flujo y los movimientos consultados. Las tarjetas de saldo actual conservan el total general. Por revisar tiene su propia consulta.')

if str(start)>str(end):
    st.warning('Desde debe ser anterior o igual a Hasta.')
    st.stop()
report=treasury.ledger(start,end,account_id=selected,kind=kind,include_undated=period=='Todo el historial')
reviews=treasury.review_expenses()
# Cobrar y pagar live in Ventas and Gastos (and Hoy), Socios in its own page: Tesorería keeps what only it shows.
TABS=['Resumen','Movimientos','Por revisar','Cuentas']
if st.session_state.get('treasury_tabs') not in (None,*TABS): st.session_state.pop('treasury_tabs')
summary_tab,movement_tab,review_tab,accounts_tab=icon_tabs(TABS,key='treasury_tabs',on_change='rerun')

with summary_tab:
    # Where the money is, account by account, lives in Resumen y previsión; this tab is the flow of the query.
    # The numbers first; how to read them waits in one menu, like Ventas' «Sobre los totales».
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.subheader('Flujo de la consulta',icon=':material/swap_vert:')
        with st.popover('Cómo leer estas cifras',icon=':material/info:'):
            st.write('Cobros, aportaciones de socios y pagos vigentes. Los anticipos se cuentan una sola vez, incluso al convertir la cotización en venta.')
            st.write('El flujo de esta consulta es distinto del saldo actual mostrado arriba. Confirma los saldos contra banco y caja cuando haya movimientos externos o correcciones de historial ya conciliado.')
            st.write('Un gasto puede aparecer en varios controles de captura. Abre Por revisar para resolverlo desde su registro.')
            st.write('Conciliar saldos ajusta banco y caja sin generar ventas o gastos. Después de una transferencia interna o un movimiento externo, confirma de nuevo las cuentas afectadas.')
    with st.container(horizontal=True):
        st.metric('Entradas',money(report['income']),border=True)
        st.metric('Salidas',money(report['outflow']),border=True)
        st.metric('Flujo neto',money(report['net']),border=True)
    if report['undated']:
        st.caption(f"El historial incluye {report['undated']} movimientos sin fecha. Al elegir un período se excluyen; consulta gastos en Por revisar y aportaciones en Socios.")
    if report['unassigned']:
        st.warning(f"{report['unassigned']} movimientos de la consulta sin cuenta asignada. Puedes asignarla desde Movimientos.")
    financial_table(report['accounts'],{'account':'Cuenta','kind':'Tipo','income':'Entradas MXN','outflow':'Salidas MXN','net':'Flujo MXN'},
        ['income','outflow','net'],label='Flujo por cuenta en la consulta')
    with st.expander('Calidad de captura · todas las fechas'),st.container(horizontal=True):
        st.metric('Gastos con fecha pendiente',sum(any(i.startswith('Fecha') for i in r['issues']) for r in reviews),border=True)
        st.metric('Comprobantes / IVA por revisar',sum(any(i in ('Comprobante','Desglose IVA') for i in r['issues']) for r in reviews),border=True)
        st.metric('Concepto / categoría pendientes',sum(any(i in ('Concepto','Categoría') for i in r['issues']) for r in reviews),border=True)
    st.link_button('Hoja de control histórica',
        'https://docs.google.com/spreadsheets/d/1jmCHf1QxrXEZLHcKPJ5ArfY8qK2v6r951KKS-uW7PvU/edit',icon=':material/table_view:')

with movement_tab:
    st.subheader('Consulta de movimientos', icon=':material/receipt_long:')
    a,b,c=st.columns([2,1,1])
    search=a.text_input('Buscar movimiento',placeholder='Concepto, cliente, proveedor, folio o referencia',key='treasury_search',persist_state='session',icon=':material/search:')
    direction=b.selectbox('Movimiento',('Todos','Entradas','Salidas'),key='treasury_direction',persist_state='session')
    category=c.selectbox('Categoría',('Todas',*sorted({r['category'] for r in report['rows'] if r['category']})),key='treasury_category')
    query=treasury.ledger(start,end,account_id=selected,kind=kind,include_undated=period=='Todo el historial',search=search,direction=direction,category=category)
    with st.container(horizontal=True):
        st.metric('Movimientos encontrados',len(query['rows']))
        st.metric('Entradas de la búsqueda',money(query['income']))
        st.metric('Salidas de la búsqueda',money(query['outflow']))
        st.download_button('Exportar consulta CSV',treasury.csv_bytes(query['rows']),file_name='NIMUS_tesoreria.csv',mime='text/csv',disabled=not query['rows'],icon=':material/download:')
    financial_table([dict(r,day=r['paid_on'] or 'Sin fecha',income=r['amount'] if r['sign']==1 else None,outflow=r['amount'] if r['sign']==-1 else None) for r in query['rows']],
        {'day':'Fecha','concept':'Concepto','party':'Cliente / proveedor','account_name':'Cuenta',
         'category':'Categoría','income':'Entrada MXN','outflow':'Salida MXN','receipt_type':'Comprobante','document':'Documento','code':'Pago'},
        ['income','outflow'],label='Movimientos con concepto, cuenta y comprobante',
        # Picking a row makes it the movement to reconcile or open below.
        open=lambda r:st.session_state.update(treasury_source=f"{r['source']}:{r['id']}"),key='treasury_movements')
    if query['rows']:
        by_key={f"{r['source']}:{r['id']}":r for r in query['rows']}
        choice=st.selectbox('Consultar origen del movimiento',list(by_key),format_func=lambda k:f"{by_key[k]['code']} · {by_key[k]['concept']} · {money(by_key[k]['amount'])}",key='treasury_source')
        with st.container(horizontal=True):
            row=by_key[choice]
            if st.button('Conciliar movimiento',key='treasury_reconcile',icon=':material/edit:'):
                movement_form(row['source'],row['id'],reconciliation.state(row['source'],row['id']))
            if row['source']!='capital' and st.button('Abrir registro',key='treasury_open',icon=':material/open_in_new:'):
                open_record(row['record_kind'],row['record_id'])
            if row['source']=='expense' and st.button('Conciliar gasto',key='treasury_reconcile_expense'):
                expense_reconciliation_form(expenses.get_expense(row['record_id']),reconciliation.state('expense_document',row['record_id']))
            if by_key[choice]['account_id'] is None and st.button('Asignar cuenta a este cobro',key='treasury_assign'):
                assign_account_form(by_key[choice])
        correction_history(row['source'],row['id'])

with review_tab: review_panel(reviews)

with accounts_tab:
    balance_details(cash_snapshot)
    with st.container(horizontal=True,horizontal_alignment='distribute'):
        st.subheader('Cuentas del negocio', icon=':material/account_balance:')
        with st.container(horizontal=True,gap='small',width='content'):
            if st.button('Conciliar saldos',key='treasury_balance',icon=':material/account_balance_wallet:',
                         help='Ajusta las diferencias contra banco o caja; no crea ingresos ni gastos.'): balance_form(cash_snapshot)
            if st.button('Agregar cuenta',key='treasury_new_account',type='primary',icon=':material/add:'): account_form()
    st.caption('La cuenta indica dónde entró o salió el dinero. Archivar una cuenta conserva su historial.')
    for row in account_rows:
        with st.container(border=True,horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            st.write(f"**{row['name']}** · {row['kind']} · {'Activa' if row['active'] else 'Archivada'}")
            with st.container(horizontal=True,gap='small',width='content'):
                if st.button('Ver historial',key=f'treasury_history_{row["id"]}',icon=':material/history:'): open_account(row['id'])
                if st.button('Editar cuenta',key=f'treasury_edit_{row["id"]}'): account_form(row)
