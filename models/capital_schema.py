"""Partner-funded expenses and auditable source rows."""


def create_capital_schema(conn):
    statements = [
        '''CREATE TABLE IF NOT EXISTS partner_expense_settlements (
            expense_id INTEGER PRIMARY KEY REFERENCES expenses(id), partner TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0), paid_on TEXT,
            origin TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS sheet_import_rows (
            origin TEXT PRIMARY KEY, sheet TEXT NOT NULL, row_number INTEGER NOT NULL,
            raw_json TEXT NOT NULL, digest TEXT NOT NULL, expense_id INTEGER REFERENCES expenses(id),
            created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS capital_movements (
            id INTEGER PRIMARY KEY, origin TEXT UNIQUE NOT NULL REFERENCES sheet_import_rows(origin),
            moved_on TEXT, partner TEXT NOT NULL DEFAULT '', movement TEXT NOT NULL,
            concept TEXT NOT NULL, party TEXT NOT NULL DEFAULT '', treatment TEXT NOT NULL DEFAULT '',
            amount_cents INTEGER NOT NULL CHECK(amount_cents>=0), subtotal_cents INTEGER, tax_cents INTEGER,
            reimbursed_cents INTEGER NOT NULL DEFAULT 0, pending_cents INTEGER NOT NULL DEFAULT 0,
            account_id INTEGER REFERENCES treasury_accounts(id), sign INTEGER NOT NULL CHECK(sign IN (-1,0,1)),
            linked_expense_id INTEGER REFERENCES expenses(id), receipt TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', CHECK(sign=0 OR account_id IS NOT NULL))''',
    ]
    for sql in statements: conn.execute(sql)
    conn.execute('''CREATE TRIGGER IF NOT EXISTS partner_settlement_check BEFORE INSERT ON partner_expense_settlements BEGIN
        SELECT CASE WHEN NEW.amount_cents<>(SELECT total_cents FROM expenses WHERE id=NEW.expense_id)
            OR EXISTS(SELECT 1 FROM expense_payments WHERE expense_id=NEW.expense_id)
            OR (SELECT status FROM expenses WHERE id=NEW.expense_id)<>'Activo'
            THEN RAISE(ABORT,'Revisa el gasto y sus pagos antes de registrar el pago del socio.') END; END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS partner_settlement_fixed BEFORE UPDATE ON partner_expense_settlements
        BEGIN SELECT RAISE(ABORT,'Conserva el pago original del socio.'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS expense_already_covered BEFORE INSERT ON expense_payments
        WHEN EXISTS(SELECT 1 FROM partner_expense_settlements WHERE expense_id=NEW.expense_id)
        BEGIN SELECT RAISE(ABORT,'Este gasto ya fue cubierto por el socio.'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS partner_expense_lock BEFORE UPDATE OF total_cents,subtotal_cents,tax_cents,tax_mode ON expenses
        WHEN EXISTS(SELECT 1 FROM partner_expense_settlements WHERE expense_id=OLD.id) AND
            (NEW.total_cents<>OLD.total_cents OR NEW.subtotal_cents IS NOT OLD.subtotal_cents OR NEW.tax_cents IS NOT OLD.tax_cents OR NEW.tax_mode<>OLD.tax_mode)
        BEGIN SELECT RAISE(ABORT,'El gasto fue cubierto por un socio. Conserva sus importes.'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS partner_expense_cancel BEFORE UPDATE OF status ON expenses
        WHEN NEW.status='Cancelado' AND EXISTS(SELECT 1 FROM partner_expense_settlements WHERE expense_id=OLD.id)
        BEGIN SELECT RAISE(ABORT,'El gasto fue cubierto por un socio. Conserva su historial.'); END''')
    for table in ('sheet_import_rows','capital_movements','partner_expense_settlements'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_keep BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT,'Conserva el historial de la migración.'); END''')
