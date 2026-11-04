import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import capture, inventory, piece_stock as s, production as p, recipes
from services.queries import load_snapshot
from tests import test_development as fixture
from tests.backends import sqlite_only


def part_of(pid):
    return next(x for x in load_snapshot()['parts'] if x['id'] == pid)


def job_of(jid):
    return next(x for x in load_snapshot()['jobs'] if x['id'] == jid)


class PieceStockTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def custom(self, units=3, name='Llavero'):
        oid = p.create_order(name, 'Cliente')
        iid = p.create_item(oid, name, units)
        return oid, p.create_part(iid, 'Base', units, 'Impresión 3D', 'PLA Prueba')

    def test_extra_units_reach_inventory_when_the_print_finishes_and_leave_if_it_reopens(self):
        oid, pid = self.custom()
        jid = p.create_jobs(pid, [dict(quantity=3, machine_id=1, extra=2)])[0]
        job = job_of(jid)
        self.assertEqual((job['quantity'], job['extra'], job['extra_posted']), (3, 2, 0))
        self.assertEqual(part_of(pid)['stock_free'], 0)  # Nothing in inventory until it is printed.
        p.job_action(jid, 'finish')
        self.assertEqual((job_of(jid)['extra_posted'], part_of(pid)['quantity_remaining']), (2, 0))
        sku = next(r for r in inventory.load_inventory()['skus'] if r['part'] == 'Base')
        self.assertEqual((sku['collection'], sku['product'], sku['unassigned']), ('General', 'Llavero', 2))
        # A new order of the same model sees those two pieces before printing.
        _, other = self.custom(name='Llavero')
        self.assertEqual((part_of(other)['stock_free'], part_of(other)['stock_detail']), (2, {'Colección': 2}))
        # Reopening the job takes its extra back out of inventory.
        job = job_of(jid)
        p.update_job(jid, quantity=3, quantity_completed=1, status='En cola', machine_id=1, priority=job['priority'],
                     expected_revision=job['updated_at'])
        self.assertEqual((job_of(jid)['extra_posted'], part_of(other)['stock_free']), (0, 0))

    def test_extra_rules_and_new_print(self):
        oid, pid = self.custom()
        jid = capture.new_print(oid, part_id=pid, quantity=3, machine_id=1, extra=4, request_key='np')
        self.assertEqual(job_of(jid)['extra'], 4)
        with self.assertRaises(ValueError):
            p.create_jobs(pid, [dict(quantity=1, machine_id=1, extra=1)])  # Capacity is still the order's 3 units.
        s.update_extra(jid, 0)
        self.assertEqual(job_of(jid)['extra'], 0)
        with self.assertRaises(ValueError):
            s.update_extra(jid, -1)
        assembly_part = p.create_part(p.create_item(oid, 'Caja', 1), 'Ensamble', 1, 'Ensamble', '')
        with self.assertRaises(ValueError):
            p.create_jobs(assembly_part, [dict(quantity=1, machine_id=None, extra=1)])
        self.assertEqual(s.free_like('base', 'pla prueba', 'Impresión 3D')['stock_free'], 0)

    def test_catalog_piece_can_be_taken_from_inventory_instead_of_printing(self):
        cid = recipes.create_component('Tapa', 'PLA Prueba', 'Impresión 3D')
        rid = recipes.publish_recipe(recipes.create_product('Lámpara'), [dict(component_id=cid, quantity=1)])
        oid = recipes.create_recipe_order(rid, 3, client='Cliente', use_stock=False)
        pid = next(x['id'] for x in load_snapshot()['parts'] if x['order_id'] == oid)
        inventory.receive_manual(2, 'Stock', 'Conteo', component_id=cid, request_key='tapas')
        self.assertEqual(part_of(pid)['stock_free'], 2)
        with self.assertRaises(ValueError):
            s.take_from_stock(pid, 3)
        s.take_from_stock(pid, 2)
        piece = part_of(pid)
        self.assertEqual((piece['quantity_required'], piece['stock_free']), (1, 0))
        order = next(o for o in load_snapshot()['orders'] if o['id'] == oid)
        self.assertEqual(order['manufactured_from_stock'], 2)
        # Covering the last unit removes the piece to print; the order keeps the requirement.
        inventory.receive_manual(1, 'Colección', 'Conteo', component_id=cid, request_key='tapa3')
        s.take_from_stock(pid, 1)
        self.assertFalse([x for x in load_snapshot()['parts'] if x['order_id'] == oid])
        order = next(o for o in load_snapshot()['orders'] if o['id'] == oid)
        self.assertEqual((order['manufactured_from_stock'], order['remaining_total']), (3, 0))

    @sqlite_only

    def test_custom_piece_cannot_be_taken_and_migration_from_30(self):
        _, pid = self.custom()
        with self.assertRaises(ValueError):
            s.take_from_stock(pid, 1)
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE job_extras');conn.execute('PRAGMA user_version=30')
        self.assertEqual(part_of(pid)['stock_free'], 0)  # The snapshot still loads before migrating.
        db.init_db();db.init_db()
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-excedentes-v31*')))


class PieceStockUITest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def test_assign_window_shows_inventory_and_sends_extra_to_the_first_job(self):
        oid = p.create_order('Lote', 'Cliente');iid = p.create_item(oid, 'Llavero', 3)
        pid = p.create_part(iid, 'Base', 3, 'Impresión 3D', 'PLA Prueba')
        inventory.receive_manual(5, 'Stock', 'Conteo', product='Llavero', part='Base', material='PLA Prueba', collection='General', request_key='x')
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        self.assertTrue(any('5 en inventario' in c.value for c in app.caption))
        app.button(key=f'part_split_{pid}').click().run()
        app.button(key=f'order_assign_{oid}_split_{pid}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(any('5 en inventario (5 en Stock)' in w.value for w in app.warning))
        app.number_input(key=f'split_{pid}_1').set_value(3).run()
        app.number_input(key=f'split_{pid}_x_extra').set_value(2).run()
        self.assertTrue(any('Se imprimen **5**' in c.value for c in app.caption))
        app.button(key='split_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        job = next(j for j in load_snapshot()['jobs'] if j['part_id'] == pid)
        self.assertEqual((job['quantity'], job['extra']), (3, 2))

    def test_take_button_covers_a_catalog_piece_from_inventory(self):
        cid = recipes.create_component('Tapa', 'PLA Prueba', 'Impresión 3D')
        rid = recipes.publish_recipe(recipes.create_product('Lámpara'), [dict(component_id=cid, quantity=1)])
        oid = recipes.create_recipe_order(rid, 3, client='Cliente', use_stock=False)
        pid = next(x['id'] for x in load_snapshot()['parts'] if x['order_id'] == oid)
        inventory.receive_manual(2, 'Stock', 'Conteo', component_id=cid, request_key='tapas')
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        app.button(key=f'part_split_{pid}').click().run()
        app.button(key=f'order_assign_{oid}_{pid}_v0_stock_take').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(part_of(pid)['quantity_required'], 1)


if __name__ == '__main__':
    unittest.main()
