"""One financial document per inventory purchase, without duplicating receipts."""


def create_purchase_expense_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS inventory_inbound_expenses (
        order_id INTEGER PRIMARY KEY REFERENCES inventory_inbound_orders(id),
        expense_id INTEGER NOT NULL UNIQUE REFERENCES expenses(id),
        payload TEXT NOT NULL CHECK(json_valid(payload)),created_at TEXT NOT NULL,
        request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0))''')
    for action in ('UPDATE','DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS inbound_expense_keep_{action.lower()}
            BEFORE {action} ON inventory_inbound_expenses BEGIN
            SELECT RAISE(ABORT,'Se conserva el vínculo entre compra y gasto. Corrige el gasto desde su detalle.'); END''')
