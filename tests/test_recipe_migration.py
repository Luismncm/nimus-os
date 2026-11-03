import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import db
from models.inventory_schema import create_inventory_schema


class RecipeMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'v3.db'
        with db.connect(self.path,write=True) as conn:
            db._create_schema(conn)
            create_inventory_schema(conn)
            conn.execute("INSERT INTO orders VALUES(1,'ORD-0001','Cliente','Anterior','a','b',NULL,'Alta','En producción','Notas',0)")
            conn.execute("INSERT INTO items VALUES(1,1,'Lámpara',10,'Conservar','a','Origen')")
            conn.execute("INSERT INTO parts VALUES(1,1,'Base',10,'Impresión 3D','PLA','Nota pieza','a')")
            conn.execute("INSERT INTO machines VALUES(1,'P1','Impresora','Disponible','','a')")
            conn.execute("INSERT INTO production_jobs VALUES(1,'JOB-0001',1,1,10,8,'Pausado','Alta','a',NULL,NULL,'Trabajo','a','b')")
            conn.execute("INSERT INTO inventory_skus VALUES(1,'identity','Origen','Lámpara','Base','PLA','Impresión 3D','a')")
            conn.execute("INSERT INTO inventory_movements(sku_id,job_id,kind,source,destination,quantity,created_at) VALUES(1,1,'Producción','Producción','Colección',8,'a')")
            conn.execute("INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,created_at,request_key) VALUES(1,'Traslado','Colección','Stock',4,'a','transfer')")
            conn.execute("INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,created_at,reversal_of) VALUES(1,'Reversión','Stock','Colección',4,'a',2)")
            db._create_guards(conn)
            conn.execute('PRAGMA user_version=3')
        self.tables=('orders','items','parts','production_jobs','machines','inventory_skus','inventory_movements')
        with db.connect(self.path) as conn:
            self.columns={t:[r['name'] for r in conn.execute(f'PRAGMA table_info({t})')] for t in self.tables}
        self.before=self.rows()

    def rows(self):
        with db.connect(self.path) as conn:
            return {t:[tuple(r) for r in conn.execute(f'SELECT {",".join(self.columns[t])} FROM {t} ORDER BY id')] for t in self.tables}

    def test_v3_ledger_ids_reversals_and_production_preserved(self):
        db.init_db(self.path)
        self.assertEqual(self.rows(),self.before)
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        db.init_db(self.path)
        self.assertEqual(self.rows(),self.before)

    def test_failed_rebuild_rolls_back_original_schema_and_rows(self):
        from models.recipe_schema import create_recipe_schema
        def fail(conn):
            create_recipe_schema(conn)
            raise sqlite3.OperationalError('Failure after schema rebuild')
        with patch('models.recipe_schema.create_recipe_schema',side_effect=fail), self.assertRaises(RuntimeError):
            db.init_db(self.path)
        self.assertEqual(self.rows(),self.before)
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertFalse(conn.execute("SELECT name FROM sqlite_master WHERE name='inventory_reservations'").fetchone())
