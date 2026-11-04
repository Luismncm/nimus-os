import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import db
from services import production as p, inventory as inv, recipes as r
from services.quick_print import fingerprint, finish_printing
from services.queries import load_snapshot
from tests.ui_helpers import enter_option
from tests.backends import sqlite_only


class QuickFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'NIMUS_DB_PATH': str(Path(self.tmp.name) / 'test.db')})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.oid = p.create_order('Lote Origen')
        self.iid = p.create_item(self.oid, 'Lámpara', 5, collection='Origen')
        self.pid = p.create_part(self.iid, 'Base', 5, 'Impresión 3D', 'PLA')

    def token(self, iid=None):
        return fingerprint([v for v in load_snapshot()['parts'] if v['item_id'] == (iid or self.iid) and v['process'] in inv.PRINT_PROCESSES])

    def receive(self, key='manual', **kwargs):
        return inv.receive_manual(5, 'Colección', 'Stock inicial', product='Lámpara', part='Base', material='PLA', request_key=key, **kwargs)

    def test_quick_finish_partial_assigned_and_unassigned_is_atomic(self):
        jid = p.create_job(self.pid, 3, 1)
        p.job_action(jid, 'start')
        job = load_snapshot()['jobs'][0]
        p.record_progress(jid, 1, expected_revision=job['updated_at'])
        other = p.create_part(self.iid, 'Cableado', 5, 'Producción externa')
        token = self.token()
        self.assertEqual(finish_printing(self.iid, expected_fingerprint=token), 4)
        snap = load_snapshot()
        self.assertEqual(snap['machines'][0]['status'], 'Disponible')
        self.assertEqual(next(v for v in snap['parts'] if v['id'] == other)['quantity_completed'], 0)
        self.assertEqual(inv.load_inventory()['skus'][0]['produced'], 5)
        self.assertEqual(len(snap['jobs']), 2)
        with self.assertRaises(ValueError):
            finish_printing(self.iid, expected_fingerprint=token)
        self.assertEqual(finish_printing(self.iid, expected_fingerprint=self.token()), 0)

    def test_blocked_and_delivered_orders_cannot_be_quick_completed(self):
        second = p.create_part(self.iid, 'Pantalla', 5, 'Resina')
        jid = p.create_job(second, 5)
        p.job_action(jid, 'block')
        with self.assertRaises(ValueError): finish_printing(self.iid, expected_fingerprint=self.token())
        self.assertEqual(load_snapshot()['parts'][0]['quantity_completed'], 0)
        p.job_action(jid, 'unblock')
        p.set_order_blocked(self.oid, True)
        with self.assertRaises(ValueError): finish_printing(self.iid, expected_fingerprint=self.token())
        p.set_order_blocked(self.oid, False)
        finish_printing(self.iid, expected_fingerprint=self.token())
        p.deliver_order(self.oid)
        with self.assertRaises(ValueError): finish_printing(self.iid, expected_fingerprint=self.token())

    def test_concurrent_quick_checks_do_not_double_production(self):
        token = self.token()
        def finish(_):
            try: return finish_printing(self.iid, expected_fingerprint=token)
            except ValueError: return 0
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(finish, range(2))), 5)
        self.assertEqual(inv.load_inventory()['skus'][0]['produced'], 5)

    def test_manual_receipt_reuses_identity_and_can_be_reversed(self):
        mid = self.receive()
        self.assertEqual(self.receive(), mid)
        row = inv.load_inventory()['skus'][0]
        self.assertEqual((row['unassigned'], row['produced']), (5, 0))
        self.assertEqual(load_snapshot()['jobs'], [])
        finish_printing(self.iid, expected_fingerprint=self.token())
        self.assertEqual(len(inv.load_inventory()['skus']), 1)
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'], 10)
        inv.reverse_movement(mid, 'Conteo corregido')
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'], 5)
        inv.reverse_movement(mid, 'Reintento')
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'], 5)

    def test_manual_validation_and_changed_retry_roll_back(self):
        self.receive()
        for qty in (0, -1, True, 1.2):
            with self.assertRaises(ValueError): inv.receive_manual(qty, 'Stock', 'Compra', sku_id=1, request_key='bad')
        with self.assertRaises(ValueError): inv.receive_manual(1, 'Stock', '', sku_id=1, request_key='bad')
        with self.assertRaises(ValueError): inv.receive_manual(2, 'Stock', 'Otro', sku_id=1, request_key='manual')
        inv.distribute(1, 'Colección', 'B2B', 1, client='Tienda')
        with self.assertRaises(ValueError): inv.reverse_movement(1, 'Reconteo')
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'], 4)

    def test_manual_catalog_stock_reservations_and_quick_recipe_finish(self):
        comp = r.create_component('Pantalla', 'PLA', 'Impresión 3D', collection='Origen')
        prod = r.create_product('Lámpara receta', collection='Origen')
        recipe = r.publish_recipe(prod, [dict(component_id=comp, quantity=1)])
        mid = inv.receive_manual(2, 'Stock', 'Compra', component_id=comp, request_key='catalog')
        oid = r.create_recipe_order(recipe, 5, client='Cliente', fulfillment='Cliente')
        order = next(o for o in load_snapshot()['orders'] if o['id'] == oid)
        iid = order['items'][0]['id']
        self.assertEqual(order['completed_total'], 2)
        with self.assertRaises(ValueError): inv.reverse_movement(mid, 'No libre')
        finish_printing(iid, expected_fingerprint=self.token(iid))
        self.assertEqual(sum(s['reserved'] for s in inv.load_inventory()['skus']), 5)
        p.deliver_order(oid)
        self.assertEqual(inv.load_inventory()['skus'][0]['delivered'], 5)

    @sqlite_only

    def test_v5_migration_preserves_ledger_reversals_and_reservations(self):
        # Use v0.7's schema creators to make an actual predecessor database.
        path = Path(self.tmp.name) / 'old.db'
        from models.inventory_schema import create_inventory_schema
        from models.recipe_schema import create_recipe_schema
        from models.operations_schema import create_operations_schema
        with db.connect(path, write=True) as c:
            db._create_schema(c)
            create_inventory_schema(c)
            create_recipe_schema(c)
            create_operations_schema(c)
            c.execute('PRAGMA user_version=5')
        with patch.dict(os.environ, {'NIMUS_DB_PATH': str(path)}):
            oid = p.create_order('Histórico')
            iid = p.create_item(oid, 'Modelo', 5, collection='Origen')
            pid = p.create_part(iid, 'Pieza', 5, 'Resina')
            # Clock tracking did not exist in the predecessor version being constructed.
            with patch('services.runtime.transition'):
                p.job_action(p.create_job(pid, 5), 'finish')
            move = inv.distribute(1, 'Colección', 'Stock', 3)
            inv.reverse_movement(move, 'Regreso')
            with db.connect() as c:
                before = [tuple(v) for v in c.execute('SELECT * FROM inventory_movements')]
            db.init_db()
            with db.connect() as c:
                self.assertEqual([tuple(v) for v in c.execute('SELECT * FROM inventory_movements')], before)
                self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertTrue(list((path.parent / 'backups').glob('*pre-v08*')))
            inv.receive_manual(1, 'Stock', 'Compra', sku_id=1, request_key='new')
            with self.assertRaises(sqlite3.IntegrityError), db.connect(write=True) as c:
                c.execute('DELETE FROM inventory_movements')

    def test_ui_quick_check_and_manual_empty_inventory(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
        app.run().switch_page('views/collection.py').run()
        app.button(key='inventory_receive').click().run()
        prefix = 'receipt_' + app.session_state['dialog_request_key']
        enter_option(app, prefix + '_product', 'Lámpara')
        enter_option(app, prefix + '_part', 'Base')
        enter_option(app, prefix + '_material', 'PLA')
        app.number_input(key=prefix + '_qty').set_value(5)
        app.text_input(key=prefix + '_reason').set_value('Stock inicial')
        next(b for b in app.button if b.label == 'Registrar entrada').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'], 5)
        app.switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{self.oid}').click().run()
        # Marking prints done lives with the order's prints, not above its pieces.
        app.button_group(key=f'order_production_view_{self.oid}').set_value('Impresiones').run()
        next(c for c in app.checkbox if c.label == 'Lámpara · impresión completa').check().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'], 10)
        self.assertFalse(load_snapshot()['items'][0]['checked_at'])
