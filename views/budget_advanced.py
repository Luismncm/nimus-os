"""Monthly planning, category control and saved projections."""
import json
import uuid
import pandas as pd
import streamlit as st
from services import budgets as b
from services.quotations import cents, money
from views.common import perform, table
from views.treasury_components import financial_table, table_csv
from views.emoji import icon_tabs


def clear_draft(_=None):
    old=st.session_state.pop('budget_draft',None)
    if old: st.session_state.get('budget_drafts',{}).pop(old['month'],None)


def prepare_draft(month,plan,lines,source):
    draft=dict(month=month,header={k:plan[k] for k in b.HEADER_FIELDS},
        lines=b.structure(dict(lines=lines)),revision=b.get_month(month)['revision'],token=uuid.uuid4().hex,source=source)
    st.session_state.setdefault('budget_drafts',{})[month]=draft
    st.session_state['budget_draft']=draft
    st.rerun()


def currency(value):
    return money(value) if value is not None else 'Pendiente'


def render(day):
    month=day.strftime('%Y-%m')
    plan=b.get_month(month)
    drafts=st.session_state.setdefault('budget_drafts',{})
    draft=drafts.get(month)
    if not draft:
        draft=dict(month=month,header={k:plan[k] for k in b.HEADER_FIELDS},lines=b.structure(plan),revision=plan['revision'],
            token=uuid.uuid4().hex,source='Presupuesto guardado' if plan['revision'] is not None else 'Estructura base; importes por definir')
        drafts[month]=draft
    st.session_state['budget_draft']=draft
    editing,control,projection,history=icon_tabs(['Plan mensual','Control por categoría','Proyecciones','Historial'],key='budget_tabs',on_change='rerun')

    with editing:
        st.subheader(f'Presupuesto de {month}', icon=':material/savings:')
        st.badge('Mes por definir' if plan['revision'] is None else f"Plan guardado · versión {plan['revision']+1}",color='orange' if plan['revision'] is None else 'green')
        st.caption('1. Prepara el mes → 2. Ajusta topes → 3. Guarda y revisa el control. Importes totales en MXN, incluyendo IVA cuando corresponda.')
        with st.expander('Preparar una propuesta editable',icon=':material/auto_awesome:'):
            st.caption('Revisa las propuestas antes de guardarlas. Recurrentes usa el equivalente mensual: adapta las cuotas anuales o bimestrales al mes en que realmente pagarás.')
            a,c=st.columns(2)
            if a.button('Usar costos recurrentes',key='budget_from_recurring',width='stretch'):
                lines=b.suggestion(month,'recurrentes')
                if lines: prepare_draft(month,plan,lines,'Propuesta desde costos recurrentes activos')
                else: st.info('No hay costos recurrentes activos con equivalente mensual.')
            previous=b.shift(month,-1)
            if c.button(f'Usar pagos de {previous}',key='budget_from_history',width='stretch'):
                lines=b.suggestion(previous,'histórico')
                if lines: prepare_draft(month,plan,lines,f'Propuesta desde pagos de {previous}; revisar fijos, variables y partidas no recurrentes')
                else: st.info('No hay pagos fechados de gastos en ese mes.')
            sources=[r['month'] for r in b.list_months() if r['month']!=month]
            if sources:
                a,c=st.columns([3,1],vertical_alignment='bottom')
                source=a.selectbox('Copiar un mes guardado',sources,key='budget_copy_month')
                if c.button('Preparar copia',key='budget_copy',width='stretch'):
                    old=b.get_month(source); prepare_draft(month,old,old['lines'],f'Copia editable de {source}')
        st.caption(draft['source'])
        key=f"budget_{month}_{draft['token']}"
        header=draft['header']
        with st.container(border=True):
            receipts=st.number_input('Meta de cobros del mes · MXN',min_value=0.0,value=header['receipts_cents']/100 if header['receipts_cents'] is not None else None,
                step=1000.0,key=key+'_receipts',placeholder='Por definir')
            draft_status=st.container()
            live_totals=st.container(horizontal=True)
            frame=pd.DataFrame([dict(Categoría=r['category'],Fijo=r['fixed_cents']/100,Variable=r['variable_cents']/100,
                Uso=r['role'],Prioridad=r['priority'],IVA=b.TAX_LABELS[r['tax_bps']],Notas=r['notes']) for r in draft['lines']])
            editor=st.data_editor(frame,hide_index=True,disabled=['Categoría'],height=550,key=key+'_lines',column_config={
                'Categoría':st.column_config.TextColumn('Categoría',width='large',pinned=True),
                'Fijo':st.column_config.NumberColumn('Fijo MXN',min_value=0,step=100.0,format='$%.2f',required=True),
                'Variable':st.column_config.NumberColumn('Variable MXN',min_value=0,step=100.0,format='$%.2f',required=True),
                'Uso':st.column_config.SelectboxColumn('Uso',options=b.ROLES,required=True),
                'Prioridad':st.column_config.SelectboxColumn('Prioridad',options=b.PRIORITIES,required=True),
                'IVA':st.column_config.SelectboxColumn('IVA previsto',options=list(b.TAX_LABELS.values()),required=True),
                'Notas':st.column_config.TextColumn('Motivo / acción del mes',width='large')},alt='Presupuesto editable de fijos y variables por categoría')
            st.caption('Uso y prioridad son propuestas editables. En Variable captura el monto para la meta del mes; en rentabilidad se ajustará en proporción a las ventas.')
            with st.expander('Supuestos de rentabilidad',icon=':material/trending_up:'):
                net=st.number_input('Meta de ventas netas sin IVA · MXN',min_value=0.0,value=header['net_sales_cents']/100 if header['net_sales_cents'] is not None else None,
                    step=1000.0,key=key+'_net',placeholder='Por definir')
                margin=st.number_input('Margen después de costos directos · %',min_value=0.01,max_value=100.0,
                    value=header['margin_bps']/100 if header['margin_bps'] is not None else None,step=1.0,key=key+'_margin',placeholder='Por definir')
                st.caption('Usa un margen sustentado en tus recetas y mezcla de ventas. El escenario descuenta únicamente gastos marcados Operación, con IVA definido; los costos directos ya están incluidos en el margen.')
            notes=st.text_area('Objetivo y decisiones de este mes',value=header['notes'],key=key+'_notes',height=80,
                placeholder='Reducir software, mantener renta, probar pauta con un tope…')
            draft_valid=False
            try:
                tax_lookup={v:k for k,v in b.TAX_LABELS.items()}
                lines=[dict(category=r['Categoría'],fixed_cents=cents(r['Fijo']),variable_cents=cents(r['Variable']),role=r['Uso'],priority=r['Prioridad'],
                    tax_bps=tax_lookup[r['IVA']],notes=r['Notas'] if pd.notna(r['Notas']) else '') for r in editor.to_dict('records')]
                values=dict(receipts_cents=cents(receipts) if receipts is not None else None,net_sales_cents=cents(net) if net is not None else None,
                    margin_bps=cents(margin) if margin is not None else None,notes=notes)
                values,normalized_lines=b.normalize(values,lines)
                draft['header']=values
                draft['lines']=lines
                draft_valid=True
            except (ValueError,KeyError,TypeError) as exc: st.error('Revisa los importes, uso, prioridad e IVA. '+str(exc))
            if draft_valid:
                base_header,base_lines=b.normalize(plan,b.structure(plan))
                changed=plan['revision'] is None or values!=base_header or normalized_lines!=base_lines
                with draft_status:
                    st.badge('Borrador sin guardar' if changed else 'Sin cambios pendientes',color='orange' if changed else 'green')
                fixed=sum(r['fixed_cents'] for r in lines); variable=sum(r['variable_cents'] for r in lines)
                with live_totals:
                    st.metric('Fijos del borrador',money(fixed),border=True)
                    st.metric('Variables del borrador',money(variable),border=True)
                    st.metric('Total previsto del borrador',money(fixed+variable),border=True)
                    st.metric('Flujo previsto del borrador',currency(values['receipts_cents']-fixed-variable if values['receipts_cents'] is not None else None),border=True)
            st.caption('Tus cambios se conservan como borrador al cambiar de mes durante esta sesión. Control y proyección mensual usan el plan guardado; los escenarios permiten probar el borrador actual.')
            if st.button('Guardar presupuesto',type='primary',width='stretch',icon=':material/check:',key=key+'_save',disabled=not draft_valid):
                perform(b.save_month,month,values,normalized_lines,expected_revision=draft['revision'],request_key=draft['token'],after=clear_draft,message='Presupuesto guardado con historial.')
        if st.button('Recargar presupuesto guardado',key='budget_reload',type='tertiary',icon=':material/refresh:'):
            clear_draft(); st.rerun()

    with control:
        report=b.comparison(month); saved=plan['revision'] is not None
        st.subheader('Presupuesto frente a pagos reales', icon=':material/compare_arrows:')
        if not saved: st.info('Guarda el plan mensual para fijar los topes. Los pagos reales ya están disponibles.')
        with st.container(horizontal=True):
            st.metric('Presupuesto de pagos',currency(report['budget_cents'] if saved else None),border=True)
            st.metric('Pagado desde cuentas',money(report['paid_cents']),border=True)
            st.metric('Por ejercer del presupuesto',currency(report['budget_cents']-report['paid_cents'] if saved else None),border=True)
            st.metric('Cobros de ventas y anticipos',money(report['receipts_cents']),border=True)
        st.caption(f"Aportaciones y ajustes de socios en cuentas: {money(report['capital_cents'])} MXN; separados de los cobros comerciales.")
        if report['undated_count']: st.info(f"Hay {report['undated_count']} pagos históricos sin fecha por {money(report['undated_cents'])} MXN; aún no pueden asignarse a un mes.")
        cols={'category':'Categoría','priority':'Prioridad','fixed_cents':'Fijo MXN','variable_cents':'Variable MXN','budget_cents':'Presupuesto MXN',
            'paid_cents':'Pagado MXN','available_cents':'Disponible del presupuesto MXN','registered_cents':'Gasto registrado MXN','partner_cents':'Cubierto por socio MXN','state':'Control'}
        amounts=('fixed_cents','variable_cents','budget_cents','paid_cents','available_cents','registered_cents','partner_cents')
        visible=[r for r in report['rows'] if r['budget_cents'] or r['paid_cents'] or r['registered_cents'] or r['partner_cents']]
        financial_table(visible,cols,amounts,label='Presupuesto y gasto real por categoría')
        st.download_button('Exportar control CSV',table_csv(visible,cols,amounts),file_name=f'NIMUS_presupuesto_{month}.csv',mime='text/csv',key='budget_csv')
        st.caption('Pagado usa la fecha efectiva de salida. Gasto registrado usa la fecha del documento e incluye compras cubiertas por socios; no se suma a Pagado. Disponible del presupuesto es el tope por ejercer, no el saldo bancario.')
        overruns=[r for r in visible if r['over_cents']]
        if overruns and saved:
            st.warning(f'{len(overruns)} categorías superan el tope o no tienen presupuesto. Revisa la diferencia antes de reasignar.')
            for row in overruns[:8]: st.write(f"**{row['category']}** · exceso {money(row['over_cents'])} · {row['priority']}")
        adjustable=[dict(r,total_cents=r['fixed_cents']+r['variable_cents']) for r in plan['lines'] if r['priority']!='Esencial' and r['fixed_cents']+r['variable_cents']>0]
        if adjustable:
            st.subheader('Partidas que puedes revisar para reasignar', icon=':material/swap_vert:')
            financial_table(adjustable,{'category':'Categoría','priority':'Prioridad','total_cents':'Tope MXN','notes':'Motivo / acción'},['total_cents'],label='Topes ajustables del mes')

    with projection:
        st.subheader('Proyección de los próximos meses', icon=':material/trending_up:')
        horizon=st.selectbox('Horizonte',(3,6,12),index=1,key='budget_horizon',format_func=lambda n:f'{n} meses')
        forecast=b.forecast(month,count=horizon)
        financial_table(forecast,{'month':'Mes','state':'Plan','receipts_cents':'Cobros previstos MXN','fixed_cents':'Fijos MXN','variable_cents':'Variables MXN',
            'total_cents':'Pagos previstos MXN','net_cents':'Flujo del mes MXN','cumulative_cents':'Flujo acumulado MXN'},
            ['receipts_cents','fixed_cents','variable_cents','total_cents','net_cents','cumulative_cents'],label='Proyección mensual de cobros y pagos presupuestados')
        st.caption('Cada mes usa su plan guardado. Las celdas vacías requieren completar el presupuesto o la meta de cobros; el acumulado se detiene cuando falta un mes. Este flujo no es saldo real: el estado de cuenta y el arqueo siguen pendientes.')
        complete=[r for r in forecast if r['net_cents'] is not None]
        if complete:
            chart=pd.DataFrame([{'Mes':r['month'],'Cobros previstos':r['receipts_cents']/100,'Pagos previstos':r['total_cents']/100} for r in complete])
            st.bar_chart(chart,x='Mes',y=['Cobros previstos','Pagos previstos'],stack=False,alt='Cobros y pagos previstos en meses con metas completas')
        st.subheader('Escenario de rentabilidad operativa', icon=':material/insights:')
        st.caption('Vista previa del borrador actual; usa Guardar presupuesto para aplicar tus decisiones al control mensual.')
        if not draft_valid: st.info('Corrige los campos del plan para probar el escenario.')
        else:
            factor=st.slider('Ventas frente a la meta · %',min_value=0,max_value=200,value=100,step=5,key='budget_sales_factor')
            cut=st.slider('Reducir topes de operación ajustables y opcionales · %',min_value=0,max_value=100,value=0,step=5,key='budget_adjustable_cut')
            scenario=b.profitability(dict(draft['header'],lines=draft['lines']),sales_factor=factor/100,adjustable_cut=cut/100)
            st.caption('La simulación conserva los topes esenciales y el presupuesto guardado. Si decides aplicar el ajuste, edita las categorías en Plan mensual y guarda una nueva versión.')
            if scenario['missing']: st.info('Completa los supuestos para calcular: '+', '.join(scenario['missing'])+'.')
            else:
                with st.container(horizontal=True):
                    st.metric('Ventas netas del escenario',money(scenario['sales_cents']),border=True)
                    st.metric('Resultado operativo estimado',money(scenario['profit_cents']),border=True)
                    st.metric('Ventas netas para cubrir operación',currency(scenario['break_even_cents']),border=True)
                if scenario['break_even_cents'] is None: st.warning('Los variables de operación consumen el margen disponible. Revisa costos, precio y variables; reducir fijos por sí solo no alcanza.')
                elif scenario['profit_cents']<0: st.warning(f"Faltan {money(-scenario['profit_cents'])} MXN de margen para cubrir la operación en este escenario.")
                st.caption('Ventas netas × margen después de costos directos − gastos de operación sin IVA. Los variables se ajustan con las ventas; los fijos se mantienen. Las inversiones se incluyen en pagos previstos y quedan fuera de este resultado. Es una estimación con tus supuestos.')

    with history:
        events=b.history(month)
        if not events: st.info('El historial comienza al guardar el primer presupuesto.')
        else:
            table(events,{'revision':'Versión','created_at':'Fecha y hora'},label='Versiones del presupuesto mensual')
            selected=st.selectbox('Consultar versión',range(len(events)),format_func=lambda i:f"Versión {events[i]['revision']} · {events[i]['created_at']}",key='budget_history')
            snapshot=json.loads(events[selected]['snapshot'])
            financial_table(snapshot['lines'],{'category':'Categoría','fixed_cents':'Fijos MXN','variable_cents':'Variables MXN','role':'Uso','priority':'Prioridad','notes':'Notas'},
                ['fixed_cents','variable_cents'],label='Presupuesto de la versión seleccionada')
            st.caption(f"Cobros previstos: {currency(snapshot['receipts_cents'])} · Ventas netas: {currency(snapshot['net_sales_cents'])}")
            if snapshot['notes']: st.write(snapshot['notes'])
