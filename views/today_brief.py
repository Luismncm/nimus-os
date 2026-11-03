"""The top of Hoy: a one-line briefing, the pulse of each work area and today's agenda.

Briefing: greeting, the date in words and one sentence with what matters most, so the day reads
before any number. Pulse: one card per work area (Producir, Entregar, Abastecer, Cobrar, Pagar) with
its total, its alerts and a way in; its edge is red, orange or calm by its worst alert. Agenda: what
happens today in time order (prints that start or finish, deliveries, money due) with a now line.
"""
import html
import streamlit as st
from services.quotations import money
from services.workbench import urgency
from utils.dates import now, parse_end
from views.kind_style import kind_of, order_tone

DAYS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def choose_front(front):
    st.session_state['today_front'] = front


def day_words(at):
    return f"{DAYS[at.weekday()].capitalize()} {at.day} de {MONTHS[at.month - 1]}"


def greeting(at):
    return 'Buenos días' if at.hour < 12 else 'Buenas tardes' if at.hour < 19 else 'Buenas noches'


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def headline(board, snapshot, supply):
    """The day in one sentence: what is late first, then the floor, then money due today."""
    daily = board['daily']
    parts = []
    if daily['overdue']:parts.append(_plural(len(daily['overdue']), 'entrega vencida', 'entregas vencidas'))
    if daily['due']:parts.append(_plural(len(daily['due']), 'entrega para hoy', 'entregas para hoy'))
    if daily['blocked']:parts.append(_plural(len(daily['blocked']), 'pedido bloqueado', 'pedidos bloqueados'))
    machines = snapshot['machines']
    running = sum(bool(m.get('current_job')) for m in machines)
    if machines:parts.append(f"{running} de {len(machines)} impresoras trabajando")
    if supply['overdue']:parts.append(_plural(supply['overdue'], 'llegada de compra vencida', 'llegadas de compra vencidas'))
    if not parts:return 'Todo al día: sin entregas vencidas ni bloqueos.'
    return (', '.join(parts[:-1]) + ' y ' + parts[-1] if len(parts) > 1 else parts[0]) + '.'


def brief(board, snapshot, supply, at=None):
    at = at or now()
    st.html(f'<div class="today-brief"><div class="today-hello">{greeting(at)} · {day_words(at)}</div>'
            f'<div class="today-line">{html.escape(headline(board, snapshot, supply))}</div></div>')


def _pulse_card(name, icon, value, alerts, front, note=''):
    """alerts: [(text, color)]; the worst color sets the card's edge."""
    tone = 'red' if any(c == 'red' for _, c in alerts) else 'orange' if any(c == 'orange' for _, c in alerts) else 'calm'
    with st.container(border=True, gap='xxsmall', key=f"pulse-{tone}-{front}"):
        st.caption(f":material/{icon}: {name}")
        st.html(f"<div class='pulse-value'>{html.escape(str(value))}</div>")
        with st.container(horizontal=True, gap='xxsmall'):
            for text, color in alerts:st.badge(text, color=color)
            if not alerts:st.badge(note or 'Al día', color='green', icon=':material/check:')
        st.button(f"Ir a {front}", key=f"today_pulse_{front}", type='tertiary', icon=':material/arrow_forward:', icon_position='right',
                  on_click=choose_front, args=(front,), width='stretch')


def pulse(board, supply):
    daily = board['daily']
    late = lambda rows, field: sum(urgency(r.get(field))[1] == 'red' for r in rows)
    with st.container(horizontal=True, gap='small', key='today-pulse'):
        running = len(daily['base']['running'])
        _pulse_card('Producir', 'precision_manufacturing', len(board['jobs']),
                    [(t, c) for t, c, n in ((f"{daily['unassigned_units']} piezas por repartir", 'orange', daily['unassigned_units']),
                                             (f"{len(daily['missing'])} por definir", 'orange', len(daily['missing']))) if n],
                    'Producir', note=f"{running} imprimiendo")
        _pulse_card('Entregar', 'local_shipping', len(board['deliveries']),
                    [(t, c) for t, c, n in ((f"{len(daily['overdue'])} vencidas", 'red', len(daily['overdue'])),
                                             (f"{len(daily['blocked'])} bloqueados", 'red', len(daily['blocked'])),
                                             (f"{len(daily['due'])} hoy", 'orange', len(daily['due'])),
                                             (f"{len(daily['ready'])} listos", 'green', len(daily['ready']))) if n],
                    'Entregar')
        _pulse_card('Abastecer', 'inventory', supply['attention'],
                    [(t, c) for t, c, n in ((f"{supply['overdue']} llegadas vencidas", 'red', supply['overdue']),
                                             (f"{len(supply['to_order'])} por pedir", 'orange', len(supply['to_order']))) if n],
                    'Abastecer')
        due_in = late(board['collections'], 'due_on')
        _pulse_card('Cobrar', 'south_west', money(board['to_collect']),
                    [(f"{due_in} vencidos", 'red')] if due_in else [], 'Cobrar', note=f"{len(board['collections'])} pendientes")
        due_out = late(board['payables'], 'due_on')
        _pulse_card('Pagar', 'north_east', money(board['to_pay']),
                    [(f"{due_out} vencidos", 'orange')] if due_out else [], 'Pagar', note=f"{len(board['payables'])} pendientes")


def agenda_items(snapshot, board, at=None):
    """Today's events: timed ones (print starts and finishes) and all-day ones (deliveries, money due)."""
    at = at or now()
    today = at.date()
    timed, allday = [], []
    for job in snapshot['jobs']:
        if job['order_status'] == 'Entregado' or job.get('commercial_cancelled'):continue
        where = job['machine_code'] or 'sin máquina'
        color = order_tone(job['order_id'], kind_of(job))[1]
        what = f"{job['part_name']} ×{job['quantity']}"
        if job['status'] == 'Terminado':
            done = parse_end(job.get('completed_at'))
            if done and done.date() == today:
                timed.append(dict(at=done, kind='done', label='Terminó', text=what, where=where, color=color, code=job['code']))
            continue
        start = parse_end(job.get('calendar_start') or job.get('planned_start'))
        end = parse_end(job.get('estimated_finish') or job.get('calendar_end'))
        if job['status'] == 'En producción':
            if end and end.date() == today:
                timed.append(dict(at=end, kind='late' if end < at else 'finish', label='Debió terminar' if end < at else 'Termina',
                                  text=what, where=where, color=color, code=job['code']))
        elif start and start.date() == today and job['status'] in ('En cola', 'Pausado'):
            timed.append(dict(at=start, kind='late' if start < at else 'start', label='Debió iniciar' if start < at else 'Inicia',
                              text=what, where=where, color=color, code=job['code']))
    for order in board['deliveries']:
        if urgency(order.get('deadline'))[0] == 'Hoy':
            allday.append(dict(kind='deliver', label='Entrega', text=f"{order['code']} · {order['project']}", where=order['client'] or 'Sin cliente'))
    for row in board['collections']:
        if urgency(row.get('due_on'))[0] == 'Hoy':
            allday.append(dict(kind='collect', label='Cobro', text=f"{row['code']} · {money(row['balance_cents'])}", where=row['client'] or ''))
    for row in board['payables']:
        if urgency(row.get('due_on'))[0] == 'Hoy':
            allday.append(dict(kind='pay', label='Pago', text=f"{row['code']} · {money(row['balance_cents'])}", where=row['concept'] or ''))
    return sorted(timed, key=lambda e: e['at']), allday


AGENDA_CSS = '''<style>
.ag{display:flex;flex-direction:column;gap:2px;font-size:.86rem}
.ag-day{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.ag-chip{display:inline-flex;gap:6px;align-items:center;border-radius:8px;padding:3px 9px;font-size:.78rem;font-weight:600;background:#F1F4F6;color:#18262E}
.ag-chip b{font-weight:700;text-transform:uppercase;letter-spacing:.04em;font-size:.66rem}
.ag-chip.deliver{background:#FBEEDC;color:#86501A}.ag-chip.collect{background:#E3F2EA;color:#235E43}.ag-chip.pay{background:#E5EEF8;color:#2D5580}
.ag-row{display:grid;grid-template-columns:3.4rem 10px 1fr;gap:10px;align-items:start;padding:5px 0}
.ag-time{font-variant-numeric:tabular-nums;font-weight:700;color:#18262E;text-align:right;padding-top:1px}
.ag-dot{width:10px;height:10px;border-radius:50%;margin-top:5px;box-shadow:0 0 0 3px #fff}
.ag-body{border-left:3px solid var(--c);padding:1px 0 1px 9px;min-width:0}
.ag-body b{font-weight:650}.ag-sub{color:#5E6E77;font-size:.78rem}
.ag-tag{font-size:.66rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-right:6px}
.ag-row.past{opacity:.55}.ag-row.late .ag-tag{color:#B2434C}.ag-row.start .ag-tag{color:#244F8A}.ag-row.finish .ag-tag{color:#2F67B2}.ag-row.done .ag-tag{color:#2F7A57}
.ag-now{display:grid;grid-template-columns:3.4rem 1fr;gap:10px;align-items:center;color:#B2434C;font-weight:700;font-size:.72rem}
.ag-now i{display:block;height:2px;background:#B2434C;border-radius:2px}
.ag-empty{color:#5E6E77;font-size:.84rem;padding:4px 0}
</style>'''


def agenda_html(timed, allday, at=None):
    at = at or now()
    out = [AGENDA_CSS, '<div class="ag">']
    if allday:
        out.append('<div class="ag-day">' + ''.join(
            f'<span class="ag-chip {e["kind"]}" title="{html.escape(e["where"])}"><b>{e["label"]}</b>{html.escape(e["text"])}</span>' for e in allday) + '</div>')
    placed = False
    for e in timed:
        if not placed and e['at'] > at:
            out.append(f'<div class="ag-now"><span style="text-align:right">{at:%H:%M}</span><i></i></div>');placed = True
        past = e['at'] <= at and e['kind'] != 'late'
        out.append(f'<div class="ag-row {e["kind"]}{" past" if past else ""}"><span class="ag-time">{e["at"]:%H:%M}</span>'
                   f'<span class="ag-dot" style="background:{e["color"]}"></span>'
                   f'<div class="ag-body" style="--c:{e["color"]}"><span class="ag-tag">{e["label"]}</span><b>{html.escape(e["text"])}</b>'
                   f'<div class="ag-sub">{html.escape(e["where"])} · {html.escape(e["code"])}</div></div></div>')
    if timed and not placed:
        out.append(f'<div class="ag-now"><span style="text-align:right">{at:%H:%M}</span><i></i></div>')
    if not timed and not allday:
        out.append('<div class="ag-empty">Nada programado para hoy: sin impresiones que inicien o terminen, ni entregas, cobros o pagos con fecha de hoy.</div>')
    elif not timed:
        out.append('<div class="ag-empty">Sin impresiones con hora para hoy.</div>')
    out.append('</div>')
    return ''.join(out)


def agenda(snapshot, board):
    at = now()
    timed, allday = agenda_items(snapshot, board, at)
    with st.container(border=True, key='panel-today-agenda'):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            st.markdown('**Agenda de hoy**', width='content')
            st.caption(f"{len(timed)} impresiones con hora · {len(allday)} entregas, cobros y pagos")
        st.html(agenda_html(timed, allday, at))
        if st.button('Ver calendario', key='today_summary_calendar', type='tertiary', icon=':material/calendar_month:'):
            st.session_state['queue_view'] = 'Calendario';st.switch_page('views/queue.py')
