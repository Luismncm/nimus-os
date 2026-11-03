"""Confirmed cash snapshots and remaining forecasts; neither posts a payment."""


def create_cash_projection_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS treasury_balance_snapshots (
        id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES treasury_accounts(id),
        balance_cents INTEGER NOT NULL CHECK(typeof(balance_cents)='integer'),
        ledger_net_cents INTEGER NOT NULL CHECK(typeof(ledger_net_cents)='integer'),
        confirmed_at TEXT NOT NULL, request_key TEXT NOT NULL CHECK(length(request_key)>0),
        UNIQUE(request_key,account_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS balance_snapshot_account ON treasury_balance_snapshots(account_id,id)')
    conn.execute('''CREATE TABLE IF NOT EXISTS expense_cash_forecasts (
        id INTEGER PRIMARY KEY, month TEXT NOT NULL CHECK(length(month)=7),
        additional_cents INTEGER NOT NULL CHECK(typeof(additional_cents)='integer' AND additional_cents>=0),
        notes TEXT NOT NULL, created_at TEXT NOT NULL,
        request_key TEXT NOT NULL UNIQUE CHECK(length(request_key)>0))''')
    conn.execute('CREATE INDEX IF NOT EXISTS cash_forecast_month ON expense_cash_forecasts(month,id)')
    for table in ('treasury_balance_snapshots','expense_cash_forecasts'):
        for operation in ('UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_immutable
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT,'Se conserva el historial de saldos y proyecciones.'); END''')
