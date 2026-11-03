"""Expense documents, actual outflows and reusable cost templates; no imported balances."""


def create_expense_schema(conn):
    statements = [
        """CREATE TABLE expense_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            payload TEXT NOT NULL, period TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            revision INTEGER NOT NULL DEFAULT 0, request_key TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            revision INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Activo' CHECK(status IN ('Activo','Cancelado')),
            expense_on TEXT NOT NULL, due_on TEXT, concept TEXT NOT NULL CHECK(length(trim(concept))>0),
            category TEXT NOT NULL, subtype TEXT NOT NULL DEFAULT '', cost_type TEXT NOT NULL,
            unit TEXT NOT NULL, supplier TEXT NOT NULL DEFAULT '', account TEXT NOT NULL,
            tax_mode TEXT NOT NULL, subtotal_cents INTEGER, tax_cents INTEGER,
            total_cents INTEGER NOT NULL CHECK(total_cents>0),
            receipt_type TEXT NOT NULL, receipt_ref TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            order_id INTEGER REFERENCES orders(id) ON DELETE RESTRICT,
            template_id INTEGER REFERENCES expense_templates(id) ON DELETE RESTRICT, occurrence TEXT,
            request_key TEXT UNIQUE NOT NULL, request_payload TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, cancel_reason TEXT,
            CHECK((subtotal_cents IS NULL AND tax_cents IS NULL) OR
                (subtotal_cents>=0 AND tax_cents>=0 AND total_cents=subtotal_cents+tax_cents)),
            CHECK((template_id IS NULL AND occurrence IS NULL) OR (template_id IS NOT NULL AND occurrence IS NOT NULL)),
            UNIQUE(template_id,occurrence))""",
        """CREATE TABLE expense_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0), paid_on TEXT NOT NULL,
            account TEXT NOT NULL, method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '',
            request_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, voided_at TEXT, void_reason TEXT,
            CHECK((voided_at IS NULL AND void_reason IS NULL) OR
                  (voided_at IS NOT NULL AND length(trim(void_reason))>0)))""",
        """CREATE TABLE expense_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
            detail TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL)""",
        'CREATE INDEX idx_expenses_date ON expenses(expense_on)',
        'CREATE INDEX idx_expense_payments_owner ON expense_payments(expense_id)',
        'CREATE INDEX idx_expense_payments_date ON expense_payments(paid_on)',
        """CREATE TRIGGER expense_keep BEFORE DELETE ON expenses BEGIN
            SELECT RAISE(ABORT,'Cancela el gasto para conservar su historial.'); END""",
        """CREATE TRIGGER expense_financial_lock BEFORE UPDATE OF total_cents,subtotal_cents,tax_cents,tax_mode ON expenses
            WHEN EXISTS(SELECT 1 FROM expense_payments WHERE expense_id=OLD.id)
            AND (NEW.total_cents<>OLD.total_cents OR NEW.subtotal_cents IS NOT OLD.subtotal_cents
                 OR NEW.tax_cents IS NOT OLD.tax_cents OR NEW.tax_mode<>OLD.tax_mode) BEGIN
            SELECT RAISE(ABORT,'El gasto tiene historial de pagos. Conserva sus importes originales.'); END""",
        """CREATE TRIGGER expense_cancel_guard BEFORE UPDATE OF status ON expenses
            WHEN NEW.status='Cancelado' AND EXISTS(SELECT 1 FROM expense_payments WHERE expense_id=OLD.id AND voided_at IS NULL) BEGIN
            SELECT RAISE(ABORT,'Revisa los pagos vigentes antes de cancelar este gasto.'); END""",
        """CREATE TRIGGER expense_payment_balance BEFORE INSERT ON expense_payments BEGIN
            SELECT CASE WHEN (SELECT status FROM expenses WHERE id=NEW.expense_id)<>'Activo'
                THEN RAISE(ABORT,'El gasto está cancelado.') END;
            SELECT CASE WHEN NEW.amount_cents + COALESCE((SELECT SUM(amount_cents) FROM expense_payments
                WHERE expense_id=NEW.expense_id AND voided_at IS NULL),0) > (SELECT total_cents FROM expenses WHERE id=NEW.expense_id)
                THEN RAISE(ABORT,'El pago supera el saldo del gasto.') END; END""",
        """CREATE TRIGGER expense_payment_keep BEFORE DELETE ON expense_payments BEGIN
            SELECT RAISE(ABORT,'Anula el pago para conservar el historial.'); END""",
        """CREATE TRIGGER expense_payment_fixed BEFORE UPDATE ON expense_payments
            WHEN OLD.voided_at IS NOT NULL OR NEW.voided_at IS NULL OR length(trim(NEW.void_reason))=0
                OR NEW.id<>OLD.id OR NEW.code<>OLD.code OR NEW.expense_id<>OLD.expense_id
                OR NEW.amount_cents<>OLD.amount_cents OR NEW.paid_on<>OLD.paid_on OR NEW.account<>OLD.account
                OR NEW.method<>OLD.method OR NEW.reference<>OLD.reference
                OR NEW.request_key<>OLD.request_key OR NEW.created_at<>OLD.created_at BEGIN
            SELECT RAISE(ABORT,'Solo se permite anular el pago conservando sus datos.'); END""",
    ]
    for statement in statements: conn.execute(statement)
