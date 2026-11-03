"""Explicit audited reconciliation; ordinary edits retain the original guards."""
import re


def create_reconciliation_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS reconciliation_events (
        id INTEGER PRIMARY KEY, source TEXT NOT NULL, record_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK(length(trim(reason))>0), before_json TEXT NOT NULL,
        after_json TEXT NOT NULL, created_at TEXT NOT NULL)''')
    for action in ('UPDATE','DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS reconciliation_keep_{action.lower()}
            BEFORE {action} ON reconciliation_events BEGIN
            SELECT RAISE(ABORT,'Conserva el historial de conciliación.'); END''')
    for name in ('expense_financial_lock','partner_expense_lock','partner_settlement_fixed',
                 'expense_payment_fixed','quote_payment_edit','sale_payment_fixed','payment_account_fixed'):
        sql=conn.execute('SELECT sql FROM sqlite_master WHERE type=\'trigger\' AND name=?',(name,)).fetchone()[0]
        if 'nimus_reconciling' in sql: continue
        head,body=re.split(r'\bBEGIN\b',sql,maxsplit=1,flags=re.I)
        parts=re.split(r'\bWHEN\b',head,maxsplit=1,flags=re.I)
        condition=f'({parts[1].strip()})' if len(parts)==2 else '1'
        conn.execute(f'DROP TRIGGER {name}')
        conn.execute(parts[0]+' WHEN nimus_reconciling()=0 AND '+condition+' BEGIN '+body)
