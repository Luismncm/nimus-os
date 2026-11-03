"""Compact time strip and one-line descriptions of booked intervals."""
from datetime import timedelta
from html import escape
import streamlit as st
from services.timeline import duration_text, when, issues
from utils.dates import now, parse_end

STRIP_CSS = """<style>
.tl{font:11px 'Segoe UI',system-ui,sans-serif;color:#5E6E77;margin:2px 0 4px}
.tl-track{position:relative;height:28px;border-radius:8px;background:#F1F5F7;overflow:hidden;
  background-image:repeating-linear-gradient(90deg,transparent 0,transparent calc(12.5% - 1px),#E1E8EB calc(12.5% - 1px),#E1E8EB 12.5%)}
.tl-b{position:absolute;top:3px;bottom:3px;border-radius:6px;display:flex;align-items:center;padding:0 7px;overflow:hidden;white-space:nowrap;
  font-weight:650;font-size:10.5px;color:#18262E;background:color-mix(in srgb,var(--c) 18%,#fff);border:1px solid color-mix(in srgb,var(--c) 55%,#fff);
  border-left:4px solid var(--c);box-sizing:border-box}
.tl-b.run{background:var(--c);color:#fff;border-color:var(--c);
  background-image:repeating-linear-gradient(135deg,rgba(255,255,255,.18) 0 6px,transparent 6px 12px)}
.tl-b.bad{box-shadow:0 0 0 2px #B2434C}
.tl-now{position:absolute;top:0;bottom:0;width:2px;background:#B2434C;left:0}
.tl-day{position:absolute;top:0;bottom:0;border-left:1.5px dashed #9AA8AF}
.tl-ticks{position:relative;height:15px;margin-top:3px;font-variant-numeric:tabular-nums}
.tl-ticks span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.tl-ticks .first{transform:none;color:#B2434C;font-weight:650}.tl-ticks .last{transform:translateX(-100%)}
.tl-ticks .day{color:#33474F;font-weight:650}
</style>"""


def _tone(job):
    from views.kind_style import kind_of, order_tone
    return order_tone(job['order_id'], kind_of(job))[1]


def strip(timeline, *, hours=24, at=None):
    """Next `hours` of one machine as labeled blocks: each print in its order's color, the running one solid
    and striped, problems outlined in red, gridlines every 3 h, a mark for now and one for midnight."""
    at = at or now();end = at + timedelta(hours=hours);span = hours * 60
    cells, labels = [], []
    for s in timeline['slots']:
        if s['state'] not in ('En marcha', 'Sin fin', 'Reservada') or not s['start']:
            continue
        first = max(s['start'], at);last = min(s['end'] or end, end)
        if last <= first or first >= end:
            continue
        left = (first - at).total_seconds() / 60 / span * 100
        width = max(1.2, (last - first).total_seconds() / 60 / span * 100)
        job = s['job']
        title = f"{job['code']} · {job['part_name']} · {when(s['start'], at)}–{when(s['end'], at) if s['end'] else 'sin fin'}"
        labels.append(title)
        text = job['part_name'] if width > 16 else job['code'] if width > 7 else ''
        cls = 'tl-b' + (' run' if s['state'] != 'Reservada' else '') + (' bad' if issues(s) else '')
        cells.append(f'<span class="{cls}" title="{escape(title)}" style="left:{left:.2f}%;width:{width:.2f}%;--c:{_tone(job)}">{escape(text)}</span>')
    midnight = (at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day = ''
    if midnight < end:
        x = (midnight - at).total_seconds() / 60 / span * 100
        day = f'<span class="tl-day" style="left:{x:.2f}%"></span>'
    ticks = ''.join(f'<span style="left:{100 * h / hours:.2f}%">{(at + timedelta(hours=h)):%H:%M}</span>' for h in range(3, hours, 3)
                    if abs((at + timedelta(hours=h) - midnight).total_seconds()) > 3600)
    if midnight < end:
        ticks += f'<span class="day" style="left:{(midnight - at).total_seconds() / 60 / span * 100:.2f}%">mañana</span>'
    summary = f"Próximas {hours} h: " + ('; '.join(labels) if labels else 'sin reservas')
    st.html(f'{STRIP_CSS}<div class="tl" role="img" aria-label="{escape(summary)}"><div class="tl-track">{"".join(cells)}{day}<span class="tl-now" title="Ahora"></span></div>'
            f'<div class="tl-ticks"><span class="first" style="left:0">Ahora {at:%H:%M}</span>{ticks}<span class="last" style="left:100%">+{hours} h</span></div></div>')


COUNTDOWN_CSS = """<style>
.cd{display:inline-flex;flex-wrap:wrap;align-items:center;gap:4px 8px;max-width:100%;box-sizing:border-box;font:12px 'Segoe UI',system-ui,sans-serif;
  font-variant-numeric:tabular-nums;padding:3px 10px 3px 8px;border-radius:12px;background:#E5EEF8;color:#2D5580;font-weight:650}
.cd small{font-weight:500;color:inherit;opacity:.8}
.cd .bar{flex:0 0 84px;height:6px;border-radius:99px;background:rgba(61,111,163,.22);overflow:hidden}
.cd .bar i{display:block;height:100%;background:#3D6FA3;border-radius:99px}
.cd.late{background:#FBE9EA;color:#922F39}.cd.late .bar{background:rgba(178,67,76,.2)}.cd.late .bar i{background:#B2434C}
.cd.wait{background:#EDF1F3;color:#4A5962}.cd.miss{background:#FBEEDC;color:#86501A}
/* Block form for narrow cards: time left on top, a full-width bar, the finish below. */
.cdb{box-sizing:border-box;width:100%;padding:7px 10px 8px;border-radius:10px;background:#E5EEF8;color:#2D5580;
  font:12px 'Segoe UI',system-ui,sans-serif;font-variant-numeric:tabular-nums}
.cdb-top{display:flex;justify-content:space-between;align-items:baseline;gap:6px;font-weight:700;font-size:12.5px}
.cdb-top span:last-child{font-weight:600;font-size:11px;opacity:.85}
.cdb .bar{height:6px;margin:6px 0 4px;border-radius:99px;background:rgba(61,111,163,.22);overflow:hidden}
.cdb .bar i{display:block;height:100%;background:#3D6FA3;border-radius:99px}
.cdb-sub{font-size:11px;opacity:.85}
.cdb.late{background:#FBE9EA;color:#922F39}.cdb.late .bar{background:rgba(178,67,76,.2)}.cdb.late .bar i{background:#B2434C}
</style>"""


def _run(s, at):
    """(fraction done, minutes left, finish) of a printing job, measured from its real start, not its booking."""
    job = s['job']
    start = parse_end(job.get('current_run_started_at')) or s['start']
    finish = parse_end(job.get('estimated_finish')) or s['end']
    if not start or not finish:
        return None, None, None
    total = (finish - start).total_seconds()
    done = min(1.0, max(0.0, (at - start).total_seconds() / total)) if total > 0 else 1.0
    return done, (finish - at).total_seconds() / 60, finish


def _pct(done):
    return 'recién iniciada' if done < .01 else f'{done:.0%}'


def countdown_html(s, at=None, *, block=False):
    """How long is left: a printing job's remaining time with a bar, or how long until a booked one starts.

    `block` lays it out for a narrow card (time left on top, full-width bar, finish below); otherwise it
    is a pill that wraps inside its row.
    """
    at = at or now()
    if s['state'] == 'Sin fin':
        return COUNTDOWN_CSS + ('<div class="cdb late"><div class="cdb-top"><span>⏱ Sin fin vigente</span></div><div class="cdb-sub">Registra el avance o termínala.</div></div>'
                                if block else '<span class="cd late">⏱ Sin fin vigente <small>· registra el avance o termina</small></span>')
    if s['state'] == 'En marcha':
        done, left, finish = _run(s, at)
        if done is None:
            return ''
        if left <= 0:
            if block:
                return (COUNTDOWN_CSS + f'<div class="cdb late"><div class="cdb-top"><span>⏱ Excedida {duration_text(max(1, -left))}</span></div>'
                        f'<div class="bar"><i style="width:100%"></i></div><div class="cdb-sub">Debió terminar {when(finish, at)}</div></div>')
            return (COUNTDOWN_CSS + f'<span class="cd late">⏱ Excedida {duration_text(max(1, -left))} <span class="bar"><i style="width:100%"></i></span>'
                    f'<small>debió terminar {when(finish, at)}</small></span>')
        if block:
            return (COUNTDOWN_CSS + f'<div class="cdb"><div class="cdb-top"><span>⏱ Faltan {duration_text(max(1, left))}</span></div>'
                    f'<div class="bar"><i style="width:{done * 100:.0f}%"></i></div><div class="cdb-sub">{_pct(done).capitalize()} · termina {when(finish, at)}</div></div>')
        return (COUNTDOWN_CSS + f'<span class="cd">⏱ Faltan {duration_text(max(1, left))} <span class="bar"><i style="width:{done * 100:.0f}%"></i></span>'
                f'<small>{_pct(done)} · termina {when(finish, at)}</small></span>')
    if s['state'] == 'Reservada' and s['start']:
        until = (s['start'] - at).total_seconds() / 60
        if until < 0:
            return COUNTDOWN_CSS + f'<span class="cd miss">⏱ Inicio vencido hace {duration_text(max(1, -until))}</span>'
        return COUNTDOWN_CSS + f'<span class="cd wait">⏱ Empieza en {duration_text(max(1, until))} <small>· {when(s["start"], at)}</small></span>'
    return ''


def countdown(s, at=None, *, block=False):
    """The remaining-time counter of a slot, when there is something to count."""
    if text := countdown_html(s, at, block=block):
        st.html(text)


# Where a print stands on the calendar, said the same way in every row: (badge color, icon, background, text).
SCHEDULE = {
    'Imprimiendo': ('blue', 'autorenew', '#E5EEF8', '#2D5580'),
    'Sin fin': ('red', 'warning', '#FBE9EA', '#922F39'),
    'Inicio vencido': ('orange', 'event_busy', '#FBEEDC', '#86501A'),
    'Programada': ('green', 'event_available', '#E3F2EA', '#235E43'),
    'Sin duración': ('yellow', 'timer_off', '#FBF3D5', '#735A0B'),
    'Asignada sin hora': ('yellow', 'schedule', '#FBF3D5', '#735A0B'),
    'Sin impresora': ('gray', 'do_not_disturb_on', '#EDF1F3', '#4A5962'),
}
SCHEDULE_HELP = {
    'Imprimiendo': 'En marcha; ocupa la impresora hasta su fin estimado.',
    'Sin fin': 'En marcha sin un fin vigente: registra el avance, termínala o ajusta la duración.',
    'Inicio vencido': 'Tenía horario y no empezó: inicia o reprograma.',
    'Programada': 'Tiene impresora, inicio y duración: reserva su horario.',
    'Sin duración': 'Tiene inicio pero no duración, así que no reserva la impresora.',
    'Asignada sin hora': 'Tiene impresora pero todavía no un inicio: dale horario para reservarla.',
    'Sin impresora': 'Todavía no tiene impresora.',
}


def schedule_state(s):
    """The calendar status of a print: Programada, Asignada sin hora, Imprimiendo… None once finished."""
    job = s['job']
    if job['status'] == 'Terminado':
        return None
    if job.get('machine_id') is None:
        return 'Sin impresora'
    if s['state'] == 'En marcha':
        return 'Imprimiendo'
    if s['state'] == 'Sin fin':
        return 'Sin fin'
    if s['state'] == 'Reservada':
        return 'Inicio vencido' if s['late'] and job['status'] != 'En producción' else 'Programada'
    if s['state'] == 'Sin duración':
        return 'Sin duración'
    return 'Asignada sin hora'


def schedule_tag(s):
    """The calendar status as a badge beside the print's state."""
    if label := schedule_state(s):
        color, icon, _, _ = SCHEDULE[label]
        st.badge(label, color=color, icon=f':material/{icon}:', help=SCHEDULE_HELP[label])


def schedule_tag_html(label):
    """The same tag inside drawn agendas."""
    if not label:
        return ''
    _, _, back, text = SCHEDULE[label]
    return (f'<span title="{escape(SCHEDULE_HELP.get(label, ""))}" style="display:inline-block;margin-left:6px;padding:1px 8px;border-radius:99px;'
            f'font-size:.68rem;font-weight:700;vertical-align:1px;background:{back};color:{text}">{escape(label)}</span>')


def slot_line(s, at=None):
    """'hoy 10:00 → 20:00 · 10 h' for the interval, or what is missing to book it."""
    at = at or now()
    if s['state'] == 'Sin horario':
        return 'Sin horario · ' + (f"{duration_text(s['minutes'])} estimadas" if s['minutes'] else 'sin duración')
    if s['state'] == 'Sin duración':
        return f"Inicio {when(s['start'], at)} · sin duración, no reserva la máquina"
    if s['state'] == 'Sin fin':
        return f"En marcha desde {when(parse_end(s['job'].get('current_run_started_at')), at)} · sin fin vigente"
    text = f"{when(s['start'], at)} → {when(s['end'], at)} · {duration_text(s['minutes'] or (s['end'] - s['start']).total_seconds() / 60)}"
    if s['state'] == 'En marcha' and s['remaining'] is not None:
        text += f" · faltan {duration_text(max(1, s['remaining']))}"
    return text
