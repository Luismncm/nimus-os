import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import inventory, piece_stock as s, production as p, recipes, stock_runs as r
from services.daily import daily_board
from services.queries import load_snapshot
from services.queue_review import destinations
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def part_of(pid):
    return next(x for x in load_snapshot()['parts'] if x['id'] == pid)


def job_of(jid):
    return next(x for x in load_snapshot()['jobs'] if x['id'] == jid)


def order_of(oid):
    return next(x for x in load_snapshot()['orders'] if x['id'] == oid)


def base_sku():
    return next(x for x in inventory.load_inventory()['skus'] if x['part'] == 'Base')


class StockRunTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def test_print_without_order_goes_to_inventory_and_closes_itself(self):
        jid = r.launch('Base', 4, material='PLA Prueba', machine_id=1, duration_minutes=60, request_key='k')
        self.assertEqual(r.launch('Base', 4, material='PLA Prueba', machine_id=1, request_key='k'), jid)  # Retry keeps one print.
        job = job_of(jid)
        self.assertTrue(job['stock_run'])
        self.assertEqual((job['status'], job['machine_id'], job['duration_minutes']), ('En cola', 1, 60))
        dest = destinations(load_snapshot())[job['order_id']]
        self.assertEqual((dest['kind'], dest.get('direct')), ('Stock', True))
        # No customer surface sees it: no delivery, no attention, no notification.
        self.assertNotIn(job['order_id'], [o['id'] for o in daily_board(load_snapshot())['orders']])
        # Each good unit enters inventory as it is recorded; a correction takes it back.
        p.record_progress(jid, 3, expected_revision=job['updated_at'])
        self.assertEqual(base_sku()['unassigned'], 3)
        job = job_of(jid)
        p.record_progress(jid, 1, expected_revision=job['updated_at'])
        self.assertEqual(base_sku()['unassigned'], 1)
        p.job_action(jid, 'finish')
        self.assertEqual((base_sku()['unassigned'], base_sku()['collection'], base_sku()['product']), (4, 'General', r.GENERAL))
        self.assertEqual(order_of(job['order_id'])['status'], 'Entregado')

    def test_the_queue_names_a_stock_print_by_its_model(self):
        cid = recipes.create_component('PANTALLA', 'PLA MATTE IVORY', 'Impresión 3D', variant='CIRRUS')
        catalog = job_of(r.launch(component_id=cid, quantity=1, request_key='catalogo'))
        free = job_of(r.launch('PANTALLA', 1, product='STRATO', material='PLA MATTE IVORY', request_key='libre'))
        general = job_of(r.launch('Base', 1, material='PLA', request_key='general'))
        self.assertEqual((catalog['part_name'], free['part_name'], general['part_name']), ('PANTALLA · CIRRUS', 'PANTALLA · STRATO', 'Base'))

    def test_any_order_with_the_same_piece_takes_it_instead_of_printing(self):
        p.job_action(r.launch('Base', 5, material='PLA Prueba', request_key='k'), 'finish')
        oid = p.create_order('Llaveros', 'Cliente');iid = p.create_item(oid, 'Llavero', 3)
        pid = p.create_part(iid, 'Base', 3, 'Impresión 3D', 'PLA Prueba')
        other = p.create_part(iid, 'Aro', 3, 'Impresión 3D', 'PLA Prueba')
        piece = part_of(pid)
        self.assertEqual((piece['stock_free'], piece['stock_detail']), (5, {'Colección': 5}))
        self.assertIn(f'incluye piezas de {r.GENERAL}', s.stock_text(piece))
        self.assertEqual(part_of(other)['stock_free'], 0)
        # Another material is another piece.
        petg = p.create_part(iid, 'Base', 3, 'Impresión 3D', 'PETG Negro')
        self.assertEqual(part_of(petg)['stock_free'], 0)
        with self.assertRaises(ValueError):
            s.cover_from_stock([(pid, 3), (other, 1)])  # Nothing of the ring in inventory: all or none.
        self.assertEqual(part_of(pid)['quantity_unassigned'], 3)
        self.assertEqual(s.cover_from_stock([(pid, 3)]), 3)
        self.assertEqual((part_of(pid)['quantity_completed'], base_sku()['unassigned']), (3, 2))

    def test_catalog_piece_for_stock_is_reserved_by_recipe_orders(self):
        cid = recipes.create_component('Tapa', 'PLA Prueba', 'Impresión 3D')
        self.assertEqual(next(c for c in r.components() if c['id'] == cid)['free'], 0)
        jid = r.launch(component_id=cid, quantity=2, request_key='t')
        self.assertEqual(job_of(jid)['part_name'], 'Tapa')
        p.job_action(jid, 'finish')
        self.assertEqual(next(c for c in r.components() if c['id'] == cid)['free'], 2)
        rid = recipes.publish_recipe(recipes.create_product('Lámpara'), [dict(component_id=cid, quantity=1)])
        oid = recipes.create_recipe_order(rid, 3, client='Cliente', use_stock=False)
        pid = next(x['id'] for x in load_snapshot()['parts'] if x['order_id'] == oid)
        self.assertEqual(part_of(pid)['stock_free'], 2)
        s.cover_from_stock([(pid, 2)])
        self.assertEqual(part_of(pid)['quantity_required'], 1)

    def test_validation_and_migration_from_32(self):
        with self.assertRaises(ValueError):
            r.launch('', 1, request_key='x')
        with self.assertRaises(ValueError):
            r.launch('Base', 0, request_key='y')
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE stock_runs');conn.execute('PRAGMA user_version=32')
        self.assertTrue(load_snapshot()['orders'])  # The snapshot still loads before migrating.
        db.init_db();db.init_db()
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-stock-directo-v33*')))


class StockRunUITest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def test_new_print_for_stock_needs_no_order_and_queue_groups_it(self):
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.button(key='queue_new_print').click().run()
        prefix = 'capture_' + app.session_state['dialog_request_key']
        app.button_group(key=prefix + '_purpose').set_value('Stock').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.text_input(key=prefix + '_piece').set_value('Base')
        app.number_input(key=prefix + '_qty_stock').set_value(6)
        app.number_input(key=prefix + '_hours').set_value(3).run()
        app.button(key=prefix + '_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        job = next(j for j in load_snapshot()['jobs'] if j['part_name'] == 'Base')
        self.assertEqual((job['stock_run'], job['quantity'], job['duration_minutes']), (True, 6, 180))
        # Every grouping shows the print with its actions; the agenda keeps it under «Sin horario».
        for group in ('Estado', 'Agenda', 'Máquina'):
            app.button_group(key='queue_group').set_value(group).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertIn(f"queue_{job['id']}_start", [b.key for b in app.button])

    def test_order_offers_to_cover_its_pieces_from_inventory(self):
        p.job_action(r.launch('Base', 5, material='PLA Prueba', request_key='k'), 'finish')
        oid = p.create_order('Llaveros', 'Cliente');iid = p.create_item(oid, 'Llavero', 3)
        pid = p.create_part(iid, 'Base', 3, 'Impresión 3D', 'PLA Prueba')
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # The order points to its Inventario view, where pieces are taken.
        app.button(key=f'order_stock_review_{oid}').click().run()
        self.assertEqual(app.session_state[f'order_production_view_{oid}'], 'Inventario')
        app.button(key=f'order_cover_{oid}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.checkbox(key=f'cover_{oid}_ok').check().run()
        app.button(key=f'cover_{oid}_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(part_of(pid)['quantity_completed'], 3)


if __name__ == '__main__':
    unittest.main()
