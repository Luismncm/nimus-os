"""Cash movements by account. Quote receipts appear once, even after conversion to sales."""
from contextlib import nullcontext
from datetime import date
from db import connect
from utils.dates import timestamp
from utils.csv_export import amount, csv_bytes as export

KINDS=('Banco','Efectivo','Pasarela','Otra')


def accounts(*,active_only=False):
    with connect() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM treasury_accounts'+(' WHERE active=1' if active_only else '')+' ORDER BY id')]


def save_account(name,kind,*,account_id=None,expected_revision=None,active=True):
    name=' '.join(str(name or '').split())
    if not name or len(name)>160: raise ValueError('Indica un nombre de cuenta de hasta 160 caracteres.')
    if kind not in KINDS: raise ValueError('Selecciona Banco, Efectivo, Pasarela u Otra.')
    with connect(write=True) as conn:
        if account_id:
            row=conn.execute('SELECT * FROM treasury_accounts WHERE id=?',(account_id,)).fetchone()
            if not row or row['revision']!=expected_revision: raise ValueError('La cuenta cambió. Actualiza antes de guardar.')
            conn.execute('UPDATE treasury_accounts SET name=?,kind=?,active=?,revision=revision+1,updated_at=? WHERE id=?',
                (name,kind,int(active),timestamp(),account_id))
            return account_id
        prior=conn.execute('SELECT * FROM treasury_accounts WHERE name=? COLLATE NOCASE',(name,)).fetchone()
        if prior:
            if prior['kind']==kind and bool(prior['active'])==bool(active): return prior['id']
            raise ValueError('Ya existe una cuenta con ese nombre. Edítala desde Cuentas.')
        return conn.execute('INSERT INTO treasury_accounts(name,kind,active,created_at,updated_at) VALUES(?,?,?,?,?)',
            (name,kind,int(active),timestamp(),timestamp())).lastrowid


def validate_account(conn,account_id):
    if account_id is None: return
    row=conn.execute('SELECT * FROM treasury_accounts WHERE id=?',(account_id,)).fetchone()
    if not row or not row['active']: raise ValueError('La cuenta no está activa. Elige otra cuenta.')


def named_account(conn,name):
    name=' '.join(str(name or '').split())
    if not name or len(name)>160: raise ValueError('Indica una cuenta de salida válida.')
    row=conn.execute('SELECT * FROM treasury_accounts WHERE name=? COLLATE NOCASE',(name,)).fetchone()
    if row:
        validate_account(conn,row['id'])
        return row['id']
    return conn.execute("INSERT INTO treasury_accounts(name,kind,created_at,updated_at) VALUES(?,'Otra',?,?)",(name,timestamp(),timestamp())).lastrowid


def link_payment(conn,source,payment_id,account_id):
    if account_id is None: return
    validate_account(conn,account_id)
    conn.execute('INSERT INTO payment_accounts(source,payment_id,account_id,created_at) VALUES(?,?,?,?)',(source,payment_id,account_id,timestamp()))


def check_retry(conn,source,payment_id,account_id):
    prior=conn.execute('SELECT account_id FROM payment_accounts WHERE source=? AND payment_id=?',(source,payment_id)).fetchone()
    if (prior['account_id'] if prior else None)!=account_id: raise ValueError('El pago ya se guardó en otra cuenta. Abre un registro nuevo.')


def payment_labels(conn,source,rows):
    labels={r['payment_id']:dict(r) for r in conn.execute('''SELECT p.payment_id,a.name account_name,a.kind account_kind
        FROM payment_accounts p JOIN treasury_accounts a ON a.id=p.account_id WHERE p.source=?''',(source,))}
    for row in rows:
        row.update({k:v for k,v in labels.get(row['id'],dict(account_name='Sin cuenta asignada',account_kind='Sin asignar')).items() if k!='payment_id'})


def assign_account(source,payment_id,account_id):
    tables={'quote':'quotation_payments','sale':'sale_payments','expense':'expense_payments'}
    if source not in tables or account_id is None: raise ValueError('Elige un movimiento y una cuenta.')
    with connect(write=True) as conn:
        row=conn.execute(f'SELECT * FROM {tables[source]} WHERE id=?',(payment_id,)).fetchone()
        if not row or row['voided_at']: raise ValueError('El pago no está vigente. Actualiza la vista.')
        prior=conn.execute('SELECT account_id FROM payment_accounts WHERE source=? AND payment_id=?',(source,payment_id)).fetchone()
        if prior:
            check_retry(conn,source,payment_id,account_id)
            return
        link_payment(conn,source,payment_id,account_id)


def ledger(start,end,*,account_id='all',kind='Todas',include_undated=False,search='',direction='Todos',category='Todas',_conn=None):
    try: start,end=date.fromisoformat(str(start)),date.fromisoformat(str(end))
    except ValueError: raise ValueError('Revisa el período de tesorería.') from None
    if start>end: raise ValueError('Desde debe ser anterior o igual a Hasta.')
    with (nullcontext(_conn) if _conn is not None else connect()) as conn:
        rows=[dict(r) for r in conn.execute('''WITH movements AS (
            SELECT 'quote' source,p.id,p.code,p.paid_on,p.amount_cents amount,1 sign,p.method,p.reference,
                q.code document,json_extract(q.payload,'$.client') party,p.concept,
                COALESCE(s.id,q.id) record_id,CASE WHEN s.id IS NULL THEN 'Cotización' ELSE 'Venta' END record_kind
                FROM quotation_payments p JOIN quotations q ON q.id=p.quote_id LEFT JOIN sales s ON s.quote_id=q.id WHERE p.voided_at IS NULL
            UNION ALL
            SELECT 'sale',p.id,p.code,p.paid_on,p.amount_cents,1,p.method,p.reference,s.code,json_extract(s.payload,'$.client'),p.concept,s.id,'Venta'
                FROM sale_payments p JOIN sales s ON s.id=p.sale_id WHERE p.voided_at IS NULL
            UNION ALL
            SELECT 'expense',p.id,p.code,p.paid_on,p.amount_cents,-1,p.method,p.reference,e.code,e.supplier,e.concept,e.id,'Gasto'
                FROM expense_payments p JOIN expenses e ON e.id=p.expense_id WHERE p.voided_at IS NULL
            UNION ALL
            SELECT 'capital',p.id,'SOC-'||printf('%04d',p.id),p.moved_on,p.amount_cents,p.sign,'Aportación de socio',COALESCE(NULLIF(p.reference,''),p.origin,''),
                'SOC-'||printf('%04d',p.id),COALESCE(NULLIF(p.partner,''),p.party),p.concept,p.id,'Socio'
                FROM capital_movements p WHERE p.sign<>0 AND p.linked_expense_id IS NULL AND p.voided_at IS NULL)
            SELECT m.*,a.id account_id,COALESCE(a.name,'Sin cuenta asignada') account_name,COALESCE(a.kind,'Sin asignar') account_kind,
                CASE WHEN m.source='capital' THEN 'Aportación de socio' ELSE COALESCE(e.category,'') END category,
                COALESCE(e.receipt_type,c.receipt,'') receipt_type,COALESCE(e.unit,'') unit
            FROM movements m LEFT JOIN payment_accounts link ON link.source=m.source AND link.payment_id=m.id
                LEFT JOIN capital_movements c ON m.source='capital' AND c.id=m.id
                LEFT JOIN treasury_accounts a ON a.id=COALESCE(c.account_id,link.account_id)
                LEFT JOIN expenses e ON m.source='expense' AND e.id=m.record_id
            WHERE m.paid_on BETWEEN ? AND ? OR (? AND COALESCE(m.paid_on,'')='')
            ORDER BY m.paid_on DESC,m.source,m.id DESC''',(start.isoformat(),end.isoformat(),int(include_undated)))]
    query=str(search or '').strip().casefold()
    if direction not in ('Todos','Entradas','Salidas'): raise ValueError('Selecciona el tipo de movimiento.')
    rows=[r for r in rows if (account_id=='all' or r['account_id']==account_id) and (kind=='Todas' or r['account_kind']==kind)
        and (direction=='Todos' or r['sign']==(1 if direction=='Entradas' else -1))
        and (category=='Todas' or r['category']==category)
        and query in ' '.join(str(r[k] or '') for k in ('code','document','party','concept','reference','category','account_name')).casefold()]
    groups={}
    for row in rows:
        group=groups.setdefault(row['account_id'],dict(account_id=row['account_id'],account=row['account_name'],kind=row['account_kind'],income=0,outflow=0,net=0))
        group['income' if row['sign']==1 else 'outflow']+=row['amount']
        group['net']+=row['amount']*row['sign']
    income=sum(r['amount'] for r in rows if r['sign']==1)
    outflow=sum(r['amount'] for r in rows if r['sign']==-1)
    return dict(rows=rows,accounts=list(groups.values()),income=income,outflow=outflow,net=income-outflow,
                unassigned=sum(r['account_id'] is None for r in rows),undated=sum(not r['paid_on'] for r in rows))


def review_expenses():
    """One review item per expense; unknown payment dates remain visible after editing the expense date."""
    from services import expenses
    with connect() as conn:
        rows=expenses._rows(conn)
        missing_dates={r[0] for r in conn.execute("SELECT expense_id FROM expense_payments WHERE voided_at IS NULL AND COALESCE(paid_on,'')='' ")}
        missing_dates.update(r[0] for r in conn.execute("SELECT expense_id FROM partner_expense_settlements WHERE COALESCE(paid_on,'')=''"))
        account_labels={}
        for p in conn.execute('''SELECT p.expense_id,a.name FROM expense_payments p
                LEFT JOIN payment_accounts pa ON pa.source='expense' AND pa.payment_id=p.id
                LEFT JOIN treasury_accounts a ON a.id=pa.account_id WHERE p.voided_at IS NULL'''):
            account_labels.setdefault(p[0],set()).add(p[1] or 'Sin cuenta asignada')
    result=[]
    for r in rows:
        if r['status']!='Activo': continue
        issues=[]
        if not r['expense_on']: issues.append('Fecha del gasto')
        if r['id'] in missing_dates: issues.append('Fecha del pago')
        if not r['category'] or r['category']=='Sin clasificar': issues.append('Categoría')
        if not r['concept'] or r['concept'].startswith('Concepto pendiente'): issues.append('Concepto')
        if r['receipt_type']=='Pendiente': issues.append('Comprobante')
        if r['receipt_type']=='Factura' and r['tax_mode']=='Sin desglose': issues.append('Desglose IVA')
        if 'Sin cuenta asignada' in account_labels.get(r['id'],set()): issues.append('Cuenta del pago')
        if issues: result.append(dict(r,issues=issues,review=' · '.join(issues),effective_account=' / '.join(sorted(account_labels.get(r['id'],{r['account']})))))
    return result


def csv_bytes(rows):
    return export(['Fecha','Folio pago','Documento','Contraparte','Concepto','Cuenta','Tipo de cuenta','Entrada MXN','Salida MXN','Método','Referencia','Categoría','Comprobante','Unidad'],
        ([r['paid_on'],r['code'],r['document'],r['party'] or '',r['concept'],r['account_name'],r['account_kind'],
          amount(r['amount']) if r['sign']==1 else '',amount(r['amount']) if r['sign']==-1 else '',r['method'],r['reference'],
          r.get('category',''),r.get('receipt_type',''),r.get('unit','')] for r in rows))
