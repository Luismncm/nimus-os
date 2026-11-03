"""Idempotent actual capital receipts, separate from sales and partner purchases."""
import json
from db import connect
from services import expenses, treasury, reconciliation
from services.quotations import cents
from utils.dates import timestamp


def register_injection(partner,amount,moved_on,account_id,*,concept='Inyección a cuenta NIMUS',reference='',receipt='Pendiente',notes='',request_key):
    partner=' '.join(expenses._text(partner,'Socio',True).split())
    concept=expenses._text(concept,'Concepto',True)
    reference=expenses._text(reference,'Referencia')
    notes=expenses._text(notes,'Notas')
    receipt=expenses._text(receipt,'Comprobante')
    amount=cents(amount)
    if amount<=0: raise ValueError('El importe recibido debe ser mayor que cero.')
    day=expenses._date(moved_on,'Fecha de recepción')
    if type(account_id) is not int or account_id<=0: raise ValueError('Selecciona dónde entró el dinero.')
    if not isinstance(request_key,str) or not request_key or len(request_key)>160: raise ValueError('Abre una nueva captura de aportación.')
    values=dict(partner=partner,concept=concept,reference=reference,notes=notes,receipt=receipt,amount_cents=amount,moved_on=day,account_id=account_id)
    signature=json.dumps(values,ensure_ascii=False,sort_keys=True)
    with connect(write=True) as conn:
        prior=conn.execute('SELECT id,request_payload FROM capital_movements WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['request_payload']!=signature: raise ValueError('Esta aportación ya se guardó con otros datos. Abre una nueva captura.')
            return prior['id']
        treasury.validate_account(conn,account_id)
        if reference and conn.execute('''SELECT 1 FROM capital_movements WHERE sign=1 AND voided_at IS NULL
            AND reference=? COLLATE NOCASE AND account_id=? AND moved_on=? AND amount_cents=?''',(reference,account_id,day,amount)).fetchone():
            raise ValueError('Ya existe una aportación con esa referencia, fecha, cuenta e importe. Revisa el registro existente.')
        cid=conn.execute('''INSERT INTO capital_movements(moved_on,partner,movement,concept,party,treatment,amount_cents,
            account_id,sign,receipt,notes,reference,request_key,request_payload,created_at)
            VALUES(?,?,'Inyección a cuenta NIMUS',?,?,'Aportación de socio',?,?,1,?,?,?,?,?,?)''',
            (day,partner,concept,partner,amount,account_id,receipt,notes,reference,request_key,signature,timestamp())).lastrowid
        reconciliation._audit(conn,'capital',cid,'Aportación capturada manualmente',{})
        return cid


def saved_partners():
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT partner FROM capital_movements WHERE trim(partner)<>'' ORDER BY partner COLLATE NOCASE")]


def void_injection(cid,reason,*,expected):
    with connect(write=True) as conn:
        before=reconciliation._state(conn,'capital',cid)
        reason=reconciliation._check(before,expected,reason)
        if before['sign']!=1 or before['linked_expense_id']:
            raise ValueError('Esta operación debe revisarse desde su gasto vinculado.')
        if before['voided_at']: raise ValueError('La aportación ya está anulada.')
        conn.execute('UPDATE capital_movements SET voided_at=?,void_reason=? WHERE id=?',(timestamp(),reason,cid))
        reconciliation._audit(conn,'capital',cid,'Aportación anulada: '+reason,before)
