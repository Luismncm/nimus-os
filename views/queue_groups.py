"""The queue grouped by state of the work, with the same rows as by printer.

Printing, queued, paused or blocked, and finished (folded). What each print is for reads from its
order's color and tag, the same in every grouping.
"""
import re
import streamlit as st
from services.timeline import duration_text
from views.queue_board import operate_row

STATE_GROUPS = {'En producción': 'Imprimiendo', 'En cola': 'En cola', 'Pausado': 'Pausadas o bloqueadas', 'Bloqueado': 'Pausadas o bloqueadas', 'Terminado': 'Terminadas'}
STATE_META = {'Imprimiendo': 'autorenew', 'En cola': 'schedule', 'Pausadas o bloqueadas': 'pause_circle', 'Terminadas': 'check_circle'}


def _key(text):
    return re.sub(r'[^a-z0-9_-]', '-', str(text).lower())


def load_text(jobs):
    """Pending units and booked work of these prints, for a heading."""
    active = [j for j in jobs if j['status'] != 'Terminado']
    minutes = sum(j.get('duration_minutes') or 0 for j in active)
    return ' · '.join(x for x in (f"{sum(j['quantity_remaining'] for j in active)} u. pendientes" if active else '',
                                  f"{duration_text(minutes)} de trabajo" if minutes else '') if x)


def heading(title, icon, count, detail='', *, key):
    """Section title of the grouped queue: icon, name, how many prints and their load."""
    with st.container(horizontal=True, vertical_alignment='center', gap='small', key=f'qhead-{_key(key)}'):
        st.markdown(f"**:material/{icon}: {title}** :gray[· {count}]", width='content')
        if detail:
            st.markdown(f":gray[{detail}]", width='content')


def state_view(jobs, labels):
    groups = {}
    for job in jobs:groups.setdefault(STATE_GROUPS.get(job['status'], 'En cola'), []).append(job)
    for name in STATE_META:
        own = groups.get(name)
        if not own:
            continue
        if name == 'Terminadas':
            # History, not work to do: folded so the open prints stay on top.
            with st.expander(f"Terminadas · {len(own)}", icon=':material/check_circle:', key='queue_state_done', on_change='ignore'):
                for job in own:operate_row(job, labels[job['order_id']])
            continue
        heading(name, STATE_META[name], len(own), load_text(own), key=f'state-{name}')
        for job in own:operate_row(job, labels[job['order_id']])
