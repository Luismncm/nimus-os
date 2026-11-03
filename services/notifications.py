"""Read-only notification center built from current operational and financial records."""
from datetime import date
from services.attention import summarize
from services.daily import daily_board
from services.workbench import due_date
from utils.dates import now

GROUPS=('Pedidos','Cobros','Pagos','Insumos','Producción')


def center(snapshot,supplies,events,sales,expenses,*,at=None,incoming=()):
    at=at or now();today=at.date();items=[]
    def add(group,kind,identity,title,detail,label,color,score,due=None,amount=None):
        items.append(dict(group=group,record_kind=kind,record_id=identity,
            identity=f'{kind}:{identity}',title=title,detail=detail,label=label,color=color,
            score=score,due=due or date.max,amount_cents=amount))
    summary=summarize(supplies,events,limit=len(supplies)+len(events))
    for r in summary['supplies']:
        add('Insumos','Insumo',r['id'],r['name']+(' · '+r['variant'] if r['variant'] else ''),
            f"Saldo neto {r['net']} · mínimo {r['minimum']} · reponer {r['replenish']} unidades",
            'Saldo negativo' if r['critical'] else 'Reposición',
            'red' if r['critical'] else 'orange',120 if r['critical'] else 50)
    order_events={}
    for r in summary['pending']:
        if r['record_kind']=='Pedido':order_events.setdefault(r['record_id'],[]).append(r)
        else:
            add('Insumos' if r['record_kind']=='Material' else 'Producción',r['record_kind'],r['record_id'],r['kind'],r['detail'],
                r['record_kind'],r['severity'],90 if r['severity']=='red' else 50 if r['severity']=='orange' else 10)
    daily=daily_board(snapshot,at)
    reasons={r['order']['id']:list(r['reasons']) for r in daily['attention']}
    for r in daily['orders']:
        notes=reasons.get(r['id'],[])
        for event in order_events.get(r['id'],[]):
            if event['kind'] not in notes:notes.append(event['kind'])
        due=due_date(r['deadline'])
        if not notes and not due:notes=['Falta fecha de entrega']
        if not notes:continue
        if r['status']=='Listo':
            stage='Por empacar' if not r['stages']['packing']['checked_at'] else 'Por entregar'
            notes=[stage if n in ('Producción lista', 'Listo para preparar') else n for n in notes]
        color='red' if (due and due<today) or r['status']=='Bloqueado' else 'orange'
        score=100 if color=='red' else 80 if due==today else 50
        add('Pedidos','Pedido',r['id'],f"{r['code']} · {r['client']}",
            r['project']+' · '+' · '.join(notes),notes[0],color,score,due)
    for group,kind,rows,status,subject in (
        ('Cobros','Venta',sales,'Activa','client'),('Pagos','Gasto',expenses,'Activo','concept')):
        for r in rows:
            if r['status']!=status or r['balance_cents']<=0 or r.get('deleted_at') or r.get('deleted'):continue
            due=due_date(r['due_on'])
            if due and due<today:label,color,score=f'Vencido · {due:%d/%m/%Y}','red',100
            elif due==today:label,color,score='Vence hoy','orange',80
            elif due:label,color,score=f'Vence {due:%d/%m/%Y}','blue',20
            else:label,color,score='Sin fecha de '+('cobro' if group=='Cobros' else 'pago'),'gray',30
            detail=r.get('project','') if group=='Cobros' else r.get('supplier','')
            add(group,kind,r['id'],f"{r['code']} · {r[subject]}",detail,label,color,score,due,r['balance_cents'])
    for r in incoming:
        if not r['pending']:continue
        due=due_date(r['expected_on'])
        if due and due<today:label,color,score='Llegada vencida','orange',100
        elif due==today:label,color,score='Llega hoy','blue',80
        else:label,color,score='Por recibir','gray',20
        add('Pedidos','Pedido de inventario',r['id'],r['code']+' · '+r['part'],
            f"{r['pending']} por recibir · {r['supplier'] or 'Sin proveedor'} · {r['expected_on'] or 'Sin fecha prevista'}",
            label,color,score,due)
    items.sort(key=lambda r:(-r['score'],r['due'],r['identity']))
    return dict(items=items,total=len(items),priority_count=sum(r['score']>=80 for r in items),
        counts={g:sum(r['group']==g for r in items) for g in GROUPS},
        to_collect=sum(r['amount_cents'] for r in items if r['group']=='Cobros'),
        to_pay=sum(r['amount_cents'] for r in items if r['group']=='Pagos'))


def select(data,group='Todas',search='',priority=False):
    term=search.strip().casefold()
    return [r for r in data['items'] if (group=='Todas' or r['group']==group)
        and (not priority or r['score']>=80)
        and term in (r['title']+' '+r['detail']+' '+r['label']).casefold()]


def load(snapshot=None):
    """Pass the snapshot already read in this run to avoid reading production twice."""
    from services import alerts,restock,sales,expenses,inbound
    from services.queries import load_snapshot
    snapshot=snapshot if snapshot is not None else load_snapshot()
    return center(snapshot,restock.rows(),alerts.feed(snapshot),sales.list_sales(),expenses.list_expenses(),incoming=inbound.list_orders())
