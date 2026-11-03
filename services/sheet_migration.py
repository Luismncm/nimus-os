"""Import observed source rows atomically, without guessing dates or tax breakdowns."""
import hashlib
import json
from contextlib import nullcontext
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from db import connect
from services import expenses, treasury
from utils.dates import timestamp


def money_cents(value):
    if value in ('', None, '-'): return None
    return int((Decimal(str(value))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def sheet_date(value):
    if value in ('', None): return None
    if isinstance(value,(int,float)): return (date(1899,12,30)+timedelta(days=int(value))).isoformat()
    return date.fromisoformat(str(value)).isoformat()


def _claim(conn, source, sheet, number, raw):
    origin=f'{source}:{sheet}:{number}'
    data=json.dumps(raw,ensure_ascii=False,separators=(',',':'))
    digest=hashlib.sha256(data.encode()).hexdigest()
    prior=conn.execute('SELECT digest FROM sheet_import_rows WHERE origin=?',(origin,)).fetchone()
    if prior:
        if prior[0]!=digest: raise ValueError(f'{sheet}, fila {number}: cambió una fila ya importada; revisa antes de volver a migrar.')
        return origin,False
    conn.execute('INSERT INTO sheet_import_rows VALUES(?,?,?,?,?,NULL,?)',(origin,sheet,number,data,digest,timestamp()))
    return origin,True


def import_snapshot(snapshot):
    stats=dict(expenses=0,partner_expenses=0,partners=0,excluded_income=0,skipped=0,undated_expenses=0)
    source=snapshot['spreadsheet_id']
    with connect(write=True) as conn:
        names={r['name']:r['id'] for r in conn.execute('SELECT * FROM treasury_accounts')}
        def account(name):
            if not name: return None
            if name not in names: names[name]=treasury.named_account(conn,name)
            return names[name]
        for n,raw in enumerate(snapshot['sheets']['MOVIMIENTOS']['values'][1:],2):
            r=list(raw)+[None]*13
            if not any(v not in ('',None) for v in raw): continue
            origin,fresh=_claim(conn,source,'MOVIMIENTOS',n,raw)
            if not fresh: stats['skipped']+=1; continue
            total=money_cents(r[8])
            if total==0: continue  # Historical cancelled test; raw row remains in audit.
            if total is None or total<0 or r[1]!='Egreso': raise ValueError(f'MOVIMIENTOS fila {n}: importe o tipo inválido.')
            if not account(r[5]): raise ValueError(f'MOVIMIENTOS fila {n}: falta la cuenta efectiva.')
            day=sheet_date(r[0]) or ''
            sub,tax=money_cents(r[6]),money_cents(r[7])
            breakdown=sub is not None and tax is not None and sub+tax==total
            notes=f'Google Sheets · MOVIMIENTOS fila {n}. Control original: {r[12] or ""}. '+str(r[10] or '')
            if not day: notes+=' Fecha de gasto y pago pendiente de confirmar.'
            d=dict(expense_on=day,due_on=None,concept=str(r[3] or f'Concepto pendiente · fila {n}').strip(),
                category=r[2] or 'Sin clasificar',subtype=r[11] or '',cost_type='Variable',unit='NIMUS',
                supplier=r[4] or '',account=r[5],tax_mode='Desglose manual' if breakdown else 'Sin desglose',
                subtotal_cents=sub if breakdown else None,tax_cents=tax if breakdown else None,total_cents=total,
                receipt_type=r[9] or 'Pendiente',receipt_ref='',notes=notes,order_id=None)
            eid=expenses._insert(conn,d,origin,(total,day,r[5],'Histórico importado',origin))
            conn.execute('UPDATE sheet_import_rows SET expense_id=? WHERE origin=?',(eid,origin))
            stats['expenses']+=1; stats['undated_expenses']+=not bool(day)
        for n,raw in enumerate(snapshot['sheets']['SOCIOS']['values'][14:],15):
            r=list(raw)+[None]*15
            if not any(v not in ('',None) for v in raw): continue
            origin,fresh=_claim(conn,source,'SOCIOS',n,raw)
            if not fresh: stats['skipped']+=1; continue
            total=money_cents(r[7])
            if total is None or total<0: raise ValueError(f'SOCIOS fila {n}: falta el importe.')
            sign={'Entrada':1,'Salida':-1,'No impacta':0}.get(r[12])
            if sign is None: raise ValueError(f'SOCIOS fila {n}: flujo sin clasificar.')
            if sign==1:
                stats['excluded_income']+=1
                continue  # User explicitly requested expenses only; reconcile incomes later.
            aid=account(r[11]); linked=None
            if r[2]=='Compra pagada por socio':
                if r[8]!='Aportación de socio': raise ValueError(f'SOCIOS fila {n}: revisar tratamiento antes de migrar compra.')
                sub,tax=money_cents(r[5]),money_cents(r[6])
                breakdown=sub is not None and tax is not None and sub+tax==total
                day=sheet_date(r[0]) or ''
                d=dict(expense_on=day,due_on=None,concept=r[3] or f'Concepto pendiente · SOCIOS fila {n}',
                    category='Compras pagadas por socio',subtype='',cost_type='Desarrollo / único',unit='NIMUS',
                    supplier=r[4] or '',account=f'Pagado por socio · {r[1] or "Socio pendiente"}',
                    tax_mode='Desglose manual' if breakdown else 'Sin desglose',subtotal_cents=sub if breakdown else None,
                    tax_cents=tax if breakdown else None,total_cents=total,receipt_type=r[13] or 'Pendiente',receipt_ref='',
                    notes=f'Google Sheets · SOCIOS fila {n}. Compra pagada directamente por {r[1] or "socio pendiente"}; aportación, sin salida de caja/banco. '+str(r[14] or ''),order_id=None)
                linked=expenses._insert(conn,d,origin)
                conn.execute('INSERT INTO partner_expense_settlements VALUES(?,?,?,?,?,?)',(linked,r[1] or '',total,sheet_date(r[0]),origin,timestamp()))
                conn.execute('UPDATE sheet_import_rows SET expense_id=? WHERE origin=?',(linked,origin))
                expenses._audit(conn,linked,'Gasto cubierto directamente por socio; no afecta caja ni banco.')
                stats['partner_expenses']+=1
            # A reimbursement can already be the outflow in MOVIMIENTOS.
            if r[2]=='Reembolso al socio' and str(r[3] or '').upper()=='CLIMA':
                matches=conn.execute("SELECT id FROM expenses WHERE upper(concept)='DEVOLUCION CLIMA' AND total_cents=? AND request_key LIKE ?",(total,source+':MOVIMIENTOS:%')).fetchall()
                if len(matches)==1: linked=matches[0][0]; sign=0
            if sign and aid is None: raise ValueError(f'SOCIOS fila {n}: flujo con cuenta pendiente.')
            conn.execute('''INSERT INTO capital_movements(origin,moved_on,partner,movement,concept,party,treatment,
                amount_cents,subtotal_cents,tax_cents,reimbursed_cents,pending_cents,account_id,sign,
                linked_expense_id,receipt,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (origin,sheet_date(r[0]),r[1] or '',r[2] or '',r[3] or '',r[4] or '',r[8] or '',total,
                 money_cents(r[5]),money_cents(r[6]),money_cents(r[9]) or 0,money_cents(r[10]) or 0,aid,sign,linked,r[13] or '',r[14] or ''))
            stats['partners']+=1
        # VENTAS is deliberately excluded under the user's expense-only scope.
        conn.execute('INSERT INTO migration_log(created_at,detail) VALUES(?,?)',(timestamp(),'Migración Google Sheets: '+json.dumps(stats,ensure_ascii=False)))
    return stats


def partner_rows():
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT m.*,a.name account_name,e.code expense_code FROM capital_movements m
            LEFT JOIN treasury_accounts a ON a.id=m.account_id LEFT JOIN expenses e ON e.id=m.linked_expense_id ORDER BY m.id''')]


def import_partner_injections(snapshot,*,_conn=None):
    """Separately authorized capital income, including rows previously claimed but excluded."""
    stats=dict(imported=0,skipped=0,amount_cents=0,undated=0)
    with (nullcontext(_conn) if _conn is not None else connect(write=True)) as conn:
        for n,raw in enumerate(snapshot['sheets']['SOCIOS']['values'][14:],15):
            r=list(raw)+[None]*15
            if r[2]!='Inyección a cuenta NIMUS': continue
            total=money_cents(r[7])
            if not total or total<0 or r[8]!='Aportación de socio' or r[12]!='Entrada' or r[11]!='Cuenta bancaria NIMUS':
                raise ValueError(f'SOCIOS fila {n}: revisa la aportación y su cuenta bancaria.')
            account=conn.execute("SELECT id FROM treasury_accounts WHERE name=? AND kind='Banco' AND active=1",(r[11],)).fetchone()
            if not account: raise ValueError('Activa la cuenta bancaria NIMUS antes de importar.')
            origin,_=_claim(conn,snapshot['spreadsheet_id'],'SOCIOS',n,raw)
            if conn.execute('SELECT 1 FROM capital_movements WHERE origin=?',(origin,)).fetchone():
                stats['skipped']+=1
                continue
            day=sheet_date(r[0])
            conn.execute('''INSERT INTO capital_movements(origin,moved_on,partner,movement,concept,party,
                treatment,amount_cents,account_id,sign,receipt,notes) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)''',
                (origin,day,r[1] or '',r[2],r[3] or 'Inyección a cuenta NIMUS',r[4] or '',r[8],total,
                 account[0],r[13] or '',r[14] or ''))
            stats['imported']+=1; stats['amount_cents']+=total; stats['undated']+=not bool(day)
        if stats['imported']:
            conn.execute('INSERT INTO migration_log(created_at,detail) VALUES(?,?)',
                (timestamp(),'Aportaciones a banco autorizadas desde SOCIOS: '+json.dumps(stats,ensure_ascii=False)))
    return stats
