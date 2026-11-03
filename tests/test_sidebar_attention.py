import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services.attention import summarize
from services import restock,inventory
from services.queries import load_snapshot
from tests import test_restock as fixture


class AttentionSummaryTest(unittest.TestCase):
    def test_groups_records_hides_seen_and_snoozed_and_limits_previews(self):
        supplies=[dict(id=i,attention=True,critical=i!=3,score=100 if i!=3 else 30,net=-i) for i in (1,2,3)]
        events=[dict(record_kind='Trabajo',record_id=1,state='Pendiente',score=80,kind='Urgente'),
                dict(record_kind='Trabajo',record_id=1,state='Pendiente',score=0,kind='Datos'),
                dict(record_kind='Pedido',record_id=2,state='Pendiente',score=30,kind='Asignar'),
                dict(record_kind='Insumo',record_id=3,state='Pendiente',score=100,kind='Negativo'),
                dict(record_kind='Trabajo',record_id=4,state='Visto',score=80,kind='Visto'),
                dict(record_kind='Máquina',record_id=5,state='Pospuesto',score=80,kind='Pospuesto')]
        row=summarize(supplies,events)
        self.assertEqual((row['supply_count'],row['pending_count'],row['total']),(3,2,5))
        self.assertEqual(len(row['supplies']),2)
        self.assertEqual([r['kind'] for r in row['pending']],['Urgente','Asignar'])

    def test_empty_summary_stays_quiet(self):
        row=summarize([],[])
        self.assertEqual(row['total'],0);self.assertEqual(row['supplies'],[]);self.assertEqual(row['pending'],[])


class SidebarAttentionUITest(unittest.TestCase):
    setUp=fixture.RestockTest.setUp
    publish=fixture.RestockTest.publish
    order=fixture.RestockTest.order
    row=fixture.RestockTest.row

    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    def clean(self,app):self.assertFalse(app.exception,[e.message for e in app.exception])

    def test_insumo_and_pending_navigation_preserve_data(self):
        self.order(3);before=load_snapshot();app=self.app();self.clean(app)
        self.assertFalse(any((b.key or '').startswith('today_restock') for b in app.button))
        app.sidebar.button(key='notifications_open').click().run();self.clean(app)
        app.button(key='sidebar_supplies_open').click().run();self.clean(app)
        self.assertEqual(app.session_state['origin_inventory_view'],'Insumos y reposición')
        app.sidebar.button(key='notifications_open').click().run();self.clean(app)
        app.button(key='sidebar_pending_open').click().run();self.clean(app)
        self.assertEqual(app.session_state['control_view'],'Avisos')
        self.assertEqual(app.session_state['control_alert_state'],'Pendiente')
        self.assertEqual(load_snapshot(),before)

    def test_sidebar_recomputes_counts_and_reading_does_not_change_seen_state(self):
        self.order(3);app=self.app();self.clean(app)
        from services import notifications
        self.assertEqual(notifications.load()['counts']['Insumos'],3)
        for cid in self.supplies.values():inventory.receive_manual(5,'Stock','Reposición',component_id=cid,request_key=f'sidebar-{cid}')
        app.run();self.clean(app)
        self.assertEqual(notifications.load()['counts']['Insumos'],0)
        import db
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM production_alert_state').fetchone()[0],0)
