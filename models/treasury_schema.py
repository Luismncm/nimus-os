"""Accounts classify existing receipts/outflows without duplicating financial records."""


def create_treasury_schema(conn):
    conn.execute('''CREATE TABLE treasury_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        kind TEXT NOT NULL CHECK(kind IN ('Banco','Efectivo','Pasarela','Otra')),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE payment_accounts (
        source TEXT NOT NULL CHECK(source IN ('quote','sale','expense')), payment_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL REFERENCES treasury_accounts(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL, PRIMARY KEY(source,payment_id))''')
    for name,kind in [('Cuenta bancaria NIMUS','Banco'),('Efectivo / caja','Efectivo'),('Tarjeta / pasarela','Pasarela')]:
        conn.execute("INSERT INTO treasury_accounts(name,kind,created_at,updated_at) VALUES(?,?,datetime('now'),datetime('now'))",(name,kind))
    # Expense payments already record their actual account explicitly. Keep those names.
    for row in conn.execute('SELECT id,account FROM expense_payments').fetchall():
        name=row['account'].strip()
        if not name: continue
        conn.execute("INSERT OR IGNORE INTO treasury_accounts(name,kind,created_at,updated_at) VALUES(?,'Otra',datetime('now'),datetime('now'))",(name,))
        account=conn.execute('SELECT id FROM treasury_accounts WHERE name=? COLLATE NOCASE',(name,)).fetchone()[0]
        conn.execute("INSERT INTO payment_accounts VALUES('expense',?,?,datetime('now'))",(row['id'],account))
    conn.execute('''CREATE TRIGGER payment_account_owner BEFORE INSERT ON payment_accounts BEGIN
        SELECT CASE WHEN (NEW.source='quote' AND NOT EXISTS(SELECT 1 FROM quotation_payments WHERE id=NEW.payment_id))
            OR (NEW.source='sale' AND NOT EXISTS(SELECT 1 FROM sale_payments WHERE id=NEW.payment_id))
            OR (NEW.source='expense' AND NOT EXISTS(SELECT 1 FROM expense_payments WHERE id=NEW.payment_id))
            THEN RAISE(ABORT,'El pago de origen no existe.') END; END''')
    conn.execute('''CREATE TRIGGER payment_account_fixed BEFORE UPDATE ON payment_accounts BEGIN
        SELECT RAISE(ABORT,'La cuenta del pago se conserva. Anula el pago y registra la corrección.'); END''')
    conn.execute('''CREATE TRIGGER payment_account_keep BEFORE DELETE ON payment_accounts BEGIN
        SELECT RAISE(ABORT,'La cuenta del pago se conserva en el historial.'); END''')
