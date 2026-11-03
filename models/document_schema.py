def create_document_schema(conn):
    conn.execute('''CREATE TABLE invoice_documents (
        owner_type TEXT NOT NULL CHECK(owner_type IN ('sale','expense')), owner_id INTEGER NOT NULL,
        required INTEGER NOT NULL CHECK(required IN (0,1)), reference TEXT NOT NULL DEFAULT '',
        filename TEXT, content BLOB, revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_type,owner_id), CHECK((filename IS NULL AND content IS NULL) OR
        (filename IS NOT NULL AND content IS NOT NULL AND required=1)))''')
    conn.execute('''CREATE TABLE sales_trash (
        sale_id INTEGER PRIMARY KEY REFERENCES sales(id), previous_status TEXT NOT NULL,
        reason TEXT NOT NULL, deleted_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE sale_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER NOT NULL REFERENCES sales(id),
        detail TEXT NOT NULL, previous_payload TEXT, created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TRIGGER invoice_owner BEFORE INSERT ON invoice_documents BEGIN
        SELECT CASE WHEN (NEW.owner_type='sale' AND NOT EXISTS(SELECT 1 FROM sales WHERE id=NEW.owner_id))
          OR (NEW.owner_type='expense' AND NOT EXISTS(SELECT 1 FROM expenses WHERE id=NEW.owner_id))
          THEN RAISE(ABORT,'El registro de la factura no existe.') END; END''')
    conn.execute('DROP TRIGGER sale_fixed')
    conn.execute('''CREATE TRIGGER sale_identity_fixed BEFORE UPDATE OF quote_id,sold_on,channel,request_key ON sales
        WHEN NEW.quote_id IS NOT OLD.quote_id OR NEW.sold_on<>OLD.sold_on OR NEW.channel<>OLD.channel
          OR NEW.request_key<>OLD.request_key BEGIN
        SELECT RAISE(ABORT,'El origen y la fecha de la venta se conservan.'); END''')
    conn.execute('''CREATE TRIGGER sale_content_guard BEFORE UPDATE OF payload,total_cents ON sales
        WHEN (NEW.payload<>OLD.payload OR NEW.total_cents<>OLD.total_cents) AND
          (OLD.status<>'Activa' OR OLD.quote_id IS NOT NULL OR OLD.order_id IS NOT NULL
           OR EXISTS(SELECT 1 FROM sale_payments WHERE sale_id=OLD.id)
           OR EXISTS(SELECT 1 FROM invoice_documents WHERE owner_type='sale' AND owner_id=OLD.id AND content IS NOT NULL))
        BEGIN SELECT RAISE(ABORT,'La venta tiene pagos, factura, cotización o pedido vinculado; conserva sus partidas.'); END''')
    conn.execute('''CREATE TRIGGER expense_invoice_guard BEFORE UPDATE OF receipt_type ON expenses
        WHEN NEW.receipt_type<>'Factura' AND EXISTS(SELECT 1 FROM invoice_documents
          WHERE owner_type='expense' AND owner_id=OLD.id AND content IS NOT NULL)
        BEGIN SELECT RAISE(ABORT,'Primero retira el PDF desde Factura y PDF para cambiar el comprobante.'); END''')
