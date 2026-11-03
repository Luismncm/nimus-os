import streamlit as st
from services.timeline import slot, issues
from views.common import job_actions
from views.components import status_badge
from views.planning_forms import planning_form
from views.navigation import open_order
from views.timeline_ui import slot_line, countdown, schedule_tag
from views.kind_style import card, kind_of
from views.tags import printer_tag, destination_tags, extra_tag, priority_tag
from services.assign_suggest import same_material

def destination_badge(job):
    """Who the print is for, with the shared tags, from the destinations the queue page computed."""
    dest=st.session_state.get('queue_destinations',{}).get(job['order_id'])
    if dest:destination_tags(dest)
    elif job.get('development'):st.badge('Prototipo',color='violet',icon=':material/science:')


def operate_row(job,dest,context='queue'):
    """One line to run the day: what, how many, for whom, when, and its actions; tinted by what it is for."""
    s=slot(job)
    with card(dest['kind'],f"{context}-{job['id']}",order_id=job['order_id']):
        info,actions=st.columns([3,2.4],vertical_alignment='center')
        with info:
            with st.container(horizontal=True,gap='xsmall',vertical_alignment='center'):
                st.markdown(f"**{job['part_name']}** ×{job['quantity']} :gray[· {job['code']}]")
                status_badge(job['status'])
                schedule_tag(s)
                printer_tag(next((m for m in st.session_state['snapshot']['all_machines'] if m['id']==job['machine_id']),None))
                destination_tags(dest)
                extra_tag(job)
                priority_tag(job['priority'])
                if job['machine_id'] and job.get('material'):
                    loaded=next((m.get('loaded_material') for m in st.session_state['snapshot']['all_machines'] if m['id']==job['machine_id']),'')
                    if loaded and not same_material(loaded,job['material']):
                        st.badge('Cambiar filamento',color='orange',icon=':material/swap_horiz:',help=f"La impresora tiene {loaded}; esta impresión usa {job['material']}.")
            problems=issues(s)
            countdown(s)
            with st.container(horizontal=True,gap='xsmall',vertical_alignment='center'):
                st.caption(f":material/schedule: {slot_line(s)} · {job['quantity_completed']}/{job['quantity']} buenas · {job['material'] or 'Sin material'}"
                           +(f"  \n:red[:material/warning: {problems[0]}]" if problems else ''))
                if job['order_status']!='Entregado' and not job.get('rides_on') and st.button('Horario',key=f'queue_{job["id"]}_plan',type='tertiary',icon=':material/edit_calendar:',
                                                                  help='Inicio, duración, gramos y tarifas; ofrece el primer horario libre de la máquina.'):
                    planning_form(job)
        with actions:job_actions(job,f'queue_{job["id"]}')


def compact_job(job):
    key=f'queue_{job["id"]}';s=slot(job)
    with card(kind_of(job),f"compact-{job['id']}",gap='xsmall',order_id=job['order_id']):
        with st.container(horizontal=True,gap='xsmall',vertical_alignment='center'):
            st.markdown(f"**{job['part_name']}** :gray[· {job['code']}]")
            status_badge(job['status'])
            if job['priority']=='Alta':st.badge('Alta',color='orange',icon=':material/priority_high:')
            destination_badge(job)
            if job.get('reprint_number'):st.badge(f"Reimpresión {job['reprint_number']} · {job['reprint_status']}",color='orange')
        st.caption(f"{job['order_code']} · {job['project']} · {job['item_name']} · {job['material'] or 'Material pendiente'}")
        # One line answers when: interval, duration and what is left; problems follow in red.
        st.markdown(f":material/schedule: {slot_line(s)}")
        for text in issues(s):st.markdown(f":red[:material/warning: {text}]")
        if job['order_blocked']:st.markdown(':red[:material/block: Pedido bloqueado: no se puede iniciar ni reanudar.]')
        st.progress(job['quantity_completed']/job['quantity'],text=f"{job['quantity_completed']}/{job['quantity']} buenas · {job['quantity_remaining']} pendientes")
        job_actions(job,key)
        with st.container(horizontal=True,gap='small'):
            if st.button('Programar' if s['state'] in ('Sin horario','Sin duración') else 'Cambiar horario',key=key+'_plan',type='tertiary',icon=':material/calendar_month:',disabled=job['order_status']=='Entregado'):planning_form(job)
            if st.button('Pedido',key=key+'_order',type='tertiary',icon=':material/open_in_new:'):open_order(job['order_id'])
        if job['notes']:
            with st.expander('Notas del lote',key=key+'_notes',on_change='ignore'):st.write(job['notes'])
