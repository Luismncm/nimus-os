"""Existing account movements and reconciled balances, in integer cents.

A confirmation already includes every movement currently recorded. Only the net
change in that account's ledger after confirmation is added to its balance.
Without a confirmation, the balance is the registered account net, visibly marked
as movement based. Reconcile after external movements or historical corrections.
"""
from db import connect
from decimal import ROUND_HALF_UP
from contextlib import nullcontext
from services import treasury, budgets
from services.quotations import cents,number
from utils.dates import timestamp


def _request(key):
    if not isinstance(key,str) or not key.strip() or len(key)>200:
        raise ValueError('Actualiza el formulario antes de guardar.')
    return key


def _overview(conn):
    ledger=treasury.ledger('0001-01-01','9999-12-31',include_undated=True,_conn=conn)
    nets={r['account_id']:r['net'] for r in ledger['accounts']}
    snapshots={r['account_id']:dict(r) for r in conn.execute('''SELECT s.* FROM treasury_balance_snapshots s
        WHERE s.id=(SELECT MAX(id) FROM treasury_balance_snapshots WHERE account_id=s.account_id)''')}
    rows=[]
    for account in conn.execute('SELECT * FROM treasury_accounts WHERE active=1 ORDER BY id'):
        row=dict(account); saved=snapshots.get(row['id']); net=nets.get(row['id'],0)
        row.update(snapshot_id=saved['id'] if saved else None,ledger_net_cents=net,
            balance_cents=saved['balance_cents']+net-saved['ledger_net_cents'] if saved else net,
            confirmed_at=saved['confirmed_at'] if saved else None,
            basis='Conciliado' if saved else 'Movimientos',income_cents=next((g['income'] for g in ledger['accounts'] if g['account_id']==row['id']),0),
            outflow_cents=next((g['outflow'] for g in ledger['accounts'] if g['account_id']==row['id']),0))
        row['token']=(row['snapshot_id'],net,row['revision'])
        rows.append(row)
    missing=[r['name'] for r in rows if r['snapshot_id'] is None]
    known=sum(r['balance_cents'] for r in rows)
    complete=bool(rows) and not missing
    return dict(accounts=rows,missing=missing,complete=complete,total_cents=known if rows else None,
                confirmed_cents=sum(r['balance_cents'] for r in rows if r['snapshot_id'] is not None),
                registered_cents=sum(nets.get(r['id'],0) for r in rows),estimated=bool(missing),
                unassigned=ledger['unassigned'],undated=ledger['undated'])


def overview(_conn=None):
    with (nullcontext(_conn) if _conn is not None else connect()) as conn:return _overview(conn)


def confirm_balances(values,*,expected,request_key):
    key=_request(request_key)
    if not isinstance(values,dict) or not values or any(type(i) is not int for i in values):
        raise ValueError('Captura al menos un saldo confirmado. Usa 0 sólo si la cuenta está vacía.')
    normalized={}
    for aid,value in values.items():
        if value is None or isinstance(value,bool):raise ValueError('Captura un saldo válido en MXN.')
        normalized[aid]=int((number(value,'Saldo',minimum=-1000000000)*100).quantize(1,rounding=ROUND_HALF_UP))
    with connect(write=True) as conn:
        prior={r['account_id']:r['balance_cents'] for r in conn.execute('SELECT * FROM treasury_balance_snapshots WHERE request_key=?',(key,))}
        if prior:
            if prior!=normalized:raise ValueError('Esta confirmación ya se guardó con otros importes. Abre una nueva.')
            return
        current={r['id']:r for r in _overview(conn)['accounts']}
        for aid in normalized:
            if aid not in current or tuple(expected.get(aid,()))!=current[aid]['token']:
                raise ValueError('Una cuenta o sus movimientos cambiaron. Cierra y abre Conciliar saldos para revisar.')
        stamp=timestamp()
        for aid,amount in normalized.items():
            conn.execute('''INSERT INTO treasury_balance_snapshots
                (account_id,balance_cents,ledger_net_cents,confirmed_at,request_key) VALUES(?,?,?,?,?)''',
                (aid,amount,current[aid]['ledger_net_cents'],stamp,key))


def forecast(month,_conn=None):
    budgets.bounds(month)
    with (nullcontext(_conn) if _conn is not None else connect()) as conn:
        row=conn.execute('SELECT * FROM expense_cash_forecasts WHERE month=? ORDER BY id DESC LIMIT 1',(month,)).fetchone()
    return dict(row) if row else dict(id=None,month=month,additional_cents=0,notes='',created_at=None)


def save_forecast(month,additional,*,notes='',expected_id=None,request_key):
    budgets.bounds(month);key=_request(request_key)
    if additional is None or isinstance(additional,bool):raise ValueError('Indica los gastos adicionales previstos, o 0.')
    amount=cents(additional)
    if amount<0:raise ValueError('Los gastos previstos no pueden ser negativos.')
    notes=str(notes or '').strip()
    if len(notes)>2000:raise ValueError('Usa una nota de hasta 2000 caracteres.')
    with connect(write=True) as conn:
        prior=conn.execute('SELECT * FROM expense_cash_forecasts WHERE request_key=?',(key,)).fetchone()
        if prior:
            if (prior['month'],prior['additional_cents'],prior['notes'])!=(month,amount,notes):
                raise ValueError('Esta proyección ya se guardó con otros datos. Abre una nueva.')
            return prior['id']
        last=conn.execute('SELECT id FROM expense_cash_forecasts WHERE month=? ORDER BY id DESC LIMIT 1',(month,)).fetchone()
        if (last['id'] if last else None)!=expected_id:raise ValueError('La proyección cambió. Cierra y abre el formulario para revisar.')
        return conn.execute('''INSERT INTO expense_cash_forecasts(month,additional_cents,notes,created_at,request_key)
            VALUES(?,?,?,?,?)''',(month,amount,notes,timestamp(),key)).lastrowid


def projection(month,*,pending_cents,pending=None,_conn=None):
    if _conn is None:
        with connect() as conn:return projection(month,pending_cents=pending_cents,pending=pending,_conn=conn)
    if type(pending_cents) is not int or pending_cents<0:raise ValueError('Revisa los gastos pendientes.')
    from services import spending_plans
    cash=overview(_conn);plan=forecast(month,_conn);scheduled=spending_plans.report(month,_conn)
    additional=plan['additional_cents']+scheduled['total_cents'];projected=pending_cents+additional
    account_rows=[dict(r,pending_cents=0,planned_cents=0) for r in cash['accounts']]
    by_id={r['id']:r for r in account_rows};by_name={r['name'].casefold():r for r in account_rows}
    allocated=0
    for row in pending or []:
        account=by_name.get(str(row['account'] or '').strip().casefold())
        if account:account['pending_cents']+=row['balance_cents'];allocated+=row['balance_cents']
    unassigned=pending_cents-allocated+plan['additional_cents']
    for row in scheduled['active']:
        account=by_id.get(row['account_id'])
        if account:account['planned_cents']+=row['amount_cents']
        else:unassigned+=row['amount_cents']
    for row in account_rows:row['after_cents']=row['balance_cents']-row['pending_cents']-row['planned_cents']
    return dict(cash=cash,forecast=plan,plans=scheduled,pending_cents=pending_cents,
                additional_cents=additional,projected_cents=projected,accounts=account_rows,unassigned_cents=unassigned,
                after_cents=cash['total_cents']-projected if cash['total_cents'] is not None else None)


def workspace(month):
    """One SQLite read transaction for cash, bills and forecasts on every page."""
    from services import expense_control
    with connect() as conn:
        report=expense_control.report(month,_conn=conn)
        result=projection(month,pending_cents=report['pending_cents'],pending=report['pending'],_conn=conn)
    return report,result
