from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests import test_order_board as fixture
from services import operations, production as p
from services.queries import load_snapshot
import unittest


class TodayDetailUXTest(unittest.TestCase):
    setUp = fixture.OrderBoardTest.setUp
    order = fixture.OrderBoardTest.order
    prepared = fixture.OrderBoardTest.prepared

    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=25).run()

    def clean(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_summary_navigation_and_filter_reset_preserve_real_data(self):
        before = load_snapshot()
        app = self.app()
        self.clean(app)
        self.assertEqual(app.session_state['today_front'], 'Resumen')
        self.assertTrue(app.button(key=f'today_focus_{self.oid}'))
        app.text_input(key='today_search').set_value('Inexistente').run()
        self.assertFalse(any(b.key == f'today_focus_{self.oid}' for b in app.button))
        app.button(key='today_clear').click().run()
        self.assertEqual(app.text_input(key='today_search').value, '')
        app.button(key='today_summary_produce').click().run()
        self.clean(app)
        self.assertEqual(app.session_state['today_front'], 'Producir')
        self.assertEqual(load_snapshot(), before)

    def test_contextual_action_opens_preparation_then_confirm_dialog(self):
        p.job_action(p.create_job(self.pid, 2), 'finish')
        app = self.app().switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{self.oid}').click().run()
        self.clean(app)
        self.assertEqual(app.button(key=f'order_step_next_{self.oid}').label, 'Continuar preparación')
        app.button(key=f'order_step_next_{self.oid}').click().run()
        self.assertEqual(app.session_state[f'order_detail_tabs_{self.oid}'], 'Preparación')
        app.checkbox(key=f'order_item_check_{self.iid}_0').check().run()
        for stage in operations.STAGES:
            app.checkbox(key=f'order_stage_{self.oid}_{stage}_0').check().run()
        self.clean(app)
        self.assertEqual(app.button(key=f'order_step_next_{self.oid}').label, 'Confirmar entrega')
        app.button(key=f'order_step_next_{self.oid}').click().run()
        self.clean(app)
        self.assertEqual(app.session_state['active_dialog'][0], 'deliver_dialog')
        self.assertEqual(self.order()['status'], 'Listo')

    def test_product_search_and_new_focus_returns_to_production(self):
        app = self.app().switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{self.oid}').click().run()
        key = f'order_products_search_{self.oid}'
        app.text_input(key=key).set_value('Inexistente').run()
        self.assertFalse(any(b.key == f'item_add_part_{self.iid}' for b in app.button))
        app.session_state[f'order_detail_tabs_{self.oid}'] = 'Documentos'
        app.session_state['pending_focus_item'] = self.iid
        app.run()
        self.clean(app)
        self.assertEqual(app.session_state[f'order_detail_tabs_{self.oid}'], 'Producción')
        self.assertEqual(app.text_input(key=key).value, '')
        self.assertTrue(app.button(key=f'item_add_part_{self.iid}'))

    def test_delivered_detail_has_history_and_disables_capture(self):
        self.prepared(); p.deliver_order(self.oid)
        app = self.app().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = self.oid
        app.run()
        self.clean(app)
        self.assertFalse(any(b.key == f'order_add_item_{self.oid}' for b in app.button))
        self.assertTrue(app.checkbox(key=f'order_stage_{self.oid}_revision_1').disabled)
        app.session_state[f'order_detail_tabs_{self.oid}'] = 'Historial'
        app.session_state[f'order_trace_{self.oid}'] = True
        app.run()
        self.clean(app)
        self.assertTrue(any('Hito' in d.value.columns for d in app.dataframe))
