def create_production_control_schema(conn):
    statements=[
        '''CREATE TABLE production_metrics (
            job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
            total_seconds REAL NOT NULL DEFAULT 0 CHECK(total_seconds>=0),
            run_seconds REAL NOT NULL DEFAULT 0 CHECK(run_seconds>=0),
            active_since TEXT,run_started_at TEXT,run_complete INTEGER NOT NULL DEFAULT 0,
            tracking_complete INTEGER NOT NULL DEFAULT 0 CHECK(tracking_complete IN (0,1)))''',
        '''CREATE TABLE production_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL REFERENCES production_jobs(id),
            rejected_units INTEGER NOT NULL CHECK(rejected_units>0),waste_grams REAL CHECK(waste_grams>=0),
            cause TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',previously_good INTEGER NOT NULL CHECK(previously_good IN (0,1)),
            request_key TEXT NOT NULL UNIQUE,signature TEXT NOT NULL,previous_plan TEXT NOT NULL,created_at TEXT NOT NULL)''',
        '''CREATE TABLE print_reprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL REFERENCES production_jobs(id),
            failure_id INTEGER NOT NULL UNIQUE REFERENCES production_failures(id),quantity INTEGER NOT NULL CHECK(quantity>0),
            number INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('Pendiente','En curso','Finalizada','Fallida')),
            previous_plan TEXT NOT NULL,created_at TEXT NOT NULL,started_at TEXT,completed_at TEXT,
            request_key TEXT NOT NULL UNIQUE,signature TEXT NOT NULL,UNIQUE(job_id,number))''',
        '''CREATE TABLE job_consumption (
            job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id),grams REAL CHECK(grams>=0),
            manual_minutes REAL CHECK(manual_minutes>=0),material_rate_cents INTEGER CHECK(material_rate_cents>=0),
            machine_rate_cents INTEGER CHECK(machine_rate_cents>=0),needs_update INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL)''',
        '''CREATE TABLE order_extra_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL REFERENCES orders(id),
            concept TEXT NOT NULL,cost_type TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents>=0),
            expense_id INTEGER REFERENCES expenses(id),status TEXT NOT NULL DEFAULT 'Activo' CHECK(status IN ('Activo','Anulado')),
            request_key TEXT NOT NULL UNIQUE,signature TEXT NOT NULL,created_at TEXT NOT NULL,void_reason TEXT)''',
        "CREATE UNIQUE INDEX idx_extra_expense ON order_extra_costs(expense_id) WHERE status='Activo' AND expense_id IS NOT NULL",
        '''CREATE TABLE production_alert_state (identity TEXT PRIMARY KEY,status TEXT NOT NULL,
            snoozed_until TEXT,updated_at TEXT NOT NULL)''',
        '''CREATE TABLE production_alert_settings (id INTEGER PRIMARY KEY CHECK(id=1),lead_minutes INTEGER NOT NULL DEFAULT 30 CHECK(lead_minutes BETWEEN 1 AND 1440))''',
        'INSERT INTO production_alert_settings(id) VALUES(1)',
        '''CREATE TRIGGER failure_keep BEFORE DELETE ON production_failures BEGIN SELECT RAISE(ABORT,'La falla conserva su historial.'); END''',
        '''CREATE TRIGGER failure_fixed BEFORE UPDATE ON production_failures BEGIN SELECT RAISE(ABORT,'La falla conserva sus datos originales.'); END''',
        '''CREATE TRIGGER extra_expense_order BEFORE UPDATE OF order_id ON expenses
            WHEN EXISTS(SELECT 1 FROM order_extra_costs c WHERE c.expense_id=OLD.id AND c.status='Activo' AND c.order_id IS NOT NEW.order_id)
            BEGIN SELECT RAISE(ABORT,'Anula primero el vínculo de costo adicional antes de cambiar el pedido del gasto.'); END'''
    ]
    for sql in statements:
        sql=sql.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ').replace('CREATE UNIQUE INDEX ','CREATE UNIQUE INDEX IF NOT EXISTS ').replace('CREATE TRIGGER ','CREATE TRIGGER IF NOT EXISTS ').replace('INSERT INTO production_alert_settings','INSERT OR IGNORE INTO production_alert_settings')
        conn.execute(sql)
    create_alert_support_schema(conn)

def create_alert_support_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS material_availability (identity TEXT PRIMARY KEY,name TEXT NOT NULL,
        available_grams REAL NOT NULL CHECK(available_grams>=0),minimum_grams REAL NOT NULL DEFAULT 0 CHECK(minimum_grams>=0),updated_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS machine_maintenance_due (machine_id INTEGER PRIMARY KEY REFERENCES machines(id) ON DELETE CASCADE,
        due_on TEXT,notes TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL)''')
