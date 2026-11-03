import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import assign_suggest as a, production as p
from services.queries import load_snapshot
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class MachinePanelTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def test_pick_a_printer_see_its_queue_and_assign_a_fitting_piece_there(self):
        a.set_loaded(2, 'PETG Negro')
        oid = p.create_order('Llaveros', 'Cliente');iid = p.create_item(oid, 'Llavero', 4)
        base = p.create_part(iid, 'Base', 4, 'Impresión 3D', 'PLA Prueba')
        ring = p.create_part(iid, 'Aro', 4, 'Impresión 3D', 'PETG Negro')
        queued = p.create_jobs(base, [dict(quantity=2, machine_id=2)])[0]
        other = p.create_jobs(base, [dict(quantity=1, machine_id=1)])[0]
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # "Todas" first: every printer's prints, with their actions, as before.
        self.assertTrue({f'queue_{queued}_start', f'queue_{other}_start'} <= {b.key for b in app.button})
        app.button(key='queue_pick_2').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.button(key='queue_pick_2').label, 'Viendo')
        keys = {b.key for b in app.button}
        self.assertIn(f'queue_{queued}_start', keys)
        self.assertNotIn(f'queue_{other}_start', keys)  # Only this printer's queue.
        # The printer opens on its agenda: the next print keeps its actions, the rest reads by day.
        self.assertTrue(any(m.value.startswith('**Siguiente**') for m in app.markdown))
        self.assertTrue(any('Agenda de P2' in m.value or 'Agenda de' in m.value for m in app.markdown))
        app.button_group(key='queue_machine_view').set_value('Lista').run()
        self.assertTrue(any(m.value.startswith('**En cola · 1**') for m in app.markdown))
        app.button_group(key='queue_machine_view').set_value('Agenda').run()
        # Back to every printer from the toolbar above the tiles.
        app.button(key='queue_pick_all').click().run()
        self.assertEqual(app.button(key='queue_pick_2').label, 'Ver su cola')
        self.assertTrue({f'queue_{queued}_start', f'queue_{other}_start'} <= {b.key for b in app.button})
        app.button(key='queue_pick_2').click().run()
        # Its loaded PETG puts the ring first among the pieces to assign here.
        fits = [b.key for b in app.button if (b.key or '').startswith('queue_here_2_')]
        self.assertEqual(fits[0], f'queue_here_2_{ring}')
        app.button(key=f'queue_here_2_{ring}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.button(key=f'split_one_{ring}_v0_use_2').label, 'Elegida')
        app.button(key=f'split_one_{ring}_v0_save').click().run()
        job = next(j for j in load_snapshot()['jobs'] if j['part_id'] == ring)
        self.assertEqual((job['machine_id'], job['quantity']), (2, 4))

    def test_machine_filter_focuses_that_printer(self):
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.selectbox(key='queue_machine').set_value(3).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.button(key='queue_pick_3').label, 'Viendo')
        self.assertTrue(any(m.value.startswith('#### P3') for m in app.markdown))


if __name__ == '__main__':
    unittest.main()
