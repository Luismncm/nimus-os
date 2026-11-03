import unittest
from datetime import timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import capture, development as d, production as p, planning
from services.queue_review import destinations, review
from services.queries import load_snapshot
from tests import test_development as fixture


class CaptureTest(unittest.TestCase):
    setUp=fixture.DevelopmentTest.setUp

    def job(self,jid):return next(j for j in load_snapshot()['jobs'] if j['id']==jid)

    def test_one_capture_for_existing_piece_new_piece_and_prototype(self):
        oid=p.create_order('Lámparas','Cliente A');iid=p.create_item(oid,'Lámpara',2);pid=p.create_part(iid,'Base',2,'Impresión 3D','PLA Prueba')
        start=self.start.isoformat()
        existing=capture.new_print(oid,part_id=pid,quantity=2,machine_id=1,planned_start=start,duration_minutes=60,estimated_grams=40,request_key='a')
        loose=capture.new_print(oid,piece='Tapa extra',quantity=1,material='PLA Prueba',machine_id=2,duration_minutes=30,request_key='b')
        proto=capture.new_print(self.project,piece='Bisagra',quantity=3,material='PLA Prueba',machine_id=3,request_key='c')
        self.assertEqual(capture.new_print(self.project,piece='Bisagra',quantity=3,material='PLA Prueba',machine_id=3,request_key='c'),proto)
        self.assertEqual((self.job(existing)['part_id'],self.job(existing)['material_rate_cents']),(pid,50000))
        self.assertEqual((self.job(loose)['part_name'],self.job(loose)['order_id']),('Tapa extra',oid))
        self.assertTrue(self.job(proto)['development'])
        # The piece is fully assigned now: a third job would exceed its units.
        with self.assertRaises(ValueError):capture.new_print(oid,part_id=pid,quantity=1,request_key='full')
        labels=destinations(load_snapshot(),[dict(order_id=oid,status='Activa',code='VEN-0009')])
        self.assertEqual((labels[oid]['label'],labels[self.project]['kind']),('ORD-0002 · Cliente A · VEN-0009','Prototipo'))

    def test_review_offers_one_click_reschedule_for_overdue_booking(self):
        late=(self.start-timedelta(hours=5)).isoformat()
        jid=d.launch_print(self.project,'Pantalla',1,machine_id=1,duration_minutes=60,request_key='x')
        nomachine=d.launch_print(self.project,'Probeta',1,request_key='y')
        # A booking whose start already passed, written as an old record would be.
        with db.connect(write=True) as conn:conn.execute('UPDATE print_plans SET planned_start=? WHERE job_id=?',(late,jid))
        rows={r['job']['id']:r for r in review(load_snapshot()['jobs'])}
        self.assertEqual((rows[jid]['fix'],rows[nomachine]['fix']),('reschedule','machine'))
        start=capture.reschedule_first_free(jid)
        self.assertGreater(start,self.start-timedelta(hours=3))
        self.assertEqual(planning.get(jid)['duration_minutes'],60)
        self.assertNotIn(jid,{r['job']['id'] for r in review(load_snapshot()['jobs'])})

    def test_schedule_unscheduled_books_in_order_without_overlap_and_reports_the_rest(self):
        first=d.launch_print(self.project,'Pantalla',1,machine_id=1,duration_minutes=60,request_key='s1')
        second=d.launch_print(self.project,'Base',1,machine_id=1,duration_minutes=30,request_key='s2')
        loose=d.launch_print(self.project,'Probeta',1,request_key='s3')
        done,skipped=capture.schedule_unscheduled([first,second,loose])
        starts=dict(done)
        self.assertEqual(set(starts),{first,second})
        # The second print on the same machine starts once the first one ends.
        self.assertGreaterEqual(starts[second],starts[first]+timedelta(minutes=60))
        self.assertEqual([j for j,_ in skipped],[loose])
        self.assertIn('máquina',skipped[0][1])
        self.assertEqual(planning.get(loose).get('planned_start') or '', '')


class CaptureUITest(unittest.TestCase):
    setUp=fixture.DevelopmentTest.setUp

    def test_queue_opens_on_operate_and_captures_a_new_piece_for_an_order(self):
        oid=p.create_order('Pedido web','Cliente B')
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/queue.py').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.button_group(key='queue_view').value,'Operar')
        app.button(key='queue_new_print').click().run()
        prefix='capture_'+app.session_state['dialog_request_key']
        app.selectbox(key=prefix+'_order').set_value(oid).run()
        app.text_input(key=prefix+'_piece').set_value('Soporte de pared')
        app.number_input(key=prefix+'_hours').set_value(2).run()
        app.button(key=prefix+'_save').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        job=next(j for j in load_snapshot()['jobs'] if j['part_name']=='Soporte de pared')
        self.assertEqual((job['order_id'],job['machine_id'],job['duration_minutes']),(oid,1,120))
        self.assertTrue(any(f'queue_{job["id"]}_start'==b.key for b in app.button))


class OrderProductionUITest(unittest.TestCase):
    setUp=fixture.DevelopmentTest.setUp

    def test_order_shows_pieces_open_with_their_jobs_and_its_own_queue(self):
        oid=p.create_order('Lámparas','Cliente');iid=p.create_item(oid,'Lámpara',2)
        pid=p.create_part(iid,'Base',2,'Impresión 3D','PLA Prueba');jid=p.create_job(pid,2,1)
        p.create_item(oid,'Repuesto',1)
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id']=oid;app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        # Products are picked like tabs and shown open; the job's actions sit on its line under the piece.
        self.assertFalse([e for e in app.expander if 'Lámpara' in e.label])
        self.assertIn(f'order_status_job_{jid}_start',[b.key for b in app.button])
        app.button_group(key=f'order_production_view_{oid}').set_value('Impresiones').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertIn(f'queue_{jid}_start',[b.key for b in app.button])
        self.assertIn(f'order_new_print_{oid}',[b.key for b in app.button])


if __name__=='__main__':
    unittest.main()
