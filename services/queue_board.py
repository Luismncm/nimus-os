"""Read-only grouping and timing filters for the production queue."""
from datetime import timedelta
from models.constants import PRIORITY_RANK
from utils.dates import now,parse_end

STATUS_RANK={'En producción':0,'Pausado':1,'En cola':2,'Bloqueado':3,'Terminado':4}
WINDOWS=('Todos','Hoy','Próximos 7 días','Vencidos','Sin programar')

def ordered(jobs):
    return sorted(jobs,key=lambda j:(STATUS_RANK[j['status']],j.get('planned_start') or j.get('estimated_finish') or j.get('expected_end') or '9999-12-31',PRIORITY_RANK[j['priority']],j['id']))

def timing_matches(job,window,*,at=None):
    at=at or now()
    if window=='Todos':return True
    if window=='Sin programar':return not job.get('planned_start')
    if window=='Vencidos':
        start=parse_end(job.get('planned_start'))
        end=parse_end(job.get('estimated_finish') or job.get('expected_end'))
        return job['status']!='Terminado' and bool((end and end<at) or (job['status']=='En cola' and start and start<at))
    point=parse_end(job.get('planned_start') or job.get('estimated_finish') or job.get('expected_end'))
    if not point:return False
    if window=='Hoy':return point.date()==at.date()
    return at.date()<=point.date()<=at.date()+timedelta(days=7)

def lanes(snapshot,jobs,*,machine='Todas',show_empty=False):
    by_machine={}
    for job in jobs:by_machine.setdefault(job['machine_id'],[]).append(job)
    result=[]
    def lane(row,own):
        active=[j for j in own if j['status']!='Terminado' and j['order_status']!='Entregado']
        return dict(machine=row,jobs=ordered(own),minutes=sum(j.get('duration_minutes') or 0 for j in active),
            missing_duration=sum(not j.get('duration_minutes') for j in active),pending_units=sum(j['quantity_remaining'] for j in active))
    for row in snapshot['all_machines']:
        own=by_machine.get(row['id'],[])
        if machine not in ('Todas',row['id']):continue
        if not own and (not show_empty or row['archived']):continue
        result.append(lane(row,own))
    if None in by_machine and machine in ('Todas','Sin máquina'):result.append(lane(None,by_machine[None]))
    result.sort(key=lambda entry:(0 if entry['machine'] and entry['machine']['current_job'] else 1 if entry['jobs'] else 2,
        entry['machine']['code'] if entry['machine'] else 'ZZZ'))
    return result
