"""What the sidebar tells at a glance: a live count beside each page and the printers right now.

A count says what needs a look on that page (late orders, prints with a problem, printers down); when
nothing does, it says how much is there, in gray. The printers list is the floor in one line each:
model color, code, state and what it prints with the time left, refreshed every minute.
"""
import html
import streamlit as st
from utils.dates import now


def badges(snapshot):
    """{page key: (markdown badge, tooltip)} for the pages with something to count."""
    from services.order_board import tracking
    from services.timeline import slot, issues
    result = {}
    orders = [o for o in snapshot['orders'] if not o.get('stock_run') and not o.get('commercial_cancelled') and not o.get('development')]
    active = [t for t in (tracking(o) for o in orders) if not t['delivered']]
    late = sum(t['overdue'] for t in active)
    ready = sum(t['lane'] == 'Salida' for t in active)
    if active:
        result['orders'] = (f":red-badge[{late}]" if late else f":gray-badge[{len(active)}]",
                            f"{len(active)} pedidos activos" + (f" · {late} atrasados" if late else '') + (f" · {ready} listos para salida" if ready else ''))
    jobs = [j for j in snapshot['jobs'] if j['status'] != 'Terminado' and j['order_status'] != 'Entregado' and not j.get('commercial_cancelled')]
    running = sum(j['status'] == 'En producción' for j in jobs)
    problems = sum(bool(issues(slot(j))) for j in jobs)
    if jobs:
        result['queue'] = (' '.join(x for x in (f":blue-badge[:material/autorenew: {running}]" if running else '',
                                                 f":red-badge[:material/warning: {problems}]" if problems else '',
                                                 '' if running or problems else f":gray-badge[{len(jobs)}]") if x),
                           f"{len(jobs)} impresiones activas · {running} en marcha" + (f" · {problems} con problema de horario" if problems else ''))
    projects = sum((o.get('development') or {}).get('status') == 'Activo' for o in snapshot['orders'])
    if projects:
        result['development'] = (f":violet-badge[{projects}]", f"{projects} proyectos de prototipo activos")
    down = [m for m in snapshot['machines'] if m['status'] in ('Mantenimiento', 'Fuera de servicio')]
    if down:
        result['machines'] = (f":orange-badge[{len(down)}]", 'Detenidas: ' + ', '.join(f"{m['code']} ({m['status'].lower()})" for m in down))
    return result


def _left(minutes):
    minutes = max(0, round(minutes))
    return f"{minutes // 60} h {minutes % 60:02d} m" if minutes >= 60 else f"{minutes} min"


def printers_html(snapshot, at=None):
    from views.live_floor import progress_of
    from views.tags import family, STATE_DOTS
    at = at or now()
    jobs = {j['id']: j for j in snapshot['jobs']}
    rows = []
    for m in snapshot['machines']:
        model, color = family(m)
        current = jobs.get((m.get('current_job') or {}).get('id'))
        if current:
            done, left = progress_of(current, at)
            what = html.escape(current['part_name'])
            time = 'sin fin' if left is None or left <= 0 else _left(left)
            state, tone = time, '#F2B8B8' if left is None or left <= 0 else '#B9D3F2'
            bar = f'<i style="width:{round((done or 0) * 100)}%"></i>' if done is not None else ''
        elif m['status'] in ('Mantenimiento', 'Fuera de servicio'):
            what, state, tone, bar = html.escape(m['status']), '', '#F2C99A', ''
        else:
            what, state, tone, bar = 'Libre', '', '#9FD8B5', ''
        title = html.escape(f"{m['name']} · {model} · {m['status']}" + (f" · {current['code']} {current['part_name']}" if current else ''))
        rows.append(f'<div class="nxp" title="{title}"><span class="nxm" style="background:{color}">{html.escape(model.upper())}</span>'
                    f'<b>{html.escape(m["code"])}</b><span class="nxd" style="background:{STATE_DOTS.get(m["status"], "#64737C")}"></span>'
                    f'<span class="nxw" style="color:{tone}">{what}</span><span class="nxt">{state}</span>'
                    + (f'<span class="nxb">{bar}</span>' if bar else '') + '</div>')
    printing = sum(bool(m.get('current_job')) for m in snapshot['machines'])
    head = f'<div class="nxh">Impresoras · {printing}/{len(snapshot["machines"])} imprimiendo</div>'
    return ('<style>.nxf{display:flex;flex-direction:column;gap:.18rem;font-size:.74rem;color:#DCE6E9}'
            '.nxh{text-transform:uppercase;letter-spacing:.06em;font-size:.66rem;font-weight:650;opacity:.7;margin-bottom:.1rem}'
            '.nxp{position:relative;display:grid;grid-template-columns:auto auto auto 1fr auto;align-items:center;gap:.35rem;padding:.22rem .4rem .3rem;'
            'border-radius:8px;background:rgba(255,255,255,.04)}'
            '.nxm{color:#fff;border-radius:5px;padding:0 .3rem;font-size:.58rem;font-weight:700;letter-spacing:.04em}'
            '.nxd{width:.45rem;height:.45rem;border-radius:50%}'
            '.nxw{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}'
            '.nxt{font-variant-numeric:tabular-nums;opacity:.85;white-space:nowrap}'
            '.nxb{position:absolute;left:.4rem;right:.4rem;bottom:.08rem;height:2px;border-radius:2px;background:rgba(255,255,255,.1);overflow:hidden}'
            '.nxb i{display:block;height:100%;background:#7FB2EA}</style>'
            f'<div class="nxf">{head}{"".join(rows)}</div>')


@st.fragment(run_every='60s')
def printers():
    """The floor in the sidebar; its own minute refresh reads the database again."""
    from services.queries import load_snapshot
    fresh = st.session_state.pop('_nav_floor_fresh', False)
    snapshot = st.session_state['snapshot'] if fresh else load_snapshot()
    if snapshot['machines']:
        st.html(printers_html(snapshot))


def render_printers():
    st.session_state['_nav_floor_fresh'] = True
    printers()
