"""Planned spending leaves the forecast atomically when captured as an expense."""
from contextlib import nullcontext
from datetime import date
from db import connect
from services import budgets,expenses,treasury,expense_control
from services.quotations import cents
from utils.dates import timestamp
from services.guards import canonical as _encode


def _key(key):
    if not isinstance(key,str) or not key.strip() or len(key)>180:raise ValueError('Abre un nuevo formulario de previsión.')
    return key


def _retry(conn,key,payload):
    row=conn.execute('SELECT * FROM spending_plan_events WHERE request_key=?',(_key(key),)).fetchone()
    if row and row['payload']!=_encode(payload):raise ValueError('Esta acción ya se guardó con otros datos. Abre un formulario nuevo.')
    return row


def _audit(conn,pid,action,payload,key):
    conn.execute('INSERT INTO spending_plan_events(plan_id,action,payload,request_key,created_at) VALUES(?,?,?,?,?)',
                 (pid,action,_encode(payload),key,timestamp()))


def _editable(conn,pid,revision):
    row=conn.execute('SELECT * FROM spending_plans WHERE id=?',(pid,)).fetchone()
    if not row or row['revision']!=revision or row['status']!='Previsto':
        raise ValueError('La previsión cambió o ya fue atendida. Actualiza antes de continuar.')
    return dict(row)


def save(month,concept,amount,*,category='',supplier='',account_id=None,due_on=None,notes='',plan_id=None,expected_revision=None,request_key):
    month=budgets.month_key(month)
    concept=expenses._text(concept,'Concepto',True);amount=cents(amount)
    if amount<=0:raise ValueError('La previsión debe ser mayor que cero.')
    category=expenses._text(category or 'Sin clasificar','Categoría');supplier=expenses._text(supplier,'Proveedor')
    notes=expenses._text(notes,'Notas')
    if due_on:
        try:due_on=date.fromisoformat(str(due_on)).isoformat()
        except ValueError:raise ValueError('Selecciona una fecha válida.') from None
        if due_on[:7]!=month:raise ValueError('La fecha prevista debe pertenecer al mes de la previsión.')
    else:due_on=None
    payload=dict(action='save',id=plan_id,month=month,concept=concept,amount_cents=amount,category=category,supplier=supplier,account_id=account_id,due_on=due_on,notes=notes)
    with connect(write=True) as conn:
        if old:=_retry(conn,request_key,payload):return old['plan_id']
        treasury.validate_account(conn,account_id);stamp=timestamp()
        values=(month,concept,amount,category,supplier,account_id,due_on,notes)
        if plan_id:
            _editable(conn,plan_id,expected_revision)
            conn.execute('''UPDATE spending_plans SET month=?,concept=?,amount_cents=?,category=?,supplier=?,account_id=?,due_on=?,notes=?,
                revision=revision+1,updated_at=? WHERE id=?''',(*values,stamp,plan_id))
        else:
            plan_id=conn.execute('''INSERT INTO spending_plans(month,concept,amount_cents,category,supplier,account_id,due_on,notes,status,request_key,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,'Previsto',?,?,?)''',(*values,request_key,stamp,stamp)).lastrowid
        _audit(conn,plan_id,'Editar' if payload['id'] else 'Crear',payload,request_key)
        return plan_id


def cancel(plan_id,*,expected_revision,request_key):
    payload=dict(action='cancel',id=plan_id)
    with connect(write=True) as conn:
        if _retry(conn,request_key,payload):return
        _editable(conn,plan_id,expected_revision)
        conn.execute("UPDATE spending_plans SET status='Cancelado',revision=revision+1,updated_at=? WHERE id=?",(timestamp(),plan_id))
        _audit(conn,plan_id,'Cancelar',payload,request_key)


def materialize(plan_id,*,expense_on,paid=False,account_id=None,method='',expected_revision,request_key):
    payload=dict(action='materialize',id=plan_id,expense_on=str(expense_on),paid=paid,account_id=account_id,method=method)
    with connect(write=True) as conn:
        if old:=_retry(conn,request_key,payload):
            return conn.execute('SELECT expense_id FROM spending_plans WHERE id=?',(old['plan_id'],)).fetchone()[0]
        row=_editable(conn,plan_id,expected_revision)
        selected=account_id if paid else row['account_id']
        if selected is not None:treasury.validate_account(conn,selected)
        eid=expense_control.register(concept=row['concept'],amount=row['amount_cents']/100,expense_on=expense_on,
            category=row['category'],supplier=row['supplier'],notes=row['notes'],due_on=row['due_on'],
            paid=paid,account_id=selected,method=method,request_key='plan:'+request_key,_conn=conn)
        conn.execute("UPDATE spending_plans SET status='Registrado',expense_id=?,revision=revision+1,updated_at=? WHERE id=?",(eid,timestamp(),plan_id))
        _audit(conn,plan_id,'Registrar gasto',payload,request_key)
        return eid


def report(month,_conn=None):
    month=budgets.month_key(month)
    with (nullcontext(_conn) if _conn is not None else connect()) as conn:
        rows=[dict(r) for r in conn.execute('''SELECT p.*,COALESCE(a.name,'Sin cuenta prevista') account_name,e.code expense_code
            FROM spending_plans p LEFT JOIN treasury_accounts a ON a.id=p.account_id LEFT JOIN expenses e ON e.id=p.expense_id
            WHERE p.month=? ORDER BY p.status,p.due_on IS NULL,p.due_on,p.id''',(month,))]
    active=[r for r in rows if r['status']=='Previsto']
    return dict(rows=rows,active=active,total_cents=sum(r['amount_cents'] for r in active))
