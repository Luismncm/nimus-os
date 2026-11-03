"""Accumulate real machine time across starts and pauses; legacy time stays unknown."""
from utils.dates import parse_end,now

def metrics(conn,job_id):
    row=conn.execute('SELECT * FROM production_metrics WHERE job_id=?',(job_id,)).fetchone()
    return dict(row) if row else None

def ensure(conn,job,*,fresh=False):
    conn.execute('''INSERT OR IGNORE INTO production_metrics(job_id,tracking_complete,run_complete,run_started_at)
        VALUES(?,?,?,?)''',(job['id'],int(fresh),int(fresh),job['started_at']))
    return metrics(conn,job['id'])

def transition(conn,old,status,stamp):
    # Unstarted queued edits do not create a fictional runtime record.
    if status!='En producción' and old['status']!='En producción' and not old['started_at'] and status!='Terminado':return
    m=ensure(conn,old,fresh=old['started_at'] is None and status=='En producción')
    total,run=m['total_seconds'],m['run_seconds']
    if m['active_since']:
        elapsed=max(0,(parse_end(stamp)-parse_end(m['active_since'])).total_seconds())
        total+=elapsed;run+=elapsed
    active=stamp if status=='En producción' else None
    started=m['run_started_at'] or (stamp if status=='En producción' else old['started_at'])
    conn.execute('UPDATE production_metrics SET total_seconds=?,run_seconds=?,active_since=?,run_started_at=? WHERE job_id=?',
        (total,run,active,started,old['id']))
    if status=='En producción':
        conn.execute("UPDATE print_reprints SET status='En curso',started_at=COALESCE(started_at,?) WHERE job_id=? AND status='Pendiente'",(stamp,old['id']))
    if status=='Terminado':
        conn.execute("UPDATE print_reprints SET status='Finalizada',completed_at=? WHERE job_id=? AND status IN ('Pendiente','En curso')",(stamp,old['id']))

def reset_run(conn,job):
    ensure(conn,job)
    conn.execute('UPDATE production_metrics SET run_seconds=0,active_since=NULL,run_started_at=NULL,run_complete=1 WHERE job_id=?',(job['id'],))

def elapsed(m,at=None):
    if not m:return None
    seconds=m['total_seconds']
    if m['active_since']:seconds+=max(0,((at or now())-parse_end(m['active_since'])).total_seconds())
    return seconds/60 if m['tracking_complete'] else None

def finish(m,duration,job):
    if m and m['run_complete'] and m['active_since'] and duration:
        from datetime import timedelta
        return parse_end(m['active_since'])+timedelta(seconds=max(0,duration*60-m['run_seconds']))
    return None
