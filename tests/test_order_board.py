import os
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import db
from services import operations, production as p, order_board as board
from services.queries import load_snapshot


class OrderBoardTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name)/'test.db'))
        env.start(); self.addCleanup(env.stop)
        db.init_db()
        self.oid = p.create_order('Cúmulo para estudio', 'Cliente', '2026-10-10', 'Alta')
        self.iid = p.create_item(self.oid, 'Cúmulo beige', 2)
        self.pid = p.create_part(self.iid, 'Pantalla', 2, 'Impresión 3D')

    def order(self):
        return next(o for o in load_snapshot()['orders'] if o['id'] == self.oid)

    def prepared(self):
        jid = p.create_job(self.pid, 2)
        p.job_action(jid, 'finish')
        operations.update_item(self.iid, checked=True, expected_revision=0)
        for stage in operations.STAGES: operations.set_stage(self.oid, stage, True, expected_revision=0)
        return jid

    def test_route_follows_work_and_checks_not_just_completion_percentage(self):
        self.assertEqual(board.tracking(self.order())['lane'], 'Planificar')
        jid = p.create_job(self.pid, 2)
        p.job_action(jid, 'start')
        self.assertEqual(board.tracking(self.order())['lane'], 'Producir')
        p.job_action(jid, 'finish')
        self.assertEqual(board.tracking(self.order())['lane'], 'Preparar')
        for stage in operations.STAGES: operations.set_stage(self.oid, stage, True, expected_revision=0)
        self.assertEqual(board.tracking(self.order())['lane'], 'Preparar')
        operations.update_item(self.iid, checked=True, expected_revision=0)
        self.assertEqual(board.tracking(self.order())['lane'], 'Salida')
        p.set_order_blocked(self.oid, True)
        self.assertEqual(board.tracking(self.order())['lane'], 'Preparar')
        self.assertEqual(board.tracking(self.order())['action'], 'Resolver bloqueo')
        p.set_order_blocked(self.oid, False)
        p.deliver_order(self.oid)
        t = board.tracking(self.order(), date(2026,10,14))
        self.assertEqual(t['lane'], 'Entregados')
        self.assertFalse(t['overdue'])

    def test_filters_search_and_no_changes_from_reading(self):
        operations.update_item(self.iid, label='Caja azul', expected_revision=0)
        oid = p.create_order('Otro', deadline='2026-10-20')
        p.set_order_blocked(oid, True)
        before = load_snapshot()
        rows = board.query(before['orders'], today=date(2026,10,14))
        self.assertEqual(rows[0]['id'], oid)
        self.assertEqual(len(board.query(before['orders'], search='beige')), 1)
        self.assertEqual(len(board.query(before['orders'], search='caja azul')), 1)
        self.assertEqual(len(board.query(before['orders'], attention='Atrasados', today=date(2026,10,14))), 1)
        self.assertEqual(len(board.query(before['orders'], priority='Baja')), 0)
        self.assertEqual(board.query(before['orders'], scope='Entregados'), [])
        self.assertEqual(load_snapshot(), before)

    def test_stock_does_not_require_shipping_and_early_checks_do_not_finish_production(self):
        o = self.order()
        o['fulfillment'] = 'Stock'
        for s in o['stages'].values(): s['checked_at'] = '2026-10-10'
        o['items'][0]['checked_at'] = '2026-10-10'
        self.assertEqual(board.tracking(o)['lane'], 'Planificar')
        o.update(required_total=2, completed_total=2, remaining_total=0, status='Listo')
        o['stages']['packing']['checked_at'] = None
        o['stages']['dispatch']['checked_at'] = None
        self.assertEqual(board.tracking(o)['lane'], 'Salida')
        self.assertEqual(board.tracking(o)['action'], 'Liberar a stock')
        o['fulfillment'] = 'Cliente'
        self.assertEqual(board.tracking(o)['lane'], 'Preparar')

    def test_milestones_only_use_recorded_dates(self):
        jid = self.prepared()
        p.deliver_order(self.oid)
        rows = board.milestones(self.order(), operations.history(self.oid))
        self.assertEqual(len(rows), 8)  # creation, job start/end, four checks, delivery
        self.assertEqual(rows[0]['event'], 'Pedido entregado')
        self.assertEqual(rows[-1]['event'], 'Pedido creado')
        self.assertTrue(any(f'JOB-{jid:04d}' in r['detail'] for r in rows))

    def test_ui_board_filters_quick_check_table_and_trace(self):
        self.prepared()
        # Move back to preparation; checking from the card returns to Salida.
        operations.set_stage(self.oid, 'packing', False, expected_revision=1)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=25).run()
        app.switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Tarjetas').run()
        self.assertFalse(app.exception)
        app.checkbox(key=f'orders_open_quick_stage_{self.oid}_packing_2').check().run()
        self.assertFalse(app.exception)
        self.assertEqual(board.tracking(self.order())['lane'], 'Salida')
        app.text_input(key='orders_search').set_value('no existe').run()
        self.assertTrue(any('No hay pedidos' in i.value for i in app.info))
        app.button(key='orders_clear').click().run()
        self.assertEqual(app.text_input(key='orders_search').value, '')
        app.button(key=f'orders_open_{self.oid}').click().run()
        self.assertFalse(app.exception)
        app.session_state[f'order_trace_{self.oid}'] = True
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Hito' in f.value.columns for f in app.dataframe))
        app.button(key='orders_back').click().run()
        # AppTest exposes segmented controls as button_group.
        app.button_group(key='orders_view').set_value('Tabla').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='orders_table_open'))
        app.button_group(key='orders_view').set_value('Lista').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key=f'orders_open_{self.oid}'))

    def test_ui_pagination_preserves_access_to_every_order(self):
        for i in range(8): p.create_order(f'Pedido {i}')
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=25).run()
        app.switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Tarjetas').run()
        self.assertFalse(app.exception)
        count = lambda: len([b for b in app.button if re.fullmatch(r'orders_open_\d+', b.key or '')])
        self.assertEqual(count(), 6)
        app.button(key='orders_more_Planificar').click().run()
        self.assertEqual(count(), 9)
        self.assertFalse(app.exception)
