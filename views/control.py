import streamlit as st
from services import resources,quality,order_costs,alerts
from services.queries import load_snapshot
from services.quotations import money
from views.common import table,perform
from views.components import status_badge
from views.navigation import open_order,open_queue
from views.quality_forms import failure_form,reprint_form,consumption_form,extra_cost_form,void_extra_form,link_sale_form,material_reading_form,maintenance_due_form
from utils.dates import fmt

snapshot=st.session_state['snapshot']
view=st.segmented_control('Control del taller',('Capacidad','Fallas y reimpresiones','Costos y margen','Avisos'),default='Capacidad',
    key='control_view',persist_state='session',width='stretch',label_visibility='collapsed',
    format_func=lambda v:{'Capacidad':':material/speed: Capacidad','Fallas y reimpresiones':':material/report: Fallas y reimpresiones',
                          'Costos y margen':':material/payments: Costos y margen','Avisos':':material/notifications: Avisos'}[v]) or 'Capacidad'

def job_lookup():return {j['id']:j for j in st.session_state['snapshot']['jobs']}
def price(v):return money(v) if v is not None else '—'

if view=='Capacidad':
    a,b=st.columns([1,3],vertical_alignment='bottom')
    block=a.number_input('Bloque requerido · minutos',min_value=1,max_value=525600,value=120,step=30,key='capacity_minutes',persist_state='session')
    b.caption('Busca el primer intervalo libre desde ahora, con la duración indicada. Las máquinas distintas pueden imprimir en paralelo. Los lotes sin horario completo requieren programación para reservar capacidad.')
    rows=resources.capacity(snapshot,block)
    for start in range(0,len(rows),2):
        for col,row in zip(st.columns(min(2,len(rows)-start)),rows[start:start+2]):
            with col.container(border=True):
                st.subheader(row['code']);st.caption(row['name']);status_badge(row['status'])
                st.write('**Primer espacio libre:** '+fmt(row['available_from'],time=True) if row['available_from'] else '**Disponibilidad pendiente:** revisa el estado o el fin del trabajo en marcha.')
                st.caption(f"{row['pending_units']} unidades pendientes · {row['estimated_hours']:.1f} h capturadas · {row['unplanned']} lotes sin intervalo completo")
                if st.button('Gestionar esta máquina',key=f'capacity_machine_{row["id"]}',icon=':material/precision_manufacturing:'):open_queue(machine_id=row['id'])
    table([dict(r,free=fmt(r['available_from'],time=True)) for r in rows],{'code':'Máquina','status':'Estado','free':'Primer bloque disponible','pending_units':'Unidades pendientes','unplanned':'Sin intervalo','estimated_hours':'Horas previstas'},label='Disponibilidad por máquina')
elif view=='Fallas y reimpresiones':
    lookup=job_lookup()
    eligible={i:j for i,j in lookup.items() if j['started_at'] and j['order_status']!='Entregado' and not j.get('commercial_cancelled')}
    a,b=st.columns([3,1],vertical_alignment='bottom')
    if eligible:
        selected=a.selectbox('Lote para registrar falla',list(eligible),format_func=lambda i:f"{eligible[i]['code']} · {eligible[i]['part_name']} · {eligible[i]['project']}",key='quality_selected_job')
        if b.button('Registrar falla',key='control_failure',type='primary',width='stretch'):failure_form(eligible[selected])
    else:st.info('Las fallas se registran en trabajos iniciados. También encontrarás la acción Falla en la cola.')
    search=st.text_input('Buscar falla',placeholder='Trabajo, pedido, pieza o causa',key='quality_search',persist_state='session')
    rows=[r for r in quality.failures() if search.casefold() in f"{r['job_code']} {r['order_code']} {r['part_name']} {r['cause']}".casefold()]
    a,b,c=st.columns(3)
    a.metric('Eventos de falla',len(rows),border=True)
    b.metric('Rechazos acumulados',sum(r['rejected_units'] for r in rows),border=True)
    c.metric('Merma capturada',f"{sum(r['waste_grams'] or 0 for r in rows):g} g",border=True)
    st.caption('Los rechazos pueden incluir varios intentos sobre las mismas pendientes. Los gramos sin capturar permanecen pendientes; la merma ya forma parte del consumo total de cada lote.')
    for r in rows:
        with st.container(border=True):
            st.write(f"**{r['job_code']} · {r['part_name']} · {r['cause']}**")
            st.caption(f"{r['order_code']} · {r['created_at'][:16]} · {r['rejected_units']} rechazadas · {str(r['waste_grams'])+' g' if r['waste_grams'] is not None else 'Merma pendiente'}")
            if r['notes']:st.write(r['notes'])
            if r['reprint_id']:st.badge('Reimpresión · '+r['reprint_status'],color='orange' if r['reprint_status']!='Finalizada' else 'green')
            job=lookup.get(r['job_id'])
            with st.container(horizontal=True):
                if job and r['remaining']>0 and not r['reprint_id'] and job['order_status']!='Entregado':
                    if st.button(f'Reimprimir {r["remaining"]} pendientes',key=f'quality_reprint_{r["id"]}',type='primary'):reprint_form(job,r['id'])
                if st.button('Abrir pedido',key=f'quality_order_{r["id"]}'):open_order(r['order_id'])
    if not rows:st.caption('Sin fallas registradas en esta consulta.')
elif view=='Costos y margen':
    reports=order_costs.reports(snapshot)
    by_order={r['order_id']:r for r in reports}
    if not by_order:
        st.info('Crea un pedido para consultar su costeo.');st.stop()
    if st.session_state.get('control_cost_order') not in by_order:st.session_state['control_cost_order']=next(iter(by_order))
    selected=st.selectbox('Pedido a costear',list(by_order),format_func=lambda i:f"{by_order[i]['code']} · {by_order[i]['project']} · {by_order[i]['client']}",key='control_cost_order',persist_state='session')
    row=by_order[selected]
    if row['development']:
        # Prototyping is a cost of development: no revenue, no margin, compared against its budget.
        budget=next(o['development']['budget_cents'] for o in snapshot['orders'] if o['id']==selected)
        st.caption('Proyecto de desarrollo · costo sin IVA de impresiones, consumibles y costos adicionales. No es una venta y no tiene margen.')
        a,b,c=st.columns(3)
        a.metric('Costo de desarrollo',money(row['actual_known_cents']),border=True)
        b.metric('Presupuesto',price(budget),border=True)
        c.metric('Disponible del presupuesto',price(budget-row['actual_known_cents'] if budget is not None else None),border=True)
        if not row['complete']:st.info(f"Costo provisional: {row['costed_jobs']}/{row['job_count']} impresiones con consumo final confirmado.")
    else:
        st.caption('Comparación sin IVA: ingreso neto de ventas vinculadas, material real, tiempo de máquina y costos adicionales explícitos. Las cotizaciones sin venta registrada no suman ingreso.')
        a,b,c,d=st.columns(4)
        a.metric('Venta neta vinculada',price(row['revenue_cents']),border=True)
        b.metric('Costos reales capturados',money(row['actual_known_cents']),border=True)
        c.metric('Margen sobre costos registrados',price(row['margin_cents']),border=True)
        d.metric('Margen %',f"{row['margin_percent']:.1f}%" if row['margin_percent'] is not None else '—',border=True)
        if not row['complete']:st.info(f"Costeo provisional: {row['costed_jobs']}/{row['job_count']} lotes con consumo final confirmado. Completa los datos pendientes para mostrar el margen.")
        if row['scope_unfinished']:st.caption('La producción del pedido todavía no está completamente definida o cubierta; el margen sigue provisional.')
    if row['revenue_cents'] is None and not row['development']:
        if st.button('Vincular venta existente',key='cost_link_sale',icon=':material/link:'):link_sale_form(selected)
    if row['tax_unknown']:st.warning('Hay gastos incluidos sin desglose de IVA. El margen permanece provisional.')
    if row['unavailable_expenses']:st.warning('Un gasto vinculado ya no está activo. Revisa su costo adicional.')
    if row['missing_stock_cost']:st.warning(f"Hay {row['stock_units']} piezas tomadas de inventario sin costo incorporado. Agrega un costo de tipo Inventario utilizado.")
    st.caption(f"Previsión vigente de lotes con datos completos: {row['estimated_cents']/100:,.2f} MXN · Extras registrados: {row['extras_cents']/100:,.2f} MXN. La previsión no genera gastos ni pagos.")
    table([dict(j,actual_material=price(j['consumption']['material_cost_cents']),actual_machine=price(j['consumption']['machine_cost_cents']),actual_total=price(j['consumption']['actual_cost_cents']),
        state='Confirmado' if j['consumption']['complete'] else 'Pendiente / parcial') for j in row['jobs']],
        {'code':'Trabajo','part_name':'Pieza','actual_consumed_grams':'Gramos reales','actual_minutes':'Minutos reales','rejected_total':'Rechazos','waste_total':'Merma g','actual_material':'Material MXN','actual_machine':'Máquina MXN','actual_total':'Costo MXN','state':'Costeo'},label='Costos reales por lote')
    if row['jobs']:
        jobs={j['id']:j for j in row['jobs']}
        a,b=st.columns([3,1],vertical_alignment='bottom')
        jid=a.selectbox('Lote para capturar consumos',list(jobs),format_func=lambda i:f"{jobs[i]['code']} · {jobs[i]['part_name']}",key='cost_job_selected')
        if b.button('Corregir costo',key='control_consumption',type='primary',width='stretch'):consumption_form(jobs[jid])
    st.subheader('Consumibles del pedido', icon=':material/inventory:')
    with st.container(horizontal=True,vertical_alignment='center',horizontal_alignment='distribute'):
        st.caption(f"{money(row['consumables_cents'])} MXN sumados al costo real"
                   +(f" · {row['consumables_unknown']} sin costo de referencia (margen provisional)" if row['consumables_unknown'] else '')
                   +'. El filamento ligado a un lote se muestra aquí pero su costo entra por el costo real del lote.')
        if st.button('Registrar consumible usado',key='control_consumable_use',icon=':material/add:'):
            from views.consumables_ui import consumable_use_form
            consumable_use_form(selected)
    if row['consumables']:
        from services.consumables import quantity_text
        table([dict(m,day=m['created_at'][:10],quantity_text=quantity_text(-m['quantity'],m['unit']),cost=price(m['cost_cents']),
                    counted='Sí' if m['charged'] else 'En el lote '+m['job_code']) for m in row['consumables']],
              {'day':'Fecha','item':'Consumible','quantity_text':'Cantidad','cost':'Costo MXN','counted':'Suma al pedido','notes':'Nota'},label='Consumibles usados en el pedido')
    st.subheader('Costos adicionales', icon=':material/add_card:')
    if st.button('Agregar costo adicional',key='control_extra',icon=':material/add:'):extra_cost_form(selected)
    extra=order_costs.extras(selected)
    table([dict(r,amount=price(r['expense_subtotal'] if r['expense_id'] and r['expense_subtotal'] is not None else r['expense_total'] if r['expense_id'] else r['amount_cents'])) for r in extra],
        {'concept':'Concepto','cost_type':'Tipo','expense_code':'Gasto vinculado','amount':'Importe MXN','status':'Estado'},label='Costos adicionales del pedido')
    active={r['id']:r for r in extra if r['status']=='Activo'}
    if active:
        with st.expander('Corregir costo adicional',key='control_extra_correct',on_change='ignore'):
            chosen=st.selectbox('Costo para anular',list(active),format_func=lambda i:active[i]['concept'])
            if st.button('Anular costo adicional',key='control_void_extra'):void_extra_form(active[chosen])
    with st.expander('Comparar todos los pedidos',key='control_all_costs',on_change='ignore'):
        table([dict(r,revenue=price(r['revenue_cents']),cost=price(r['actual_known_cents']),margin=price(r['margin_cents']),state='Completo' if r['complete'] else 'Provisional') for r in reports],
            {'code':'Pedido','project':'Proyecto','revenue':'Venta neta MXN','cost':'Costos capturados MXN','margin':'Margen MXN','state':'Costeo'},label='Comparación de costos y margen por pedido')
else:
    @st.fragment(run_every='60s')
    def live_alerts():
        fresh=load_snapshot()
        rows=alerts.feed(fresh)
        a,b=st.columns([3,1],vertical_alignment='bottom')
        a.caption('Se actualiza cada minuto mientras esta vista esté abierta. Se muestran condiciones actuales; un aviso resuelto desaparece. Visto o pospuesto no modifica la producción.')
        if b.button('Actualizar avisos',key='control_alert_refresh',width='stretch'):st.rerun(scope='fragment')
        with st.expander('Anticipación del aviso',key='control_alert_settings',on_change='ignore'):
            with st.form('alert_settings'):
                lead=st.number_input('Avisar antes del fin · minutos',min_value=1,max_value=1440,value=alerts.lead_minutes(),step=5)
                if st.form_submit_button('Guardar anticipación'):perform(alerts.settings,lead,message='Anticipación guardada.')
        with st.container(horizontal=True):
            if st.button('Material disponible',key='control_material_reading',icon=':material/inventory_2:'):material_reading_form()
            if st.button('Próximo mantenimiento',key='control_maintenance_due',icon=':material/build:'):maintenance_due_form()
        state=st.selectbox('Mostrar avisos',('Pendiente','Todos','Pospuesto','Visto'),key='control_alert_state',persist_state='session')
        filtered=[r for r in rows if state=='Todos' or r['state']==state]
        st.write(f"**{sum(r['state']=='Pendiente' for r in rows)} avisos pendientes**")
        lookup={j['id']:j for j in fresh['jobs']}
        if not filtered:st.success('No hay avisos en esta consulta.')
        for r in filtered:
            with st.container(border=True):
                st.badge(r['kind'],color=r['severity']);st.write(r['detail']);st.caption(r['state'])
                with st.container(horizontal=True):
                    if r['record_kind']=='Trabajo':
                        job=lookup[r['record_id']]
                        if st.button('Abrir lote',key='alert_open_'+r['identity']):open_queue(order_id=job['order_id'],machine_id=job['machine_id'])
                    elif r['record_kind']=='Pedido':
                        if st.button('Abrir pedido',key='alert_open_'+r['identity']):open_order(r['record_id'])
                    elif r['record_kind']=='Máquina':
                        if st.button('Abrir máquina',key='alert_open_'+r['identity']):open_queue(machine_id=r['record_id'])
                    elif r['record_kind']=='Insumo':
                        if st.button('Revisar reposición',key='alert_open_'+r['identity']):
                            from views.restock_ui import open_restock
                            open_restock(r['record_id'])
                    else:
                        if st.button('Actualizar material',key='alert_open_'+r['identity']):material_reading_form()
                    if r['state']!='Visto' and st.button('Marcar visto',key='alert_seen_'+r['identity']):perform(alerts.resolve,r['identity'],message='Aviso marcado como visto.')
                    if r['state']!='Pospuesto' and st.button('Posponer 30 min',key='alert_snooze_'+r['identity']):perform(alerts.resolve,r['identity'],snooze_minutes=30,message='Aviso pospuesto 30 minutos.')
    live_alerts()
