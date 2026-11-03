import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from streamlit.testing.v1 import AppTest
import db
from services import production as p,planning,quality,consumption,order_costs,alerts
from services.queries import load_snapshot
from utils.dates import now

class ControlUITest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'test.db')});env.start();self.addCleanup(env.stop)
        db.init_db()
        self.oid=p.create_order('Origen','Cliente')
        iid=p.create_item(self.oid,'Lámpara',4);self.pid=p.create_part(iid,'Base',4,'Impresión 3D','PLA')
    def app(self,page='views/control.py'):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page(page).run()
        self.assertFalse(app.exception,[e.message for e in app.exception]);return app
    def assert_clean(self,app):self.assertFalse(app.exception,[e.message for e in app.exception])
    def test_failure_and_reprint_from_operator_actions(self):
        jid=p.create_job(self.pid,4,1);p.job_action(jid,'start')
        app=self.app('views/queue.py')
        app.button(key=f'queue_{jid}_failure').click().run()
        prefix='failure_'+app.session_state['dialog_request_key']
        app.number_input(key=prefix+'_quantity').set_value(1)
        app.checkbox(key=prefix+'_known').check();app.number_input(key=prefix+'_grams').set_value(30)
        next(b for b in app.button if b.label=='Registrar falla y pausar').click().run()
        self.assert_clean(app);self.assertEqual(quality.failures()[0]['rejected_units'],1)
        app.button(key=f'queue_{jid}_reprint').click().run()
        self.assert_clean(app)
        self.assertTrue(any(b.label=='Preparar reimpresión' for b in app.button),[(b.key,b.label) for b in app.button])
        next(b for b in app.button if b.label=='Preparar reimpresión').click().run()
        self.assert_clean(app)
        self.assertEqual(load_snapshot()['jobs'][0]['reprint_status'],'Pendiente')
        self.assertEqual(load_snapshot()['parts'][0]['quantity_assigned'],4)
    def test_cost_capture_and_extra_cost_keep_production_and_money_separate(self):
        jid=p.create_job(self.pid,4);p.job_action(jid,'finish')
        app=self.app();app.session_state['control_view']='Costos y margen';app.run()
        app.button(key='control_consumption').click().run()
        prefix='consumption_'+app.session_state['dialog_request_key']
        app.checkbox(key=prefix+'_grams_known').check();app.number_input(key=prefix+'_grams').set_value(250)
        app.checkbox(key=prefix+'_time_manual').check();app.number_input(key=prefix+'_minutes').set_value(120)
        app.checkbox(key=prefix+'_rates').check();app.number_input(key=prefix+'_material').set_value(400)
        app.number_input(key=prefix+'_machine').set_value(20)
        next(b for b in app.button if b.label=='Guardar corrección').click().run()
        self.assert_clean(app);self.assertEqual(consumption.get(jid)['actual_cost_cents'],14000)
        app.button(key='control_extra').click().run()
        prefix='extra_cost_'+app.session_state['dialog_request_key']
        app.text_input(key=prefix+'_concept').set_value('Empaque')
        app.number_input(key=prefix+'_amount').set_value(100)
        next(b for b in app.button if b.label=='Agregar costo').click().run()
        self.assert_clean(app);self.assertEqual(order_costs.reports(load_snapshot())[0]['actual_known_cents'],24000)
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM expenses').fetchone()[0],0)
    def test_alert_view_and_ack(self):
        jid=p.create_job(self.pid,4)
        app=self.app();app.session_state['control_view']='Avisos';app.run()
        self.assert_clean(app)
        row=next(r for r in alerts.feed(load_snapshot()) if r['kind']=='Datos por completar')
        app.button(key='alert_seen_'+row['identity']).click().run()
        self.assert_clean(app)
        self.assertEqual(next(r for r in alerts.feed(load_snapshot()) if r['identity']==row['identity'])['state'],'Visto')
    def test_planning_preview_offers_free_slot_and_save_remains_atomic(self):
        start=(now()+timedelta(hours=1)).replace(second=0,microsecond=0)
        plan=dict(planned_start=start.isoformat(),duration_minutes=120,estimated_grams=100,actual_grams=None,material_rate_cents=None,machine_rate_cents=None)
        first=p.create_job(self.pid,2,1,plan=plan);second=p.create_job(self.pid,2,1)
        app=self.app('views/queue.py');app.button(key=f'queue_{second}_plan').click().run()
        prefix='plan_'+app.session_state['dialog_request_key']
        app.date_input(key=prefix+'_day').set_value(start.date());app.time_input(key=prefix+'_time').set_value(start.time())
        app.number_input(key=prefix+'_hours').set_value(2)
        next(b for b in app.button if b.label=='Guardar programación').click().run()
        self.assert_clean(app);self.assertTrue(any('Horario ocupado' in r.value for r in app.error))
        self.assertIsNone(planning.get(second)['planned_start'])
        next(b for b in app.button if b.label=='Revisar estimación').click().run()
        app.button(key=prefix+'_use_slot').click().run()
        self.assert_clean(app)
        self.assertEqual(app.time_input(key=prefix+'_time').value,(start+timedelta(hours=2)).time())
        next(b for b in app.button if b.label=='Guardar programación').click().run()
        self.assert_clean(app)
        self.assertEqual(planning.get(second)['planned_start'],(start+timedelta(hours=2)).isoformat(timespec='minutes'))
