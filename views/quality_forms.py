import streamlit as st
from services import quality, planning, consumption, order_costs, expenses, sales, alert_inputs
from services.quotations import cents,money
from views.common import managed_dialog,perform
from views.planning_forms import plan_fields

@managed_dialog('Registrar falla y merma',width='medium')
def failure_form(job):
    prefix='failure_'+st.session_state['dialog_request_key']
    st.write(f"**{job['code']} · {job['part_name']}**")
    st.caption('Las piezas rechazadas no ingresan al inventario de buenas. El lote se pausa y su reserva anterior se libera.')
    with st.form(prefix):
        quantity=st.number_input('Piezas rechazadas *',min_value=1,max_value=job['quantity'],value=1,step=1,key=prefix+'_quantity')
        options=list(dict.fromkeys([*quality.CAUSES,*[r['cause'] for r in quality.failures()]]))
        cause=st.selectbox('Causa *',options,accept_new_options=True,key=prefix+'_cause')
        previous=st.checkbox('Estas piezas ya estaban registradas como buenas',key=prefix+'_previous')
        known=st.checkbox('Capturar gramos desperdiciados',key=prefix+'_known')
        grams=st.number_input('Gramos de merma',min_value=0.0,value=0.0,step=1.0,key=prefix+'_grams')
        notes=st.text_area('Notas',key=prefix+'_notes',height=80)
        st.caption('Si marcas piezas que ya eran buenas, se corrige su avance; las unidades ya asignadas a stock/B2B requieren devolución previa. La merma forma parte del consumo total, se clasifica por separado.')
        if st.form_submit_button('Registrar falla y pausar',type='primary',width='stretch'):
            perform(quality.record_failure,job['id'],quantity,cause,notes,grams if known else None,previous,
                request_key=st.session_state['dialog_request_key'],expected_revision=job['updated_at'],message='Falla registrada. Puedes preparar la reimpresión de las pendientes.')

@managed_dialog('Reimprimir piezas pendientes',width='large')
def reprint_form(job,failure_id=None):
    row=planning.get(job['id']);prefix='reprint_'+st.session_state['dialog_request_key']
    st.write(f"**{job['code']} · {job['quantity_remaining']} piezas pendientes**")
    st.caption('Se reprograma este mismo lote y se registra otro intento. Revisa tiempo y gramos para las pendientes; las piezas buenas anteriores se conservan.')
    machines={m['id']:m for m in st.session_state['snapshot']['machines']}
    options=[None,*machines]
    with st.form(prefix):
        machine=st.selectbox('Máquina para reimpresión',options,index=options.index(job['machine_id']) if job['machine_id'] in options else 0,
            format_func=lambda i:'Sin máquina' if i is None else f"{machines[i]['code']} · {machines[i]['status']}",key=prefix+'_machine_id')
        data=plan_fields(row,prefix)
        if st.form_submit_button('Preparar reimpresión',type='primary',width='stretch'):
            perform(quality.prepare_reprint,job['id'],failure_id or job['latest_failure_id'],machine,data,
                request_key=st.session_state['dialog_request_key'],expected_job_revision=job['updated_at'],expected_plan_revision=row['revision'],message='Reimpresión preparada. Iníciala desde la cola cuando corresponda.')

@managed_dialog('Consumo y costo real del lote',width='large')
def consumption_form(job):
    row=consumption.get(job['id']);prefix='consumption_'+st.session_state['dialog_request_key']
    st.write(f"**{job['code']} · {job['part_name']}**")
    st.caption(f"Merma registrada: {row['waste_grams']:g} g. El consumo total debe incluir todos los intentos, soportes y material perdido.")
    if row['automatic_minutes'] is not None:st.info(f"Tiempo de máquina registrado: {row['automatic_minutes']:.1f} min; excluye las pausas.")
    else:st.info('El tiempo histórico no está completo. Puedes capturar los minutos reales manualmente.')
    with st.form(prefix):
        a,b=st.columns(2)
        grams_known=a.checkbox('Capturar consumo real total',value=row['grams'] is not None,key=prefix+'_grams_known')
        grams=a.number_input('Gramos reales totales',min_value=0.0,value=float(row['grams'] or 0),step=1.0,key=prefix+'_grams')
        time_manual=b.checkbox('Usar tiempo real manual',value=row['manual_minutes'] is not None,key=prefix+'_time_manual')
        minutes=b.number_input('Minutos reales totales',min_value=0.0,value=float(row['manual_minutes'] if row['manual_minutes'] is not None else row['automatic_minutes'] or 0),step=1.0,key=prefix+'_minutes')
        rates=st.checkbox('Capturar tarifas de costo sin IVA',value=row['material_rate_cents'] is not None or row['machine_rate_cents'] is not None,key=prefix+'_rates')
        a,b=st.columns(2)
        material=a.number_input('Material · tarifa media MXN/kg sin IVA',min_value=0.0,value=(row['material_rate_cents'] or 0)/100,step=10.0,key=prefix+'_material')
        machine=b.number_input('Máquina · tarifa media MXN/h sin IVA',min_value=0.0,value=(row['machine_rate_cents'] or 0)/100,step=1.0,key=prefix+'_machine')
        from services import consumables
        reference=consumables.material_rate(job.get('material'))
        if reference is not None:
            st.caption(f"Costo de referencia de {job['material']} en Insumos y consumibles: {money(reference)} MXN/kg sin IVA.")
        st.caption('Las tarifas se aplican al consumo total. Si hubo varios precios de material o equipos, utiliza sus tarifas medias ponderadas.')
        st.caption('Sin corrección, la impresión cierra con los gramos, la duración y las tarifas capturados al asignarla. Corrige solo si cambió algo (por ejemplo, tras una falla). No cambia piezas, inventario ni pagos.')
        if st.form_submit_button('Guardar corrección',type='primary',width='stretch'):
            perform(consumption.save,job['id'],grams if grams_known else None,minutes if time_manual else None,cents(material) if rates else None,cents(machine) if rates else None,
                expected_revision=row['revision'],expected_job_revision=row['job_revision'],message='Consumo y costo real guardados.')

@managed_dialog('Costo adicional del pedido',width='medium')
def extra_cost_form(order_id):
    prefix='extra_cost_'+st.session_state['dialog_request_key']
    rows={r['id']:r for r in expenses.list_expenses() if r['order_id']==order_id and r['status']=='Activo'}
    with st.form(prefix):
        source=st.selectbox('Origen del costo',[None,*rows],format_func=lambda i:'Captura manual sin IVA' if i is None else f"{rows[i]['code']} · {rows[i]['concept']}",key=prefix+'_source')
        concept=st.text_input('Concepto *',key=prefix+'_concept')
        kind=st.selectbox('Tipo de costo',order_costs.COST_TYPES,key=prefix+'_type')
        amount=st.number_input('Costo manual · MXN sin IVA',min_value=0.0,value=0.0,step=1.0,key=prefix+'_amount')
        st.caption('Si eliges un gasto, se utiliza su importe actual sin IVA cuando tenga desglose. Incluye solo conceptos que no estén ya cubiertos por gramos o tarifas de impresión. Para inventario utilizado, captura el costo de todas las piezas tomadas del inventario para este pedido.')
        if st.form_submit_button('Agregar costo',type='primary',width='stretch'):
            perform(order_costs.add,order_id,concept,kind,amount,source,request_key=st.session_state['dialog_request_key'],expected_expense_revision=rows[source]['revision'] if source else None,message='Costo adicional registrado.')

@managed_dialog('Anular costo adicional',width='small')
def void_extra_form(row):
    st.write(row['concept'])
    with st.form('void_extra'):
        reason=st.text_input('Motivo *')
        if st.form_submit_button('Anular costo',type='primary',width='stretch'):perform(order_costs.void,row['id'],reason,message='Costo adicional anulado; historial conservado.')

@managed_dialog('Vincular venta existente al pedido',width='medium')
def link_sale_form(order_id):
    rows={r['id']:r for r in sales.list_sales() if r['status']=='Activa' and not r['order_id']}
    if not rows:
        st.info('No hay ventas activas sin pedido. Registra la venta o revisa los vínculos existentes.')
        return
    with st.form('link_sale_order'):
        selected=st.selectbox('Venta registrada',list(rows),format_func=lambda i:f"{rows[i]['code']} · {rows[i]['client']} · {money(rows[i]['total_cents'])} MXN")
        st.caption('Vincula los registros capturados para comparar ingreso, costos y margen. Revisa que la venta corresponda a este pedido.')
        if st.form_submit_button('Confirmar vínculo',type='primary',width='stretch'):
            row=rows[selected]
            perform(sales.link_existing_order,selected,order_id,expected_revision=row['revision'],expected_quote_revision=row['quote_revision'],message='Venta vinculada al pedido.')

@managed_dialog('Datos de material para avisos',width='medium')
def material_reading_form():
    from services.catalog import saved_values
    values=list(dict.fromkeys([*saved_values('material'),*[r['name'] for r in alert_inputs.readings()]]))
    with st.form('material_reading'):
        name=st.selectbox('Material *',values,accept_new_options=True,index=None,placeholder='Elige el material o escribe su nombre')
        available=st.number_input('Gramos disponibles · lectura actual',min_value=0.0,value=0.0,step=50.0)
        minimum=st.number_input('Mínimo deseado · gramos',min_value=0.0,value=0.0,step=50.0)
        st.caption('Esta lectura manual se compara con los gramos previstos de trabajos en cola. Actualízala al consumir o recibir material; no hay descuento automático. Un mínimo de 0 desactiva el aviso por mínimo.')
        if st.form_submit_button('Guardar lectura',type='primary',width='stretch'):perform(alert_inputs.save_material,name,available,minimum,message='Lectura de material guardada.')

@managed_dialog('Próximo mantenimiento',width='medium')
def maintenance_due_form():
    machines={m['id']:m for m in st.session_state['snapshot']['machines']}
    if not machines:st.info('Agrega una máquina para registrar su mantenimiento.');return
    selected=st.selectbox('Máquina',list(machines),format_func=lambda i:machines[i]['code'])
    record=alert_inputs.maintenance().get(selected,{})
    from datetime import date
    with st.form('maintenance_due'):
        day=st.date_input('Próxima fecha · vacía para retirar el aviso',value=date.fromisoformat(record['due_on']) if record.get('due_on') else None,key=f'maintenance_due_{selected}')
        notes=st.text_input('Notas',value=record.get('notes',''),key=f'maintenance_notes_{selected}')
        st.caption('Se avisa desde tres días antes. Al realizar el mantenimiento, captura su siguiente fecha o retira el aviso; el estado operativo se gestiona en Máquinas.')
        if st.form_submit_button('Guardar mantenimiento',type='primary',width='stretch'):perform(alert_inputs.save_maintenance,selected,day.isoformat() if day else None,notes,message='Fecha de mantenimiento guardada.')
