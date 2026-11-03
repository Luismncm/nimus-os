import hashlib
from datetime import timedelta
from db import connect
from services import planning, alert_inputs
from services.catalog import clean
from utils.dates import now,parse_end,timestamp

def lead_minutes():
    with connect() as conn:return conn.execute('SELECT lead_minutes FROM production_alert_settings WHERE id=1').fetchone()[0]

def settings(lead):
    if type(lead) is not int or not 1<=lead<=1440:raise ValueError('El aviso anticipado debe ser de 1 a 1440 minutos.')
    with connect(write=True) as conn:conn.execute('UPDATE production_alert_settings SET lead_minutes=? WHERE id=1',(lead,))

def resolve(identity,*,snooze_minutes=None):
    if snooze_minutes is not None and (type(snooze_minutes) is not int or not 1<=snooze_minutes<=1440):raise ValueError('Revisa el tiempo para posponer.')
    with connect(write=True) as conn:
        until=(now()+timedelta(minutes=snooze_minutes)).isoformat() if snooze_minutes else None
        conn.execute('''INSERT INTO production_alert_state(identity,status,snoozed_until,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(identity) DO UPDATE SET status=excluded.status,snoozed_until=excluded.snoozed_until,updated_at=excluded.updated_at''',
            (identity,'Pospuesto' if until else 'Visto',until,timestamp()))

def feed(snapshot,*,at=None):
    at=at or now();lead=lead_minutes();board=planning.schedule(snapshot,at=at);result=[]
    def add(kind,identity,detail,severity,record_kind,record_id,token='',score=None):
        key=hashlib.sha256(f'{kind}|{identity}|{token}'.encode()).hexdigest()
        result.append(dict(identity=key,kind=kind,detail=detail,severity=severity,record_kind=record_kind,record_id=record_id,score=score if score is not None else {'red':80,'orange':30,'gray':0}[severity]))
    for job in board['active']:
        end=parse_end(job['estimated_finish'])
        if job['status']=='En producción' and end and at<=end<=at+timedelta(minutes=lead):
            add('Por terminar',job['id'],f"{job['code']} · {job['machine_code'] or 'Sin máquina'} · fin estimado {end:%d/%m %H:%M}",'orange','Trabajo',job['id'],job['estimated_finish'])
        if job in board['late']:add('Horario vencido',job['id'],f"{job['code']} · revisa inicio, duración o avance.",'red','Trabajo',job['id'],job['estimated_finish'] or job['planned_start'])
        if job['id'] in board['conflicts']:add('Cruce de horario',job['id'],f"{job['code']} coincide con {', '.join(sorted(board['conflicts'][job['id']]))} en {job['machine_code']}.",'red','Trabajo',job['id'],job['planned_start']+str(job['plan_revision']) if job['planned_start'] else job['updated_at'])
        if job.get('latest_failure_id') and job['quantity_remaining']>0 and job.get('reprint_status') not in ('Pendiente','En curso'):
            add('Reimpresión pendiente',job['id'],f"{job['code']} · {job['quantity_remaining']} piezas buenas pendientes tras la falla.",'orange','Trabajo',job['id'],job['latest_failure_id'])
        missing=[]
        if not job['planned_start']:missing.append('inicio')
        if not job['duration_minutes']:missing.append('duración')
        if job['estimated_grams'] is None and job['process'] in ('Impresión 3D','Resina'):missing.append('gramos')
        if missing:add('Datos por completar',job['id'],f"{job['code']} · falta {', '.join(missing)}.",'gray','Trabajo',job['id'],'|'.join(missing))
        if job['status']=='Bloqueado' or job['order_blocked']:add('Producción bloqueada',job['id'],f"{job['code']} · {job['project']}.",'red','Trabajo',job['id'],str(job['status'])+str(job['order_blocked']))
    for order in snapshot['orders']:
        if order['status']=='Entregado' or order.get('commercial_cancelled'):continue
        if order['deadline']:
            due=parse_end(order['deadline']+'T23:59:59')
            ends=[parse_end(j['estimated_finish']) for j in board['active'] if j['order_id']==order['id'] and j['estimated_finish']]
            if due<at:add('Entrega vencida',order['id'],f"{order['code']} · entrega comprometida {order['deadline']}.",'red','Pedido',order['id'],order['deadline'])
            elif ends and max(ends)>due:add('Entrega en riesgo',order['id'],f"{order['code']} · el fin de impresión previsto supera la fecha de entrega.",'orange','Pedido',order['id'],str(max(ends)))
        if any(p['quantity_unassigned']>0 for i in order['items'] for p in i['parts']):add('Piezas por asignar',order['id'],f"{order['code']} tiene unidades sin trabajo de producción.",'orange','Pedido',order['id'])
    for job in snapshot['jobs']:
        if job['status']=='Terminado' and job['order_status']!='Entregado' and not job.get('commercial_cancelled') and not job.get('cost_complete'):
            add('Costeo pendiente',job['id'],f"{job['code']} · faltan sus gramos, o una falla pide revisar su consumo.",'gray','Trabajo',job['id'],job['completed_at'])
    for machine in snapshot['machines']:
        if machine['status'] in ('Mantenimiento','Fuera de servicio'):add('Equipo no operativo',machine['id'],f"{machine['code']} · {machine['status']}.",'orange','Máquina',machine['id'],machine['updated_at'])
    due_dates=alert_inputs.maintenance()
    for machine in snapshot['machines']:
        record=due_dates.get(machine['id'])
        if record and record['due_on']:
            day=parse_end(record['due_on']+'T00:00:00').date()
            if day<=at.date()+timedelta(days=3):
                add('Mantenimiento pendiente',machine['id'],f"{machine['code']} · mantenimiento previsto {record['due_on']} · {record['notes']}",
                    'red' if day<at.date() else 'orange','Máquina',machine['id'],record['due_on'])
    demand={}
    for job in board['active']:
        if job['status']!='En cola' or job['estimated_grams'] is None or not job['material']:continue
        key=clean(job['material']).casefold()
        row=demand.setdefault(key,dict(name=clean(job['material']),grams=0,tokens=[]))
        row['grams']+=job['estimated_grams'];row['tokens'].append((job['id'],job['estimated_grams']))
    stock={r['identity']:r for r in alert_inputs.readings()}
    for key in sorted(set(demand)|set(stock)):
        target=demand.get(key,dict(name=stock[key]['name'],grams=0,tokens=[])) if key in stock else demand[key]
        reading=stock.get(key)
        token=str(target['tokens'])+str((reading['available_grams'],reading['minimum_grams'])) if reading else str(target['tokens'])
        if not reading:
            add('Existencias por confirmar',key,f"{target['name']} · {target['grams']:g} g previstos en cola; falta lectura de material disponible.",'gray','Material',key,token)
        elif at-parse_end(reading['updated_at'])>timedelta(days=1) and target['grams']:
            add('Existencias por actualizar',key,f"{target['name']} · la última lectura tiene más de 24 horas. Confirma el material disponible.",'orange','Material',key,reading['updated_at'])
        elif reading['available_grams']<target['grams']:
            add('Material insuficiente',key,f"{target['name']} · disponibles {reading['available_grams']:g} g / previstos en cola {target['grams']:g} g.",'red','Material',key,token)
        elif reading['minimum_grams'] and reading['available_grams']<reading['minimum_grams']:
            add('Material bajo mínimo',key,f"{target['name']} · {reading['available_grams']:g} g disponibles; mínimo deseado {reading['minimum_grams']:g} g.",'orange','Material',key,token)
    from services import restock
    for supply in restock.rows():
        if not supply['attention']:continue
        add('Insumo en negativo' if supply['critical'] else 'Insumo en mínimo',supply['id'],
            f"{supply['name']} · {supply['variant']} · saldo neto {supply['net']} / mínimo {supply['minimum']}. Reposición sugerida: {supply['replenish']} unidades.",
            'red' if supply['critical'] else 'orange','Insumo',supply['id'],
            token=str((supply['net'],supply['minimum'],supply['committed'])),score=supply['score'])
    with connect() as conn:states={r['identity']:dict(r) for r in conn.execute('SELECT * FROM production_alert_state')}
    for row in result:
        state=states.get(row['identity'])
        row['state']='Visto' if state and state['status']=='Visto' else 'Pospuesto' if state and state['snoozed_until'] and parse_end(state['snoozed_until'])>at else 'Pendiente'
    return sorted(result,key=lambda r:(-r['score'],r['kind'],str(r['record_id'])))
