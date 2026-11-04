"""Read-only time model shared by the queue and the agenda.

Every active job with a machine falls in exactly one timing state:
  En marcha        printing now; occupies the machine until its estimated finish.
  Sin fin          printing without a computable finish; blocks the machine's agenda.
  Reservada        planned start + duration; the machine is booked for that interval.
  Sin duración     planned start without duration (legacy); reserves nothing.
  Sin horario      no planned start; waits in the queue without a booked time.
Intervals come from the reservations computed in services.planning/resources.
"""
from datetime import datetime
from utils.dates import now, parse_end

STATES = ('En marcha', 'Sin fin', 'Reservada', 'Sin duración', 'Sin horario')


def duration_text(minutes):
    if not minutes:
        return 'Sin duración'
    hours, rest = divmod(int(round(minutes)), 60)
    return f"{hours} h {rest:02d} min" if hours and rest else f"{hours} h" if hours else f"{rest} min"


def when(value, at=None):
    """Short local time: 'hoy 14:00', 'mañana 09:30' or '24/10 18:00'."""
    if not value:
        return 'sin fecha'
    at = at or now()
    days = (value.date() - at.date()).days
    return (f"hoy {value:%H:%M}" if days == 0 else f"mañana {value:%H:%M}" if days == 1 else
            f"ayer {value:%H:%M}" if days == -1 else f"{value:%d/%m %H:%M}")


def slot(job, at=None):
    """Timing state, interval and problems of one job."""
    at = at or now()
    start = parse_end(job.get('reservation_start'))
    end = parse_end(job.get('reservation_end'))
    if job['status'] == 'En producción':
        state = 'Sin fin' if job.get('reservation_indefinite') or not end else 'En marcha'
    elif start and end:
        state = 'Reservada'
    elif job.get('planned_start'):
        state = 'Sin duración'
    else:
        state = 'Sin horario'
    late = bool(job.get('overdue_schedule'))
    return dict(job=job, state=state, start=start, end=end if state != 'Sin fin' else None,
                minutes=job.get('duration_minutes'), conflicts=list(job.get('schedule_conflicts') or ()),
                late=late, remaining=(end - at).total_seconds() / 60 if state == 'En marcha' and end else None)


def issues(s):
    """Plain sentences for what needs fixing in this slot, most blocking first."""
    job = s['job'];found = []
    if s['state'] == 'Sin fin':
        # resources.interval keeps a print past its finish occupying the machine until someone acts.
        found.append('Ya pasó su fin estimado y sigue ocupando la máquina: registra el avance, termínalo o ajusta la duración.'
                     if s['minutes'] else 'En marcha sin duración: bloquea la agenda de la máquina. Captura la duración o termina el trabajo.')
    if s['conflicts']:
        found.append('Se cruza con ' + ', '.join(s['conflicts']) + ' en la misma máquina.')
    if s['late'] and s['state'] != 'Sin fin':
        found.append('El fin estimado ya pasó: registra el avance o ajusta la duración.' if job['status'] == 'En producción'
                     else 'Su inicio programado ya pasó: reprograma o inicia el trabajo.')
    if s['state'] == 'Sin duración':
        found.append('Tiene inicio pero no duración, así que no reserva la máquina.')
    return found


def availability(slots, at=None):
    """When the machine is free, walking its booked intervals from now."""
    at = at or now()
    booked = sorted((s for s in slots if s['state'] in ('En marcha', 'Sin fin', 'Reservada')), key=lambda s: s['start'] or at)
    cursor, holder = at, None
    for s in booked:
        if s['state'] == 'Sin fin':
            return dict(kind='bloqueada', since=None, until=None, job=s['job'])
        if s['end'] <= cursor:
            continue
        if s['start'] > cursor:
            return dict(kind='libre' if cursor == at else 'ocupada', since=cursor, until=s['start'], job=s['job'] if cursor == at else holder)
        cursor, holder = s['end'], s['job']
    return dict(kind='libre' if cursor == at else 'ocupada', since=cursor, until=None, job=holder)


def availability_text(a, at=None):
    if a['kind'] == 'bloqueada':
        return f"Bloqueada · {a['job']['code']} sigue en marcha sin fin vigente"
    if a['kind'] == 'libre':
        return 'Libre ahora' + (f" · hasta {when(a['until'], at)} ({a['job']['code']})" if a['until'] else '')
    return f"Ocupada hasta {when(a['since'], at)}" + (f" · luego libre hasta {when(a['until'], at)}" if a['until'] else ' · luego libre')


def machine_timeline(machine, jobs, at=None):
    """Summary of one machine: availability, booked hours ahead and jobs still without a time."""
    at = at or now()
    own = [slot(j, at) for j in jobs if j['machine_id'] == (machine['id'] if machine else None)
           and j['status'] != 'Terminado' and j['order_status'] != 'Entregado' and not j.get('commercial_cancelled') and not j.get('rides_on')]
    booked = [s for s in own if s['state'] in ('En marcha', 'Reservada') and s['end'] and s['end'] > at]
    ahead = sum((s['end'] - max(s['start'], at)).total_seconds() / 60 for s in booked)
    unscheduled = [s for s in own if s['state'] in ('Sin horario', 'Sin duración')]
    return dict(machine=machine, slots=own, availability=availability(own, at) if machine else None,
                booked_minutes=ahead, unscheduled=len(unscheduled),
                unscheduled_minutes=sum(s['minutes'] or 0 for s in unscheduled),
                missing_duration=sum(not s['minutes'] for s in own if s['state'] != 'En marcha'),
                problems=sum(bool(issues(s)) for s in own))


def attention(jobs, at=None):
    """Active jobs with a timing problem, most blocking first."""
    at = at or now()
    rank = {'Sin fin': 0, 'En marcha': 1, 'Reservada': 1, 'Sin duración': 2, 'Sin horario': 3}
    rows = [slot(j, at) for j in jobs if j['status'] != 'Terminado' and j['order_status'] != 'Entregado' and not j.get('commercial_cancelled')]
    rows = [s for s in rows if issues(s)]
    return sorted(rows, key=lambda s: (rank[s['state']], not s['conflicts'], s['start'] or datetime.max, s['job']['id']))


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
