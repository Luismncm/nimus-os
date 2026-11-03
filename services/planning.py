"""Local workshop schedule and cost inputs. Planning never starts production by itself."""
from datetime import datetime,timedelta,time
from decimal import Decimal,ROUND_HALF_UP
from db import connect
from services.quotations import number
from utils.dates import parse_end,now,timestamp
from utils.csv_export import amount, csv_bytes as export

FIELDS=('planned_start','duration_minutes','estimated_grams','actual_grams','material_rate_cents','machine_rate_cents')


def defaults():return dict(planned_start=None,duration_minutes=None,estimated_grams=None,actual_grams=None,material_rate_cents=None,machine_rate_cents=None,revision=0)


def normalize(data):
    try:start=parse_end(data.get('planned_start'))
    except (ValueError,TypeError):raise ValueError('Revisa la fecha y hora del inicio programado.') from None
    duration=data.get('duration_minutes')
    if duration is not None and (type(duration) is not int or duration<1 or duration>525600):
        raise ValueError('La duración debe ser de 1 minuto a 365 días.')
    grams={}
    for field,label in [('estimated_grams','Gramos estimados'),('actual_grams','Gramos reales')]:
        value=data.get(field)
        grams[field]=float(number(value,label,maximum=1000000)) if value is not None else None
    rates={}
    for field in ('material_rate_cents','machine_rate_cents'):
        value=data.get(field)
        if value is not None and (type(value) is not int or value<0 or value>1000000000):raise ValueError('Revisa las tarifas de costo.')
        rates[field]=value
    if start and duration:
        try:start+timedelta(minutes=duration)
        except OverflowError:raise ValueError('La fecha de fin supera el calendario válido.') from None
    return dict(planned_start=start.isoformat(timespec='minutes') if start else None,duration_minutes=duration,**grams,**rates)


def get(job_id):
    with connect() as conn:
        if not conn.execute('SELECT 1 FROM production_jobs WHERE id=?',(job_id,)).fetchone():raise ValueError('El trabajo ya no está disponible.')
        row=conn.execute('SELECT * FROM print_plans WHERE job_id=?',(job_id,)).fetchone()
    return dict(row) if row else dict(defaults(),job_id=job_id)


def _write(conn,job_id,data,*,expected_revision=None):
    d=normalize(data)
    from services.production import _owner,_editable
    _editable(conn,_owner(conn,'production_jobs',job_id))
    row=conn.execute('SELECT * FROM print_plans WHERE job_id=?',(job_id,)).fetchone()
    if expected_revision is not None and (row['revision'] if row else 0)!=expected_revision:
        raise ValueError('La planificación cambió en otra ventana. Actualiza antes de guardar.')
    from services.resources import validate
    validate(conn,job_id,d)
    conn.execute('''INSERT INTO print_plans(job_id,planned_start,duration_minutes,estimated_grams,actual_grams,material_rate_cents,machine_rate_cents,updated_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET planned_start=excluded.planned_start,
        duration_minutes=excluded.duration_minutes,estimated_grams=excluded.estimated_grams,actual_grams=excluded.actual_grams,
        material_rate_cents=excluded.material_rate_cents,machine_rate_cents=excluded.machine_rate_cents,
        revision=print_plans.revision+1,updated_at=excluded.updated_at''',(job_id,*[d[f] for f in FIELDS],timestamp()))


def save(job_id,data,*,expected_revision,expected_job_revision,actual_start=None):
    with connect(write=True) as conn:
        job=conn.execute('SELECT * FROM production_jobs WHERE id=?',(job_id,)).fetchone()
        if not job or job['updated_at']!=expected_job_revision:raise ValueError('El trabajo cambió. Actualiza antes de guardar.')
        if actual_start is not None:
            start=parse_end(actual_start)
            if not start or start>now():raise ValueError('El inicio real debe ser una fecha y hora transcurrida.')
            if not job['started_at']:raise ValueError('Inicia el trabajo antes de corregir su hora real.')
            if job['completed_at'] and start>parse_end(job['completed_at']):raise ValueError('El inicio real debe ser anterior al término.')
            if conn.execute("SELECT 1 FROM print_reprints WHERE job_id=? AND status='Pendiente'",(job_id,)).fetchone():
                raise ValueError('El nuevo intento todavía no se inicia. La hora real se registra al pulsar Iniciar.')
        if actual_start is not None:
            from services import runtime
            runtime.ensure(conn,job)
            conn.execute('UPDATE production_metrics SET run_started_at=?,run_complete=0,tracking_complete=0 WHERE job_id=?',(start.isoformat(timespec='minutes'),job_id))
            conn.execute('UPDATE production_jobs SET started_at=? WHERE id=?',(start.isoformat(timespec='minutes'),job_id))
        _write(conn,job_id,data,expected_revision=expected_revision)
        if actual_start is not None:
            conn.execute('UPDATE production_jobs SET started_at=?,updated_at=? WHERE id=?',(start.isoformat(timespec='minutes'),timestamp(),job_id))
        else:conn.execute('UPDATE production_jobs SET updated_at=? WHERE id=?',(timestamp(),job_id))


def costs(plan):
    def rounded(value):return int(value.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    from services.capture import DEFAULT_MATERIAL_RATE_CENTS
    grams,minutes=plan.get('estimated_grams'),plan.get('duration_minutes')
    material=plan.get('material_rate_cents') if plan.get('material_rate_cents') is not None else DEFAULT_MATERIAL_RATE_CENTS
    machine=plan.get('machine_rate_cents') or 0
    mc=rounded(Decimal(str(grams))*material/1000) if grams is not None else None
    # Without a machine rate the print costs its filament only.
    hc=0 if not machine else rounded(Decimal(minutes)*machine/60) if minutes is not None else None
    return dict(material_cost_cents=mc,machine_cost_cents=hc,estimated_cost_cents=mc+hc if mc is not None and hc is not None else None)


def annotate(conn,jobs):
    plans={r['job_id']:dict(r) for r in conn.execute('SELECT * FROM print_plans')}
    for job in jobs:
        plan=plans.get(job['id'],defaults())
        job.update({f:plan[f] for f in FIELDS},plan_revision=plan['revision'])
        job.update(costs(plan))
        start=parse_end(job['planned_start'])
        job['planned_end']=(start+timedelta(minutes=job['duration_minutes'])).isoformat(timespec='minutes') if start and job['duration_minutes'] else None
        from services import runtime
        metrics=runtime.metrics(conn,job['id'])
        actual=parse_end(metrics['run_started_at']) if metrics else parse_end(job['started_at'])
        if job['status']=='Terminado' and actual is None:actual=parse_end(job['started_at'])
        job['current_run_started_at']=actual.isoformat() if actual else None
        event_start=(parse_end(metrics['active_since']) if metrics and metrics['active_since'] else actual or start) if job['status']=='En producción' else actual or start if job['status']=='Terminado' else start
        # Completed history uses actual start and finish; planned timestamps remain available separately.
        live_end=runtime.finish(metrics,job['duration_minutes'],job) if job['status']=='En producción' else None
        end=parse_end(job['completed_at']) or live_end or (event_start+timedelta(minutes=job['duration_minutes']) if event_start and job['duration_minutes'] else parse_end(job['expected_end']))
        job.update(calendar_start=event_start.isoformat(timespec='minutes') if event_start else None,
                   calendar_end=end.isoformat(timespec='minutes') if end and event_start and end>=event_start else None,
                   estimated_finish=end.isoformat(timespec='minutes') if end and job['status']!='Terminado' else None)
        from services.resources import interval
        window=interval(conn,job)
        job.update(reservation_start=window[0].isoformat() if window else None,
            reservation_end=window[1].isoformat() if window and window[1]!=datetime.max else None,
            reservation_indefinite=bool(window and window[1]==datetime.max))


def schedule(snapshot,*,at=None):
    at=at or now()
    active=[j for j in snapshot['jobs'] if j['status']!='Terminado' and j['order_status']!='Entregado' and not j.get('commercial_cancelled')]
    windows=[]
    for job in active:
        start=parse_end(job.get('reservation_start'))
        end=parse_end(job.get('reservation_end')) or (datetime.max if job.get('reservation_indefinite') else None)
        if start and end:windows.append((job,start,end))
    windows.sort(key=lambda x:(x[1],x[0]['id']))
    planned=[j for j,s,e in windows]
    conflicts={}
    for i,(a,first,last) in enumerate(windows):
        if a['machine_id'] is None:continue
        for b,bfirst,blast in windows[i+1:]:
            if bfirst>=last:break
            if b['machine_id']==a['machine_id'] and blast>first:
                conflicts.setdefault(a['id'],set()).add(b['code']);conflicts.setdefault(b['id'],set()).add(a['code'])
    late=[j for j in active if (j['estimated_finish'] and parse_end(j['estimated_finish'])<at)
          or (j['status']=='En cola' and j['planned_start'] and parse_end(j['planned_start'])<at)]
    upcoming=sorted((j for j in active if j['status'] in ('En cola','Pausado')),
        key=lambda j:(j['planned_start'] or '9999-12-31',j['id']))
    return dict(active=active,planned=planned,unplanned=[j for j in active if not j['planned_start']],conflicts=conflicts,late=late,upcoming=upcoming)


def calendar_rows(jobs,start_date,end_date):
    start=datetime.combine(start_date,time.min);end=datetime.combine(end_date+timedelta(days=1),time.min)
    rows=[]
    for job in jobs:
        first=parse_end(job['calendar_start']);last=parse_end(job['calendar_end'])
        finish_only=False
        if not first and job['expected_end']:
            first=parse_end(job['expected_end']);last=None;finish_only=True
        if first and first<end and (last or first)>=start:
            rows.append(dict(job,start=first,end=last,machine_label=job['machine_code'] or 'Sin máquina',
                start_label='Pendiente' if finish_only else first.strftime('%d/%m/%Y %H:%M'),
                end_label=first.strftime('%d/%m/%Y %H:%M') if finish_only else last.strftime('%d/%m/%Y %H:%M') if last else 'Pendiente',
                anchor_kind='Fin manual' if finish_only else 'Inicio',
                grams_label=f"{job['estimated_grams']:g} g" if job['estimated_grams'] is not None else 'Pendiente',
                duration_label=f"{job['duration_minutes']//60} h {job['duration_minutes']%60:02d} min" if job['duration_minutes'] else 'Pendiente'))
    return rows


def csv_bytes(jobs):
    fields=('code','project','part_name','material','machine_code','status','planned_start','started_at','duration_minutes','planned_end','completed_at','estimated_grams','actual_grams','estimated_cost_cents')
    return export(['Trabajo','Proyecto','Pieza','Material','Máquina','Estado','Inicio programado','Inicio real','Duración min','Fin programado','Fin real','Gramos estimados','Gramos reales','Costo estimado MXN'],
        ([amount(job.get(k)) if k=='estimated_cost_cents' else job.get(k) for k in fields] for job in jobs))
