"""A board movement is a real, validated operation, never an arbitrary status."""
import hashlib
import json
from db import connect
from services.order_board import tracking,LANES
from services.queries import load_snapshot
from services import production
from utils.dates import timestamp

# Read from the clock while a print runs: they change on every load without anything having happened.
LIVE=('actual_minutes','actual_cost_cents','reservation_start','reservation_end','calendar_start','calendar_end','estimated_finish')


def _steady(value):
    if isinstance(value,dict): return {k:_steady(v) for k,v in value.items() if k not in LIVE}
    if isinstance(value,list): return [_steady(v) for v in value]
    return value


def token(order):
    # Derived snapshot includes quantities, revisions, requirements and reservations.
    raw=_steady({k:v for k,v in order.items() if k!='tracking'})
    return hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def _open_jobs(order):
    return [j for i in order['items'] for p in i['parts'] for j in p['jobs'] if j['status']!='Terminado']


def prototype_proposal(order,target):
    """A project moves by its prints: start one, finish them and close it, or reopen it."""
    current=tracking(order)
    if current['delivered']:
        if target=='Entregados': raise ValueError('El proyecto ya está cerrado.')
        return dict(action='reopen_project',label='Reabrir proyecto',detail='El proyecto vuelve a Desarrollo y prototipos activo: podrás lanzar e iniciar impresiones. Sus impresiones terminadas se conservan.')
    jobs=_open_jobs(order)
    # Producir also starts the next print of a project already printing.
    if target=='Producir':
        queued=[j for j in jobs if j['status'] in ('En cola','Pausado')]
        if queued:
            return dict(action='start',label='Iniciar impresión',jobs=queued,detail='Selecciona la impresión que empieza ahora en su máquina.')
        if current['lane']=='Planificar':
            return dict(action='launch',label='Lanzar impresión',detail='Este prototipo aún no tiene impresiones. Lanza la primera: pieza, filamento, máquina y hora.')
        raise ValueError('No hay impresiones en cola para iniciar. Lanza otra prueba desde la tarjeta.')
    if target==current['lane']: raise ValueError('El prototipo ya está en esta etapa.')
    if target=='Entregados':
        if blocked:=[j for j in jobs if j['status']=='Bloqueado']:
            raise ValueError(f'Hay {len(blocked)} impresión(es) bloqueada(s). Desbloquéalas en la cola antes de cerrar.')
        started=[j for j in jobs if j['status']=='En producción' or j.get('started_at') or j['quantity_completed']]
        pending=[j for j in jobs if j not in started]
        detail=(f"Se terminan {len(started)} impresión(es) en marcha con todas sus piezas. " if started else '')+('Elige qué impresiones en cola sí se hicieron; las demás se descartan. ' if pending else '')+'El proyecto se cierra y pasa al histórico; puedes reabrirlo después.'
        return dict(action='close_project',label='Terminar y cerrar proyecto',started=started,pending=pending,detail=detail)
    if target=='Planificar': raise ValueError('Un prototipo con impresiones sigue en Producir. Pausa o elimina sus impresiones desde la cola si ya no se harán.')
    raise ValueError('Los prototipos no se preparan ni se entregan. Llévalo a Entregados para terminar sus impresiones y cerrar el proyecto.')


def proposal(order,target):
    if target not in (*LANES,'Entregados'): raise ValueError('Etapa no válida.')
    if order.get('development'): return prototype_proposal(order,target)
    current=tracking(order)
    if current['delivered']: raise ValueError('El pedido entregado se conserva como histórico de solo lectura.')
    if current['blocked']: raise ValueError('Resuelve el bloqueo del pedido antes de moverlo.')
    if target==current['lane']: raise ValueError('El pedido ya está en esta etapa.')
    if target=='Producir' and current['lane']=='Planificar':
        jobs=[j for i in order['items'] for p in i['parts'] for j in p['jobs'] if j['status'] in ('En cola','Pausado')]
        if not jobs: raise ValueError('Primero asigna las piezas a un trabajo desde el detalle del pedido.')
        return dict(action='start',label='Iniciar trabajo',jobs=jobs,detail='Selecciona el trabajo que empieza ahora. La producción se registra desde sus avances.')
    if target=='Salida':
        if not current['complete']: raise ValueError('Completa la fabricación y reserva todos los insumos del pedido antes de preparar la salida.')
        description='Confirmas el ensamble y revisión de todas las lámparas y la revisión final.' if any(i.get('is_origin_lamp') for i in order['items']) else 'Confirmas la revisión de todos los productos y la revisión final.'
        return dict(action='prepare',label='Confirmar preparación',detail=description+('' if order.get('fulfillment')=='Stock' else ' También confirmas empaque y salida preparada.'))
    if target=='Preparar' and current['lane']=='Salida':
        return dict(action='reopen',label='Volver a preparación',detail='La revisión final volverá a pendiente.' if order.get('fulfillment')=='Stock' else 'La salida preparada volverá a pendiente. Las piezas terminadas se conservan.')
    if target=='Entregados':
        if current['lane']!='Salida': raise ValueError('Completa producción, revisión y preparación antes de entregar.')
        return dict(action='deliver',label='Liberar a stock' if order.get('fulfillment')=='Stock' else 'Confirmar entrega',detail='El pedido pasará al histórico de solo lectura. '+('Las piezas reservadas se liberarán al almacén.' if order.get('fulfillment')=='Stock' else 'Las piezas reservadas se descontarán y se registrará su entrega.'))
    if target=='Preparar': raise ValueError('Registra las unidades buenas en los trabajos. El pedido pasará a Preparar al completar la producción.')
    raise ValueError('Este movimiento requiere editar los trabajos en el pedido. La producción registrada determina su etapa.')

def _close_project(conn,order_id,plan,finished):
    pending={j['id']:j for j in plan['pending']}
    if set(finished)-set(pending): raise ValueError('Selecciona impresiones en cola de este prototipo.')
    for job in plan['started']:production._job_action(conn,job['id'],'finish',expected_revision=job['updated_at'])
    for jid,job in pending.items():
        if jid in finished:production._job_action(conn,jid,'finish',expected_revision=job['updated_at'])
        else:
            # Never started: nothing was printed, so the booked print is dropped instead of counted.
            if any(conn.execute(f'SELECT 1 FROM {table} WHERE job_id=? LIMIT 1',(jid,)).fetchone() for table in ('job_consumption','production_failures','inventory_movements')):
                raise ValueError(f"{job['code']} ya tiene consumo o movimientos registrados: márcala como hecha.")
            from services.piece_stock import release_riders
            release_riders(conn,[jid])
            conn.execute('DELETE FROM production_jobs WHERE id=?',(jid,))
    production.refresh_order(conn,order_id)
    conn.execute("UPDATE development_projects SET status='Cerrado',closed_at=? WHERE order_id=?",(timestamp(),order_id))


def apply(order_id,target,*,expected_token,request_key,job_id=None,finished=()):
    if not isinstance(request_key,str) or not request_key or len(request_key)>100: raise ValueError('Solicitud de movimiento no válida.')
    finished=sorted({int(j) for j in finished})
    signature=json.dumps([order_id,target,expected_token,job_id]+([finished] if finished else []),ensure_ascii=False)
    with connect(write=True) as conn:
        previous=conn.execute('SELECT signature FROM board_requests WHERE request_key=?',(request_key,)).fetchone()
        if previous:
            if previous[0]!=signature: raise ValueError('La solicitud ya se usó para otro movimiento.')
            return
        order=next((o for o in load_snapshot(conn)['orders'] if o['id']==order_id),None)
        if not order: raise ValueError('El pedido ya no existe. Actualiza el tablero.')
        if token(order)!=expected_token: raise ValueError('El pedido cambió en otra ventana. Actualiza el tablero antes de moverlo.')
        plan=proposal(order,target)
        if plan['action']=='launch': raise ValueError('Lanza la impresión desde su formulario.')
        if plan['action']=='close_project': _close_project(conn,order_id,plan,finished)
        elif plan['action']=='reopen_project': conn.execute("UPDATE development_projects SET status='Activo',closed_at=NULL WHERE order_id=?",(order_id,))
        elif plan['action']=='start':
            job=next((j for j in plan['jobs'] if j['id']==job_id),None)
            if not job: raise ValueError('Selecciona un trabajo de este pedido.')
            production._job_action(conn,job_id,'start',expected_revision=job['updated_at'])
        elif plan['action']=='deliver': production._deliver_order(conn,order_id)
        else:
            stamp=timestamp()
            if plan['action']=='prepare':
                for item in order['items']:
                    if item.get('checked_at'): continue
                    conn.execute('''INSERT INTO item_tracking VALUES(?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE
                      SET checked_at=excluded.checked_at,revision=excluded.revision,updated_at=excluded.updated_at''',
                      (item['id'],item.get('label',''),stamp,item['tracking_revision']+1,stamp))
                stages=('revision',) if order.get('fulfillment')=='Stock' else ('revision','packing','dispatch')
                for stage in stages:
                    old=order['stages'][stage]
                    if old['checked_at']: continue
                    conn.execute('''INSERT INTO order_stages VALUES(?,?,?,?,?) ON CONFLICT(order_id,stage) DO UPDATE
                      SET checked_at=excluded.checked_at,revision=excluded.revision,updated_at=excluded.updated_at''',
                      (order_id,stage,stamp,old['revision']+1,stamp))
            else:
                stage='revision' if order.get('fulfillment')=='Stock' else 'dispatch'
                conn.execute('UPDATE order_stages SET checked_at=NULL,revision=revision+1,updated_at=? WHERE order_id=? AND stage=?',(stamp,order_id,stage))
        conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',
            (order_id,f"Tablero · {tracking(order)['lane']} → {target} · {plan['label']}"+(f" · JOB-{job_id:04d}" if plan['action']=='start' else f" · {len(order['items'])} partidas revisadas" if plan['action']=='prepare' else f" · {len(plan['started'])+len(finished)} terminadas · {len(plan['pending'])-len(finished)} descartadas" if plan['action']=='close_project' else ''),timestamp()))
        conn.execute('INSERT INTO board_requests VALUES(?,?,?,?)',(request_key,order_id,signature,timestamp()))
