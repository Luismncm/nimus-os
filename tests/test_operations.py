import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import operations as ops, production as p
from services.daily import daily_board
from services.queries import load_snapshot
from tests.ui_helpers import enter_option


class OperationsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.db'
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.oid=p.create_order('Pedido diario','Cliente','2026-10-07')
        self.iid=p.create_item(self.oid,'Lámpara',3)
        self.pid=p.create_part(self.iid,'Base',3,'Impresión 3D','PLA')

    def test_checks_and_labels_do_not_change_production_or_inventory(self):
        before=load_snapshot()
        ops.update_item(self.iid,label=' Caja  2 ',expected_revision=0)
        ops.update_item(self.iid,checked=True,expected_revision=1)
        ops.set_stage(self.oid,'packing',True,expected_revision=0)
        after=load_snapshot()
        self.assertEqual(after['parts'],before['parts'])
        self.assertEqual(after['jobs'],before['jobs'])
        self.assertEqual(after['orders'][0]['status'],'Pendiente')
        self.assertEqual(after['items'][0]['label'],'Caja 2')
        self.assertTrue(after['items'][0]['checked_at'])
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM inventory_movements').fetchone()[0],0)
        self.assertEqual(len(ops.history(self.oid)),3)
        ops.set_stage(self.oid,'packing',False,expected_revision=1)
        ops.update_item(self.iid,checked=False,expected_revision=2)
        self.assertFalse(load_snapshot()['items'][0]['checked_at'])
        self.assertEqual(load_snapshot()['items'][0]['label'],'Caja 2')

    def test_stale_edits_rejected_and_delivery_readonly(self):
        ops.update_item(self.iid,label='B2B',expected_revision=0)
        with self.assertRaises(ValueError):ops.update_item(self.iid,checked=True,expected_revision=0)
        ops.set_stage(self.oid,'packing',True,expected_revision=0)
        with self.assertRaises(ValueError):ops.set_stage(self.oid,'packing',False,expected_revision=0)
        p.job_action(p.create_job(self.pid,3),'finish')
        p.deliver_order(self.oid)
        with self.assertRaises(ValueError):ops.update_item(self.iid,label='Otro',expected_revision=1)
        with self.assertRaises(ValueError):ops.set_stage(self.oid,'dispatch',True,expected_revision=0)
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as conn:
            conn.execute('UPDATE item_tracking SET label=? WHERE item_id=?',('Otro',self.iid))

    def test_deadlines_include_orders_without_jobs_and_exclude_delivered(self):
        overdue=p.create_order('Vencido','Cliente','2026-10-06')
        blocked=p.create_order('Bloqueado')
        p.set_order_blocked(blocked,True)
        board=daily_board(load_snapshot(),datetime(2026,10,7,10))
        self.assertEqual([o['id'] for o in board['overdue']],[overdue])
        self.assertEqual([o['id'] for o in board['due']],[self.oid])
        self.assertEqual([r['order']['id'] for r in board['attention']][:3],[overdue,self.oid,blocked])
        self.assertEqual(board['unassigned_units'],3)
        p.job_action(p.create_job(self.pid,3),'finish')
        self.assertEqual(len(daily_board(load_snapshot())['packing']),1)
        ops.set_stage(self.oid,'packing',True,expected_revision=0)
        self.assertEqual(len(daily_board(load_snapshot())['packing']),0)
        p.deliver_order(self.oid)
        self.assertFalse(daily_board(load_snapshot(),datetime(2026,10,7,10))['due'])

    def test_ui_checks_persist_across_pages_and_label_is_quick(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20)
        app.session_state['today_front']='Entregar'  # Hoy → Entregar holds the review and packing checks.
        app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.checkbox(key=f'hub_delivery_stage_{self.oid}_packing_0').check().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.checkbox(key=f'hub_delivery_item_check_{self.iid}_0').check().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        enter_option(app,f'hub_delivery_label_{self.iid}_1','Caja 2')
        next(b for b in app.button if b.label=='Guardar etiqueta').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{self.oid}').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertTrue(app.checkbox(key=f'order_stage_{self.oid}_packing_1').value)
        self.assertTrue(app.checkbox(key=f'detail_item_check_{self.iid}_2').value)
        self.assertEqual(load_snapshot()['items'][0]['label'],'Caja 2')

    def test_v4_migration_preserves_every_existing_row_and_defaults_pending(self):
        # Build a true v4 database using the preceding migration functions.
        old=Path(self.temp.name)/'old.db'
        from models.inventory_schema import create_inventory_schema
        from models.recipe_schema import create_recipe_schema
        with db.connect(old,write=True) as conn:
            db._create_schema(conn)
            create_inventory_schema(conn)
            create_recipe_schema(conn)
            conn.execute("INSERT INTO orders(code,client,project,created_at,updated_at,priority,status) VALUES('OLD','Cliente','Conservar','a','b','Media','Pendiente')")
            conn.execute("INSERT INTO items(order_id,name,quantity,notes,created_at) VALUES(1,'Item',1,'Notas','a')")
            conn.execute('PRAGMA user_version=4')
            before=[tuple(r) for r in conn.execute('SELECT * FROM orders')]
        db.init_db(old)
        with db.connect(old) as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM orders')],before)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM item_tracking').fetchone()[0],0)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
