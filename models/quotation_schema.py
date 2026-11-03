"""Local quotes and explicitly recorded payments; production remains separate."""
def create_quotation_schema(conn):
    conn.execute('''CREATE TABLE quotations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
        revision INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Borrador'
            CHECK(status IN ('Borrador','Enviada','Aceptada','Cancelada')),
        payload TEXT NOT NULL, total_cents INTEGER NOT NULL CHECK(total_cents>=0),
        order_id INTEGER UNIQUE REFERENCES orders(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE quotation_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
        quote_id INTEGER NOT NULL REFERENCES quotations(id) ON DELETE RESTRICT,
        amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
        paid_on TEXT NOT NULL, method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '',
        concept TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL, void_reason TEXT, voided_at TEXT,
        CHECK((void_reason IS NULL)=(voided_at IS NULL)))''')
    conn.execute('CREATE INDEX idx_quote_payment ON quotation_payments(quote_id)')
    conn.execute('''CREATE TRIGGER quote_payment_balance BEFORE INSERT ON quotation_payments BEGIN
        SELECT CASE WHEN (SELECT status FROM quotations WHERE id=NEW.quote_id)='Cancelada'
          OR NEW.amount_cents + COALESCE((SELECT SUM(amount_cents) FROM quotation_payments WHERE quote_id=NEW.quote_id AND voided_at IS NULL),0)
             > (SELECT total_cents FROM quotations WHERE id=NEW.quote_id)
          THEN RAISE(ABORT,'El pago excede el saldo o la cotización está cancelada.') END; END''')
    conn.execute('''CREATE TRIGGER quote_locked BEFORE UPDATE OF payload,total_cents ON quotations
        WHEN (OLD.order_id IS NOT NULL OR EXISTS(SELECT 1 FROM quotation_payments WHERE quote_id=OLD.id))
          AND (NEW.payload<>OLD.payload OR NEW.total_cents<>OLD.total_cents)
        BEGIN SELECT RAISE(ABORT,'Cotización con pedido o historial de pagos: duplica para modificar su alcance.'); END''')
    conn.execute('''CREATE TRIGGER quote_payment_keep BEFORE DELETE ON quotation_payments
        BEGIN SELECT RAISE(ABORT,'Conserva el historial; anula el pago con un motivo.'); END''')
    conn.execute('''CREATE TRIGGER quote_payment_edit BEFORE UPDATE ON quotation_payments
        WHEN OLD.voided_at IS NOT NULL OR NEW.voided_at IS NULL OR length(trim(NEW.void_reason))=0
          OR NEW.amount_cents<>OLD.amount_cents OR NEW.quote_id<>OLD.quote_id OR NEW.code<>OLD.code
          OR NEW.paid_on<>OLD.paid_on OR NEW.method<>OLD.method OR NEW.reference<>OLD.reference
          OR NEW.concept<>OLD.concept OR NEW.request_key<>OLD.request_key OR NEW.created_at<>OLD.created_at
        BEGIN SELECT RAISE(ABORT,'Solo puedes anular un pago, conservando sus datos originales.'); END''')
    conn.execute("INSERT INTO migration_log(created_at,detail) VALUES(datetime('now'),'v0.9: cotizaciones por volumen, pagos explícitos y vínculo a pedidos. Sin importes inferidos.')")
