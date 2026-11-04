import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import development as d, production as p, consumables as c, order_costs, notifications
from services.daily import daily_board
from services.queries import load_snapshot
from utils.dates import now
from tests.backends import sqlite_only


class DevelopmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'dev.db')});env.start();self.addCleanup(env.stop)
        db.init_db()
        self.pla=c.save_item('PLA Prueba',package_cost=500)
        c.receive(self.pla,1000,request_key='in')
        self.project=d.create_project('Prototipo Nimbus',goal='Validar ajuste de la pantalla',budget=300)
        self.start=(now()+timedelta(hours=2)).replace(second=0,microsecond=0)

    def order(self):return next(o for o in load_snapshot()['orders'] if o['id']==self.project)
    def launch(self,key='launch',**kw):
        args=dict(material='PLA Prueba',machine_id=1,planned_start=self.start.isoformat(),duration_minutes=120,estimated_grams=80,machine_rate=20,request_key=key)
        return d.launch_print(self.project,'Pantalla v3',2,**(args|kw))

    def test_launch_creates_one_booked_print_counted_in_filament_and_cost(self):
        jid=self.launch();self.assertEqual(self.launch(),jid)
        job=next(j for j in load_snapshot()['jobs'] if j['id']==jid)
        self.assertEqual((job['development'],job['machine_id'],job['status'],job['planned_start'][:16]),(True,1,'En cola',self.start.isoformat()[:16]))
        # 80 g × $500/kg = $40 + 2 h × $20 = $40 → $80 estimated; the filament's reference cost priced it.
        self.assertEqual((job['material_rate_cents'],job['estimated_cost_cents']),(50000,8000))
        self.assertEqual(next(r for r in c.items(load_snapshot()['jobs']) if r['id']==self.pla)['committed'],80)
        # Its interval is reserved: a second print at the same time on the same machine is refused.
        with self.assertRaises(ValueError):self.launch('clash')
        summary=next(r for r in d.summaries(load_snapshot()) if r['order']['id']==self.project)
        self.assertEqual((summary['waiting'],summary['grams_estimated'],summary['estimated_cents']),(1,80,8000))

    def test_project_is_a_cost_not_a_sale_and_stays_out_of_customer_lists(self):
        self.launch()
        c.consume(self.pla,20,order_id=self.project,request_key='use')
        report=next(r for r in order_costs.reports(load_snapshot()) if r['order_id']==self.project)
        self.assertEqual((report['development'],report['revenue_cents'],report['margin_cents'],report['consumables_cents']),(True,None,None,1000))
        daily=daily_board(load_snapshot())
        self.assertNotIn(self.project,[o['id'] for o in daily['orders']])
        self.assertFalse(any(r['order']['id']==self.project for r in daily['attention']))
        self.assertFalse(any(r['record_kind']=='Pedido' and r['record_id']==self.project for r in notifications.load()['items']))

    def test_close_needs_finished_prints_and_blocks_new_launches(self):
        jid=self.launch()
        with self.assertRaises(ValueError):d.close_project(self.project)
        p.job_action(jid,'finish');d.close_project(self.project)
        self.assertEqual(self.order()['development']['status'],'Cerrado')
        with self.assertRaises(ValueError):self.launch('after-close')
        d.reopen_project(self.project);self.launch('reopened',planned_start=(self.start+timedelta(days=1)).isoformat())
        self.assertEqual(sum(j['order_id']==self.project for j in load_snapshot()['jobs']),2)

    @sqlite_only

    def test_migration_from_28_adds_projects_with_backup(self):
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE development_launches');conn.execute('DROP TABLE development_projects');conn.execute('PRAGMA user_version=28')
        db.init_db();db.init_db()
        with db.connect() as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-desarrollo-v29*')))


class DevelopmentUITest(unittest.TestCase):
    setUp=DevelopmentTest.setUp

    def app(self,page):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page(page).run()
        self.assertFalse(app.exception,[e.message for e in app.exception]);return app

    def test_page_launches_a_print_and_queue_filters_prototypes(self):
        oid=p.create_order('Pedido cliente','Cliente');iid=p.create_item(oid,'Lámpara',1);p.create_job(p.create_part(iid,'Base',1,'Impresión 3D','PLA'),1,2)
        app=self.app('views/development.py')
        app.button(key=f'dev_launch_{self.project}').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        # The project's print opens the shared Nueva impresión window, already on Prototipo and this project.
        prefix='capture_'+app.session_state['dialog_request_key']
        self.assertEqual((app.button_group(key=prefix+'_purpose').value,app.selectbox(key=prefix+'_order').value),('Prototipo',self.project))
        app.text_input(key=prefix+'_piece').set_value('Bisagra 0.2 mm')
        app.selectbox(key=prefix+'_material').set_value('PLA Prueba').run()
        app.number_input(key=prefix+'_grams').set_value(15).run()
        app.button(key=prefix+'_save').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        job=next(j for j in load_snapshot()['jobs'] if j['development'])
        self.assertEqual((job['part_name'],job['estimated_grams']),('Bisagra 0.2 mm',15))
        app.switch_page('views/queue.py').run()
        # The prototype's print sits in the queue beside the orders', told apart by its violet tag.
        app.session_state['queue_view']='Tabla';app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(set(app.dataframe[0].value['Pieza']),{'Bisagra 0.2 mm','Base'})


if __name__=='__main__':
    unittest.main()
