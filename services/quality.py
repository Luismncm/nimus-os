import json
from db import connect
from services import production as p,runtime,consumption,planning
from services.quotations import number
from utils.dates import timestamp

CAUSES=('Adherencia','Atasco / filamento','Corte de energía','Desplazamiento de capas','Soportes / acabado','Otro')

def failures(job_id=None):
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT f.*,j.code job_code,p.name part_name,i.order_id,o.code order_code,o.project,
            j.quantity-j.quantity_completed remaining,r.id reprint_id,r.status reprint_status
            FROM production_failures f JOIN production_jobs j ON j.id=f.job_id JOIN parts p ON p.id=j.part_id
            JOIN items i ON i.id=p.item_id JOIN orders o ON o.id=i.order_id LEFT JOIN print_reprints r ON r.failure_id=f.id
            WHERE (? IS NULL OR f.job_id=?) ORDER BY f.id DESC''',(job_id,job_id))]

def record_failure(job_id,rejected_units,cause,notes='',waste_grams=None,previously_good=False,*,request_key,expected_revision):
    p._integer(rejected_units,'Piezas rechazadas')
    cause=p._text(cause,'Causa')
    if len(cause)>250 or len(notes)>5000:raise ValueError('Acorta la causa o las notas de la falla.')
    if type(previously_good) is not bool or not request_key:raise ValueError('Abre un formulario de falla nuevo.')
    waste=float(number(waste_grams,'Gramos de merma',maximum=1000000)) if waste_grams is not None else None
    signature=json.dumps([job_id,rejected_units,cause,notes.strip(),waste,previously_good],ensure_ascii=False)
    with connect(write=True) as conn:
        prior=conn.execute('SELECT id,signature FROM production_failures WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['signature']!=signature:raise ValueError('La falla ya se guardó con otros datos. Abre otro formulario.')
            return prior['id']
        job=p._get(conn,'production_jobs',job_id)
        p._editable(conn,p._owner(conn,'production_jobs',job_id))
        if job['updated_at']!=expected_revision:raise ValueError('El trabajo cambió. Actualiza antes de registrar la falla.')
        if not job['started_at']:raise ValueError('Inicia el trabajo antes de registrar una falla de impresión.')
        available=job['quantity_completed'] if previously_good else job['quantity']-job['quantity_completed']
        if rejected_units>available:raise ValueError(f'Solo puedes rechazar hasta {available} piezas en esta opción.')
        current=consumption._get(conn,job_id)
        if waste is not None and current['grams'] is not None and current['waste_grams']+waste>current['grams']:
            raise ValueError('La merma supera el consumo real capturado. Actualiza el consumo total o revisa los gramos de merma.')
        completed=job['quantity_completed']-rejected_units if previously_good else job['quantity_completed']
        previous_plan=conn.execute('SELECT * FROM print_plans WHERE job_id=?',(job_id,)).fetchone()
        archive=dict(previous_plan) if previous_plan else {}
        archive.update(previous_expected_end=job['expected_end'],previous_started_at=job['started_at'])
        p._save_job(conn,job,quantity=job['quantity'],quantity_completed=completed,status='Pausado',machine_id=job['machine_id'],
            priority=job['priority'],expected_end='',notes=job['notes'])
        fid=conn.execute('''INSERT INTO production_failures(job_id,rejected_units,cause,notes,waste_grams,previously_good,request_key,signature,previous_plan,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',(job_id,rejected_units,cause,notes.strip(),waste,int(previously_good),request_key,signature,json.dumps(archive,ensure_ascii=False),timestamp())).lastrowid
        conn.execute('UPDATE print_plans SET planned_start=NULL,revision=revision+1,updated_at=? WHERE job_id=?',(timestamp(),job_id))
        conn.execute("UPDATE print_reprints SET status='Fallida',completed_at=? WHERE job_id=? AND status IN ('Pendiente','En curso')",(timestamp(),job_id))
        conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',
            (p._owner(conn,'production_jobs',job_id),f"Falla en {job['code']}: {rejected_units} rechazadas · {cause}",timestamp()))
        return fid

def prepare_reprint(job_id,failure_id,machine_id,data,*,request_key,expected_job_revision,expected_plan_revision):
    clean=planning.normalize(data)
    signature=json.dumps([job_id,failure_id,machine_id,clean],ensure_ascii=False,sort_keys=True)
    with connect(write=True) as conn:
        prior=conn.execute('SELECT id,signature FROM print_reprints WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['signature']!=signature:raise ValueError('Esta reimpresión ya se guardó con otros datos.')
            return prior['id']
        job=p._get(conn,'production_jobs',job_id)
        if job['updated_at']!=expected_job_revision:raise ValueError('El trabajo cambió. Actualiza antes de reimprimir.')
        if job['status']=='En producción':raise ValueError('Registra la falla o pausa la impresión antes de preparar otra.')
        if job['quantity_completed']>=job['quantity']:raise ValueError('Este lote no tiene piezas pendientes.')
        failure=conn.execute('SELECT * FROM production_failures WHERE id=? AND job_id=?',(failure_id,job_id)).fetchone()
        if not failure:raise ValueError('La falla no pertenece al trabajo.')
        if conn.execute('SELECT 1 FROM print_reprints WHERE failure_id=?',(failure_id,)).fetchone():raise ValueError('Esta falla ya tiene una reimpresión vinculada.')
        if conn.execute("SELECT 1 FROM print_reprints WHERE job_id=? AND status IN ('Pendiente','En curso')",(job_id,)).fetchone():raise ValueError('Ya existe una reimpresión pendiente para este lote.')
        previous=conn.execute('SELECT * FROM print_plans WHERE job_id=?',(job_id,)).fetchone()
        number_=conn.execute('SELECT COALESCE(MAX(number),0)+1 FROM print_reprints WHERE job_id=?',(job_id,)).fetchone()[0]
        p._save_job(conn,job,quantity=job['quantity'],quantity_completed=job['quantity_completed'],status='En cola',machine_id=machine_id,
            priority=job['priority'],expected_end='',notes=job['notes'])
        runtime.reset_run(conn,job)
        planning._write(conn,job_id,clean,expected_revision=expected_plan_revision)
        rid=conn.execute('''INSERT INTO print_reprints(job_id,failure_id,quantity,number,status,previous_plan,created_at,request_key,signature)
            VALUES(?,?,?,?,'Pendiente',?,?,?,?)''',(job_id,failure_id,job['quantity']-job['quantity_completed'],number_,failure['previous_plan'],timestamp(),request_key,signature)).lastrowid
        consumption.mark_reprint(conn,job_id)
        conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',
            (p._owner(conn,'production_jobs',job_id),f"{job['code']} · Reimpresión {number_}: {job['quantity']-job['quantity_completed']} pendientes",timestamp()))
        return rid

def annotate(conn,jobs):
    totals={r['job_id']:dict(r) for r in conn.execute('SELECT job_id,COUNT(*) failure_count,SUM(rejected_units) rejected_total,COALESCE(SUM(waste_grams),0) waste_total,MAX(id) latest_failure_id FROM production_failures GROUP BY job_id')}
    reprints={}
    for row in conn.execute('SELECT * FROM print_reprints ORDER BY id'):reprints[row['job_id']]=dict(row)
    for job in jobs:
        t=totals.get(job['id'],dict(failure_count=0,rejected_total=0,waste_total=0,latest_failure_id=None))
        r=reprints.get(job['id'])
        job.update({k:v for k,v in t.items() if k!='job_id'},reprint_number=r['number'] if r else 0,
                   reprint_status=r['status'] if r else None,latest_reprint_id=r['id'] if r else None)
