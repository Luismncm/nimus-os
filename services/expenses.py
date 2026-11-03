from services import treasury
"""Expense capture, payable balances and real payments with cent-exact calculations."""
import json
from datetime import date
from contextlib import nullcontext
from decimal import Decimal, ROUND_HALF_UP

from db import connect
from services.quotations import cents, money
from services.production import _code
from services.expense_catalog import ACCOUNTS, CATEGORIES, COST_TYPES, PERIODS, RECEIPTS, TAX_MODES, UNITS
from utils.dates import now, timestamp
from services.guards import fetch, past_date as _date, same_revision
from utils.csv_export import amount, csv_bytes

FIELDS = ('expense_on','due_on','concept','category','subtype','cost_type','unit','supplier','account',
          'tax_mode','subtotal_cents','tax_cents','total_cents','receipt_type','receipt_ref','notes','order_id')


def _text(value,label,required=False):
    value=str(value or '').strip()
    if required and not value: raise ValueError(f'Completa {label}.')
    if len(value)>5000: raise ValueError(f'{label}: el texto es demasiado largo.')
    return value


def defaults():
    return dict(expense_on=now().date().isoformat(),due_on='',concept='',category=next(iter(CATEGORIES)),subtype='',
                cost_type='Variable',unit='NIMUS',supplier='',account=ACCOUNTS[0],tax_mode='Sin desglose',
                amount=0.0,tax=0.0,receipt_type='Pendiente',receipt_ref='',notes='',order_id=None)


def amounts(mode,amount,tax=0):
    if mode not in TAX_MODES: raise ValueError('Selecciona cómo se captura el importe.')
    value=cents(amount)
    if mode=='Sin desglose': subtotal,iva,total=None,None,value
    elif mode=='Subtotal + IVA 16%':
        subtotal=value
        iva=int((Decimal(value)*Decimal('.16')).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        total=subtotal+iva
    elif mode=='Total con IVA 16%':
        total=value
        subtotal=int((Decimal(value)/Decimal('1.16')).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        iva=total-subtotal
    else: subtotal,iva,total=value,cents(tax),value+cents(tax)
    if total<=0: raise ValueError('El importe total debe ser mayor que cero.')
    return dict(subtotal_cents=subtotal,tax_cents=iva,total_cents=total)


def normalize(payload,*,allow_undated=False):
    d=defaults()|payload
    out={k:_text(d.get(k),k,k in ('concept','category','unit','account')) for k in
         ('concept','category','subtype','unit','supplier','account','receipt_ref','notes')}
    if out['category'] in CATEGORIES and out['subtype'] and out['subtype'] not in CATEGORIES[out['category']]:
        raise ValueError('El tipo de gasto no corresponde a la categoría. Elige una etiqueta de esa categoría.')
    for field,options in (('cost_type',COST_TYPES),('receipt_type',RECEIPTS),('tax_mode',TAX_MODES)):
        if d[field] not in options: raise ValueError(f'Revisa {field}.')
        out[field]=d[field]
    out['expense_on']='' if allow_undated and not d['expense_on'] else _date(d['expense_on'],'Fecha del gasto')
    out['due_on']=_date(d['due_on'],'Vencimiento',future=True) if d.get('due_on') else None
    if out['due_on'] and out['due_on']<out['expense_on']: raise ValueError('El vencimiento no puede ser anterior al gasto.')
    out.update(amounts(d['tax_mode'],d['amount'],d.get('tax',0)))
    oid=d.get('order_id')
    if oid is not None and (isinstance(oid,bool) or not isinstance(oid,int) or oid<=0): raise ValueError('Selecciona un pedido válido.')
    out['order_id']=oid
    return out


def editable(row):
    d={k:row[k] for k in FIELDS}
    d['amount']=(row['total_cents'] if row['tax_mode'] in ('Sin desglose','Total con IVA 16%') else row['subtotal_cents'])/100
    d['tax']=(row['tax_cents'] or 0)/100
    return d


def _get(conn, eid): return fetch(conn, 'expenses', eid, 'El gasto ya no está disponible.')


def _revision(row, expected): same_revision(row, expected, 'Este registro cambió en otra ventana. Actualiza antes de guardar.')


def _audit(conn,eid,detail):
    conn.execute('INSERT INTO expense_events(expense_id,detail,snapshot,created_at) VALUES(?,?,?,?)',
        (eid,detail,json.dumps(dict(_get(conn,eid)),ensure_ascii=False),timestamp()))


def _payment_values(amount,paid_on,account,method,reference=''):
    amount=cents(amount)
    if amount<=0: raise ValueError('El pago debe ser mayor que cero.')
    return (amount,_date(paid_on,'Fecha del pago'),_text(account,'Cuenta',True),_text(method,'Método',True),_text(reference,'Referencia'))


def _pay(conn,eid,values,key):
    pid,code=_code(conn,'expense_payments','EGR')
    conn.execute('''INSERT INTO expense_payments(id,code,expense_id,amount_cents,paid_on,account,method,reference,request_key,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',(pid,code,eid,*values,key,timestamp()))
    conn.execute('UPDATE expenses SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),eid))
    treasury.link_payment(conn,'expense',pid,treasury.named_account(conn,values[2]))
    _audit(conn,eid,f'Pago registrado {code} · {money(values[0])} MXN · {values[2]}')
    return pid


def _insert(conn,d,key,payment=None,template_id=None,occurrence=None):
    if not key: raise ValueError('Abre un nuevo formulario de gasto.')
    signature=json.dumps([d,payment,template_id,occurrence],ensure_ascii=False,sort_keys=True)
    prior=conn.execute('SELECT id,request_payload FROM expenses WHERE request_key=?',(key,)).fetchone()
    if prior:
        if prior['request_payload']!=signature: raise ValueError('Esta captura ya se guardó con otros datos. Abre un formulario nuevo.')
        return prior['id']
    eid,code=_code(conn,'expenses','GAS')
    columns=(*FIELDS,'id','code','request_key','request_payload','template_id','occurrence','created_at','updated_at')
    values=(*[d[k] for k in FIELDS],eid,code,key,signature,template_id,occurrence,timestamp(),timestamp())
    conn.execute(f'INSERT INTO expenses({",".join(columns)}) VALUES({",".join("?" for _ in columns)})',values)
    _audit(conn,eid,'Gasto registrado'+(f' desde costo recurrente · {occurrence}' if template_id else ''))
    if payment: _pay(conn,eid,payment,key+':payment')
    return eid


def create(payload,*,request_key,payment=None):
    d=normalize(payload)
    values=_payment_values(**payment) if payment else None
    with connect(write=True) as conn: return _insert(conn,d,request_key,values)


def update(eid,payload,*,expected_revision):
    with connect(write=True) as conn:
        row=_get(conn,eid)
        _revision(row,expected_revision)
        if row['status']!='Activo': raise ValueError('El gasto está cancelado y conserva su historial.')
        d=normalize(payload,allow_undated=not bool(row['expense_on']))
        conn.execute(f'UPDATE expenses SET {",".join(k+"=?" for k in FIELDS)},revision=revision+1,updated_at=? WHERE id=?',
            (*[d[k] for k in FIELDS],timestamp(),eid))
        from services.reconciliation import _sync_partner
        _sync_partner(conn,eid)
        _audit(conn,eid,'Gasto actualizado; versión anterior conservada en historial')


def _rows(conn):
    rows=[dict(r) for r in conn.execute('''SELECT e.*,o.code order_code,
        COALESCE((SELECT SUM(p.amount_cents) FROM expense_payments p WHERE p.expense_id=e.id AND p.voided_at IS NULL),0)
          +COALESCE((SELECT amount_cents FROM partner_expense_settlements WHERE expense_id=e.id),0) paid_cents,
        (EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id)
          OR EXISTS(SELECT 1 FROM partner_expense_settlements WHERE expense_id=e.id)) money_locked
        FROM expenses e LEFT JOIN orders o ON o.id=e.order_id ORDER BY e.expense_on DESC,e.id DESC''')]
    for r in rows:
        r['balance_cents']=r['total_cents']-r['paid_cents']
        r['payment_status']='Cancelado' if r['status']=='Cancelado' else 'Pagado' if not r['balance_cents'] else 'Pago parcial' if r['paid_cents'] else 'Por pagar'
        r['overdue']=bool(r['status']=='Activo' and r['balance_cents'] and r['due_on'] and r['due_on']<now().date().isoformat())
        r['control']='Comprobante pendiente' if r['receipt_type']=='Pendiente' else 'Revisar desglose IVA' if r['receipt_type']=='Factura' and r['tax_mode']=='Sin desglose' else 'Completo'
    return rows


def list_expenses():
    with connect() as conn: return _rows(conn)


def get_expense(eid):
    with connect() as conn:
        _get(conn,eid)
        row=next(r for r in _rows(conn) if r['id']==eid)
        row['payments']=[dict(p) for p in conn.execute('SELECT * FROM expense_payments WHERE expense_id=? ORDER BY id',(eid,))]
        row['events']=[dict(p) for p in conn.execute('SELECT * FROM expense_events WHERE expense_id=? ORDER BY id DESC',(eid,))]
        row['partner_settlement']=next((dict(p) for p in conn.execute('SELECT * FROM partner_expense_settlements WHERE expense_id=?',(eid,))),None)
    return row


def record_payment(eid,amount,paid_on,account,method,reference='',*,request_key,expected_revision):
    values=_payment_values(amount,paid_on,account,method,reference)
    if not request_key: raise ValueError('Abre un nuevo formulario de pago.')
    with connect(write=True) as conn:
        prior=conn.execute('SELECT * FROM expense_payments WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if (prior['expense_id'],*[prior[k] for k in ('amount_cents','paid_on','account','method','reference')]) != (eid,*values):
                raise ValueError('Este pago ya se guardó con otros datos.')
            return prior['id']
        _revision(_get(conn,eid),expected_revision)
        return _pay(conn,eid,values,request_key)


def void_payment(pid,reason):
    reason=_text(reason,'Motivo',True)
    with connect(write=True) as conn:
        row=conn.execute('SELECT * FROM expense_payments WHERE id=?',(pid,)).fetchone()
        if not row: raise ValueError('El pago no existe.')
        if row['voided_at']: return
        conn.execute('UPDATE expense_payments SET void_reason=?,voided_at=? WHERE id=?',(reason,timestamp(),pid))
        conn.execute('UPDATE expenses SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),row['expense_id']))
        _audit(conn,row['expense_id'],f"Pago anulado {row['code']} · {reason}")


def cancel(eid,reason,*,expected_revision,_conn=None):
    reason=_text(reason,'Motivo',True)
    with (nullcontext(_conn) if _conn is not None else connect(write=True)) as conn:
        row=_get(conn,eid)
        if row['status']=='Cancelado': return
        _revision(row,expected_revision)
        conn.execute("UPDATE expenses SET status='Cancelado',cancel_reason=?,revision=revision+1,updated_at=? WHERE id=?",(reason,timestamp(),eid))
        _audit(conn,eid,'Gasto cancelado · '+reason)


def saved_values(field):
    if field not in ('category','subtype','unit','supplier','account','concept'): raise ValueError('Propiedad no válida.')
    defaults_=list(CATEGORIES) if field=='category' else list(ACCOUNTS) if field=='account' else list(UNITS) if field=='unit' else [v for values in CATEGORIES.values() for v in values] if field=='subtype' else []
    with connect() as conn:
        values=[r[0] for r in conn.execute(f'SELECT DISTINCT {field} FROM expenses')]
        if field=='account': values += [r[0] for r in conn.execute('SELECT name FROM treasury_accounts WHERE active=1')]
        if field=='account': values += [r[0] for r in conn.execute('SELECT DISTINCT account FROM expense_payments')]
        values += [json.loads(r[0]).get(field,'') for r in conn.execute('SELECT payload FROM expense_templates')]
    result={}
    for value in defaults_+values:
        if value and value.strip(): result.setdefault(value.strip().casefold(),value.strip())
    return list(result.values())


def report(start,end,*,search='',category='Todas',subtype='Todos',unit='Todas',cost_type='Todos',status='Todos'):
    start,end=_date(start,'Desde',future=True),_date(end,'Hasta',future=True)
    if start>end: raise ValueError('Desde debe ser anterior o igual a Hasta.')
    with connect() as conn:
        allrows=[r for r in _rows(conn) if search.casefold() in f"{r['code']} {r['concept']} {r['supplier']} {r['receipt_ref']} {r['category']} {r['subtype']}".casefold()
            and (category=='Todas' or r['category']==category) and (subtype=='Todos' or r['subtype']==subtype)
            and (unit=='Todas' or r['unit']==unit)
            and (cost_type=='Todos' or r['cost_type']==cost_type) and (status=='Todos' or r['payment_status']==status)]
        ids={r['id'] for r in allrows if r['status']=='Activo'}
        payments=[dict(r) for r in conn.execute('SELECT * FROM expense_payments WHERE voided_at IS NULL AND paid_on BETWEEN ? AND ?',(start,end)) if r['expense_id'] in ids]
        payments += [dict(r) for r in conn.execute('''SELECT p.expense_id,p.amount_cents,p.paid_on,
            'SOC-'||printf('%04d',p.expense_id) code,e.account,'Socio / aportación' method,p.origin reference
            FROM partner_expense_settlements p JOIN expenses e ON e.id=p.expense_id
            WHERE p.paid_on BETWEEN ? AND ?''',(start,end)) if r['expense_id'] in ids]
    rows=[r for r in allrows if start<=r['expense_on']<=end]
    active=[r for r in rows if r['status']=='Activo']
    pending=[r for r in allrows if r['status']=='Activo' and r['balance_cents']>0]
    groups={}
    for r in active: groups[r['category']]=groups.get(r['category'],0)+r['total_cents']
    return dict(rows=rows,payments=payments,pending=sorted(pending,key=lambda r:(not r['overdue'],r['due_on'] or '9999',r['id'])),
        total_cents=sum(r['total_cents'] for r in active),paid_cents=sum(p['amount_cents'] for p in payments),
        balance_cents=sum(r['balance_cents'] for r in active),all_balance_cents=sum(r['balance_cents'] for r in pending),
        overdue_cents=sum(r['balance_cents'] for r in pending if r['overdue']),
        missing_receipts=sum(r['control']!='Completo' for r in active),categories=groups)


def templates():
    with connect() as conn: rows=[dict(r) for r in conn.execute('SELECT * FROM expense_templates ORDER BY active DESC,name,id')]
    for row in rows:
        row['data']=json.loads(row.pop('payload'))
        divisor=PERIODS[row['period']]
        row['total_cents']=normalize(row['data'])['total_cents']
        row['monthly_cents']=int((Decimal(row['total_cents'])/divisor).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if divisor else 0
    return rows


def save_template(name,payload,period,*,request_key,template_id=None,expected_revision=None,active=True):
    name=_text(name,'Nombre del costo',True)
    if period not in PERIODS: raise ValueError('Selecciona la periodicidad.')
    # Templates carry no obligations, payment records or original receipt/order references.
    data=defaults()|payload
    data.update(expense_on=now().date().isoformat(),due_on='',receipt_type='Pendiente',receipt_ref='',order_id=None)
    normalize(data)
    if data['cost_type']=='Desarrollo / único' and period!='Único': raise ValueError('Desarrollo / único usa periodicidad Único.')
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True)
    with connect(write=True) as conn:
        if template_id:
            old=conn.execute('SELECT * FROM expense_templates WHERE id=?',(template_id,)).fetchone()
            if not old: raise ValueError('El costo recurrente no existe.')
            _revision(old,expected_revision)
            conn.execute('UPDATE expense_templates SET name=?,payload=?,period=?,active=?,revision=revision+1,updated_at=? WHERE id=?',
                (name,encoded,period,int(active),timestamp(),template_id))
            return template_id
        if not request_key: raise ValueError('Abre un nuevo formulario de costo.')
        prior=conn.execute('SELECT * FROM expense_templates WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if (prior['name'],prior['payload'],prior['period'])!=(name,encoded,period): raise ValueError('Este costo ya se guardó con otros datos.')
            return prior['id']
        return conn.execute('INSERT INTO expense_templates(name,payload,period,active,request_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (name,encoded,period,int(active),request_key,timestamp(),timestamp())).lastrowid


def generate(template_id,expense_on,due_on,*,expected_revision,request_key):
    with connect(write=True) as conn:
        row=conn.execute('SELECT * FROM expense_templates WHERE id=?',(template_id,)).fetchone()
        if not row: raise ValueError('El costo recurrente no existe.')
        _revision(row,expected_revision)
        if not row['active']: raise ValueError('Este costo está archivado.')
        d=normalize(dict(json.loads(row['payload']),expense_on=str(expense_on),due_on=str(due_on or '')))
        dt=date.fromisoformat(d['expense_on'])
        months=PERIODS[row['period']]
        occurrence='Único' if months is None else f'{dt.year}-{1+(dt.month-1)//months:02d}/{months}m'
        prior=conn.execute('SELECT id FROM expenses WHERE template_id=? AND occurrence=?',(template_id,occurrence)).fetchone()
        if prior: raise ValueError('Ya existe un gasto de este costo en el período, incluso si fue cancelado. Ábrelo para revisarlo.')
        return _insert(conn,d,request_key,template_id=template_id,occurrence=occurrence)


def export_csv(rows):
    fields=('code','expense_on','concept','category','subtype','cost_type','unit','supplier','account','receipt_type','receipt_ref','control','payment_status','due_on')
    return csv_bytes(['Folio','Fecha','Concepto','Categoría','Tipo de gasto','Naturaleza','Unidad','Proveedor','Cuenta prevista','Comprobante','Referencia','Control','Estado','Vencimiento','Subtotal MXN','IVA MXN','Total MXN','Pagado MXN','Saldo MXN'],
        ([str(row.get(k) or '') for k in fields]+[amount(row[k]) for k in ('subtotal_cents','tax_cents','total_cents','paid_cents','balance_cents')] for row in rows))
