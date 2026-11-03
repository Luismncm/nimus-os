import unittest
from datetime import timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import production as p, order_board as board
from services.queries import load_snapshot
from utils.dates import now
from views.nav_status import badges, printers_html
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class NavigationUXTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp
    launch = fixture.DevelopmentTest.launch

    def late_order(self):
        oid = p.create_order('Lámparas', 'Cliente')
        with db.connect(write=True) as conn:
            conn.execute('UPDATE orders SET deadline=? WHERE id=?', ((now() - timedelta(days=2)).date().isoformat(), oid))
        return oid

    def clean(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_sidebar_counts_what_needs_a_look_on_each_page(self):
        self.late_order()
        p.create_order('Otro', 'Cliente')
        jid = self.launch()
        p.job_action(jid, 'start')
        p.update_machine(2, 'Mantenimiento')
        counts = badges(load_snapshot())
        # Late orders in red (prototypes are not counted as orders), prints running in blue, projects and stopped printers.
        self.assertEqual(counts['orders'][0], ':red-badge[1]')
        self.assertIn('2 pedidos activos · 1 atrasados', counts['orders'][1])
        self.assertIn(':blue-badge[:material/autorenew: 1]', counts['queue'][0])
        self.assertEqual(counts['development'][0], ':violet-badge[1]')
        self.assertEqual(counts['machines'][0], ':orange-badge[1]')
        floor = printers_html(load_snapshot())
        self.assertIn('Pantalla v3', floor)
        self.assertIn('Mantenimiento', floor)
        self.assertIn('Libre', floor)

    def test_orders_focus_counts_and_filters_in_one_click(self):
        late = self.late_order()
        p.create_order('A tiempo', 'Cliente')
        self.assertEqual([o['id'] for o in board.query(load_snapshot()['orders'], attention='Atrasados', kind='Pedidos')], [late])
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        self.clean(app)
        app.button_group(key='orders_attention').set_value('Atrasados').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        self.clean(app)
        shown = {b.key for b in app.button if (b.key or '').startswith('orders_open_') and b.key[12:].isdigit()}
        self.assertEqual(shown, {f'orders_open_{late}'})

    def test_queue_state_counts_filter_the_views(self):
        jid = self.launch()
        p.job_action(jid, 'start')
        self.launch('second', planned_start=(self.start + timedelta(days=1)).isoformat())
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        self.clean(app)
        app.button_group(key='queue_quick').set_value('En marcha').run()
        self.clean(app)
        app.button_group(key='queue_view').set_value('Tabla').run()
        self.clean(app)
        self.assertEqual(len(app.dataframe[0].value), 1)


if __name__ == '__main__':
    unittest.main()
