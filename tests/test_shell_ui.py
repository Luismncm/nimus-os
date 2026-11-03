import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services.queries import load_snapshot
from services import production,board_moves
from views.shell import registry
from tests import test_origin as fixture

class ShellUITest(unittest.TestCase):
    setUp=fixture.OriginModelsTest.setUp
    records=fixture.OriginModelsTest.records

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        self.clean(app);return app
    def clean(self,app):self.assertFalse(app.exception,[e.message for e in app.exception])

    def test_area_selector_and_search_offer_every_page_without_modifying_records(self):
        before=self.records();app=self.app()
        self.assertEqual(app.button_group(key='shell_area').value,'Taller')
        self.assertEqual(len(app.selectbox(key='shell_jump').options),17)
        app.button_group(key='shell_area').set_value('Negocio').run();self.clean(app)
        self.assertEqual(app.button_group(key='shell_area').value,'Negocio')
        self.assertTrue(any(h.value=='Hoy' for h in app.header))
        self.assertEqual(self.records(),before)

    def test_search_route_resets_and_cross_page_navigation_tracks_active_area(self):
        app=self.app();before=self.records()
        app.selectbox(key='shell_jump').set_value('expenses').run();self.clean(app)
        self.assertEqual(app.session_state['shell_last_page'],'Gastos')
        self.assertEqual(app.session_state['shell_area'],'Negocio')
        self.assertIsNone(app.selectbox(key='shell_jump').value)
        app.switch_page('views/origen.py').run();self.clean(app)
        self.assertEqual(app.session_state['shell_area'],'Taller')
        self.assertEqual(self.records(),before)

    def test_all_pages_render_and_motion_preference_survives_navigation(self):
        app=self.app();before=self.records()
        app.toggle(key='ui_reduce_motion').set_value(True).run();self.clean(app)
        for row in registry():
            app.switch_page(row['path']).run();self.clean(app)
            self.assertEqual(app.session_state['shell_area'],row['area'])
            self.assertTrue(app.toggle(key='ui_reduce_motion').value)
        self.assertEqual(self.records(),before)

    def test_performance_history_view_renders_without_modifying_records(self):
        from services import sales,quotations as q
        from utils.dates import now
        sales.create_direct(dict(q.defaults(),client='Cliente',lines=[dict(description='CIRRUS · BEIGE',quantity=2,price=620,produce=False)]),
                            now().date(),request_key='history-sale')
        app=self.app();before=self.records()
        app.switch_page('views/performance.py').run();self.clean(app)
        app.button_group(key='perf_view').set_value('Histórico de ventas').run();self.clean(app)
        for grouping in ('Trimestre','Año'):
            app.button_group(key='hist_grouping').set_value(grouping).run();self.clean(app)
        app.button_group(key='perf_view').set_value('Salud financiera').run();self.clean(app)
        app.button_group(key='health_window').set_value(6).run();self.clean(app)
        self.assertEqual(self.records(),before)

    def test_board_acknowledges_dialog_without_recording_a_movement(self):
        oid=production.create_order('Pedido pendiente','Cliente')
        order=next(o for o in load_snapshot()['orders'] if o['id']==oid)
        app=self.app();before=self.records();calls=[]
        event=dict(id=oid,target='Producir',token=board_moves.token(order))
        def emitted(data):
            calls.append(data)
            return SimpleNamespace(open=None,move=event if len(calls)==1 else None)
        with patch('views.kanban.mount',side_effect=emitted):
            app.switch_page('views/orders.py').run();self.clean(app)
            self.assertEqual(app.session_state['active_dialog'][0],'board_move_form')
            app.session_state['active_dialog']=None;app.run();self.clean(app)
        self.assertEqual(calls[0]['ack'],0)
        self.assertTrue(all(c['ack']==1 for c in calls[1:]))
        self.assertEqual(self.records(),before)
