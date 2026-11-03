"""Live floor: one tile per printer with what it prints, how far it is and when it finishes.

Progress is estimated from the real start and the planned duration (pauses already handled by the
runtime model); there is no printer connection yet. The tiles refresh by themselves every 30 s.
"""
from datetime import timedelta
import streamlit as st
from services import assign_suggest
from services.queries import load_snapshot
from services.queue_review import destinations
from services.timeline import machine_timeline, duration_text, when, slot
from utils.dates import now, parse_end
from views.tags import printer_tag, destination_tags

def progress_of(job, at):
    """Estimated fraction done and minutes left of a running print, from its run start and finish."""
    start, finish = parse_end(job.get('current_run_started_at')), parse_end(job.get('estimated_finish'))
    if not start or not finish or finish <= start:
        return None, None
    done = min(1.0, max(0.0, (at - start) / (finish - start)))
    return done, (finish - at).total_seconds() / 60


PICK = 'queue_machine_pick'


def _choose(value):
    st.session_state[PICK] = value
    st.rerun(scope='app')


def tile(machine, snapshot, labels, at, *, pick=False):
    t = machine_timeline(machine, snapshot['jobs'], at)
    current = next((j for j in snapshot['jobs'] if j['id'] == (machine['current_job'] or {}).get('id')), None)
    upcoming = sorted((s for s in t['slots'] if s['job']['status'] in ('En cola', 'Pausado')), key=lambda s: (s['start'] or at + timedelta(days=3650), s['job']['id']))
    down = machine['status'] in ('Mantenimiento', 'Fuera de servicio')
    done, left = progress_of(current, at) if current else (None, None)
    # Tile edge by state, styled in kind_style: printing blue, free green, needs attention orange.
    state = 'alert' if down or (current and (done is None or left <= 0)) else 'printing' if current else 'free'
    picked = pick and st.session_state.get(PICK) == machine['id']
    with st.container(border=True, gap='xxsmall', key=f"floor-{state}-{'on' if picked else 'off'}-{machine['id']}"):
        printer_tag(machine)
        if down:
            st.markdown(f":orange[**{machine['status']}**]")
        elif current:
            st.markdown(f"**{current['part_name']}** ×{current['quantity']}")
            # Order and sale side by side, wrapping inside the card.
            with st.container(horizontal=True, gap='xxsmall', vertical_alignment='center'):
                destination_tags(labels.get(current['order_id']))
            if done is None:
                st.caption(':red[En marcha sin duración: captura la duración para ver su avance.]')
            else:
                # The queue's remaining-time counter, laid out as a block to fit the card.
                from views.timeline_ui import countdown
                countdown(slot(current, at), at, block=True)
        else:
            st.markdown(':green[**Libre**]')
            nxt = upcoming[0]['job'] if upcoming else None
            st.caption(f"Siguiente: {nxt['part_name']} · {when(upcoming[0]['start'], at) if upcoming[0]['start'] else 'sin horario'}" if nxt else 'Sin impresiones en cola')
        queued = len(upcoming)
        st.caption(f"{queued} en cola" + (f" · {duration_text(t['booked_minutes'])} reservadas" if t['booked_minutes'] else '')
                   + (f" · :red[{t['problems']} con problema]" if t['problems'] else ''))
        loaded_form(machine)
        # Grouped by printer, the tile also picks the printer shown below.
        if pick and st.button('Viendo' if picked else 'Ver su cola', key=f"queue_pick_{machine['id']}", type='primary' if picked else 'secondary',
                              width='stretch', icon=':material/visibility:' if picked else None):
            _choose(ALL if picked else machine['id'])


def loaded_form(machine):
    with st.popover('Filamento cargado', icon=':material/swap_horiz:', type='tertiary', help='Qué carrete tiene montado: la asignación prefiere esta impresora para ese material.'):
        from views.development_forms import materials
        options = materials()
        current = machine.get('loaded_material') or None
        value = st.selectbox('Material montado', options, index=options.index(current) if current in options else None, accept_new_options=True,
                             key=f"loaded_{machine['id']}", placeholder='Elige o escribe el material')
        if st.button('Guardar', key=f"loaded_save_{machine['id']}", type='primary'):
            assign_suggest.set_loaded(machine['id'], value or '')
            st.rerun(scope='app')


ALL, EXTERNAL = 'all', 'external'


def live_floor(machine_filter='Todas', *, pick=False, external=0, bar=None):
    """Printer tiles; with `pick` they also choose the printer shown below (Todas / one / Sin máquina).

    Its switches go in `bar` when the page gives one, beside the page's own controls.
    """
    with bar or st.container(horizontal=True, vertical_alignment='center', gap='small'):
        if pick:
            picked = st.session_state.get(PICK)
            if st.button('Todas las impresoras', key='queue_pick_all', icon=':material/view_agenda:', type='primary' if picked == ALL else 'tertiary'):
                _choose(ALL)
            if external and st.button(f'Sin máquina · {external}', key='queue_pick_external', icon=':material/do_not_disturb_on:',
                                      type='primary' if picked == EXTERNAL else 'tertiary'):
                _choose(EXTERNAL)
        st.space('stretch')
        live = st.toggle('En vivo', key='queue_live', value=True, help='Las tarjetas de impresoras se actualizan cada 30 s.')
    @st.fragment(run_every='30s' if live else None)
    def floor():
        # The timer reruns only these tiles, so they read fresh data instead of the page's snapshot.
        snapshot = load_snapshot() if st.session_state.get('_floor_ran') else st.session_state['snapshot']
        st.session_state['_floor_ran'] = True
        labels = st.session_state.get('queue_destinations') or destinations(snapshot)
        at = now()
        machines = [m for m in snapshot['machines'] if machine_filter in ('Todas', m['id'])]
        for start in range(0, len(machines), 5):
            for col, m in zip(st.columns(5, gap='small'), machines[start:start + 5]):
                with col:tile(m, snapshot, labels, at, pick=pick)
        st.caption(f"Avance estimado por tiempo desde el inicio real y la duración · actualizado {at:%H:%M:%S}")
    st.session_state['_floor_ran'] = False
    floor()
