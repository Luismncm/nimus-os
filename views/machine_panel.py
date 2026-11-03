"""Queue by printer, full width, in the same style as the queue grouped by state.

On top, the live printer tiles (what each prints, estimated progress, when it frees up) also pick the
printer: "Todas las impresoras" shows every printer as a section with its 24 h strip and its prints;
one printer shows what it prints now, its queue with actions, and pending pieces that fit it (its
loaded filament first) to assign there; "Sin máquina" shows the prints still without a printer.
Only the tiles refresh every 30 s; the sections refresh with any action, so dialogs open normally.
"""
import streamlit as st
from services.assign_suggest import same_material
from services.timeline import machine_timeline, availability_text, duration_text
from utils.dates import now
from views.assign_panel import pending_pieces
from views.live_floor import ALL, EXTERNAL, PICK as STATE, live_floor
from views.queue_board import operate_row
from views.queue_groups import heading
from views.tags import printer_tag
from views.timeline_ui import strip
from views.common import remembered


def _queued(jobs, machine_id):
    return [j for j in jobs if j['machine_id'] == machine_id and j['status'] != 'Terminado']


def _pick(value):
    st.session_state[STATE] = value


def fit_pieces(snapshot, machine):
    """Pending pieces for this printer: its loaded filament first, then the most urgent."""
    pieces = [p for p in pending_pieces(snapshot) if p['process'] in ('Impresión 3D', 'Resina')]
    return sorted(pieces, key=lambda p: not same_material(machine.get('loaded_material'), p['material']))


def assign_here(part, machine):
    """Open the piece's window with this printer already picked."""
    from views.assign_panel import _version
    from views.common import split_form
    st.session_state[f"split_one_{part['id']}_v{_version('split_one')}_machine"] = machine['id']
    st.session_state[f"split_mode_{part['id']}"] = 'Una impresora'
    split_form(part)


VIEWS = ('Agenda', 'Lista')


def machine_detail(m, snapshot, jobs, labels):
    t = machine_timeline(m, snapshot['jobs'])
    with st.container(horizontal=True, vertical_alignment='center', gap='small'):
        # The loaded filament is changed from the printer's tile just above.
        st.markdown(f"#### {m['code']} :gray[· {m['name']}]")
        printer_tag(m)
        st.space('stretch')
        view = st.segmented_control('Ver la cola como', VIEWS, default=remembered('queue_machine_view', 'Agenda'), key='queue_machine_view',
                                    persist_state='session', label_visibility='collapsed',
                                    format_func=lambda v: {'Agenda': ':material/calendar_view_day: Agenda', 'Lista': ':material/view_list: Lista'}[v]) or 'Agenda'
    st.caption(availability_text(t['availability']) if t['availability'] else m['status'])
    strip(t)
    own = sorted(_queued(jobs, m['id']), key=lambda j: (j['status'] != 'En producción', j.get('planned_start') or '9999', j['id']))
    running = [j for j in own if j['status'] == 'En producción']
    st.markdown('**Ahora**')
    if running:
        for job in running:operate_row(job, labels[job['order_id']])
    else:
        st.caption(':green[Libre.]' if m['status'] == 'Disponible' else m['status'])
    waiting = [j for j in own if j['status'] != 'En producción']
    if view == 'Agenda':
        # What comes next keeps its actions (start, schedule, more); the rest of the queue reads as a day-by-day agenda.
        if waiting:
            st.markdown(f"**Siguiente** :gray[· {len(waiting)} en cola · {sum(j['quantity_remaining'] for j in waiting)} unidades]")
            operate_row(waiting[0], labels[waiting[0]['order_id']])
        else:
            st.caption('Sin impresiones en cola para estos filtros.')
        from views.machine_agenda import agenda
        agenda(snapshot, m['id'], f"queue_machine_{m['id']}", pick_gaps=False)
    else:
        st.markdown(f"**En cola · {len(waiting)}**" + (f" :gray[· {sum(j['quantity_remaining'] for j in waiting)} unidades]" if waiting else ''))
        if not waiting:
            st.caption('Sin impresiones en cola para estos filtros.')
        for job in waiting:operate_row(job, labels[job['order_id']])
    pieces = fit_pieces(snapshot, m) if m['status'] not in ('Mantenimiento', 'Fuera de servicio') else []
    if pieces:
        st.markdown(f"**Para asignar aquí · {len(pieces)}**")
        for p in pieces[:5]:
            with st.container(border=True, gap='xxsmall', key=f"queue_fit_{m['id']}_{p['id']}"):
                match = same_material(m.get('loaded_material'), p['material'])
                with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center', gap='small'):
                    st.markdown(f"**{p['name']}** ×{p['quantity_unassigned']} :gray[· {p['item_name']} · {labels[p['order_id']]['label']}]  \n"
                                + (f":green[:material/check: {p['material']} cargado]" if match else f":gray[{p['material'] or 'Sin material'}]"), width='stretch')
                    if st.button('Asignar', key=f"queue_here_{m['id']}_{p['id']}", icon=':material/add_task:', width='content',
                                 help=f"Abre la pieza con {m['code']} ya elegida."):
                        assign_here(p, m)
        if len(pieces) > 5:
            st.caption(f"Y {len(pieces) - 5} más en la vista Asignar.")
    done = [j for j in snapshot['jobs'] if j['machine_id'] == m['id'] and j['status'] == 'Terminado' and (j.get('completed_at') or '')[:10] == now().date().isoformat()]
    if done:
        st.caption(':material/check_circle: Terminadas hoy · ' + ' · '.join(f"{j['code']} {j['part_name']} ×{j['quantity']}" for j in done))


def all_detail(snapshot, jobs, labels, machine_filter):
    """Every printer as a section: header with its load, its 24 h strip and its prints."""
    with st.container(horizontal=True, vertical_alignment='center', gap='small'):
        show_empty = st.toggle('Mostrar máquinas libres', key='queue_show_empty', persist_state='session')
        st.caption('Franja de 24 h: cada bloque en el color de su pedido · relleno rayado: imprimiendo · borde rojo: con problema · línea roja: ahora.')
    groups = {}
    for job in jobs:groups.setdefault(job['machine_id'], []).append(job)
    if show_empty:
        for m in snapshot['machines']:
            if machine_filter in ('Todas', m['id']):groups.setdefault(m['id'], [])
    by_id = {m['id']: m for m in snapshot['all_machines']}
    for mid, own in sorted(groups.items(), key=lambda g: (g[0] is None, by_id[g[0]]['code'] if g[0] in by_id else '')):
        m = by_id.get(mid)
        active = [j for j in own if j['status'] != 'Terminado']
        load = ' · '.join(x for x in (f"{len(active)} {'impresión' if len(active) == 1 else 'impresiones'}",
                                      f"{sum(j['quantity_remaining'] for j in active)} u. pendientes" if active else '',
                                      duration_text(sum(j.get('duration_minutes') or 0 for j in active)) + ' de trabajo'
                                      if any(j.get('duration_minutes') for j in active) else '') if x)
        if m:
            t = machine_timeline(m, snapshot['jobs'])
            with st.container(horizontal=True, vertical_alignment='center', gap='small', key=f"qhead-machine-{mid}"):
                st.markdown(f"**{m['code']}** :gray[· {m['name']}]", width='content')
                printer_tag(m, material=True)
                st.markdown(f":gray[{availability_text(t['availability']) if t['availability'] else m['status']} · {load}]", width='stretch')
                if not m['archived']:
                    st.button('Ver impresora', key=f"queue_open_{mid}", icon=':material/open_in_full:', type='tertiary', on_click=_pick, args=(mid,))
            strip(t)
        else:
            heading('Sin máquina / externo', 'do_not_disturb_on', len(own), load, key='machine-external')
        if not own:st.caption('Sin impresiones en esta consulta.')
        for job in own:operate_row(job, labels[job['order_id']])


def machine_panel(snapshot, jobs, labels, machine_filter, *, bar=None):
    ids = {m['id'] for m in snapshot['machines']}
    if machine_filter not in ('Todas', 'Sin máquina'):
        st.session_state[STATE] = machine_filter
    elif machine_filter == 'Sin máquina':
        st.session_state[STATE] = EXTERNAL
    external = _queued(jobs, None)
    if st.session_state.get(STATE) not in (ALL, EXTERNAL, *ids) or (st.session_state[STATE] == EXTERNAL and not external):
        st.session_state[STATE] = ALL
    live_floor(machine_filter, pick=True, external=len(external), bar=bar)
    picked = st.session_state[STATE]
    if picked == ALL:
        all_detail(snapshot, jobs, labels, machine_filter)
    elif picked == EXTERNAL:
        heading('Sin máquina / externo', 'do_not_disturb_on', len(external), 'Trabajos fuera de impresora o todavía sin máquina. Edítalos para moverlos a una impresora.', key='external')
        for job in external:operate_row(job, labels[job['order_id']])
    else:
        machine_detail(next(m for m in snapshot['machines'] if m['id'] == picked), snapshot, jobs, labels)
