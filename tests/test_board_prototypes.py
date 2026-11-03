import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from datetime import timedelta
from services import board_moves as moves, development as d, order_board as board, production as p
from services.queries import load_snapshot
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class BoardPrototypesTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp
    launch = fixture.DevelopmentTest.launch

    def project_row(self):
        return next(o for o in load_snapshot()['orders'] if o['id'] == self.project)

    def test_a_project_plans_prints_and_closes_on_the_board(self):
        self.assertEqual((board.tracking(self.project_row())['lane'], board.tracking(self.project_row())['action']), ('Planificar', 'Lanzar la primera impresión'))
        jid = self.launch()
        t = board.tracking(self.project_row())
        self.assertEqual((t['lane'], t['action'], t['delivered']), ('Planificar', 'Iniciar 1 en cola', False))
        p.job_action(jid, 'finish')
        d.close_project(self.project)
        self.assertEqual(board.tracking(self.project_row())['lane'], 'Entregados')
        # The kind filter splits projects from customer orders.
        oid = p.create_order('Lámparas', 'Cliente')
        orders = load_snapshot()['orders']
        self.assertEqual([o['id'] for o in board.query(orders, kind='Prototipos', scope='Todos')], [self.project])
        self.assertEqual([o['id'] for o in board.query(orders, kind='Pedidos', scope='Todos')], [oid])

    def move(self, target, key, **kw):
        moves.apply(self.project, target, expected_token=moves.token(self.project_row()), request_key=key, **kw)

    def test_a_prototype_card_starts_finishes_closes_and_reopens_like_an_order(self):
        self.assertEqual(moves.proposal(self.project_row(), 'Producir')['action'], 'launch')
        with self.assertRaises(ValueError):
            moves.proposal(self.project_row(), 'Preparar')  # Prototypes are never prepared or delivered.
        first = self.launch()
        second = self.launch('second', planned_start=(self.start + timedelta(days=1)).isoformat())
        third = self.launch('third', planned_start=(self.start + timedelta(days=2)).isoformat())
        plan = moves.proposal(self.project_row(), 'Producir')
        self.assertEqual((plan['action'], {j['id'] for j in plan['jobs']}), ('start', {first, second, third}))
        self.move('Producir', 'start', job_id=first)
        jobs = {j['id']: j for j in load_snapshot()['jobs']}
        self.assertEqual((jobs[first]['status'], board.tracking(self.project_row())['lane']), ('En producción', 'Producir'))
        # Already printing, Producir still starts the next one in the queue.
        self.assertEqual({j['id'] for j in moves.proposal(self.project_row(), 'Producir')['jobs']}, {second, third})
        # Closing finishes the running print, keeps the queued one marked as done and drops the one never made.
        plan = moves.proposal(self.project_row(), 'Entregados')
        self.assertEqual(([j['id'] for j in plan['started']], {j['id'] for j in plan['pending']}), ([first], {second, third}))
        self.move('Entregados', 'close', finished=[second])
        jobs = {j['id']: j for j in load_snapshot()['jobs']}
        self.assertEqual((jobs[first]['status'], jobs[second]['status'], third in jobs), ('Terminado', 'Terminado', False))
        row = self.project_row()
        self.assertEqual((row['development']['status'], board.tracking(row)['lane']), ('Cerrado', 'Entregados'))
        # The closed card goes back to work from the board.
        self.assertEqual(moves.proposal(row, 'Planificar')['action'], 'reopen_project')
        self.move('Planificar', 'reopen')
        self.assertEqual((self.project_row()['development']['status'], board.tracking(self.project_row())['lane']), ('Activo', 'Producir'))

    def test_prototype_cards_sit_on_the_orders_board_with_their_own_action(self):
        p.create_order('Lámparas', 'Cliente')
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        keys = {b.key for b in app.button}
        self.assertIn(f'orders_open_launch_{self.project}', keys)  # Launch its next print from the card.
        self.assertIn(f'orders_open_{self.project}', keys)
        app.button_group(key='orders_type').set_value('Prototipos').run()
        self.assertEqual([k for k in (b.key for b in app.button) if (k or '').startswith('orders_open_') and k[12:].isdigit()], [f'orders_open_{self.project}'])
        app.button(key=f'orders_open_launch_{self.project}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        prefix = 'capture_' + app.session_state['dialog_request_key']
        self.assertEqual((app.button_group(key=prefix + '_purpose').value, app.selectbox(key=prefix + '_order').value), ('Prototipo', self.project))
        # With prints, its card follows them: start one or finish and close from Seguimiento.
        self.launch()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        keys = {b.key for b in app.button}
        self.assertTrue({f'orders_open_start_{self.project}', f'orders_open_close_{self.project}'} <= keys, keys)
        app.button(key=f'orders_open_close_{self.project}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state['active_dialog'][0], 'board_move_form')
        app.multiselect(key='board_move_done_' + app.session_state['dialog_request_key']).select(app.multiselect[0].options[0]).run()
        app.button(key='board_move_confirm').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(self.project_row()['development']['status'], 'Cerrado')
        # The board view takes it too.
        app.button_group(key='orders_view').set_value('Tablero').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])


if __name__ == '__main__':
    unittest.main()
