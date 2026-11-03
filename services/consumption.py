"""Financial consumption records, including failed attempts, independent of good-unit inventory."""
from decimal import Decimal,ROUND_HALF_UP
from db import connect
from services.quotations import number
from services import runtime
from utils.dates import timestamp

def _get(conn,job_id,at=None):
    job=conn.execute('SELECT * FROM production_jobs WHERE id=?',(job_id,)).fetchone()
    if not job:raise ValueError('El trabajo ya no está disponible.')
    plan=conn.execute('SELECT * FROM print_plans WHERE job_id=?',(job_id,)).fetchone()
    plan=dict(plan) if plan else {}
    stored=conn.execute('SELECT * FROM job_consumption WHERE job_id=?',(job_id,)).fetchone()
    # What was captured when the print was assigned is its real consumption, unless someone corrected it.
    from services.capture import DEFAULT_MATERIAL_RATE_CENTS
    grams=plan.get('actual_grams') if plan.get('actual_grams') is not None else plan.get('estimated_grams')
    row=dict(stored) if stored else dict(job_id=job_id,grams=grams,manual_minutes=None,
        material_rate_cents=plan.get('material_rate_cents'),machine_rate_cents=plan.get('machine_rate_cents'),
        needs_update=0,revision=0,updated_at=plan.get('updated_at'))
    if row['material_rate_cents'] is None:row['material_rate_cents']=DEFAULT_MATERIAL_RATE_CENTS
    row['automatic_minutes']=runtime.elapsed(runtime.metrics(conn,job_id),at)
    row['minutes']=(row['manual_minutes'] if row['manual_minutes'] is not None else row['automatic_minutes'] if stored
                    else plan.get('duration_minutes') if plan.get('duration_minutes') is not None else row['automatic_minutes'])
    waste=conn.execute('SELECT COALESCE(SUM(waste_grams),0) FROM production_failures WHERE job_id=?',(job_id,)).fetchone()[0]
    row.update(waste_grams=waste,job_revision=job['updated_at'],status=job['status'],completed_at=job['completed_at'])
    def rounded(v):return int(v.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    g,m,gr,mr=row['grams'],row['minutes'],row['material_rate_cents'],row['machine_rate_cents']
    material=rounded(Decimal(str(g))*gr/1000) if g is not None and gr is not None else None
    # Without a machine rate the print costs its filament only.
    machine=0 if not mr else rounded(Decimal(str(m))*mr/60) if m is not None else None
    # Finished prints close with the captured values; only a failure asks to review them.
    final=bool(job['status']=='Terminado' and not row['needs_update'])
    row.update(material_cost_cents=material,machine_cost_cents=machine,actual_cost_cents=material+machine if material is not None and machine is not None else None,
        finalized=final,complete=final and material is not None and machine is not None)
    return row

def get(job_id):
    with connect() as conn:return _get(conn,job_id)

def save(job_id,grams,manual_minutes,material_rate_cents,machine_rate_cents,*,expected_revision,expected_job_revision):
    g=float(number(grams,'Gramos reales',maximum=1000000)) if grams is not None else None
    m=float(number(manual_minutes,'Minutos reales',maximum=5256000)) if manual_minutes is not None else None
    for rate in (material_rate_cents,machine_rate_cents):
        if rate is not None and (type(rate) is not int or rate<0 or rate>1000000000):raise ValueError('Revisa las tarifas reales.')
    with connect(write=True) as conn:
        row=_get(conn,job_id)
        if row['revision']!=expected_revision or row['job_revision']!=expected_job_revision:raise ValueError('El trabajo cambió. Actualiza antes de guardar consumos.')
        if g is not None and g<row['waste_grams']:raise ValueError('El consumo total debe incluir los gramos de merma registrados.')
        conn.execute('''INSERT INTO job_consumption(job_id,grams,manual_minutes,material_rate_cents,machine_rate_cents,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET grams=excluded.grams,manual_minutes=excluded.manual_minutes,
            material_rate_cents=excluded.material_rate_cents,machine_rate_cents=excluded.machine_rate_cents,
            needs_update=0,revision=job_consumption.revision+1,updated_at=excluded.updated_at''',
            (job_id,g,m,material_rate_cents,machine_rate_cents,timestamp()))

def mark_reprint(conn,job_id):
    row=_get(conn,job_id)
    if row['revision']:
        conn.execute('UPDATE job_consumption SET needs_update=1,revision=revision+1 WHERE job_id=?',(job_id,))
    elif row['grams'] is not None:
        conn.execute('''INSERT INTO job_consumption(job_id,grams,material_rate_cents,machine_rate_cents,needs_update,updated_at)
            VALUES(?,?,?,?,1,?)''',(job_id,row['grams'],row['material_rate_cents'],row['machine_rate_cents'],timestamp()))

def annotate(conn,jobs):
    for job in jobs:
        row=_get(conn,job['id'])
        job.update(actual_minutes=row['minutes'],actual_consumed_grams=row['grams'],actual_cost_cents=row['actual_cost_cents'],cost_complete=row['complete'])
