"""A printer's queue as a day-by-day agenda, like the agenda view of a calendar.

Days on the left (weekday and number, today marked), on the right each print with its start and end,
the color of its order, piece and state; the free gaps between prints say how long they are. The print
being set up appears in its place, highlighted, and is flagged when it overlaps another one. Picking a
free gap moves the new print's start there. Each print carries its calendar tag (Programada, Imprimiendo,
Inicio vencido…), and the prints assigned to the printer without a start yet close the agenda in their
own block, «Asignadas sin hora», so the printer's whole load is in one place.
"""
from datetime import datetime, timedelta
from html import escape
import streamlit as st
from services.timeline import duration_text, machine_timeline
from utils.dates import now
from views.kind_style import kind_of, order_tone
from views.timeline_ui import schedule_state, schedule_tag_html

DAYS = ('LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM')
HORIZON = 7
MIN_GAP = 15

CSS = '''<style>
.ag{border:1px solid #DCE4E8;border-radius:14px;background:#fff;overflow:hidden;font-variant-numeric:tabular-nums}
.ag-day{display:grid;grid-template-columns:76px 1fr;border-bottom:1px solid #EDF1F3}.ag-day:last-child{border-bottom:0}
.ag-date{padding:12px 0 10px;text-align:center;color:#5E6E77}.ag-dow{display:block;font-size:.68rem;font-weight:700;letter-spacing:.08em}
.ag-num{display:inline-grid;place-items:center;width:34px;height:34px;margin-top:2px;border-radius:50%;font-size:1.15rem;font-weight:650;color:#18262E}
.ag-day.today .ag-dow{color:var(--nx-accent,#0F6F78)}.ag-day.today .ag-num{background:var(--nx-accent,#0F6F78);color:#fff}
.ag-list{padding:6px 12px 8px 0;display:flex;flex-direction:column;gap:4px}
.ag-ev{display:grid;grid-template-columns:118px 12px 1fr;align-items:center;gap:8px;padding:7px 10px;border-radius:10px}
@media (hover:hover){.ag-ev:hover{background:#F6F8F9}}
.ag-time{font-size:.82rem;color:#33474F;white-space:nowrap}.ag-dot{width:10px;height:10px;border-radius:50%;background:var(--c)}
.ag-title{font-size:.9rem;font-weight:600;color:#18262E;line-height:1.25}.ag-meta{display:block;font-size:.76rem;font-weight:400;color:#5E6E77}
.ag-run .ag-dot{box-shadow:0 0 0 3px color-mix(in srgb,var(--c) 30%,transparent)}
.ag-new{background:color-mix(in srgb,var(--nx-accent,#0F6F78) 9%,#fff);border:1.5px dashed var(--nx-accent,#0F6F78)}
.ag-new .ag-title{color:var(--nx-accent,#0F6F78)}.ag-clash{border-color:#B2434C;background:#FBE9EA}.ag-clash .ag-title{color:#922F39}
.ag-gap{display:grid;grid-template-columns:118px 12px 1fr;gap:8px;padding:2px 10px;font-size:.76rem;color:#2F7A57}
.ag-gap span:last-child{border-top:1px dashed #BFD9CB;align-self:center}
.ag-empty{padding:12px 10px;font-size:.84rem;color:#5E6E77}
.ag-day.wait{background:#FFFDF6}.ag-day.wait .ag-dow{color:#735A0B}.ag-day.wait .ag-num{font-size:1.2rem;color:#735A0B}
.ag-new-tag{display:inline-block;margin-left:6px;padding:1px 8px;border-radius:99px;font-size:.68rem;font-weight:700;vertical-align:1px;
  background:var(--nx-accent,#0F6F78);color:#fff}
</style>'''


def _hm(value):
    return f'{value:%H:%M}'


def _events(snapshot, machine_id, at):
    """Booked prints of the machine, with their order color: (start, end or None, job, state)."""
    machine = next((m for m in snapshot['all_machines'] if m['id'] == machine_id), None)
    slots = machine_timeline(machine, snapshot['jobs'], at)['slots'] if machine else []
    booked = sorted((s for s in slots if s['start'] and s['state'] in ('En marcha', 'Sin fin', 'Reservada')), key=lambda s: s['start'])
    waiting = [s for s in slots if s not in booked]
    return booked, waiting


def gaps(booked, at, days=HORIZON, minutes=None):
    """Free intervals from now on, between booked prints: [(start, end or None)], long enough for `minutes`."""
    cursor, found = at, []
    for s in booked:
        if s['state'] == 'Sin fin':
            return found  # The machine stays taken until someone records it.
        if s['end'] <= cursor:
            continue
        if s['start'] > cursor and (s['start'] - cursor).total_seconds() / 60 >= max(MIN_GAP, minutes or 0):
            found.append((cursor, s['start']))
        cursor = max(cursor, s['end'])
    if cursor < at + timedelta(days=days):
        found.append((cursor, None))
    return found


def _row(start, end, title, meta, color, cls='', tag='', span=None):
    span = span or (f"{_hm(start)} – {_hm(end)}" if end and end.date() == start.date() else f"{_hm(start)} – {end:%d/%m %H:%M}" if end else f"{_hm(start)} · sin fin")
    return (f'<div class="ag-ev {cls}" style="--c:{color}"><span class="ag-time">{span}</span><span class="ag-dot"></span>'
            f'<span class="ag-title">{escape(title)}{tag}<span class="ag-meta">{escape(meta)}</span></span></div>')


def agenda(snapshot, machine_id, key, *, proposal=None, pick_gaps=True):
    """The machine's agenda for the next days, the print being set up included; returns nothing.

    `proposal` is {'start': datetime or None, 'minutes': int or None, 'label': str} for the print in the form.
    Picking a free gap sets the form's start through its schedule controls (`key`); outside a form
    (`pick_gaps=False`) the gaps are only shown.
    """
    if machine_id is None:
        return
    at = now()
    booked, waiting = _events(snapshot, machine_id, at)
    code = next((m['code'] for m in snapshot['all_machines'] if m['id'] == machine_id), '')
    entries = []
    for s in booked:
        job = s['job']
        kind = kind_of(job)
        color = order_tone(job['order_id'], kind)[1]
        who = {'Prototipo': f"Prototipo · {job['project']}", 'Stock': 'Stock'}.get(kind) or f"{job['order_code']} · {job['client'] or job['project']}"
        tag = schedule_tag_html(schedule_state(s))
        entries.append((s['start'], s['end'], _row(s['start'], s['end'], f"{job['part_name']} ×{job['quantity_remaining']}",
                                                 f"{who} · {job['code']} · {duration_text(s['minutes'])}", color,
                                                 'ag-run' if s['state'] in ('En marcha', 'Sin fin') else '', tag)))
    new = None
    if proposal and proposal.get('start'):
        start = proposal['start']
        end = start + timedelta(minutes=proposal['minutes']) if proposal.get('minutes') else None
        clash = [s['job']['code'] for s in booked if end and s['start'] < end and (s['end'] is None or s['end'] > start)]
        new = (start, end, _row(start, end, f"Esta impresión · {proposal.get('label', '')}",
                                ('Se cruza con ' + ', '.join(clash)) if clash else (duration_text(proposal.get('minutes')) + ' · aún sin guardar'),
                                'var(--nx-accent,#0F6F78)', 'ag-new ag-clash' if clash else 'ag-new', '<span class="ag-new-tag">Nueva · Programada</span>'))
        entries.append(new)
    entries.sort(key=lambda e: e[0])
    free = gaps(booked, at, minutes=proposal.get('minutes') if proposal else None)

    # Days with something, today always; free gaps placed between the prints of each day.
    days = sorted({at.date(), *(e[0].date() for e in entries if e[0].date() >= at.date() - timedelta(days=1))})
    html = []
    for day in days[:HORIZON + 1]:
        rows = [e for e in entries if e[0].date() == day]
        day_gaps = [g for g in free if g[0].date() == day]
        merged = sorted([(e[0], e[2]) for e in rows] + [(g[0], f'<div class="ag-gap"><span>{_hm(g[0])}</span><span></span>'
                         f'<span>Libre · {duration_text((g[1] - g[0]).total_seconds() / 60) if g[1] else "desde aquí"}</span></div>') for g in day_gaps],
                        key=lambda r: r[0])
        body = ''.join(r[1] for r in merged) or '<div class="ag-empty">Sin impresiones · libre todo el día</div>'
        html.append(f'<div class="ag-day{" today" if day == at.date() else ""}"><div class="ag-date"><span class="ag-dow">{DAYS[day.weekday()]}</span>'
                    f'<span class="ag-num">{day.day}</span></div><div class="ag-list">{body}</div></div>')
    # Assigned to this printer without a start: the rest of its load, in a block of their own at the end.
    unscheduled = []
    for s in sorted(waiting, key=lambda s: s['job']['id']):
        job = s['job']
        kind = kind_of(job)
        who = {'Prototipo': f"Prototipo · {job['project']}", 'Stock': 'Stock'}.get(kind) or f"{job['order_code']} · {job['client'] or job['project']}"
        unscheduled.append(_row(at, None, f"{job['part_name']} ×{job['quantity_remaining']}", f"{who} · {job['code']}",
                                order_tone(job['order_id'], kind)[1], tag=schedule_tag_html(schedule_state(s)),
                                span=duration_text(s['minutes']) if s['minutes'] else 'sin duración'))
    if proposal and not proposal.get('start') and proposal.get('label'):
        unscheduled.insert(0, _row(at, None, f"Esta impresión · {proposal['label']}", 'aún sin guardar · sin inicio', 'var(--nx-accent,#0F6F78)', 'ag-new',
                                   '<span class="ag-new-tag">Nueva · Asignada sin hora</span>',
                                   span=duration_text(proposal['minutes']) if proposal.get('minutes') else 'sin duración'))
    if unscheduled:
        html.append(f'<div class="ag-day wait"><div class="ag-date"><span class="ag-dow">SIN HORA</span><span class="ag-num">{len(unscheduled)}</span></div>'
                    f'<div class="ag-list">{"".join(unscheduled)}</div></div>')
    with st.container(gap='xsmall', key=f'agenda-{key}'):
        with st.container(horizontal=True, vertical_alignment='center', gap='small'):
            st.markdown(f"**:material/calendar_view_day: Agenda de {code}**", width='content')
            st.caption(f"{len(booked)} programadas · {len(waiting)} asignadas sin hora · próximos días")
        st.html(CSS + '<div class="ag">' + ''.join(html) + '</div>')
        # The next free gaps where this print fits: picking one moves its start there.
        options = {g[0].isoformat(timespec='minutes'): g for g in free[:6]} if pick_gaps else {}
        if options:
            from services.timeline import when
            st.pills('Usar un hueco libre', list(options), key=f'{key}_gap_{machine_id}', selection_mode='single',
                     format_func=lambda k: f"{when(options[k][0])} · " + (duration_text((options[k][1] - options[k][0]).total_seconds() / 60) if options[k][1] else 'libre'),
                     on_change=_use_gap, args=(key, machine_id))


def _use_gap(key, machine_id):
    """The gap picked becomes the print's start: 'Otra fecha' with that day and hour."""
    value = st.session_state.get(f'{key}_gap_{machine_id}')
    if not value:
        return
    start = datetime.fromisoformat(value)
    if start < now():
        # A gap that starts now: the next quarter hour, as the first free slot does.
        start = (now() + timedelta(minutes=5)).replace(second=0, microsecond=0)
        start += timedelta(minutes=(-start.minute) % 15)
    st.session_state[f'{key}_when_{machine_id}'] = 'Otra fecha'
    st.session_state[f'{key}_day'] = start.date()
    st.session_state[f'{key}_hour'] = start.time()
