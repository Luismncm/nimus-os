"""Production routes of the cloud app: the queue, machines, workshop control and development projects.

Same services as the local app (views/queue.py, machines.py, control.py, development.py). Every write
carries the revision the screen loaded, so a change made from another device is refused instead of being
overwritten; forms that create a record carry a request key, so a repeated click creates it once.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cloud import auth
from cloud.routes import write

router = APIRouter(prefix='/api')

ACTIONS = ('start', 'pause', 'finish', 'block', 'unblock')


class JobAction(BaseModel):
    action: str
    expected_revision: str


class Progress(BaseModel):
    quantity_completed: int
    expected_revision: str


class Failure(BaseModel):
    rejected_units: int
    cause: str
    notes: str = ''
    waste_grams: float | None = None
    previously_good: bool = False
    request_key: str
    expected_revision: str


class Schedule(BaseModel):
    planned_start: str | None = None
    duration_minutes: int | None = None
    estimated_grams: float | None = None
    expected_revision: int
    expected_job_revision: str


class Batch(BaseModel):
    job_ids: list[int]


class Machine(BaseModel):
    code: str
    name: str
    status: str = 'Disponible'
    notes: str = ''


class Loaded(BaseModel):
    material: str = ''


class Archive(BaseModel):
    archived: bool


class Snooze(BaseModel):
    snooze_minutes: int | None = None


class Project(BaseModel):
    name: str = ''
    goal: str = ''
    budget: float | None = None
    priority: str = 'Media'
    deadline: str | None = None


class Launch(BaseModel):
    piece: str
    quantity: int
    material: str = ''
    process: str = 'Impresión 3D'
    machine_id: int | None = None
    planned_start: str | None = None
    duration_minutes: int | None = None
    estimated_grams: float | None = None
    notes: str = ''
    request_key: str


def _iso(value):
    return value.isoformat(timespec='minutes') if value else None


def _machine_row(m, jobs, at):
    from services.timeline import availability_text, machine_timeline
    t = machine_timeline(m, jobs, at)
    current, upcoming = m.get('current_job') or {}, m.get('next_job') or {}
    return dict(id=m['id'], code=m['code'], name=m['name'], status=m['status'], notes=m.get('notes') or '',
                material=m.get('loaded_material') or '', pending_units=m.get('pending_units', 0),
                availability=availability_text(t['availability'], at) if t['availability'] else '',
                booked_minutes=round(t['booked_minutes']), unscheduled=t['unscheduled'], problems=t['problems'],
                current=dict(id=current['id'], code=current['code'], part=current['part_name']) if current else None,
                next=dict(id=upcoming['id'], code=upcoming['code'], part=upcoming['part_name']) if upcoming else None)


def _job_row(j, labels, machines, at):
    """One print as the queue card shows it: what, for whom, when, problems and what can be done now."""
    from services.assign_suggest import same_material
    from services.timeline import issues, slot, slot_line
    s = slot(j, at)
    machine = machines.get(j['machine_id'])
    loaded = (machine or {}).get('loaded_material') or ''
    dest = labels.get(j['order_id']) or {}
    closed = j['order_status'] == 'Entregado' or bool(j.get('commercial_cancelled'))
    return dict(
        id=j['id'], code=j['code'], part=j['part_name'], item=j['item_name'], process=j['process'],
        quantity=j['quantity'], completed=j['quantity_completed'], remaining=j['quantity_remaining'],
        status=j['status'], priority=j['priority'], material=j['material'] or '', notes=j['notes'] or '',
        machine_id=j['machine_id'], machine=j['machine_code'] or '', order_id=j['order_id'], order=j['order_code'],
        project=j['project'], client=j['client'] or '', revision=j['updated_at'], plan_revision=j.get('plan_revision') or 0,
        destination=dict(kind=dest.get('kind', 'Pedido'), label=dest.get('label', j['order_code'])),
        slot=dict(state=s['state'], line=slot_line(s, at), start=_iso(s['start']), end=_iso(s['end']), minutes=s['minutes']),
        issues=issues(s) if j['status'] != 'Terminado' else [],
        change_filament=bool(j['machine_id'] and j['material'] and loaded and not same_material(loaded, j['material'])),
        loaded=loaded, started=bool(j['started_at']), order_blocked=bool(j['order_blocked']), closed=closed,
        rides_on=(j.get('rides_on') or {}).get('code'), reprint=j.get('reprint_status') if j.get('reprint_number') else None,
        # Starting needs a free, available machine and an unblocked order (the service checks it again).
        can_start=not j['order_blocked'] and (machine is None or machine['status'] == 'Disponible'))


@router.get('/cola')
def queue(terminados: bool = False, user=Depends(auth.current_user)):
    """The queue: active prints in the local order (status, time, priority), machines and what needs fixing."""
    from services import sales
    from services.queries import load_snapshot
    from services.queue_board import ordered
    from services.queue_review import destinations, review
    from utils.dates import now
    at = now()
    snapshot = load_snapshot()
    labels = destinations(snapshot, sales.list_sales())
    machines = {m['id']: m for m in snapshot['all_machines']}
    active = [j for j in snapshot['jobs'] if j['status'] != 'Terminado' and j['order_status'] != 'Entregado']
    rows = ordered(active)
    if terminados:
        done = sorted((j for j in snapshot['jobs'] if j['status'] == 'Terminado'), key=lambda j: j['completed_at'] or '', reverse=True)
        rows += done[:60]
    return dict(
        now=_iso(at),
        jobs=[_job_row(j, labels, machines, at) for j in rows],
        machines=[_machine_row(m, snapshot['jobs'], at) for m in snapshot['machines']],
        review=[dict(job_id=r['job']['id'], text=r['text'], fix=r['fix'], label=r['label'], rank=r['rank']) for r in review(active)],
        causes=_causes())


def _causes():
    from services.quality import CAUSES
    return CAUSES


@router.post('/cola/{job_id}/accion')
def job_action(job_id: int, body: JobAction, user=Depends(auth.current_user)):
    from services.production import job_action as act
    if body.action not in ACTIONS:
        raise HTTPException(status_code=400, detail='Acción no válida.')
    write(act, job_id, body.action, expected_revision=body.expected_revision)
    return dict(ok=True)


@router.post('/cola/{job_id}/avance')
def job_progress(job_id: int, body: Progress, user=Depends(auth.current_user)):
    from services.production import record_progress
    write(record_progress, job_id, body.quantity_completed, expected_revision=body.expected_revision)
    return dict(ok=True)


@router.post('/cola/{job_id}/falla')
def job_failure(job_id: int, body: Failure, user=Depends(auth.current_user)):
    """A failed print: rejected pieces and their cause. The job pauses and loses its booked time, as locally."""
    from services.quality import record_failure
    failure = write(record_failure, job_id, body.rejected_units, body.cause, body.notes, body.waste_grams, body.previously_good,
                    request_key=body.request_key, expected_revision=body.expected_revision)
    return dict(ok=True, failure_id=failure)


@router.get('/cola/{job_id}/horario')
def schedule_form(job_id: int, user=Depends(auth.current_user)):
    """Start, duration and grams of a print, plus the first free slot of its machine for that duration."""
    from services import planning, resources
    from services.queries import load_snapshot
    job = next((j for j in load_snapshot()['jobs'] if j['id'] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail='El trabajo ya no existe.')
    plan = write(planning.get, job_id)
    free = None
    if job['machine_id'] and plan.get('duration_minutes'):
        free = _iso(resources.first_free(job_id, job['machine_id'], plan['duration_minutes']))
    return dict(job_id=job_id, code=job['code'], part=job['part_name'], machine=job['machine_code'] or '',
                planned_start=plan.get('planned_start'), duration_minutes=plan.get('duration_minutes'),
                estimated_grams=plan.get('estimated_grams'), revision=plan.get('revision') or 0,
                job_revision=job['updated_at'], first_free=free)


@router.post('/cola/{job_id}/horario')
def schedule_save(job_id: int, body: Schedule, user=Depends(auth.current_user)):
    """Save start, duration and grams; actual grams and rates stay as they were (Costos edits them)."""
    from services import planning
    plan = write(planning.get, job_id)
    data = {f: plan.get(f) for f in planning.FIELDS} | dict(planned_start=body.planned_start or None,
                                                            duration_minutes=body.duration_minutes, estimated_grams=body.estimated_grams)
    write(planning.save, job_id, data, expected_revision=body.expected_revision, expected_job_revision=body.expected_job_revision)
    return dict(ok=True)


@router.post('/cola/{job_id}/reprogramar')
def reschedule(job_id: int, user=Depends(auth.current_user)):
    from services.capture import reschedule_first_free
    return dict(ok=True, start=_iso(write(reschedule_first_free, job_id)))


@router.post('/cola/programar')
def schedule_batch(body: Batch, user=Depends(auth.current_user)):
    """Every print without a time to its machine's first free slot, in the order given (the queue's)."""
    from services.capture import schedule_unscheduled
    done, skipped = write(schedule_unscheduled, body.job_ids)
    return dict(scheduled=len(done), skipped=[dict(job_id=j, reason=r) for j, r in skipped])


@router.get('/maquinas')
def machines(user=Depends(auth.current_user)):
    from services.queries import load_snapshot
    from utils.dates import now
    at = now()
    snapshot = load_snapshot()
    from services.resources import capacity
    free = {r['id']: r['available_from'] for r in capacity(snapshot, 120, at=at)}
    rows = [dict(_machine_row(m, snapshot['jobs'], at), free_from=free.get(m['id'])) for m in snapshot['machines']]
    archived = [dict(id=m['id'], code=m['code'], name=m['name']) for m in snapshot['all_machines'] if m['archived']]
    from models.constants import MACHINE_STATUSES
    return dict(machines=rows, archived=archived, statuses=MACHINE_STATUSES)


@router.post('/maquinas')
def machine_create(body: Machine, user=Depends(auth.current_user)):
    from services.machines import save_machine
    return dict(ok=True, id=write(save_machine, body.code, body.name, body.status, body.notes))


@router.put('/maquinas/{machine_id}')
def machine_update(machine_id: int, body: Machine, user=Depends(auth.current_user)):
    from services.machines import save_machine
    write(save_machine, body.code, body.name, body.status, body.notes, machine_id)
    return dict(ok=True)


@router.post('/maquinas/{machine_id}/filamento')
def machine_loaded(machine_id: int, body: Loaded, user=Depends(auth.current_user)):
    from services.assign_suggest import set_loaded
    write(set_loaded, machine_id, body.material)
    return dict(ok=True)


@router.post('/maquinas/{machine_id}/archivo')
def machine_archive(machine_id: int, body: Archive, user=Depends(auth.current_user)):
    from services.machines import archive_machine
    write(archive_machine, machine_id, body.archived)
    return dict(ok=True)


@router.get('/control')
def control(minutos: int = 120, user=Depends(auth.current_user)):
    """Capacity for a block of time, failures, and the workshop's notices (pending first)."""
    from services import alerts, quality, resources
    from services.queries import load_snapshot
    if not 1 <= minutos <= 525600:
        raise HTTPException(status_code=400, detail='El bloque debe ser de 1 minuto a 365 días.')
    snapshot = load_snapshot()
    capacity = [dict(id=r['id'], code=r['code'], name=r['name'], status=r['status'], free_from=r['available_from'],
                     pending_units=r['pending_units'], unplanned=r['unplanned'], hours=round(r['estimated_hours'], 1))
                for r in resources.capacity(snapshot, minutos)]
    failures = [dict(id=f['id'], job=f['job_code'], part=f['part_name'], order=f['order_code'], order_id=f['order_id'],
                     cause=f['cause'], notes=f['notes'] or '', rejected=f['rejected_units'], waste_grams=f['waste_grams'],
                     created_at=f['created_at'], reprint=f['reprint_status'], remaining=f['remaining'])
                for f in quality.failures()[:100]]
    notices = [dict(identity=a['identity'], kind=a['kind'], detail=a['detail'], severity=a['severity'], state=a['state'],
                    record_kind=a['record_kind'], record_id=a['record_id'])
               for a in alerts.feed(snapshot)]
    return dict(minutes=minutos, capacity=capacity, failures=failures, notices=notices)


@router.post('/control/avisos/{identity}')
def notice_seen(identity: str, body: Snooze, user=Depends(auth.current_user)):
    from services import alerts
    write(alerts.resolve, identity, snooze_minutes=body.snooze_minutes)
    return dict(ok=True)


@router.get('/desarrollo')
def projects(user=Depends(auth.current_user)):
    """Development projects with their prints. Costs and budgets only for administration."""
    from services import development
    from services.queries import load_snapshot
    from services.timeline import slot, slot_line
    finances = user['role'] == 'admin'
    rows = []
    for r in development.summaries(load_snapshot()):
        order, info = r['order'], r['info']
        rows.append(dict(
            id=order['id'], code=order['code'], name=order['project'], goal=info['goal'] or '', status=info['status'],
            running=r['running'], waiting=r['waiting'], finished=r['finished'],
            grams_estimated=round(r['grams_estimated'], 1), grams_used=round(r['grams_used'], 1),
            money=dict(estimated_cents=r['estimated_cents'], real_cents=r['real_cents'], consumables_cents=r['consumables_cents'],
                       budget_cents=info['budget_cents'], budget_left=r['budget_left']) if finances else None,
            jobs=[dict(id=j['id'], code=j['code'], part=j['part_name'], material=j['material'] or '', machine=j['machine_code'] or '',
                       status=j['status'], schedule=slot_line(slot(j)) if j['status'] != 'Terminado' else 'Terminada')
                  for j in r['jobs']]))
    from models.constants import PRIORITIES, PROCESSES
    return dict(projects=rows, priorities=PRIORITIES, processes=PROCESSES)


@router.post('/desarrollo')
def project_create(body: Project, user=Depends(auth.current_user)):
    from services import development
    return dict(ok=True, id=write(development.create_project, body.name, goal=body.goal,
                                  budget=body.budget if user['role'] == 'admin' else None,
                                  priority=body.priority, deadline=body.deadline))


@router.put('/desarrollo/{order_id}')
def project_update(order_id: int, body: Project, user=Depends(auth.current_user)):
    from services import development
    budget = body.budget
    if user['role'] != 'admin':
        # The workshop never sees the budget, so its edit keeps the one stored instead of clearing it.
        from services.queries import load_snapshot
        order = next((o for o in load_snapshot()['orders'] if o['id'] == order_id and o.get('development')), None)
        stored = order['development']['budget_cents'] if order else None
        budget = None if stored is None else stored / 100
    write(development.update_project, order_id, goal=body.goal, budget=budget)
    return dict(ok=True)


@router.post('/desarrollo/{order_id}/cerrar')
def project_close(order_id: int, user=Depends(auth.current_user)):
    from services import development
    write(development.close_project, order_id)
    return dict(ok=True)


@router.post('/desarrollo/{order_id}/reabrir')
def project_reopen(order_id: int, user=Depends(auth.current_user)):
    from services import development
    write(development.reopen_project, order_id)
    return dict(ok=True)


@router.post('/desarrollo/{order_id}/impresion')
def project_print(order_id: int, body: Launch, user=Depends(auth.current_user)):
    """A prototype print: piece, job, machine and booked time together, or nothing."""
    from services import development
    job = write(development.launch_print, order_id, body.piece, body.quantity, material=body.material, process=body.process,
                machine_id=body.machine_id, planned_start=body.planned_start or None, duration_minutes=body.duration_minutes,
                estimated_grams=body.estimated_grams, notes=body.notes, request_key=body.request_key)
    return dict(ok=True, job_id=job)
