"""Atomic machine reservations using [start,end) intervals and next-free-slot search."""
from datetime import datetime,timedelta
from db import connect
from utils.dates import parse_end,now
from services import runtime

def _jobs(conn,machine_id):
    return [dict(r) for r in conn.execute('''SELECT j.*,p.planned_start,p.duration_minutes,o.status order_status
        FROM production_jobs j JOIN parts part ON part.id=j.part_id JOIN items i ON i.id=part.item_id
        JOIN orders o ON o.id=i.order_id LEFT JOIN print_plans p ON p.job_id=j.id
        WHERE j.machine_id=? AND j.status<>'Terminado' AND o.status<>'Entregado'
        AND NOT EXISTS(SELECT 1 FROM order_cancellations c WHERE c.order_id=o.id) ''',(machine_id,))]

def interval(conn,job,plan=None,at=None):
    at=at or now()
    d=dict(job)
    if plan is not None:d.update(plan)
    planned=parse_end(d.get('planned_start'));duration=d.get('duration_minutes')
    manual=parse_end(d.get('expected_end'))
    m=runtime.metrics(conn,d['id'])
    if d['status']=='En producción':
        start=parse_end(m['run_started_at']) if m and m['run_started_at'] else parse_end(d.get('started_at')) or at
        end=runtime.finish(m,duration,d)
        if not end:end=start+timedelta(minutes=duration) if duration else manual
        # An overdue/live print keeps the machine occupied until its finish is corrected or it stops.
        if not end or end<=at:end=datetime.max
        return max(start,at),end
    if planned:
        end=planned+timedelta(minutes=duration) if duration else manual
        return (planned,end) if end and end>planned else None
    return None

def blocks(conn,machine_id,*,exclude=None,at=None):
    result=[]
    for job in _jobs(conn,machine_id):
        if job['id']==exclude:continue
        window=interval(conn,job,at=at)
        if window:result.append(dict(job,start=window[0],end=window[1]))
    return sorted(result,key=lambda j:j['start'])

def next_free(conn,machine_id,start,duration,*,exclude=None,at=None):
    if not duration or duration<=0:return None
    machine=conn.execute('SELECT * FROM machines WHERE id=?',(machine_id,)).fetchone()
    if not machine or machine['archived'] or machine['status'] in ('Mantenimiento','Fuera de servicio'):return None
    def ceil_minute(value):
        return value.replace(second=0,microsecond=0)+(timedelta(minutes=1) if value.second or value.microsecond else timedelta())
    candidate=ceil_minute(start)
    for block in blocks(conn,machine_id,exclude=exclude,at=at):
        try:end=candidate+timedelta(minutes=duration)
        except OverflowError:return None
        if candidate<block['end'] and end>block['start']:
            if block['end']==datetime.max:return None
            candidate=ceil_minute(block['end'])
    return candidate

def check(conn,job_id,plan=None,*,at=None):
    at=at or now()
    row=conn.execute('''SELECT j.*,p.planned_start,p.duration_minutes FROM production_jobs j
        LEFT JOIN print_plans p ON p.job_id=j.id WHERE j.id=?''',(job_id,)).fetchone()
    if not row:raise ValueError('El trabajo ya no está disponible.')
    job=dict(row)
    if plan is not None:job.update(plan)
    if job['machine_id'] is None or job['status']=='Terminado':return dict(conflicts=[],next_start=None,end=None)
    if plan is not None and job.get('planned_start') and not job.get('duration_minutes'):
        raise ValueError('Para reservar un horario en la máquina, captura la duración estimada del lote.')
    machine=conn.execute('SELECT * FROM machines WHERE id=?',(job['machine_id'],)).fetchone()
    if job.get('planned_start') and (not machine or machine['archived'] or machine['status'] in ('Mantenimiento','Fuera de servicio')):
        raise ValueError('Elige una máquina operativa antes de reservar un horario.')
    window=interval(conn,job,at=at)
    if job.get('planned_start') and window is None:
        raise ValueError('Para reservar el horario, captura duración o un fin manual posterior al inicio.')
    if not window:return dict(conflicts=[],next_start=None,end=None)
    conflicts=[b for b in blocks(conn,job['machine_id'],exclude=job_id,at=at) if window[0]<b['end'] and window[1]>b['start']]
    duration=job.get('duration_minutes') or ((window[1]-window[0]).total_seconds()/60 if window[1]!=datetime.max else None)
    free=next_free(conn,job['machine_id'],window[0],duration,exclude=job_id,at=at) if duration else None
    return dict(conflicts=conflicts,next_start=free,end=window[1],machine_code=machine['code'])

def validate(conn,job_id,plan=None,*,at=None):
    result=check(conn,job_id,plan,at=at)
    if result['conflicts']:
        codes=', '.join(j['code'] for j in result['conflicts'])
        suggestion=' Siguiente espacio: '+result['next_start'].strftime('%d/%m/%Y %H:%M')+'.' if result['next_start'] else ' Actualiza el fin del trabajo en marcha o libera el equipo.'
        raise ValueError(f"Horario ocupado en {result['machine_code']} por {codes}."+suggestion)
    return result

def first_free(job_id,machine_id,duration,*,at=None):
    """Earliest start where `duration` minutes fit on the machine, ignoring this job's own booking.

    Searching starts at the next quarter hour at least 5 minutes away: offering "now" would make the
    booking overdue as soon as it is saved, before anyone can load the printer.
    """
    at=at or now()
    earliest=(at+timedelta(minutes=5)).replace(second=0,microsecond=0)
    earliest+=timedelta(minutes=(-earliest.minute)%15)
    with connect() as conn:return next_free(conn,machine_id,earliest,duration,exclude=job_id,at=at)

def preview(job_id,data):
    from services.planning import normalize
    clean=normalize(data)
    with connect() as conn:return check(conn,job_id,clean)

def capacity(snapshot,minutes=120,*,at=None):
    at=at or now();rows=[]
    with connect() as conn:
        for machine in snapshot['machines']:
            assigned=[j for j in snapshot['jobs'] if j['machine_id']==machine['id'] and j['status']!='Terminado' and j['order_status']!='Entregado' and not j.get('commercial_cancelled')]
            free=next_free(conn,machine['id'],at,minutes,at=at)
            windows=[interval(conn,j,at=at) for j in assigned]
            rows.append(dict(machine,available_from=free.isoformat(timespec='minutes') if free else None,
                estimated_hours=sum(j.get('duration_minutes') or 0 for j in assigned)/60,
                unplanned=sum(w is None or w[1]==datetime.max for w in windows),pending_units=sum(j['quantity_remaining'] for j in assigned)))
    return rows
