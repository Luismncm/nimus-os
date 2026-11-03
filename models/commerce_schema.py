"""Versioned commercial rules, requests and reversible operational cancellation markers."""
def create_commerce_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS commercial_terms (
      id INTEGER PRIMARY KEY AUTOINCREMENT,quote_id INTEGER REFERENCES quotations(id),sale_id INTEGER REFERENCES sales(id),
      payload TEXT NOT NULL,created_at TEXT NOT NULL,CHECK((quote_id IS NULL)<>(sale_id IS NULL)))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS commercial_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,quote_id INTEGER REFERENCES quotations(id),sale_id INTEGER REFERENCES sales(id),
      detail TEXT NOT NULL,created_at TEXT NOT NULL,CHECK((quote_id IS NULL)<>(sale_id IS NULL)))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS commercial_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,quote_id INTEGER REFERENCES quotations(id),sale_id INTEGER REFERENCES sales(id),
      kind TEXT NOT NULL CHECK(kind IN ('Cambio','Cancelación')),detail TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'Pendiente' CHECK(state IN ('Pendiente','Resuelta','Aplicada')),
      resolution TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,resolved_at TEXT,
      CHECK((quote_id IS NULL)<>(sale_id IS NULL)))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS order_cancellations (
      order_id INTEGER PRIMARY KEY REFERENCES orders(id),reason TEXT NOT NULL,created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS commercial_document_requests (
      request_key TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('quote','sale')),
      quote_id INTEGER REFERENCES quotations(id),sale_id INTEGER REFERENCES sales(id),signature TEXT NOT NULL,
      CHECK((quote_id IS NULL)<>(sale_id IS NULL)))''')
    for table in ('commercial_terms','commercial_events','order_cancellations','commercial_document_requests'):
        for event in ('UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS keep_{table}_{event.lower()} BEFORE {event} ON {table}
              BEGIN SELECT RAISE(ABORT,'Se conserva el historial comercial. Registra otra versión.'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS keep_commercial_requests_delete BEFORE DELETE ON commercial_requests
      BEGIN SELECT RAISE(ABORT,'Conserva la solicitud en el historial.'); END''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS keep_commercial_requests_edit BEFORE UPDATE ON commercial_requests
      WHEN OLD.state<>'Pendiente' OR NEW.quote_id IS NOT OLD.quote_id OR NEW.sale_id IS NOT OLD.sale_id OR NEW.kind<>OLD.kind
      OR NEW.detail<>OLD.detail OR NEW.created_at<>OLD.created_at OR NEW.state='Pendiente' OR length(trim(NEW.resolution))=0 OR NEW.resolved_at IS NULL
      BEGIN SELECT RAISE(ABORT,'Solo puedes resolver una solicitud conservando su contenido.'); END''')
