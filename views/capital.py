"""Partner purchases and practical capture controls."""
import streamlit as st
from services import treasury, sheet_migration, expenses, reconciliation
from views.reconciliation_forms import movement_form,correction_history
from services.quotations import money
from views.work_context import open_record
from views.treasury_components import financial_table,table_csv,opens
from views.partner_forms import injection_form,void_injection_form


def partners_panel():
    """The Socios page: its one place, so Tesorería links here instead of repeating it."""
    allrows=sheet_migration.partner_rows()
    from views.shell import actions
    with actions():
        with st.popover('Cómo se refleja en las cuentas',icon=':material/info:'):
            st.write('Las aportaciones de dinero suman entradas de capital en la cuenta elegida. Las compras pagadas por el socio no salen del banco ni de caja; el reembolso vinculado se cuenta una sola vez en su gasto.')
        if st.button('Nueva aportación',key='partner_new',type='primary',icon=':material/add:'): injection_form()
    # Every filter on one line; the search takes the room left.
    a,b,c,d=st.columns([1,1,1,2])
    partner=a.selectbox('Socio',('Todos',*sorted({r['partner'] or 'Sin identificar' for r in allrows})),key='partner_filter')
    movement=b.selectbox('Tipo de movimiento',('Todos',*sorted({r['movement'] for r in allrows})),key='partner_movement')
    status=c.selectbox('Estado del registro',('Vigentes','Todos','Anulados'),key='partner_status')
    search=d.text_input('Buscar movimiento del socio',placeholder='Concepto o proveedor',key='partner_search',persist_state='session',icon=':material/search:')
    rows=[r for r in allrows if (partner=='Todos' or (r['partner'] or 'Sin identificar')==partner)
        and (movement=='Todos' or r['movement']==movement)
        and (status=='Todos' or bool(r['voided_at'])==(status=='Anulados'))
        and search.strip().casefold() in f"SOC-{r['id']:04d} {r['concept']} {r['partner']} {r['party']} {r['reference']} {r['expense_code'] or ''}".casefold()]
    active=[r for r in rows if not r['voided_at']]
    with st.container(horizontal=True):
        st.metric('Aportaciones a cuenta',money(sum(r['amount_cents'] for r in active if r['sign']==1)),border=True)
        st.metric('Compras cubiertas',money(sum(r['amount_cents'] for r in active if r['movement']=='Compra pagada por socio')),border=True)
        st.metric('Reembolsos vinculados',money(sum(r['amount_cents'] for r in active if r['movement']=='Reembolso al socio' and r['linked_expense_id'])),border=True)
        st.metric('Reembolsable pendiente',money(sum(r['pending_cents'] for r in active)),border=True)
    data=[dict(r,code=f"SOC-{r['id']:04d}",state='Anulado' if r['voided_at'] else 'Vigente',partner=r['partner'] or 'Sin identificar',day=r['moved_on'] or 'Sin fecha',flow='Registro anulado' if r['voided_at'] else f"Entrada a {r['account_name']}" if r['sign']==1 else 'Sin salida de caja/banco' if r['movement']=='Compra pagada por socio'
        else f"Salida en {r['expense_code']}" if r['linked_expense_id'] else 'Revisar vínculo') for r in rows]
    columns={'code':'Folio','day':'Fecha','partner':'Socio','movement':'Movimiento','concept':'Concepto','reference':'Referencia','amount_cents':'Total MXN','state':'Estado',
        'treatment':'Tratamiento','flow':'Efecto en tesorería','expense_code':'Gasto','pending_cents':'Por reembolsar MXN'}
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.caption('Aportaciones, compras cubiertas y reembolsos · todas las fechas. Toca una fila para abrir su gasto o conciliar la aportación.')
        st.download_button('Exportar socios CSV',table_csv(data,columns,('amount_cents','pending_cents')),file_name='NIMUS_socios.csv',mime='text/csv',disabled=not data,icon=':material/download:')
    # A purchase opens its expense; an aportación is picked below to edit or void it.
    financial_table(data,columns,['amount_cents','pending_cents'],label='Compras de socios y reembolsos sin duplicar salidas',
                    open=lambda r:open_record('Gasto',r['linked_expense_id']) if r['linked_expense_id'] else st.session_state.update(partner_focus_id=r['id']))
    if not allrows: st.info('Registra la primera aportación con Nueva aportación.')
    elif not rows: st.info('No hay movimientos con estos filtros. Prueba otro socio, estado o búsqueda.')
    injections={r['id']:r for r in rows if r['sign']==1 and not r['linked_expense_id']}
    if injections:
        if any(not r['moved_on'] or not r['partner'] for r in injections.values()):
            st.info('Hay aportaciones con fecha o socio pendiente. Se incluyen en Todo el historial; puedes completarlas aquí.')
        focus=st.session_state.pop('partner_focus_id',None)
        # A row picked in the table (or a new capture) becomes the aportación to work on.
        if focus in injections: st.session_state['partner_injection']=focus
        selected=st.selectbox('Aportación a conciliar',list(injections),
            format_func=lambda i:f"SOC-{i:04d} · {injections[i]['partner'] or 'Sin identificar'} · {money(injections[i]['amount_cents'])}",key='partner_injection')
        with st.container(horizontal=True):
            if st.button('Editar aportación',key='partner_edit',icon=':material/edit:',disabled=bool(injections[selected]['voided_at'])):
                movement_form('capital',selected,reconciliation.state('capital',selected))
            if st.button('Anular registro',key='partner_void',type='tertiary',disabled=bool(injections[selected]['voided_at'])):
                void_injection_form(reconciliation.state('capital',selected))
        correction_history('capital',selected)
    linked={r['id']:r for r in rows if r['linked_expense_id']}
    if linked:
        selected=st.selectbox('Consultar gasto del socio',list(linked),format_func=lambda i:f"{linked[i]['expense_code']} · {linked[i]['concept']}",key='partner_selected')
        if st.button('Abrir gasto del socio',key='partner_open',icon=':material/open_in_new:'):
            open_record('Gasto',linked[selected]['linked_expense_id'])


def review_panel(allrows):
    st.subheader('Datos por completar', icon=':material/edit_note:')
    st.caption('Gastos activos de todas las fechas. Un mismo gasto puede tener varios pendientes; su importe se cuenta una sola vez en esta consulta.')
    a,b,c=st.columns([1,1,2])
    issue=a.selectbox('Pendiente',('Todos','Fecha del gasto','Fecha del pago','Categoría','Concepto','Comprobante','Desglose IVA','Cuenta del pago'),key='treasury_review_issue')
    account=b.selectbox('Cuenta del gasto / pago',('Todas',*sorted({r['effective_account'] for r in allrows})),key='treasury_review_account')
    search=c.text_input('Buscar pendiente',placeholder='Concepto, proveedor o folio',key='treasury_review_search',persist_state='session')
    rows=[r for r in allrows if (issue=='Todos' or issue in r['issues']) and (account=='Todas' or r['effective_account']==account)
        and search.strip().casefold() in f"{r['code']} {r['concept']} {r['supplier']}".casefold()]
    with st.container(horizontal=True):
        st.metric('Gastos por revisar',len(rows))
        st.metric('Importe de estos gastos',money(sum(r['total_cents'] for r in rows)))
    columns={'code':'Gasto','concept':'Concepto','supplier':'Proveedor','effective_account':'Cuenta','total_cents':'Total MXN','review':'Completar'}
    st.download_button('Exportar pendientes CSV',table_csv(rows,columns,('total_cents',)),file_name='NIMUS_pendientes_captura.csv',mime='text/csv',disabled=not rows)
    financial_table(rows,columns,['total_cents'],label='Gastos con datos pendientes y motivo de revisión',open=opens('Gasto'))
    if rows:
        by_id={r['id']:r for r in rows}
        selected=st.selectbox('Revisar gasto',list(by_id),format_func=lambda i:f"{by_id[i]['code']} · {by_id[i]['concept']}",key='treasury_review_selected')
        st.caption(by_id[selected]['review'])
        if st.button('Abrir gasto para completar',key='treasury_review_open',type='primary',icon=':material/edit:'):
            open_record('Gasto',selected)
    with st.expander('Cómo completar fechas y comprobantes'):
        st.write('En el detalle del gasto, usa Editar gasto para completar fecha, concepto, categoría o comprobante. La fecha del gasto y la del pago son independientes.')
        st.caption('Puedes completar la clasificación de un gasto histórico aunque todavía desconozcas su fecha. Una fecha ya registrada no se puede borrar.')
        st.write('Para corregir fecha, importe o cuenta de un pago, usa Conciliar movimiento en Tesorería o Conciliar pago en el gasto. Para corregir el importe del gasto y su IVA, usa Conciliar gasto. Cada corrección pide un motivo y conserva los valores anteriores. Adjunta la factura desde Factura y PDF.')


def historical_expenses_panel():
    rows=[r for r in treasury.review_expenses() if any(i.startswith('Fecha') for i in r['issues'])]
    st.subheader('Gastos con fecha pendiente', icon=':material/event_busy:')
    st.caption('Incluye fecha del gasto o del pago pendiente. Los pagos sin fecha se muestran en Tesorería → Todo el historial, pero se excluyen de los períodos. Completar la fecha del gasto no modifica la fecha de su pago.')
    st.download_button('Exportar gastos sin fecha CSV',expenses.export_csv(rows),file_name='NIMUS_gastos_sin_fecha.csv',mime='text/csv',disabled=not rows)
    financial_table(rows,{'code':'Folio','concept':'Concepto','category':'Categoría','effective_account':'Cuenta','total_cents':'Total MXN','review':'Completar'},
        ['total_cents'],label='Gastos con fecha del documento o del pago pendiente',open=opens('Gasto'))
    if rows:
        by_id={r['id']:r for r in rows}
        selected=st.selectbox('Consultar gasto histórico',list(by_id),format_func=lambda i:f"{by_id[i]['code']} · {by_id[i]['concept']}",key='historical_expense')
        if st.button('Abrir gasto histórico',key='historical_expense_open'): open_record('Gasto',selected)
