"""Calendar view of the queue: every machine as a row, booked prints as bars colored by state or by order.

By state, prototypes keep their violet. By order, each order takes its identity color, Colección Origen its
gold, stock its blue and prototypes their violet: the same colors as the cards and tags of the queue.
"""
from datetime import datetime, time, timedelta
import pandas as pd
import altair as alt
import streamlit as st
from services import planning
from services.timeline import issues, slot
from utils.dates import now
from views.kind_style import PALETTE as P, order_tone
from views.emoji import tag

PERIODS = {'Hoy': 0, '3 días': 2, '7 días': 6, '14 días': 13}
# Orders keep the status palette; prototypes always read as prototypes, whatever their status.
LEGEND = {'En cola': P['booked'], 'En producción': P['printing'], 'Pausado': P['paused'], 'Bloqueado': P['danger'], 'Terminado': P['muted'],
          'Prototipo': P['prototype']}


def calendar_view(snapshot, jobs, machine='Todas'):
    today = now().date()
    with st.container(horizontal=True, gap='small', vertical_alignment='bottom'):
        period = st.segmented_control('Periodo del calendario', tuple(PERIODS), default='7 días', key='queue_calendar_period', persist_state='session') or '7 días'
        paint = st.segmented_control('Color por', ('Estado', 'Pedido'), default='Estado', key='queue_calendar_color', persist_state='session',
                                     help='Estado: en cola, imprimiendo, pausado… Pedido: el color de cada pedido, Origen en dorado, stock en azul y prototipos en violeta.', format_func=tag) or 'Estado'
    start, end = today, today + timedelta(days=PERIODS[period])
    timed = planning.calendar_rows(jobs, start, end)
    if not timed:
        st.info('No hay impresiones con horario en este periodo. Usa Horario en cada línea de Operar o Por resolver para programarlas.', icon=':material/calendar_month:')
        return
    problems = {j['id'] for j in jobs if issues(slot(j))}
    rows = [m['code'] for m in snapshot['machines'] if machine in ('Todas', m['id'])]
    dests = st.session_state.get('queue_destinations', {})
    colors = dict(LEGEND)
    def owner(r):
        """Legend entry and color of a print's order, when the calendar is colored by order."""
        dest = dests.get(r['order_id'], {})
        kind = dest.get('kind') or ('Prototipo' if r.get('development') else 'Pedido')
        name = {'Prototipo': f"Prototipo · {r.get('project')}", 'Origen': f"Origen · {dest.get('code', '')}"}.get(kind) or dest.get('code') or str(r['order_id'])
        colors[name] = order_tone(r['order_id'], kind)[1]
        return name, kind
    frame = pd.DataFrame([{k: r.get(k) for k in ('code', 'machine_label', 'status', 'start', 'end', 'start_label', 'end_label', 'anchor_kind', 'part_name', 'project', 'duration_label')}
                          | dict(legend=owner(r)[0] if paint == 'Pedido' else 'Prototipo' if r.get('development') else r['status'], kind=owner(r)[1],
                                 problem='Con problema' if r['id'] in problems else 'Sin problema') for r in timed])
    shown = list(dict.fromkeys(frame['legend'])) if paint == 'Pedido' else list(LEGEND)
    frame['start'] = pd.to_datetime(frame['start'], utc=True)
    frame['end'] = pd.to_datetime(frame['end'], utc=True)
    lo = datetime.combine(start, time.min);hi = datetime.combine(end + timedelta(days=1), time.min)
    labels = list(dict.fromkeys(rows + sorted(set(frame['machine_label']) - set(rows))))
    days = (end - start).days
    # Local workshop times on a UTC scale so the browser never shifts them; dates avoid English day names.
    x = alt.X('start:T', title=None, scale=alt.Scale(type='utc', domain=[lo.isoformat() + 'Z', hi.isoformat() + 'Z']),
              axis=alt.Axis(format='%d/%m' if days else '%H:%M', tickCount='day' if days else 12, grid=True))
    y = alt.Y('machine_label:N', title=None, scale=alt.Scale(domain=labels))
    color = alt.Color('legend:N', title=None, scale=alt.Scale(domain=shown, range=[colors[k] for k in shown]), legend=alt.Legend(orient='top'))
    tooltip = [alt.Tooltip('code:N', title='Trabajo'), alt.Tooltip('part_name:N', title='Pieza'), alt.Tooltip('project:N', title='Pedido / proyecto'),
               alt.Tooltip('kind:N', title='Tipo'), alt.Tooltip('start_label:N', title='Inicio'), alt.Tooltip('end_label:N', title='Fin'),
               alt.Tooltip('duration_label:N', title='Duración'), alt.Tooltip('problem:N', title='Horario')]
    stroke = alt.condition("datum.problem=='Con problema'", alt.value(P['danger']), alt.value('transparent'))
    base = alt.Chart(frame).encode(x=x, y=y, color=color, tooltip=tooltip)
    layers = (base.transform_filter('isValid(datum.end)').mark_bar(size=22, cornerRadius=3, strokeWidth=2).encode(x2='end:T', stroke=stroke)
              + base.transform_filter('!isValid(datum.end) && datum.anchor_kind=="Inicio"').mark_point(size=110, filled=True)
              + base.transform_filter('datum.anchor_kind=="Fin manual"').mark_point(size=130, shape='triangle-up', filled=True))
    current = now()
    if lo <= current < hi:
        layers += alt.Chart(pd.DataFrame({'t': [pd.Timestamp(current.isoformat() + 'Z')]})).mark_rule(color=P['danger'], strokeDash=[4, 3]).encode(x='t:T')
    st.altair_chart(layers.properties(height=max(160, len(labels) * 48)), width='stretch',
                    alt='Calendario de impresión por máquina; prototipos en violeta y la línea discontinua marca la hora actual')
    st.caption(('Barra: horario reservado · color de cada pedido; dorado: Colección Origen; azul: stock; violeta: prototipo' if paint == 'Pedido'
                else 'Barra: horario reservado · violeta: prototipo')
               + ' · borde rojo: cruce u horario vencido · línea discontinua: ahora · círculo: inicio sin duración · triángulo: solo fin manual.')
