"""Confirmed sales. Quote payments remain the single source for quote-origin sales."""


def create_sales_schema(conn):
    statements = [
        """CREATE TABLE sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            quote_id INTEGER UNIQUE REFERENCES quotations(id) ON DELETE RESTRICT,
            order_id INTEGER UNIQUE REFERENCES orders(id) ON DELETE RESTRICT,
            revision INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Activa' CHECK(status IN ('Activa','Cancelada')),
            payload TEXT NOT NULL, total_cents INTEGER NOT NULL CHECK(total_cents>=0),
            sold_on TEXT NOT NULL, due_on TEXT, channel TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            cancel_reason TEXT, cancelled_at TEXT,
            CHECK(quote_id IS NULL OR order_id IS NULL),
            CHECK((status='Activa' AND cancelled_at IS NULL AND cancel_reason IS NULL)
               OR (status='Cancelada' AND cancelled_at IS NOT NULL AND length(trim(cancel_reason))>0)))""",
        """CREATE TABLE sale_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0), paid_on TEXT NOT NULL,
            method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', concept TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
            void_reason TEXT, voided_at TEXT,
            CHECK((void_reason IS NULL AND voided_at IS NULL)
                OR (length(trim(void_reason))>0 AND voided_at IS NOT NULL)))""",
        'CREATE INDEX idx_sales_date ON sales(sold_on)',
        'CREATE INDEX idx_sale_payments_sale ON sale_payments(sale_id)',
        """CREATE VIEW sales_payment_ledger AS
            SELECT s.id sale_id, p.id, p.code, p.amount_cents, p.paid_on, p.method, p.reference,
                   p.concept, p.created_at, p.void_reason, p.voided_at, 'Cotización' source
            FROM sales s JOIN quotation_payments p ON p.quote_id=s.quote_id
            UNION ALL
            SELECT sale_id,id,code,amount_cents,paid_on,method,reference,concept,created_at,
                   void_reason,voided_at,'Directa' source FROM sale_payments""",
        """CREATE TRIGGER sale_keep BEFORE DELETE ON sales BEGIN
            SELECT RAISE(ABORT,'Cancela la venta para conservar el historial.'); END""",
        """CREATE TRIGGER sale_fixed BEFORE UPDATE OF payload,total_cents,quote_id,sold_on,channel,request_key ON sales
            WHEN NEW.payload<>OLD.payload OR NEW.total_cents<>OLD.total_cents
                OR NEW.quote_id IS NOT OLD.quote_id OR NEW.sold_on<>OLD.sold_on
                OR NEW.channel<>OLD.channel OR NEW.request_key<>OLD.request_key BEGIN
            SELECT RAISE(ABORT,'La venta confirmada conserva su alcance original.'); END""",
        """CREATE TRIGGER sale_cancel_guard BEFORE UPDATE OF status ON sales
            WHEN NEW.status='Cancelada' AND EXISTS(SELECT 1 FROM sales_payment_ledger
                 WHERE sale_id=OLD.id AND voided_at IS NULL) BEGIN
            SELECT RAISE(ABORT,'La venta tiene pagos vigentes. Revisa los registros antes de cancelarla.'); END""",
        """CREATE TRIGGER sale_quote_fixed BEFORE UPDATE OF payload,total_cents,status ON quotations
            WHEN EXISTS(SELECT 1 FROM sales WHERE quote_id=OLD.id)
                 AND (NEW.payload<>OLD.payload OR NEW.total_cents<>OLD.total_cents OR NEW.status<>'Aceptada') BEGIN
            SELECT RAISE(ABORT,'La cotización tiene una venta registrada y conserva su aceptación y alcance.'); END""",
        """CREATE TRIGGER sale_quote_payment_guard BEFORE INSERT ON quotation_payments
            WHEN EXISTS(SELECT 1 FROM sales WHERE quote_id=NEW.quote_id AND status='Cancelada') BEGIN
            SELECT RAISE(ABORT,'La venta vinculada está cancelada.'); END""",
        """CREATE TRIGGER sale_quote_order_guard BEFORE UPDATE OF order_id ON quotations
            WHEN EXISTS(SELECT 1 FROM sales WHERE quote_id=OLD.id AND status='Cancelada')
                AND NEW.order_id IS NOT OLD.order_id BEGIN
            SELECT RAISE(ABORT,'La venta vinculada está cancelada.'); END""",
        """CREATE TRIGGER sale_payment_balance BEFORE INSERT ON sale_payments BEGIN
            SELECT CASE WHEN EXISTS(SELECT 1 FROM sales WHERE id=NEW.sale_id
                AND (status='Cancelada' OR quote_id IS NOT NULL))
                THEN RAISE(ABORT,'Revisa el origen y el estado de la venta.') END;
            SELECT CASE WHEN NEW.amount_cents + COALESCE((SELECT SUM(amount_cents) FROM sale_payments
                WHERE sale_id=NEW.sale_id AND voided_at IS NULL),0) > (SELECT total_cents FROM sales WHERE id=NEW.sale_id)
                THEN RAISE(ABORT,'El pago supera el saldo de la venta.') END; END""",
        """CREATE TRIGGER sale_payment_keep BEFORE DELETE ON sale_payments BEGIN
            SELECT RAISE(ABORT,'Anula el registro de pago para conservar el historial.'); END""",
        """CREATE TRIGGER sale_payment_fixed BEFORE UPDATE ON sale_payments
            WHEN OLD.voided_at IS NOT NULL OR NEW.voided_at IS NULL OR length(trim(NEW.void_reason))=0
              OR NEW.id<>OLD.id OR NEW.code<>OLD.code OR NEW.sale_id<>OLD.sale_id
              OR NEW.amount_cents<>OLD.amount_cents OR NEW.paid_on<>OLD.paid_on OR NEW.method<>OLD.method
              OR NEW.reference<>OLD.reference OR NEW.concept<>OLD.concept
              OR NEW.request_key<>OLD.request_key OR NEW.created_at<>OLD.created_at BEGIN
            SELECT RAISE(ABORT,'Solo se permite anular el pago conservando sus datos.'); END""",
    ]
    for statement in statements:
        conn.execute(statement)
