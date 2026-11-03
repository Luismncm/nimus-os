from datetime import date,datetime,time,timedelta
import streamlit as st
from services import planning,resources,costing,timeline
from views.timeline_ui import slot_line
from views.costing_forms import job_cost_form
from services.quotations import money,cents
from views.common import managed_dialog,perform


def plan_fields(row,prefix):
    start=datetime.fromisoformat(row['planned_start']) if row.get('planned_start') else None
    a,b=st.columns(2)
    day=a.date_input('Inicio programado · fecha',value=None if prefix+'_day' in st.session_state else start.date() if start else None,key=prefix+'_day')
    hour=b.time_input('Inicio programado · hora',value=None if prefix+'_time' in st.session_state else start.time() if start else time(9),key=prefix+'_time')
    minutes=row.get('duration_minutes') or 0
    a,b,c=st.columns([1,1,2])
    hours=a.number_input('Duración · horas',min_value=0,max_value=8760,value=minutes//60,step=1,key=prefix+'_hours')
    mins=b.number_input('Duración · minutos',min_value=0,max_value=59,value=minutes%60,step=1,key=prefix+'_minutes')
    grams=c.number_input('Gramos estimados · lote completo',min_value=0.0,value=float(row.get('estimated_grams') or 0),step=1.0,key=prefix+'_grams')
    st.caption('Duración y gramos del lote completo (todas sus unidades), incluidos soportes y merma prevista. '
               'Fin = inicio + duración, y ese intervalo queda reservado en la máquina. Con duración 0 el trabajo no reserva horario. '
               'Al iniciar, el fin se recalcula desde el inicio real y las pausas no consumen duración.')
    with st.expander('Tarifas para la previsión',key=prefix+'_costs',on_change='ignore'):
        st.caption('Estos gramos, duración y tarifas son el costo de la impresión al terminar. Usa Corregir costo solo si algo cambió.')
        rates_known=st.checkbox('Asignar tarifas para estimar el costo',value=row.get('material_rate_cents') is not None or row.get('machine_rate_cents') is not None,key=prefix+'_rates_known')
        a,b=st.columns(2)
        material=a.number_input('Material · MXN por kg',min_value=0.0,value=(row.get('material_rate_cents') or 0)/100,step=10.0,key=prefix+'_material')
        machine=b.number_input('Máquina · MXN por hora',min_value=0.0,value=(row.get('machine_rate_cents') or 0)/100,step=1.0,key=prefix+'_machine')
        st.caption('Las tarifas son opcionales y se guardan en este trabajo. El costo estimado combina material y tiempo de máquina; puedes incluir energía y desgaste en la tarifa por hora.')
    return dict(planned_start=(datetime.combine(day,hour).isoformat(timespec='minutes') if hour else day.isoformat()+'T') if day else None,
        duration_minutes=hours*60+mins or None,estimated_grams=grams or None,actual_grams=row.get('actual_grams'),
        material_rate_cents=cents(material) if rates_known else None,machine_rate_cents=cents(machine) if rates_known else None)


def machine_agenda(job,row,prefix):
    """What already occupies this machine, so the start is chosen against real bookings."""
    snapshot=st.session_state.get('snapshot')
    machine=next((m for m in snapshot['all_machines'] if m['id']==job['machine_id']),None) if snapshot else None
    if not machine:
        st.caption('Sin máquina: el horario es orientativo y no reserva ningún equipo.')
        return
    others=[j for j in snapshot['jobs'] if j['id']!=job['id']]
    t=timeline.machine_timeline(machine,others)
    with st.container(border=True,gap='xsmall'):
        st.markdown(f"**{machine['code']}** · {timeline.availability_text(t['availability'])}")
        booked=sorted((s for s in t['slots'] if s['state'] in ('En marcha','Sin fin','Reservada')),key=lambda s:s['start'] or datetime.min)
        for s in booked[:5]:
            st.caption(f"{s['job']['code']} · {s['job']['part_name']} · {slot_line(s)}")
        if not booked:st.caption('Sin otras impresiones reservadas en esta máquina.')
        duration=row.get('duration_minutes')
        if not duration:
            st.caption('Captura la duración para reservar la máquina y encontrar el primer horario libre.')
            return
        free=resources.first_free(job['id'],machine['id'],duration)
        if free is None:
            st.caption('No hay un horario libre calculable: la máquina no está operativa o tiene una impresión sin fin vigente.')
            return
        def use_free():
            st.session_state[prefix+'_day']=free.date();st.session_state[prefix+'_time']=free.time()
        st.button(f"Usar primer horario libre · {timeline.when(free)} → {timeline.when(free+timedelta(minutes=duration))} ({timeline.duration_text(duration)})",
                  key=prefix+'_first_free',icon=':material/event_available:',on_click=use_free)


@managed_dialog('Programar impresión y consumos',width='large')
def planning_form(job):
    row=planning.get(job['id'])
    prefix='plan_'+st.session_state['dialog_request_key']
    st.write(f"**{job['code']} · {job['part_name']} · {job['machine_code'] or 'Sin máquina'}**")
    st.caption(f"{job['quantity']} unidades · {job['material'] or 'Material pendiente'} · Horario local del taller")
    machine_agenda(job,row,prefix)
    with st.form(prefix):
        data=plan_fields(row,prefix)
        actual=None
        actual_value=job.get('current_run_started_at') if 'current_run_started_at' in job else job['started_at']
        if actual_value:
            with st.expander('Hora de inicio real',key=prefix+'_actual',on_change='ignore'):
                current=datetime.fromisoformat(actual_value)
                st.caption('Registrada: '+current.strftime('%d/%m/%Y %H:%M'))
                change=st.checkbox('Corregir hora de inicio real',key=prefix+'_adjust')
                a,b=st.columns(2)
                day=a.date_input('Inicio real · fecha',value=current.date(),key=prefix+'_actual_day')
                hour=b.time_input('Inicio real · hora',value=current.time().replace(second=0,microsecond=0),key=prefix+'_actual_time')
                if change:actual=datetime.combine(day,hour).isoformat(timespec='minutes')
        a,b=st.columns(2)
        preview=a.form_submit_button('Revisar estimación',icon=':material/calculate:',width='stretch')
        save=b.form_submit_button('Guardar programación',type='primary',icon=':material/calendar_month:',width='stretch')
        if preview:
            try:
                clean=planning.normalize(data);estimate=planning.costs(clean)
                if clean['planned_start'] and clean['duration_minutes']:
                    from datetime import timedelta
                    end=datetime.fromisoformat(clean['planned_start'])+timedelta(minutes=clean['duration_minutes'])
                    st.info('Fin programado: '+end.strftime('%d/%m/%Y %H:%M'))
                if estimate['estimated_cost_cents'] is not None:st.success('Costo estimado del lote: '+money(estimate['estimated_cost_cents'])+' MXN')
                else:st.caption('Completa duración, gramos estimados y tarifas para calcular el costo.')
                available=resources.preview(job['id'],clean)
                if available['conflicts']:
                    st.error('Horario ocupado por '+', '.join(j['code'] for j in available['conflicts'])+'. Elige otro inicio.')
                    st.session_state[prefix+'_offer']=available['next_start'].isoformat() if available['next_start'] else None
                else:
                    st.session_state.pop(prefix+'_offer',None)
                    if available['end'] and available['end'].year<9999:st.info('Horario disponible para esta máquina hasta '+available['end'].strftime('%d/%m/%Y %H:%M'))
            except ValueError as exc:st.error(str(exc))
        if save:
            perform(planning.save,job['id'],data,expected_revision=row['revision'],expected_job_revision=job['updated_at'],actual_start=actual,message='Programación y consumos guardados.')
    offer=st.session_state.get(prefix+'_offer')
    if offer:
        def use_slot():
            value=datetime.fromisoformat(offer)
            st.session_state[prefix+'_day']=value.date()
            st.session_state[prefix+'_time']=value.time()
            st.session_state.pop(prefix+'_offer',None)
        value=datetime.fromisoformat(offer)
        st.button('Usar horario libre · '+value.strftime('%d/%m/%Y %H:%M'),key=prefix+'_use_slot',type='primary',on_click=use_slot)

    reference=costing.job_reference(job['id'])
    if reference:
        st.divider()
        st.caption('Puedes reutilizar la previsión de este lote en la pieza del catálogo. El consumo real se registra por separado en Costo real.')
        if st.button('Usar costo guardado en recetas',key=prefix+'_publish_cost'):
            job_cost_form(reference)
