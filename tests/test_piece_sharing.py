import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import inventory, piece_stock as s, production as p, recipes
from services.queries import load_snapshot
from tests import test_development as fixture
from tests.backends import sqlite_only

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def part_of(pid):
    return next(x for x in load_snapshot()['parts'] if x['id'] == pid)


def job_of(jid):
    return next(x for x in load_snapshot()['jobs'] if x['id'] == jid)


def order_of(oid):
    return next(x for x in load_snapshot()['orders'] if x['id'] == oid)


class PieceSharingTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def custom(self, units, client='Cliente', material='PLA Prueba'):
        oid = p.create_order('Llaveros ' + client, client);iid = p.create_item(oid, 'Llavero', units)
        return oid, p.create_part(iid, 'Base', units, 'Impresión 3D', material)

    def host(self, extra=3):
        oid, pid = self.custom(3)
        return oid, pid, p.create_jobs(pid, [dict(quantity=3, machine_id=1, extra=extra)])[0]

    def test_a_piece_rides_in_another_print_extra_and_finishes_with_it(self):
        _, _, host = self.host()
        other, pid = self.custom(2, 'Otro')
        piece = part_of(pid)
        self.assertEqual((piece['stock_free'], piece['stock_incoming'], piece['incoming'][0]['job_id']), (0, 3, host))
        rider = s.ride_print(pid, host, 2)
        self.assertEqual((job_of(host)['extra'], part_of(pid)['quantity_unassigned']), (1, 0))
        self.assertEqual((job_of(rider)['machine_id'], job_of(rider)['rides_on']['id']), (1, host))
        self.assertEqual(job_of(host)['riders'][0]['quantity'], 2)
        self.assertEqual(part_of(pid)['stock_incoming'], 1)  # Only the extra nobody took: no double count.
        with self.assertRaises(ValueError):
            p.job_action(rider, 'start')  # It runs inside its host.
        p.job_action(host, 'start');p.job_action(host, 'finish')
        self.assertEqual((job_of(rider)['status'], part_of(pid)['quantity_completed']), ('Terminado', 2))
        self.assertEqual(order_of(other)['manufacturing']['remaining'], 0)
        # Only the extra nobody took reaches inventory.
        sku = next(r for r in inventory.load_inventory()['skus'] if r['part'] == 'Base')
        self.assertEqual(sku['unassigned'], 1)

    def test_detach_delete_and_wrong_piece_give_units_back(self):
        _, _, host = self.host()
        _, pid = self.custom(2, 'Otro')
        rider = s.ride_print(pid, host, 2)
        s.detach_rider(rider)
        self.assertEqual((job_of(host)['extra'], part_of(pid)['quantity_unassigned']), (3, 2))
        rider = s.ride_print(pid, host, 1)
        p.delete_record('job', rider)
        self.assertEqual(job_of(host)['extra'], 3)
        with self.assertRaises(ValueError):
            s.ride_print(pid, host, 4)  # More than the extra.
        _, petg = self.custom(2, 'PETG', material='PETG Negro')
        with self.assertRaises(ValueError):
            s.ride_print(petg, host, 1)  # Another material is another piece.
        self.assertEqual(part_of(petg)['stock_incoming'], 0)

    def test_custom_piece_taken_from_inventory_is_a_finished_job_from_stock(self):
        inventory.receive_manual(5, 'Stock', 'Conteo', product='Llavero', part='Base', material='PLA Prueba', collection='General', request_key='x')
        oid, pid = self.custom(3)
        self.assertEqual(part_of(pid)['stock_free'], 5)
        jid = s.use_stock(pid, 2)
        job = job_of(jid)
        self.assertEqual((job['status'], job['from_stock'], part_of(pid)['quantity_completed']), ('Terminado', True, 2))
        self.assertEqual(part_of(pid)['stock_free'], 3)
        with self.assertRaises(ValueError):
            s.use_stock(pid, 2)  # Only 1 unit left to assign.
        with self.assertRaises(ValueError):
            p.update_job(jid, quantity=2, quantity_completed=1, status='En cola', machine_id=None, priority=job['priority'])

    def test_catalog_piece_rides_and_is_reserved_for_its_order(self):
        cid = recipes.create_component('Tapa', 'PLA Prueba', 'Impresión 3D')
        rid = recipes.publish_recipe(recipes.create_product('Lámpara'), [dict(component_id=cid, quantity=1)])
        first = recipes.create_recipe_order(rid, 2, client='A', use_stock=False)
        second = recipes.create_recipe_order(rid, 1, client='B', use_stock=False)
        parts = {x['order_id']: x['id'] for x in load_snapshot()['parts']}
        host = p.create_jobs(parts[first], [dict(quantity=2, machine_id=1, extra=2)])[0]
        self.assertEqual(part_of(parts[second])['stock_incoming'], 2)
        s.ride_print(parts[second], host, 1)
        p.job_action(host, 'finish')
        self.assertEqual((order_of(first)['remaining_total'], order_of(second)['remaining_total']), (0, 0))
        # One extra left, free in inventory for the next order.
        third = recipes.create_recipe_order(rid, 1, client='C', use_stock=False)
        piece = next(x for x in load_snapshot()['parts'] if x['order_id'] == third)
        self.assertEqual((piece['stock_free'], piece['stock_incoming']), (1, 0))

    @sqlite_only

    def test_migration_from_31(self):
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE job_riders');conn.execute('DROP TABLE stock_pulls');conn.execute('PRAGMA user_version=31')
        _, pid = self.custom(1)
        self.assertEqual(part_of(pid)['stock_incoming'], 0)  # The snapshot loads before migrating.
        db.init_db();db.init_db()
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-piezas-compartidas-v32*')))


class AvailabilityTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def row(self, oid):
        return s.availability(order_of(oid))[0]

    def test_availability_follows_a_piece_from_nothing_to_covered(self):
        oid, pid = PieceSharingTest.custom(self, 3)
        host_order, host_part = PieceSharingTest.custom(self, 3, 'Otro')
        self.assertEqual((self.row(oid)['state'], self.row(oid)['unassigned'], self.row(oid)['free']), ('Imprimir', 3, 0))
        host = p.create_jobs(host_part, [dict(quantity=3, machine_id=1, extra=2)])[0]
        self.assertEqual((self.row(oid)['state'], self.row(oid)['coming']), ('En camino', 2))
        p.job_action(host, 'start');p.job_action(host, 'finish')
        row = self.row(oid)
        self.assertEqual((row['state'], row['free'], row['take'], row['covered']), ('Parcial', 2, 2, 0))
        self.assertIn('2 en Colección', row['where'])
        s.use_stock(pid, 2)
        row = self.row(oid)
        self.assertEqual((row['state'], row['required'], row['covered'], row['unassigned'], row['take']), ('Imprimir', 3, 2, 1, 0))
        p.create_jobs(pid, [dict(quantity=1, machine_id=1)])
        self.assertEqual((self.row(oid)['state'], self.row(oid)['assigned']), ('Asignada', 1))

    def test_catalog_pieces_taken_from_inventory_can_be_returned(self):
        cid = recipes.create_component('Tapa', 'PLA Prueba', 'Impresión 3D')
        rid = recipes.publish_recipe(recipes.create_product('Lámpara'), [dict(component_id=cid, quantity=1)])
        inventory.receive_manual(3, 'Stock', 'Conteo', component_id=cid, request_key='tapas')
        oid = recipes.create_recipe_order(rid, 3, client='Cliente')  # Reserves the 3 units: nothing to print.
        self.assertFalse([x for x in load_snapshot()['parts'] if x['order_id'] == oid])
        row = self.row(oid)
        self.assertEqual((row['state'], row['covered'], row['returnable'], row['requirement_id'] is not None), ('Cubierta', 3, 3, True))
        with self.assertRaises(ValueError):
            s.return_to_stock(oid, 4, requirement_id=row['requirement_id'])
        s.return_to_stock(oid, 2, requirement_id=row['requirement_id'])
        row = self.row(oid)
        self.assertEqual((row['state'], row['covered'], row['unassigned'], row['free'], row['take']), ('Disponible', 1, 2, 2, 2))
        self.assertEqual(order_of(oid)['manufactured_from_stock'], 1)
        # The piece to print exists again and can be covered again, or returned in full.
        s.use_stock(row['part_id'], 2)
        s.return_to_stock(oid, 3, requirement_id=self.row(oid)['requirement_id'])
        row = self.row(oid)
        self.assertEqual((row['covered'], row['unassigned'], row['free']), (0, 3, 3))
        self.assertEqual(sum(1 for x in load_snapshot()['parts'] if x['order_id'] == oid), 1)
        order = order_of(oid)
        p.deliver_order(oid) if order['status'] == 'Listo' else None

    def test_custom_pieces_taken_from_inventory_cannot_be_returned(self):
        inventory.receive_manual(5, 'Stock', 'Conteo', product='Llavero', part='Base', material='PLA Prueba', collection='General', request_key='x')
        oid, pid = PieceSharingTest.custom(self, 4)
        s.use_stock(pid, 3)
        row = self.row(oid)
        self.assertEqual((row['covered'], row['returnable'], row['free'], row['unassigned']), (3, 0, 2, 1))
        with self.assertRaises(ValueError):
            s.return_to_stock(oid, 1)
        with self.assertRaises(ValueError):
            s.return_to_stock(oid, 1, requirement_id=999)

    def test_stock_printing_straight_to_inventory_shows_as_coming(self):
        from services import stock_runs
        jid = stock_runs.launch('Base', 4, material='PLA Prueba', machine_id=1, request_key='k')
        oid, pid = PieceSharingTest.custom(self, 3)
        row = self.row(oid)
        self.assertEqual((row['state'], row['free'], [h['free'] for h in row['soon']]), ('En camino', 0, [4]))
        p.job_action(jid, 'finish')
        row = self.row(oid)
        self.assertEqual((row['state'], row['free'], row['soon']), ('Disponible', 4, []))

    def test_a_recipe_piece_fully_covered_from_inventory_is_covered(self):
        rows = s.availability(dict(items=[dict(name='Producto', parts=[], recipe_id=1, requirements=[
            dict(name='Pantalla', material='PLA', process='Impresión 3D', quantity=2, from_stock=2, supply='Fabricar', production_part_id=None)])]))
        self.assertEqual((rows[0]['state'], rows[0]['required'], rows[0]['covered'], rows[0]['unassigned']), ('Cubierta', 2, 2, 0))


class PieceSharingUITest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def test_order_inventory_view_shows_every_piece_against_stock(self):
        host_order, host_part = PieceSharingTest.custom(self, 3)
        host = p.create_jobs(host_part, [dict(quantity=3, machine_id=1, extra=2)])[0]
        p.job_action(host, 'start');p.job_action(host, 'finish')
        oid, pid = PieceSharingTest.custom(self, 3, 'Otro')
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        app.button_group(key=f'order_production_view_{oid}').set_value('Inventario').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual({m.label: m.value for m in app.metric if m.label in ('Necesarias', 'De inventario', 'Por asignar', 'Libres ahora')},
                         {'Necesarias': '3', 'De inventario': '0', 'Por asignar': '3', 'Libres ahora': '2'})
        app.button(key=f'avail_take_{oid}_{pid}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.checkbox(key=f'cover_{oid}_ok').check().run()  # A custom piece leaves inventory: it asks first.
        app.button(key=f'cover_{oid}_save').click().run()
        self.assertEqual(s.availability(order_of(oid))[0]['covered'], 2)
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # The piece cards of the same order keep rendering their prints.
        app.button_group(key=f'order_production_view_{oid}').set_value('Piezas').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(app.button(key=f'part_split_{pid}'))

    def test_returning_a_catalog_piece_from_the_order_view(self):
        cid = recipes.create_component('Tapa', 'PLA Prueba', 'Impresión 3D')
        rid = recipes.publish_recipe(recipes.create_product('Lámpara'), [dict(component_id=cid, quantity=1)])
        inventory.receive_manual(3, 'Stock', 'Conteo', component_id=cid, request_key='tapas')
        oid = recipes.create_recipe_order(rid, 3, client='Cliente')
        req = s.availability(order_of(oid))[0]['requirement_id']
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        app.button_group(key=f'order_production_view_{oid}').set_value('Inventario').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.button(key=f'avail_return_{oid}_r{req}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.number_input(key=f'return_{oid}_r{req}_qty').set_value(2).run()
        app.button(key=f'return_{oid}_r{req}_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        row = s.availability(order_of(oid))[0]
        self.assertEqual((row['covered'], row['unassigned'], row['free'], row['state']), (1, 2, 2, 'Disponible'))
        # Its piece card appears again with its action.
        app.button_group(key=f'order_production_view_{oid}').set_value('Piezas').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(app.button(key=f"part_split_{row['part_id']}"))

    def test_assign_panel_offers_the_print_on_its_way_and_inventory_shows_it(self):
        oid, pid = PieceSharingTest.custom(self, 3)
        host = p.create_jobs(pid, [dict(quantity=3, machine_id=1, extra=2)])[0]
        other, piece = PieceSharingTest.custom(self, 2, 'Otro')
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = other;app.run()
        app.button_group(key=f'order_production_view_{other}').set_value('Asignar').run()
        self.assertTrue(any('en camino' in w.value for w in app.warning))
        app.button(key=f'order_assign_{other}_{piece}_v0_stock_ride_{host}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        rider = next(j for j in load_snapshot()['jobs'] if j['part_id'] == piece)
        self.assertEqual((rider['rides_on']['id'], rider['quantity']), (host, 2))
        app.switch_page('views/collection.py').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(next(m for m in app.metric if m.label == 'En camino').value, '0')  # Its 2 extra are taken.


if __name__ == '__main__':
    unittest.main()
