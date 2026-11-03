"""The queue as an agenda: every printer's prints by day, each with its hours on the left and its actions.

A period (a day, three days or a week) moves back and forth from a chosen date. Each day says how many
prints and hours it holds and how they split by printer. On today, prints still running from before and
starts already missed are shown first, so nothing pending hides in a past day. Prints without a time are
listed at the end, with their actions, to schedule them.
"""
from datetime import timedelta
import streamlit as st
from services.timeline import duration_text, issues, slot
from utils.dates import now
from views.common import job_actions
from views.components import status_badge
from views.kind_style import card
from views.planning_forms import planning_form
from views.timeline_ui import countdown, schedule_tag
from views.tags import destination_tags, extra_tag, printer_tag, priority_tag
from views.common import remembered

PERIODS = {'Día': 1, '3 días': 3, 'Semana': 7}
DAYS = ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo')
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
DAY = 'queue_agenda_day'


def _shift(days):
    st.session_state[DAY] = st.session_state.get(DAY, now().date()) + timedelta(days=days)


def _today():
    st.session_state[DAY] = now().date()


def day_title(day, today):
    relative = {0: 'Hoy', 1: 'Mañana', -1: 'Ayer'}.get((day - today).days)
    return f"{DAYS[day.weekday()]} {day.day} de {MONTHS[day.month - 1]}" + (f" · {relative}" if relative else '')


def bucket(jobs, start, days, at):
    """Prints by day in [start, start + days), plus those without a time.

    Prints running from an earlier day and booked starts already missed count on today, when today is shown.
    Returns ({date: [slot]}, [slot without time]).
    """
    days_shown = [start + timedelta(days=i) for i in range(days)]
    by_day, waiting = {d: [] for d in days_shown}, []
    for job in jobs:
        if job['status'] == 'Terminado' or job.get('rides_on') or job['order_status'] == 'Entregado' or job.get('commercial_cancelled'):
            continue
        s = slot(job, at)
        if not s['start']:
            waiting.append(s)
            continue
        day = s['start'].date()
        if day < at.date() and at.date() in by_day and (s['state'] in ('En marcha', 'Sin fin') or job['status'] in ('En cola', 'Pausado', 'Bloqueado')):
            day = at.date()  # Still printing, or its start was missed: it is today's business.
        if day in by_day:
            by_day[day].append(s)
    for rows in by_day.values():
        rows.sort(key=lambda s: (s['state'] not in ('En marcha', 'Sin fin'), s['start'], s['job']['id']))
    waiting.sort(key=lambda s: (s['job']['machine_code'] or '~', s['job']['id']))
    return by_day, waiting


def _span(s, day):
    """'09:00 – 11:30', with the date when the print starts or ends on another day."""
    start, end = s['start'], s['end']
    left = f"{start:%H:%M}" if start.date() == day else f"{start:%d/%m %H:%M}"
    if s['state'] == 'Sin fin':
        return f"{left} · sin fin"
    right = '' if not end else f"{end:%H:%M}" if end.date() == start.date() == day else f"{end:%d/%m %H:%M}"
    return f"{left} – {right}" if right else left


def agenda_row(s, day, labels):
    """One print in the agenda: its hours first, then what, for whom, on which printer, and its actions."""
    job = s['job']
    dest = labels[job['order_id']]
    with card(dest['kind'], f"agenda-{job['id']}", order_id=job['order_id']):
        when_col, info, actions = st.columns([1.15, 3.6, 2.6], vertical_alignment='center')
        with when_col:
            st.markdown(f"**{_span(s, day)}**")
            st.caption(duration_text(s['minutes']))
        with info:
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                st.markdown(f"**{job['part_name']}** ×{job['quantity_remaining']} :gray[· {job['code']}]")
                status_badge(job['status'])
                schedule_tag(s)
                printer_tag(next((m for m in st.session_state['snapshot']['all_machines'] if m['id'] == job['machine_id']), None), material=False)
                destination_tags(dest)
                extra_tag(job)
                priority_tag(job['priority'])
            problems = issues(s)
            countdown(s)
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                st.caption(f"{job['quantity_completed']}/{job['quantity']} buenas · {job['material'] or 'Sin material'}"
                           + (f"  \n:red[:material/warning: {problems[0]}]" if problems else ''))
                if not job.get('rides_on') and st.button('Horario', key=f"queue_{job['id']}_plan", type='tertiary', icon=':material/edit_calendar:',
                                                         help='Inicio, duración, gramos y tarifas; ofrece el primer horario libre de la máquina.'):
                    planning_form(job)
        with actions:
            job_actions(job, f"queue_{job['id']}")


LAYOUTS = ('Por hora', 'Por máquina')
MACHINE = 'queue_agenda_machine'


def _gap_line(previous, s):
    """Free time on the same printer between two prints, when there is some worth saying."""
    if previous and previous['end'] and s['start'] and (s['start'] - previous['end']).total_seconds() >= 15 * 60:
        st.caption(f":green[:material/more_time: Libre · {duration_text((s['start'] - previous['end']).total_seconds() / 60)} "
                   f"· {previous['end']:%H:%M} – {s['start']:%H:%M}]")


def _rows(rows, day, labels, *, gaps=False):
    previous = None
    for s in rows:
        if gaps:
            _gap_line(previous, s)
        agenda_row(s, day, labels)
        previous = s if s['end'] else previous


def _machine_head(machine, rows, key):
    """A printer inside a day: its tag, how many prints and how much of the day they take."""
    from views.tags import printer_tag
    minutes = sum(s['minutes'] or 0 for s in rows)
    with st.container(horizontal=True, vertical_alignment='center', gap='small', key=key):
        printer_tag(machine, material=True)
        st.markdown(f":gray[{len(rows)} {'impresión' if len(rows) == 1 else 'impresiones'}" + (f" · {duration_text(minutes)}" if minutes else '') + ']',
                    width='stretch')


def queue_agenda(jobs, labels):
    at = now()
    today = at.date()
    snapshot = st.session_state['snapshot']
    machines = {m['id']: m for m in snapshot['machines']}
    st.session_state.setdefault(DAY, today)
    with st.container(horizontal=True, vertical_alignment='bottom', gap='small'):
        period = st.segmented_control('Periodo', tuple(PERIODS), default=remembered('queue_agenda_period', 'Día'),
                                      key='queue_agenda_period', persist_state='session') or 'Día'
        step = PERIODS[period]
        st.button('Anterior', key='queue_agenda_prev', icon=':material/chevron_left:', on_click=_shift, args=(-step,), help=f'{period} anterior')
        st.button('Hoy', key='queue_agenda_today', on_click=_today, icon=':material/today:')
        st.button('Siguiente', key='queue_agenda_next', icon=':material/chevron_right:', icon_position='right', on_click=_shift, args=(step,), help=f'{period} siguiente')
        start = st.date_input('Desde', key=DAY, width=170, format='DD/MM/YYYY')
        st.space('stretch')
        layout = st.segmented_control('Organizar', LAYOUTS, default=remembered('queue_agenda_layout', 'Por hora'),
                                      key='queue_agenda_layout', persist_state='session',
                                      help='Por hora: todas las impresoras juntas. Por máquina: cada día dividido por impresora.') or 'Por hora'
    # One printer's own agenda: picked here, its prints, its 24 h strip and the free time between prints.
    from views.tags import family
    if st.session_state.get(MACHINE) not in (None, *machines):
        st.session_state[MACHINE] = None
    focus = st.pills('Ver una impresora', list(machines), key=MACHINE, selection_mode='single',
                     format_func=lambda i: f"{family(machines[i])[0]} · {machines[i]['code']}",
                     help='Elige una impresora para ver solo su agenda; vuelve a pulsarla para ver todas.')
    if focus:
        jobs = [j for j in jobs if j['machine_id'] == focus]
        from services.timeline import machine_timeline, availability_text
        from views.timeline_ui import strip
        t = machine_timeline(machines[focus], snapshot['jobs'], at)
        with st.container(border=True, gap='xsmall', key=f'panel-agenda-machine-{focus}'):
            _machine_head(machines[focus], [s for s in t['slots'] if s['start']], f'qhead-agenda-focus-{focus}')
            st.caption(availability_text(t['availability']) if t['availability'] else machines[focus]['status'])
            strip(t, at=at)
    by_day, waiting = bucket(jobs, start, step, at)
    total = sum(len(v) for v in by_day.values())
    minutes = sum(s['minutes'] or 0 for v in by_day.values() for s in v)
    st.caption(f"{total} {'impresión' if total == 1 else 'impresiones'} con horario · {duration_text(minutes) if minutes else 'sin duración capturada'}"
               + (f" · {len(waiting)} sin horario" if waiting else ''))
    for day, rows in by_day.items():
        load = {}
        for s in rows:
            load[s['job']['machine_code'] or 'Sin máquina'] = load.get(s['job']['machine_code'] or 'Sin máquina', 0) + (s['minutes'] or 0)
        with st.container(horizontal=True, vertical_alignment='center', gap='small', key=f"qhead-agenda-{day.isoformat()}"):
            st.markdown(f"**:material/{'today' if day == today else 'calendar_today'}: {day_title(day, today)}** :gray[· {len(rows)}]", width='content')
            if load and not focus:
                st.markdown(':gray[' + ' · '.join(f"{code} {duration_text(m) if m else 's/d'}" for code, m in sorted(load.items())) + ']', width='stretch')
        if not rows:
            st.caption('Sin impresiones programadas. Usa Asignar o Nueva impresión para ocupar el día.')
        elif focus:
            _rows(rows, day, labels, gaps=True)
        elif layout == 'Por máquina':
            groups = {}
            for s in rows:groups.setdefault(s['job']['machine_id'], []).append(s)
            for mid, own in sorted(groups.items(), key=lambda g: (g[0] is None, machines[g[0]]['code'] if g[0] in machines else '')):
                _machine_head(machines.get(mid), own, f"qhead-agenda-{day.isoformat()}-m{mid}")
                with st.container(gap='xsmall', key=f"qorder-agenda-{day.isoformat()}-m{mid}"):
                    _rows(own, day, labels, gaps=True)
        else:
            _rows(rows, day, labels)
    unscheduled(waiting, machines, labels)


def unscheduled(waiting, machines, labels):
    """Prints without a start, in sight: those already on a printer (by printer) and those still without one."""
    if not waiting:
        return
    from views.queue_board import operate_row
    assigned = [s for s in waiting if s['job']['machine_id'] is not None]
    loose = [s for s in waiting if s['job']['machine_id'] is None]
    with st.container(horizontal=True, vertical_alignment='center', gap='small', key='qhead-agenda-unscheduled'):
        st.markdown(f"**:material/pending_actions: Asignadas sin hora** :gray[· {len(assigned)}]" + (f" · **Sin impresora** :gray[· {len(loose)}]" if loose else ''),
                    width='content')
        st.markdown(':gray[Tienen lugar en la cola pero no un inicio: Horario les da fecha y pasan a su día.]', width='stretch')
    groups = {}
    for s in assigned:groups.setdefault(s['job']['machine_id'], []).append(s)
    for mid, own in sorted(groups.items(), key=lambda g: machines[g[0]]['code'] if g[0] in machines else ''):
        _machine_head(machines.get(mid) or next((m for m in st.session_state['snapshot']['all_machines'] if m['id'] == mid), None), own, f'qhead-agenda-unscheduled-m{mid}')
        for s in own:operate_row(s['job'], labels[s['job']['order_id']])
    if loose:
        _machine_head(None, loose, 'qhead-agenda-unscheduled-none')
        for s in loose:operate_row(s['job'], labels[s['job']['order_id']])
