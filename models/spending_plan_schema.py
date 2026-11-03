"""Explicit future expenses, with audited conversion into existing expense records."""


def create_spending_plan_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS spending_plans (
        id INTEGER PRIMARY KEY,month TEXT NOT NULL,concept TEXT NOT NULL CHECK(length(trim(concept))>0),
        amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
        category TEXT NOT NULL,supplier TEXT NOT NULL,account_id INTEGER REFERENCES treasury_accounts(id),
        due_on TEXT,notes TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('Previsto','Registrado','Cancelado')),
        expense_id INTEGER UNIQUE REFERENCES expenses(id),revision INTEGER NOT NULL DEFAULT 0,
        request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        CHECK((status='Registrado' AND expense_id IS NOT NULL) OR (status<>'Registrado' AND expense_id IS NULL)))''')
    conn.execute('CREATE INDEX IF NOT EXISTS spending_plan_month ON spending_plans(month,status,id)')
    conn.execute('''CREATE TABLE IF NOT EXISTS spending_plan_events (
        id INTEGER PRIMARY KEY,plan_id INTEGER NOT NULL REFERENCES spending_plans(id),
        action TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),
        request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL)''')
    conn.execute('''CREATE TRIGGER IF NOT EXISTS spending_plan_no_delete BEFORE DELETE ON spending_plans
        BEGIN SELECT RAISE(ABORT,'Cancela la previsión para conservar su historial.'); END''')
    for action in ('UPDATE','DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS spending_plan_event_{action.lower()}
            BEFORE {action} ON spending_plan_events BEGIN SELECT RAISE(ABORT,'El historial de previsiones se conserva.'); END''')
