"""Shared concise money cards and explicit balance/forecast confirmations."""
import streamlit as st
from services import cash_projection as cash
from services.quotations import money
from views.common import managed_dialog,perform
from views.treasury_components import financial_table


@managed_dialog('Conciliar saldos',width='large')
def balance_form(snapshot):
    st.caption('Los importes ya vienen de tus cuentas y movimientos. Ajusta únicamente las diferencias contra banco o caja y confirma. No se crearán ingresos ni gastos. Importes en MXN.')
    if not snapshot['accounts']:
        st.info('Primero agrega una cuenta en Tesorería → Cuentas.');return
    with st.form('cash_balances_form'):
        values={};cols=st.columns(2)
        for index,row in enumerate(snapshot['accounts']):
            value=cols[index%2].number_input(row['name']+' · '+row['kind'],value=row['balance_cents']/100 if row['balance_cents'] is not None else None,
                min_value=-1000000000.0,max_value=1000000000.0,step=100.0,format='%.2f',
                placeholder='Sin confirmar',key='cash_balance_'+str(row['id'])+'_'+st.session_state['dialog_request_key'])
            if value is not None:values[row['id']]=value
        st.caption('Los saldos incluyen los movimientos ya capturados. Los nuevos cobros y pagos registrados los actualizarán. Si hay movimientos externos, transferencias o correcciones de historial ya conciliado, vuelve a confirmar contra banco y caja.')
        if st.form_submit_button('Confirmar saldos',type='primary',width='stretch'):
            perform(cash.confirm_balances,values,expected={r['id']:r['token'] for r in snapshot['accounts']},
                request_key=st.session_state['dialog_request_key'],message='Saldos confirmados.')


@managed_dialog('Ajuste mensual de previsión',width='medium')
def forecast_form(plan):
    st.write('**Ajuste adicional · '+plan['month']+'**')
    st.caption('Usa este ajuste sólo para importes generales sin concepto. Prefiere agregar gastos previstos individuales: se pueden convertir en gastos sin duplicar la proyección.')
    with st.form('cash_forecast_form'):
        additional=st.number_input('Adicional por gastar · MXN',min_value=0.0,max_value=1000000000.0,value=plan['additional_cents']/100,step=100.0,format='%.2f')
        notes=st.text_area('Referencia · opcional',value=plan['notes'],placeholder='Ej. compras o servicios que aún faltan por registrar',max_chars=2000)
        st.caption('Este ajuste manual es adicional a los pendientes y a las previsiones por concepto. Redúcelo cuando ya no aplique.')
        if st.form_submit_button('Guardar previsión',type='primary',width='stretch'):
            perform(cash.save_forecast,plan['month'],additional,notes=notes,expected_id=plan['id'],
                    request_key=st.session_state['dialog_request_key'],message='Previsión guardada.')


def balance_details(snapshot):
    rows=[dict(r,status=r['basis'],confirmed=r['confirmed_at'] or 'Sin conciliación manual') for r in snapshot['accounts']]
    financial_table(rows,{'name':'Cuenta o caja','kind':'Tipo','balance_cents':'Saldo MXN','status':'Estado','confirmed':'Última confirmación'},
                    ['balance_cents'],label='Saldos de las cuentas activas, banco y efectivo por separado')
    st.caption('Movimientos: entradas menos salidas de todo el historial asignado a esa cuenta. Conciliado: último saldo confirmado más movimientos posteriores. Las cuentas archivadas no se suman.')
    if snapshot['unassigned']:
        st.caption(f"{snapshot['unassigned']} movimientos históricos sin cuenta: revísalos en Tesorería → Movimientos. Al asignarlos, revisa también el saldo confirmado.")


def projection_cards(result,*,key='control',details=True):
    from views.treasury_components import money_pulse
    snapshot=result['cash'];total=snapshot['total_cents'];after=result['after_cents']
    money_pulse([
        ('Total en cuentas',money(total) if total is not None else '—','calm'),
        ('Gastos proyectados',money(result['projected_cents']),'calm'),
        ('Después de gastos',money(after) if after is not None else '—','red' if after is not None and after<0 else 'calm'),
    ],key=key+'-pulse')
    st.caption(f"MXN · Por pagar {money(result['pending_cents'])[1:]} + por gastar {money(result['additional_cents'])[1:]} · Previsión {result['forecast']['month']}.")
    with st.container(horizontal=True,vertical_alignment='center'):
        if st.button('Agregar previsto',key=key+'_planned',icon=':material/add:'):
            from views.spending_plan_forms import planned_expense_form
            planned_expense_form(result['forecast']['month'])
        if st.button('Conciliar saldos',key=key+'_balance',icon=':material/account_balance_wallet:'):balance_form(snapshot)
        if after is not None:
            st.badge('Disponible proyectado' if after>=0 else 'Faltan '+money(-after),color='green' if after>=0 else 'orange')
        else:st.caption('Agrega una cuenta en Tesorería para empezar.')
    if snapshot['estimated']:st.caption('Saldo calculado con los movimientos existentes. '+str(len(snapshot['missing']))+' cuentas sin conciliación manual; el historial incluye '+str(snapshot['undated'])+' movimientos sin fecha.')
    if snapshot['unassigned']:st.caption(str(snapshot['unassigned'])+' movimientos sin cuenta no se incluyen en el saldo. Asígnalos desde Tesorería → Movimientos.')
    if not details:return
    with st.expander('Cuentas y cálculo',key=key+'_projection_detail',on_change='rerun') as detail:
        if detail.open:
            balance_details(snapshot)
            financial_table(result['accounts'],{'name':'Cuenta','balance_cents':'Saldo MXN','pending_cents':'Por pagar MXN','planned_cents':'Por gastar MXN','after_cents':'Después MXN'},
                            ['balance_cents','pending_cents','planned_cents','after_cents'],label='Proyección de gastos por cuenta')
            if result['unassigned_cents']:st.caption('Por asignar a cuenta: '+money(result['unassigned_cents'])+' MXN. Se descuenta del total global, todavía no de una cuenta específica.')
            st.write('**Total en cuentas − gastos proyectados = saldo estimado.**')
            st.caption('Incluye todos los pendientes actuales más lo previsto para el mes seleccionado. Lo pagado no se resta otra vez. No suma ventas por cobrar ni presupuestos anteriores.')
            if result['forecast']['notes']:st.write(result['forecast']['notes'])


def account_cards(result):
    from views.finance_workspace import open_account
    st.subheader('Dónde está el dinero',icon=':material/account_balance_wallet:')
    cols=st.columns(3)
    for index,row in enumerate(result['accounts']):
        with cols[index%3],st.container(border=True,gap='xxsmall'):
            st.write('**'+row['name']+'**')
            st.caption(row['kind']+' · '+row['basis'])
            st.metric('Saldo',money(row['balance_cents']))
            st.caption(f"Por pagar {money(row['pending_cents'])[1:]} · Por gastar {money(row['planned_cents'])[1:]} MXN")
            st.write('Después: **'+money(row['after_cents'])+'**')
            if st.button('Ver historial',key=f'account_history_{row["id"]}',icon=':material/history:',type='tertiary',width='stretch'):
                open_account(row['id'])
    if result['unassigned_cents']:st.caption('Hay '+money(result['unassigned_cents'])+' MXN de gastos sin cuenta prevista; ya se descuentan del saldo global.')
