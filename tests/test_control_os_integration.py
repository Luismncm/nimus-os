import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch

import db
from services import production as p, planning, resources, alerts
from services.queries import load_snapshot
from utils.dates import now, timestamp


class ControlOSIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'os.db')});env.start();self.addCleanup(env.stop)
        db.init_db()

    def test_cancelled_order_does_not_reserve_machine_or_raise_operational_alerts(self):
        oid=p.create_order('Cancelado');iid=p.create_item(oid,'Producto',1);pid=p.create_part(iid,'Pieza',1,'Impresión 3D')
        start=(now()+timedelta(hours=1)).replace(second=0,microsecond=0)
        plan=dict(planned_start=start.isoformat(),duration_minutes=120,estimated_grams=500)
        jid=p.create_job(pid,1,1,plan=plan)
        with db.connect(write=True) as conn:
            conn.execute('INSERT INTO order_cancellations VALUES(?,?,?)',(oid,'Cancelación de prueba',timestamp()))
        other=p.create_order('Activo');item=p.create_item(other,'Producto',1);part=p.create_part(item,'Pieza',1,'Impresión 3D')
        active=p.create_job(part,1,1,plan=plan)
        with db.connect() as conn:self.assertEqual([r['id'] for r in resources.blocks(conn,1)],[active])
        self.assertNotIn(jid,[r['id'] for r in planning.schedule(load_snapshot())['active']])
        self.assertFalse(any(r['record_kind']=='Pedido' and r['record_id']==oid for r in alerts.feed(load_snapshot())))

    def test_migration_from_os20_preserves_every_existing_value(self):
        from models.production_control_schema import create_production_control_schema
        path=Path(self.tmp.name)/'old20.db'
        with patch('models.production_control_schema.create_production_control_schema'):
            db.init_db(path)
        with db.connect(path,write=True) as conn:conn.execute('PRAGMA user_version=20')
        def contents():
            with db.connect(path) as conn:
                tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                return {t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}
        original=contents();db.init_db(path);after=contents()
        for table,rows in original.items():self.assertEqual(after[table],rows,table)
        self.assertIn('production_failures',after)
        with db.connect(path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
