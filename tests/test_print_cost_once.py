import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import capture, consumption, machines, order_costs, production as p
from services.queries import load_snapshot
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class PrintCostOnceTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def order_part(self, material='PETG Gris'):
        oid = p.create_order('Lámparas', 'Cliente')
        iid = p.create_item(oid, 'Lámpara', 1)
        return oid, p.create_part(iid, 'Base', 2, 'Impresión 3D', material)

    def job(self, jid):
        return next(j for j in load_snapshot()['jobs'] if j['id'] == jid)

    def test_assignment_values_are_the_real_cost_without_asking_again(self):
        oid, pid = self.order_part()
        # 120 g at the average MXN 380/kg, 3 h without machine rate: the print costs its filament only.
        plan = capture.plan_for('PETG Gris', None, 180, 120, 0)
        jid = p.create_jobs(pid, [dict(quantity=2, machine_id=1)], plan=plan)[0]
        self.assertEqual((plan['material_rate_cents'], self.job(jid)['estimated_cost_cents']), (38000, 4560))
        p.job_action(jid, 'finish')
        row = consumption.get(jid)
        # Finished, it closes with the captured grams and time: nothing left to confirm.
        self.assertEqual((row['grams'], row['minutes'], row['actual_cost_cents'], row['complete']), (120, 180, 4560, True))
        report = next(r for r in order_costs.reports(load_snapshot()) if r['order_id'] == oid)
        self.assertEqual((report['costed_jobs'], report['job_count']), (1, 1))

    def test_filament_price_given_once_and_machine_rate_add_up(self):
        oid, pid = self.order_part('PLA Prueba')
        self.assertEqual(capture.material_rate('PLA Prueba'), 50000)  # The registered spool keeps its own price.
        plan = capture.plan_for('PLA Prueba', None, 120, 100, 20, 420)
        jid = p.create_jobs(pid, [dict(quantity=2, machine_id=1)], plan=plan)[0]
        p.job_action(jid, 'finish')
        # 100 g × $420/kg = $42 + 2 h × $20/h = $40.
        self.assertEqual(consumption.get(jid)['actual_cost_cents'], 8200)

    def test_assign_window_shows_the_cost_and_saves_the_price(self):
        oid, pid = self.order_part()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.session_state['queue_view'] = 'Asignar'
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        key = next(n.key for n in app.number_input if (n.key or '').endswith('_price'))
        base = key[:-len('_price')]
        self.assertEqual(app.number_input(key=key).value, 380.0)
        app.number_input(key=base + '_grams').set_value(50)
        app.number_input(key=key).set_value(400).run()
        self.assertTrue(any('Costo de impresión \\$20.00' in m.value for m in app.markdown))
        app.button(key=base + '_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        job = next(j for j in load_snapshot()['jobs'] if j['order_id'] == oid)
        self.assertEqual((job['estimated_grams'], job['material_rate_cents'], job['estimated_cost_cents']), (50, 40000, 2000))


    def test_no_grams_blocks_save_and_a_configured_machine_rate_fills_in(self):
        machines.save_machine('A1-01', 'Bambu Lab A1', machine_id=1, hourly_rate=15)
        oid, pid = self.order_part()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.session_state['queue_view'] = 'Asignar'
        app.run()
        key = next(n.key for n in app.number_input if (n.key or '').endswith('_price'))
        base = key[:-len('_price')]
        # No filament captured yet: the save button for this piece is disabled, not just unhelpful.
        self.assertTrue(next(b for b in app.button if b.key == base + '_save').disabled)
        # Its printer (A1-01, chosen by default) already has a configured rate; no blank field to fill by hand.
        self.assertEqual(app.number_input(key=base + '_rate').value, 15.0)
        app.number_input(key=base + '_grams').set_value(30).run()
        self.assertFalse(next(b for b in app.button if b.key == base + '_save').disabled)

    def test_gcode_upload_fills_grams_and_duration(self):
        oid, pid = self.order_part()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.session_state['queue_view'] = 'Asignar'
        app.run()
        key = next(n.key for n in app.number_input if (n.key or '').endswith('_price'))
        base = key[:-len('_price')]
        text = '; total filament weight [g] : 27.5\n; total estimated time: 1h 15m 0s\n'
        app.file_uploader(key=base + '_gcode').set_value(('pieza.gcode', text.encode('utf-8'), 'text/plain')).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual((app.number_input(key=base + '_grams').value, app.number_input(key=base + '_hours').value,
                          app.number_input(key=base + '_minutes').value), (27.5, 1, 15))
        self.assertTrue(any('pieza.gcode' in m.value for m in app.success))
        self.assertFalse(next(b for b in app.button if b.key == base + '_save').disabled)


if __name__ == '__main__':
    unittest.main()
