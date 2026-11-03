"""Read-only priorities for daily actions across existing operational records."""
from datetime import date, timedelta
from services.daily import daily_board
from utils.dates import now


def due_date(value):
    try: return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError: return None


def urgency(value, today=None):
    today=today or now().date()
    due=due_date(value)
    if not due: return 'Sin fecha','gray'
    if due<today: return 'Vencido','red'
    if due==today: return 'Hoy','orange'
    return f'En {(due-today).days} días','blue'


def visible(row,search,scope,*,date_field,fields,today=None):
    today=today or now().date()
    if search.casefold() not in ' '.join(str(row.get(f) or '') for f in fields).casefold(): return False
    due=due_date(row.get(date_field))
    if scope=='Vencidos y hoy': return bool(due and due<=today)
    if scope=='Próximos 7 días': return bool(due and today<=due<=today+timedelta(days=7))
    return True


def operating_board(snapshot,sales,expenses,at=None):
    at=at or now()
    today=at.date()
    daily=daily_board(snapshot,at)
    def priority(value,identity):
        d=due_date(value)
        return (0 if d and d<today else 1 if d==today else 2 if d else 3,d or date.max,identity)
    jobs=[j for j in snapshot['jobs'] if j['status']!='Terminado' and j['order_status']!='Entregado' and not j.get('commercial_cancelled')]
    jobs.sort(key=lambda j: (0 if j['status']=='En producción' else 1 if j['status']=='Pausado' else 2,
                             priority(j['deadline'],j['id'])))
    collections=[r for r in sales if r['status']=='Activa' and r['balance_cents']>0]
    payables=[r for r in expenses if r['status']=='Activo' and r['balance_cents']>0]
    collections.sort(key=lambda r:priority(r['due_on'],r['id']))
    payables.sort(key=lambda r:priority(r['due_on'],r['id']))
    return dict(daily=daily,jobs=jobs,deliveries=daily['orders'],collections=collections,payables=payables,
        to_collect=sum(r['balance_cents'] for r in collections),to_pay=sum(r['balance_cents'] for r in payables))
