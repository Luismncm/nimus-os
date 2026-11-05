import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import assign_suggest as a, production as p
from services.queries import load_snapshot
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class AssignPanelTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def order(self):
        oid = p.create_order('Llaveros', 'Cliente');iid = p.create_item(oid, 'Llavero', 5)
        return oid, p.create_part(iid, 'Base', 5, 'Impresión 3D', 'PLA Prueba'), p.create_part(iid, 'Aro', 5, 'Impresión 3D', 'PETG Negro')

    def open_assign(self, oid):
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        app.button_group(key=f'order_production_view_{oid}').set_value('Asignar').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_split_a_piece_between_printers_with_a_booked_slot(self):
        a.set_loaded(2, 'PLA Prueba')
        oid, base, ring = self.order()
        app = self.open_assign(oid)
        scope = f'order_assign_{oid}'
        self.assertTrue(any(m.value.startswith('**Por asignar · 2 piezas · 10 unidades') for m in app.markdown))
        # The piece's filament is loaded on P2: it is the suggested and preselected printer.
        app.button(key=f'{scope}_piece_{base}').click().run()
        key = f'{scope}_{base}_v0'
        self.assertEqual(app.button(key=f'{key}_use_2').label, 'Elegida')
        app.number_input(key=f'{key}_units').set_value(3).run()
        app.number_input(key=f'{key}_hours').set_value(2).run()
        app.number_input(key=f'{key}_grams').set_value(30).run()
        save = app.button(key=f'{key}_save')
        self.assertIn('Crear trabajo · 3 en P2', save.label)
        save.click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        job = next(j for j in load_snapshot()['jobs'] if j['part_id'] == base)
        self.assertEqual((job['machine_id'], job['quantity'], job['duration_minutes']), (2, 3, 120))
        self.assertIsNotNone(job['planned_start'])  # First free slot booked by default.
        # The same piece stays picked with its two remaining units: send them elsewhere, without a schedule.
        key = f'{scope}_{base}_v1'
        self.assertEqual(app.number_input(key=f'{key}_units').value, 2)
        app.button(key=f'{key}_use_external').click().run()
        app.number_input(key=f'{key}_grams').set_value(20).run()
        app.button(key=f'{key}_save').click().run()
        jobs = [j for j in load_snapshot()['jobs'] if j['part_id'] == base]
        self.assertEqual(sorted((j['machine_id'] or 0, j['quantity']) for j in jobs), [(0, 2), (2, 3)])
        # Fully assigned, the panel moves to the next piece.
        self.assertTrue(any(m.value.startswith('#### Aro') for m in app.markdown))

    def test_queue_assign_view_and_dialog_mode(self):
        oid, base, ring = self.order()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.button_group(key='queue_view').set_value('Asignar').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.button_group(key='queue_assign_material').set_value('PETG Negro').run()
        self.assertTrue(any(m.value.startswith('#### Aro') for m in app.markdown))
        app.number_input(key=f'queue_assign_{ring}_v0_grams').set_value(15).run()
        app.button(key=f'queue_assign_{ring}_v0_save').click().run()
        self.assertEqual([j['part_id'] for j in load_snapshot()['jobs']], [ring])
        # The piece's Asignar button opens the order's Asignar view on that piece, with the same single-printer flow.
        app.switch_page('views/orders.py').run();app.session_state['open_order_id'] = oid;app.run()
        app.button(key=f'part_split_{base}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.number_input(key=f'order_assign_{oid}_{base}_v0_grams').set_value(15).run()
        app.button(key=f'order_assign_{oid}_{base}_v0_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(sorted(j['part_id'] for j in load_snapshot()['jobs']), sorted([ring, base]))


if __name__ == '__main__':
    unittest.main()
