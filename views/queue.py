import streamlit as st
from models.constants import JOB_STATUSES,PRIORITIES,PROCESSES
from services.queries import filter_jobs
from services.queue_board import ordered,timing_matches,WINDOWS
from services import capture,sales,planning
from services.quotations import money
from views.queue_calendar import calendar_view
from views.live_floor import live_floor
from services.queue_review import destinations,review
from services.timeline import slot, issues
from views.common import job_form,job_table,perform,progress_form
from views.capture_forms import new_print_form
from views.planning_forms import planning_form
from views.queue_board import compact_job
from views.assign_panel import assign_panel,pending_pieces
from views.machine_panel import machine_panel
from views.queue_groups import state_view
from views.common import remembered,picks

snapshot=st.session_state['snapshot']

def reset_filters():
    st.session_state.update(queue_machine='Todas',queue_status='Activos',queue_priority='Todas',queue_project=None,
        queue_process='Todos',queue_search='',queue_window='Todos')

machines={'Todas':'Todas','Sin máquina':'Sin máquina',**{m['id']:m['code']+(' · archivada' if m['archived'] else '') for m in snapshot['all_machines']}}
projects={None:'Todos',**{o['id']:f"{o['code']} · {o['project']}" for o in snapshot['orders']}}
focus=st.session_state.pop('queue_focus',None)
if focus is not None:
    reset_filters()
    st.session_state['queue_machine']=focus.get('machine_id') or 'Todas'
    st.session_state['queue_project']=focus.get('order_id')
if st.session_state.get('queue_project') not in projects:st.session_state['queue_project']=None
if st.session_state.get('queue_machine','Todas') not in machines:st.session_state['queue_machine']='Todas'
# One bar for the whole page: view, search, Filtrar and Nueva impresión, like Hoy and Pedidos. The view and
# the button are drawn once the filters are known (Asignar shows its count), so each part gets its own slot.
bar=st.container(horizontal=True,vertical_alignment='center',gap='small')
with bar:
    view_slot=st.container(width='content')
    filter_slot=st.container(horizontal=True,vertical_alignment='center',gap='small',width='stretch')
    new_slot=st.container(width='content')
with filter_slot:
    search=st.text_input('Buscar lote',placeholder='Pieza, cliente, material, pedido o trabajo',key='queue_search',persist_state='session',
                         icon=':material/search:',label_visibility='collapsed')
    # Read before drawing, so the menu's own label can say how many filters are on.
    on=sum(st.session_state.get(k,d) not in (d,None) for k,d in (('queue_machine','Todas'),('queue_status','Activos'),('queue_project',None),
            ('queue_window','Todos'),('queue_priority','Todas'),('queue_process','Todos')))
    with st.popover('Filtrar'+(f' · {on}' if on else ''),icon=':material/filter_alt:',width='content'):
        machine=st.selectbox('Máquina',list(machines),format_func=lambda i:machines[i],key='queue_machine',persist_state='session')
        status=st.selectbox('Estado',('Activos','Todos',*JOB_STATUSES),key='queue_status',persist_state='session')
        order_id=st.selectbox('Pedido',list(projects),format_func=lambda i:projects[i],key='queue_project',persist_state='session',placeholder='Todos')
        window=st.selectbox('Programación',WINDOWS,key='queue_window',persist_state='session')
        priority=st.selectbox('Prioridad',('Todas',*PRIORITIES),key='queue_priority',persist_state='session')
        process=st.selectbox('Proceso',('Todos',*PROCESSES),key='queue_process',persist_state='session')
        st.button('Limpiar filtros',key='queue_reset',type='tertiary',icon=':material/filter_alt_off:',on_click=reset_filters)
# What is filtered stays in sight beside the quick states, so arriving from another page never hides prints silently.
active_filters=[machines[machine] if machine!='Todas' else '',status if status!='Activos' else '',
                projects[order_id].split(' · ',1)[0] if order_id is not None else '',window if window!='Todos' else '',
                f'Prioridad {priority}' if priority!='Todas' else '',process if process!='Todos' else '']
jobs=filter_jobs(snapshot['jobs'],machine=machine,status='Todos' if status=='Activos' else status,priority=priority,order_id=order_id,process=process)
if status=='Activos':jobs=[j for j in jobs if j['status']!='Terminado' and j['order_status']!='Entregado']
labels=destinations(snapshot,sales.list_sales())
# Cards anywhere on the page read who each print is for from here.
st.session_state['queue_destinations']=labels
jobs=ordered([j for j in jobs if timing_matches(j,window) and search.casefold() in
    ' '.join(str(j.get(f) or '') for f in ('code','order_code','project','client','part_name','material','item_name')).casefold()])
slots={j['id']:slot(j) for j in jobs if j['status']!='Terminado'}
# The queue's state counts are also its quick filters: one click narrows every view below.
QUICK={'Todas':lambda j,s:True,
       'En marcha':lambda j,s:j['status']=='En producción',
       'Con horario':lambda j,s:bool(s) and s['state']=='Reservada',
       'Sin horario':lambda j,s:bool(s) and s['state'] in ('Sin horario','Sin duración'),
       'Con problema':lambda j,s:bool(s) and bool(issues(s)),
       'Bloqueadas':lambda j,s:j['status']=='Bloqueado' or (j['order_blocked'] and j['status']!='Terminado')}
QUICK_STYLE={'Todas':'select_all','En marcha':'autorenew','Con horario':'event_available','Sin horario':'event_busy','Con problema':'warning','Bloqueadas':'block'}
counts={k:sum(f(j,slots.get(j['id'])) for j in jobs) for k,f in QUICK.items()}
if st.session_state.get('queue_quick') not in (None,*QUICK):st.session_state['queue_quick']='Todas'
picked=st.session_state.get('queue_quick') or 'Todas'
with st.container(horizontal=True,gap='small',vertical_alignment='center'):
    quick=st.pills('Estado rápido',[k for k in QUICK if k=='Todas' or counts[k] or k==picked],default=remembered('queue_quick', 'Todas'),
                   key='queue_quick',persist_state='session',label_visibility='collapsed',
                   format_func=lambda k:f":material/{QUICK_STYLE[k]}: {k} · {counts[k]}") or 'Todas'
    # Prints without a time have no end, no agenda and no delay warnings: book them all in one go,
    # each in its machine's first free slot, in the queue's order (priority, then delivery date).
    unscheduled=[j['id'] for j in jobs if (slots.get(j['id']) or {}).get('state')=='Sin horario']
    if unscheduled and st.button(f'Programar {len(unscheduled)} sin horario',key='queue_schedule_all',icon=':material/event_available:',
                                 help='Cada impresión toma el primer horario libre de su máquina, por prioridad y fecha de entrega. Las que no tienen máquina o duración se quedan como están.'):
        with st.spinner('Buscando horarios libres…'):
            done,skipped=capture.schedule_unscheduled(unscheduled)
        st.session_state['flash']=(f'{len(done)} impresiones programadas en el primer horario libre.' if done else 'Ninguna impresión se pudo programar.')+(
            f" {len(skipped)} sin programar: {skipped[0][1]}" if skipped else '')
        st.rerun()
    st.space('stretch')
    for label in filter(None,active_filters):st.badge(label,color='blue',icon=':material/filter_alt:')
    if any(active_filters):st.button('Quitar filtros',key='queue_reset_inline',type='tertiary',icon=':material/close:',on_click=reset_filters)
    st.caption(f"{sum(j['quantity_remaining'] for j in jobs)} unidades pendientes")
pending=review(jobs)
jobs=[j for j in jobs if QUICK[quick](j,slots.get(j['id']))]
if pending:
    # Open by itself only for what blocks the floor now (a print past its end, overlaps or late starts).
    with st.expander(f'Por resolver · {len(pending)}',icon=':material/build:',expanded=any(r['rank']<=1 for r in pending),key='queue_review_panel',on_change='ignore'):
        by_machine={m['id']:m for m in snapshot['all_machines']}
        shown=pending if st.session_state.get('queue_review_all') else pending[:3]
        for row in shown:
            job=row['job']
            with st.container(horizontal=True,vertical_alignment='center',gap='small',key=f"review-row-{job['id']}"):
                from views.tags import printer_html
                st.html(printer_html(by_machine.get(job['machine_id']),material=False),width='content')
                st.markdown(f"**{job['part_name']}** :gray[· {job['code']} · {labels[job['order_id']]['label']}]  \n:red[{row['text']}]",width='stretch')
                # Secondary: the page's one primary action stays Nueva impresión.
                if st.button(row['label'],key=f"queue_fix_{job['id']}",width='content',type='secondary',
                             icon=':material/event_repeat:' if row['fix']=='reschedule' else ':material/edit_calendar:'):
                    if row['fix']=='reschedule':perform(capture.reschedule_first_free,job['id'],message='Reprogramado en el primer horario libre de la máquina.')
                    elif row['fix']=='plan':planning_form(job)
                    elif row['fix']=='machine':job_form(snapshot,job=job)
                    else:progress_form(job)
        if len(pending)>3:
            st.toggle(f'Ver los {len(pending)}',key='queue_review_all')
VIEWS=('Operar','Asignar','Calendario','Tabla')
# What each print is for (order, Origen, stock, prototype) reads from its color and tag in every grouping.
GROUPS=('Máquina','Estado','Agenda')
GROUP_ICONS={'Máquina':'print','Estado':'view_week','Agenda':'calendar_view_day'}
# Views retired with the Agenda merge fall back to Operar instead of failing on a remembered value.
if st.session_state.get('queue_view') not in (None,*VIEWS):st.session_state['queue_view']='Operar'
to_assign=[p for p in pending_pieces(snapshot,order_id) if (process=='Todos' or p['process']==process)
           and search.casefold() in ' '.join(str(p.get(f) or '') for f in ('name','material','item_name','order_code','project')).casefold()]
VIEW_ICONS={'Operar':'play_circle','Asignar':'assignment_add','Calendario':'calendar_month','Tabla':'table_rows'}
with view_slot:
    view=st.segmented_control('Vista de la cola',VIEWS,default=remembered('queue_view', 'Operar'),key='queue_view',persist_state='session',
                              label_visibility='collapsed',
                              format_func=lambda v:f":material/{VIEW_ICONS[v]}: "+(f"Asignar · {sum(p['quantity_unassigned'] for p in to_assign)}" if v=='Asignar' and to_assign else v)) or 'Operar'
with new_slot:
    if st.button('Nueva impresión',key='queue_new_print',icon=':material/add_task:',type='primary',
                 help='Para un pedido, stock o prototipo: pieza existente o nueva, máquina, duración y horario en una sola ventana.'):
        new_print_form(order_id=st.session_state.get('queue_project'))
if not jobs and view!='Asignar':
    st.info('Sin trabajos para estos filtros. Usa Nueva impresión para agregar uno a la cola.')
if view=='Asignar':
    assign_panel(snapshot,'queue_assign',parts=to_assign,order_id=order_id,labels=labels)
elif view=='Operar':
    if st.session_state.get('queue_group') not in (None,*GROUPS):st.session_state['queue_group']='Máquina'  # A grouping that was retired.
    toolbar=st.container(horizontal=True,vertical_alignment='center',gap='small',key='queue-toolbar')
    with toolbar:
        group_by=st.segmented_control('Agrupar por',GROUPS,default=remembered('queue_group', 'Máquina'),key='queue_group',persist_state='session',
                                      label_visibility='collapsed',format_func=lambda g:f":material/{GROUP_ICONS[g]}: {g}",
                                      help='Máquina: qué hace cada impresora. Estado: qué se imprime, qué espera y qué está detenido. Agenda: las impresiones por día, todas juntas, por máquina o de una sola impresora.') or 'Máquina'
    shown={j['id'] for j in jobs}
    for m in snapshot['machines']:
        current=m['current_job']
        if current and current['id'] not in shown and machine in ('Todas',m['id']):
            st.info(f"En marcha fuera de estos filtros: {current['code']} · {current['part_name']} en {m['code']}.")
    # The same live printer tiles on top and the same rows below; only the grouping changes.
    if group_by=='Máquina':
        machine_panel(snapshot,jobs,labels,machine,bar=toolbar)
    elif group_by=='Estado':
        live_floor(machine,bar=toolbar)
        state_view(jobs,labels)
    else:
        live_floor(machine,bar=toolbar)
        from views.queue_agenda import queue_agenda
        queue_agenda(jobs,labels)
elif view=='Calendario':
    calendar_view(snapshot,jobs,machine)
else:
    if jobs:
        # Picking a row makes it the print managed below the table.
        job_table(jobs,'Cola de producción filtrada',open=picks('queue_table_selected'),key='queue_table')
        with st.container(horizontal=True,vertical_alignment='center'):
            grams=sum(j.get('estimated_grams') or 0 for j in jobs);known=[j for j in jobs if j.get('estimated_cost_cents') is not None]
            st.caption(f"{grams:,.0f} g estimados · costo previsto {money(sum(j['estimated_cost_cents'] for j in known))} en {len(known)}/{len(jobs)} impresiones con gramos, duración y tarifas")
            st.download_button('Exportar CSV',planning.csv_bytes(jobs),file_name='NIMUS_cola_impresion.csv',mime='text/csv',icon=':material/download:',on_click='ignore')
        lookup={j['id']:j for j in jobs}
        if st.session_state.get('queue_table_selected') not in lookup:st.session_state['queue_table_selected']=next(iter(lookup))
        selected=st.selectbox('Gestionar lote de la tabla',list(lookup),format_func=lambda i:f"{lookup[i]['code']} · {lookup[i]['part_name']} · {lookup[i]['machine_code'] or 'Sin máquina'}",key='queue_table_selected')
        compact_job(lookup[selected])
