"""Editable monthly cash plans, actual spending and explicit profitability assumptions."""
import calendar
import json
import re
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

from db import connect
from services import expenses, treasury
from services.expense_catalog import CATEGORIES
from utils.dates import timestamp

ROLES=('Operación','Costo directo','Inversión / único')
PRIORITIES=('Esencial','Ajustable','Opcional')
TAX_LABELS={None:'Sin definir',0:'Sin IVA',1600:'IVA 16%'}
HEADER_FIELDS=('receipts_cents','net_sales_cents','margin_bps','notes')
LINE_FIELDS=('category','fixed_cents','variable_cents','role','priority','tax_bps','notes')


def month_key(value):
    value=str(value)
    if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',value) or not 1<=int(value[:4])<=9999:
        raise ValueError('Selecciona un mes válido (AAAA-MM).')
    return value


def bounds(month):
    month=month_key(month)
    year,number=map(int,month.split('-'))
    return month+'-01',f'{month}-{calendar.monthrange(year,number)[1]:02d}'


def shift(month,offset):
    year,number=map(int,month_key(month).split('-'))
    year,zero_month=divmod(year*12+number-1+offset,12)
    return month_key(f'{year:04d}-{zero_month+1:02d}')


def line_defaults(category):
    role='Costo directo' if category.startswith('Producción /') else 'Inversión / único' if category=='Equipo / activos' else 'Operación'
    priority='Esencial' if category not in CATEGORIES or category in ('Personal / nómina','Instalaciones / servicios','Impuestos') else 'Ajustable'
    return dict(category=category,fixed_cents=0,variable_cents=0,role=role,priority=priority,tax_bps=None,notes='')


def _get(conn,month):
    row=conn.execute('SELECT * FROM budget_months WHERE month=?',(month,)).fetchone()
    if not row:
        return dict(month=month,revision=None,receipts_cents=None,net_sales_cents=None,margin_bps=None,notes='',lines=[])
    result=dict(row)
    result['lines']=[{k:r[k] for k in LINE_FIELDS} for r in conn.execute('SELECT * FROM budget_lines WHERE month_id=? ORDER BY id',(row['id'],))]
    return result


def get_month(month):
    with connect() as conn: return _get(conn,month_key(month))


def list_months():
    with connect() as conn: return [dict(r) for r in conn.execute('SELECT * FROM budget_months ORDER BY month DESC')]


def structure(plan):
    with connect() as conn:
        legacy=[r[0] for r in conn.execute("SELECT DISTINCT category FROM expenses WHERE status='Activo' ORDER BY category")]
    values={r['category']:r for r in plan['lines']}
    names=list(dict.fromkeys([*CATEGORIES,*legacy,*values]))
    return [line_defaults(name)|values.get(name,{}) for name in names]


def _amount(value,label,*,optional=False,maximum=100000000000):
    if optional and value is None: return None
    if type(value) is not int or not 0<=value<=maximum: raise ValueError(f'Revisa {label}; usa un importe válido sin negativos.')
    return value


def normalize(header,lines):
    d={k:header.get(k) for k in HEADER_FIELDS}
    for key in ('receipts_cents','net_sales_cents'): d[key]=_amount(d[key],key,optional=True)
    if d['margin_bps'] is not None:
        if type(d['margin_bps']) is not int or not 0<d['margin_bps']<=10000: raise ValueError('El margen debe ser mayor que 0 y hasta 100%.')
    d['notes']=str(d['notes'] or '').strip()
    if len(d['notes'])>5000: raise ValueError('Reduce las notas del mes a 5,000 caracteres.')
    clean=[]; names=set()
    for line in lines:
        row={k:line.get(k) for k in LINE_FIELDS}
        row['category']=str(row['category'] or '').strip()
        if not row['category'] or len(row['category'])>160 or row['category'] in names: raise ValueError('Cada categoría debe aparecer una sola vez y tener nombre.')
        names.add(row['category'])
        for key in ('fixed_cents','variable_cents'): row[key]=_amount(row[key],key)
        if row['role'] not in ROLES or row['priority'] not in PRIORITIES: raise ValueError('Revisa el uso y la prioridad del presupuesto.')
        if row['tax_bps'] is not None and (type(row['tax_bps']) is not int or row['tax_bps'] not in (0,1600)): raise ValueError('Define Sin IVA, IVA 16% o deja Sin definir.')
        row['notes']=str(row['notes'] or '').strip()
        if len(row['notes'])>1000: raise ValueError('Reduce las notas de cada categoría a 1,000 caracteres.')
        clean.append(row)
    if len(clean)>200: raise ValueError('El presupuesto admite hasta 200 categorías.')
    return d,sorted(clean,key=lambda r:r['category'])


def save_month(month,header,lines,*,expected_revision,request_key):
    month=month_key(month)
    d,rows=normalize(header,lines)
    signature=json.dumps(dict(month=month,**d,lines=rows),ensure_ascii=False,sort_keys=True)
    if not isinstance(request_key,str) or not request_key or len(request_key)>160: raise ValueError('Actualiza la vista antes de guardar el presupuesto.')
    with connect(write=True) as conn:
        prior=conn.execute('SELECT snapshot,revision FROM budget_events WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['snapshot']!=signature: raise ValueError('Esta captura ya se guardó con otros datos. Actualiza la vista.')
            return prior['revision']
        existing=_get(conn,month)
        if existing['revision']!=expected_revision: raise ValueError('Este presupuesto cambió en otra ventana. Recarga el mes antes de guardar.')
        stamp=timestamp()
        revision=0 if expected_revision is None else expected_revision+1
        if expected_revision is None:
            mid=conn.execute('''INSERT INTO budget_months(month,receipts_cents,net_sales_cents,margin_bps,notes,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)''',(month,*[d[k] for k in HEADER_FIELDS],stamp,stamp)).lastrowid
        else:
            mid=existing['id']
            conn.execute('''UPDATE budget_months SET receipts_cents=?,net_sales_cents=?,margin_bps=?,notes=?,revision=?,updated_at=? WHERE id=?''',
                (*[d[k] for k in HEADER_FIELDS],revision,stamp,mid))
            conn.execute('DELETE FROM budget_lines WHERE month_id=?',(mid,))
        for line in rows:
            conn.execute(f'INSERT INTO budget_lines(month_id,{",".join(LINE_FIELDS)}) VALUES({",".join("?" for _ in range(8))})',
                (mid,*[line[k] for k in LINE_FIELDS]))
        conn.execute('INSERT INTO budget_events(month_id,revision,snapshot,request_key,created_at) VALUES(?,?,?,?,?)',
            (mid,revision,signature,request_key,stamp))
        return revision


def history(month):
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT e.revision,e.snapshot,e.created_at FROM budget_events e
            JOIN budget_months m ON m.id=e.month_id WHERE m.month=? ORDER BY e.revision DESC''',(month_key(month),))]


def comparison(month):
    start,end=bounds(month); plan=get_month(month)
    ledger=treasury.ledger(start,end)
    groups={r['category']:dict(r,budget_cents=r['fixed_cents']+r['variable_cents'],paid_cents=0,registered_cents=0,partner_cents=0,has_plan=True)
            for r in plan['lines']}
    def group(category):
        return groups.setdefault(category,dict(line_defaults(category),budget_cents=0,paid_cents=0,registered_cents=0,partner_cents=0,has_plan=False))
    for row in ledger['rows']:
        if row['source']=='expense': group(row['category'])['paid_cents']+=row['amount']
    with connect() as conn:
        for row in conn.execute("SELECT category,total_cents FROM expenses WHERE status='Activo' AND expense_on BETWEEN ? AND ?",(start,end)):
            group(row['category'])['registered_cents']+=row['total_cents']
        for row in conn.execute('''SELECT e.category,p.amount_cents FROM partner_expense_settlements p
            JOIN expenses e ON e.id=p.expense_id WHERE e.status='Activo' AND p.paid_on BETWEEN ? AND ?''',(start,end)):
            group(row['category'])['partner_cents']+=row['amount_cents']
        undated=conn.execute("SELECT COUNT(*),COALESCE(SUM(amount_cents),0) FROM expense_payments WHERE voided_at IS NULL AND COALESCE(paid_on,'')='' ").fetchone()
    rows=[]
    for row in groups.values():
        row['available_cents']=row['budget_cents']-row['paid_cents']
        row['over_cents']=max(0,-row['available_cents'])
        row['state']='Sin presupuesto' if row['paid_cents'] and (not row['has_plan'] or not row['budget_cents']) else 'Excedido' if row['over_cents'] else 'Dentro del presupuesto'
        rows.append(row)
    rows.sort(key=lambda r:(-r['over_cents'],-r['paid_cents'],r['category']))
    return dict(plan=plan,rows=rows,budget_cents=sum(r['budget_cents'] for r in rows),paid_cents=sum(r['paid_cents'] for r in rows),
        receipts_cents=sum(r['amount'] for r in ledger['rows'] if r['source'] in ('sale','quote')),
        capital_cents=sum(r['amount']*r['sign'] for r in ledger['rows'] if r['source']=='capital'),
        undated_count=undated[0],undated_cents=undated[1])


def suggestion(month,source):
    """Return a draft only; nothing is persisted or generated as a real expense."""
    groups={}
    def add(category,amount,nature,tax=None):
        row=groups.setdefault(category,line_defaults(category)|{'tax_bps':tax})
        row['fixed_cents' if nature=='Fijo' else 'variable_cents']+=amount
        if row['tax_bps']!=tax: row['tax_bps']=None
    if source=='recurrentes':
        for row in expenses.templates():
            if row['active'] and row['monthly_cents'] and row['period']!='Único':
                tax=1600 if row['data']['tax_mode'] in ('Subtotal + IVA 16%','Total con IVA 16%') else None
                add(row['data']['category'],row['monthly_cents'],row['data']['cost_type'],tax)
        note='Equivalente mensual de recurrentes; adaptar al calendario de pagos y revisar antes de guardar.'
    elif source=='histórico':
        by_id={r['id']:r for r in expenses.list_expenses()}
        for payment in treasury.ledger(*bounds(month))['rows']:
            if payment['source']=='expense':
                expense=by_id[payment['record_id']]
                add(expense['category'],payment['amount'],expense['cost_type'])
        note=f'Propuesta desde pagos de {month}; revisar naturaleza, topes y partidas que no se repiten.'
    else: raise ValueError('Fuente de propuesta inválida.')
    for row in groups.values(): row['notes']=note
    return list(groups.values())


def profitability(plan,*,sales_factor=1,adjustable_cut=0):
    """Gross margin already contains recipe/direct costs. Deduct only net overhead."""
    sales=plan['net_sales_cents']; margin=plan['margin_bps']
    missing=[]
    if sales is None or sales<=0: missing.append('Meta de ventas netas sin IVA')
    if margin is None: missing.append('Margen después de costos directos')
    overhead=[r for r in plan['lines'] if r['role']=='Operación' and r['fixed_cents']+r['variable_cents']>0]
    missing += ['IVA de '+r['category'] for r in overhead if r['tax_bps'] is None]
    if missing: return dict(missing=missing)
    factor=Decimal(str(sales_factor))
    if not factor.is_finite() or not 0<=factor<=10: raise ValueError('La variación de ventas debe estar entre 0 y 1,000%.')
    cut=Decimal(str(adjustable_cut))
    if not cut.is_finite() or not 0<=cut<=1: raise ValueError('El recorte debe estar entre 0 y 100%.')
    net=lambda r,key:Decimal(r[key])/(1+Decimal(r['tax_bps'])/10000)*(1-cut if r['priority']!='Esencial' else 1)
    fixed=sum((net(r,'fixed_cents') for r in overhead),Decimal(0))
    variable=sum((net(r,'variable_cents') for r in overhead),Decimal(0))
    rate=Decimal(margin)/10000
    denominator=rate-variable/Decimal(sales)
    rounded=lambda amount:int(amount.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    threshold=int((fixed/denominator).quantize(Decimal('1'),rounding=ROUND_CEILING)) if denominator>0 else None
    return dict(missing=[],sales_cents=rounded(Decimal(sales)*factor),fixed_net_cents=rounded(fixed),
        variable_net_cents=rounded(variable*factor),profit_cents=rounded(Decimal(sales)*factor*rate-fixed-variable*factor),
        break_even_cents=threshold,contribution_bps=rounded(denominator*10000))


def forecast(month,*,count=6):
    if type(count) is not int or not 1<=count<=24: raise ValueError('Proyecta entre 1 y 24 meses.')
    result=[]; cumulative=0; complete=True
    for index in range(count):
        key=shift(month,index); plan=get_month(key); saved=plan['revision'] is not None
        fixed=sum(r['fixed_cents'] for r in plan['lines']) if saved else None
        variable=sum(r['variable_cents'] for r in plan['lines']) if saved else None
        total=fixed+variable if saved else None
        receipts=plan['receipts_cents']
        net=receipts-total if saved and receipts is not None else None
        complete=complete and net is not None
        if complete: cumulative+=net
        result.append(dict(month=key,state='Guardado' if saved else 'Sin presupuesto',receipts_cents=receipts,fixed_cents=fixed,
            variable_cents=variable,total_cents=total,net_cents=net,cumulative_cents=cumulative if complete else None))
    return result
