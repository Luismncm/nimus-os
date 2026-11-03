def create_planning_schema(conn):
    conn.execute('''CREATE TABLE print_plans (
        job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
        planned_start TEXT, duration_minutes INTEGER CHECK(duration_minutes>0),
        estimated_grams REAL CHECK(estimated_grams>=0), actual_grams REAL CHECK(actual_grams>=0),
        material_rate_cents INTEGER CHECK(material_rate_cents>=0), machine_rate_cents INTEGER CHECK(machine_rate_cents>=0),
        revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)''')
    conn.execute('CREATE INDEX idx_print_plans_start ON print_plans(planned_start)')
    conn.execute('''CREATE TRIGGER delivered_print_plan_update BEFORE UPDATE ON print_plans
        WHEN (SELECT o.status FROM orders o JOIN items i ON i.order_id=o.id
        JOIN parts p ON p.item_id=i.id JOIN production_jobs j ON j.part_id=p.id WHERE j.id=OLD.job_id)='Entregado'
        BEGIN SELECT RAISE(ABORT,'El pedido entregado conserva su planificación.'); END''')
    conn.execute('''CREATE TRIGGER delivered_print_plan_insert BEFORE INSERT ON print_plans
        WHEN (SELECT o.status FROM orders o JOIN items i ON i.order_id=o.id
        JOIN parts p ON p.item_id=i.id JOIN production_jobs j ON j.part_id=p.id WHERE j.id=NEW.job_id)='Entregado'
        BEGIN SELECT RAISE(ABORT,'El pedido entregado conserva su planificación.'); END''')
