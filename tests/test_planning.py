import os
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import planning as p,production as prod
from services.queries import load_snapshot
from utils.dates import now


class PlanningTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'plan.db')});env.start();self.addCleanup(env.stop)
        db.init_db()
        self.oid=prod.create_order('Lámparas','Cliente')
        self.iid=prod.create_item(self.oid,'Origen',10)
        self.pid=prod.create_part(self.iid,'Base',10,'Impresión 3D','PLA')
        self.at=now().replace(second=0,microsecond=0)
        self.data=dict(planned_start=self.at.isoformat(),duration_minutes=90,estimated_grams=250,actual_grams=None,material_rate_cents=40000,machine_rate_cents=2000)

    def job(self,qty=2,**kw):return prod.create_job(self.pid,qty,1,**kw)
    def row(self,jid):return next(j for j in load_snapshot()['jobs'] if j['id']==jid)
    def save(self,jid,data=None,**kw):
        row=self.row(jid)
        p.save(jid,data or self.data,expected_revision=row['plan_revision'],expected_job_revision=row['updated_at'],**kw)

    def test_create_plan_atomic_and_total_cost(self):
        jid=self.job(plan=self.data);row=self.row(jid)
        self.assertEqual(row['planned_end'],(self.at+timedelta(minutes=90)).isoformat(timespec='minutes'))
        self.assertEqual(row['estimated_cost_cents'],13000)
        self.assertEqual(row['status'],'En cola');self.assertIsNone(row['started_at'])
        self.assertIsNone(p.costs(p.defaults())['estimated_cost_cents'])
        with self.assertRaises(ValueError):self.job(plan=dict(self.data,duration_minutes=-1))
        self.assertEqual(len(load_snapshot()['jobs']),1)

    def test_actual_start_automatic_remaining_estimate_and_manual_correction(self):
        jid=self.job(plan=self.data)
        prod.job_action(jid,'start')
        row=self.row(jid);actual=datetime.fromisoformat(row['started_at'])
        self.assertEqual(row['estimated_finish'],(actual+timedelta(minutes=90)).isoformat(timespec='minutes'))
        earlier=(now()-timedelta(minutes=30)).isoformat(timespec='minutes')
        self.save(jid,actual_start=earlier)
        self.assertEqual(self.row(jid)['started_at'],earlier)
        with self.assertRaises(ValueError):self.save(jid,actual_start=(now()+timedelta(days=1)).isoformat())
        prod.job_action(jid,'pause');prod.job_action(jid,'start')
        self.assertEqual(self.row(jid)['started_at'],earlier)
        prod.job_action(jid,'pause')
        future=(now()+timedelta(days=1)).isoformat(timespec='minutes')
        self.save(jid,dict(self.data,planned_start=future))
        self.assertEqual(self.row(jid)['calendar_start'],future)

    def test_conflicts_midnight_and_machine_next_order(self):
        first=self.job(plan=dict(self.data,planned_start=(self.at+timedelta(hours=5)).isoformat()))
        second=prod.create_job(self.pid,2,2,plan=dict(self.data,planned_start=(self.at+timedelta(hours=4)).isoformat()))
        # Legacy overlapping reservations remain visible after migration, but new writes reject them.
        with db.connect(write=True) as conn:conn.execute('UPDATE production_jobs SET machine_id=1 WHERE id=?',(second,))
        board=p.schedule(load_snapshot())
        self.assertEqual(board['conflicts'][first],{self.row(second)['code']})
        self.assertEqual(load_snapshot()['machines'][0]['next_job']['id'],second)
        # Keep the midnight example after both reservations regardless of the time of day.
        midnight=datetime.combine((self.at+timedelta(days=2)).date(),datetime.min.time())+timedelta(hours=23)
        self.save(first,dict(self.data,planned_start=midnight.isoformat(),duration_minutes=180))
        rows=p.calendar_rows([self.row(first)],midnight.date()+timedelta(days=1),midnight.date()+timedelta(days=1))
        self.assertEqual(len(rows),1)

    def test_invalid_unknown_values_stale_and_readonly_delivery(self):
        jid=self.job()
        for field,value in [('estimated_grams',-1),('actual_grams',float('nan')),('duration_minutes',True),('machine_rate_cents',-1),('planned_start','bad')]:
            with self.assertRaises(ValueError):self.save(jid,dict(self.data,**{field:value}))
        row=self.row(jid);self.save(jid)
        with self.assertRaises(ValueError):p.save(jid,self.data,expected_revision=0,expected_job_revision=row['updated_at'])
        # Complete the remainder and deliver; planning becomes read-only.
        prod.job_action(jid,'finish');other=self.job(8);prod.job_action(other,'finish');prod.deliver_order(self.oid)
        with self.assertRaises(ValueError):self.save(jid)

    def test_ui_planning_preview_calendar_and_costs(self):
        jid=self.job()
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run().switch_page('views/queue.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        # Scheduling is on each print's line in the queue (Operar), where the agenda used to be.
        app.button(key=f'queue_{jid}_plan').click().run()
        prefix='plan_'+app.session_state['dialog_request_key']
        app.date_input(key=prefix+'_day').set_value(self.at.date())
        app.number_input(key=prefix+'_hours').set_value(1)
        app.number_input(key=prefix+'_minutes').set_value(30)
        app.number_input(key=prefix+'_grams').set_value(250)
        app.checkbox(key=prefix+'_rates_known').check()
        app.number_input(key=prefix+'_material').set_value(400)
        app.number_input(key=prefix+'_machine').set_value(20)
        next(b for b in app.button if b.label=='Revisar estimación').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertIn('$130.00',app.success[0].value)
        next(b for b in app.button if b.label=='Guardar programación').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(self.row(jid)['estimated_cost_cents'],13000)
        # The calendar view draws the booking and the table carries its time and forecast cost.
        app.session_state['queue_view']='Calendario';app.run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertTrue(app.get('arrow_vega_lite_chart') or app.get('vega_lite_chart'))
        app.session_state['queue_view']='Tabla';app.run()
        self.assertTrue(any('Horario' in w.value.columns for w in app.dataframe))
        self.assertTrue(any('$130.00' in c.value for c in app.caption))
        app.selectbox(key='queue_machine').set_value('Sin máquina').run()
        self.assertTrue(any('Sin trabajos para estos filtros' in i.value for i in app.info))

    def test_start_due_flags_csv_and_unknown_duration(self):
        legacy=dict(self.data,planned_start=(self.at-timedelta(hours=2)).isoformat(),duration_minutes=None)
        with self.assertRaises(ValueError):self.job(plan=legacy)
        jid=self.job()
        # Old reservations without duration are retained for review, while new reservations require an interval.
        with db.connect(write=True) as conn:
            conn.execute('INSERT INTO print_plans(job_id,planned_start,estimated_grams,updated_at) VALUES(?,?,?,?)',
                         (jid,legacy['planned_start'],legacy['estimated_grams'],self.at.isoformat()))
        board=p.schedule(load_snapshot(),at=self.at)
        self.assertEqual(board['late'][0]['id'],jid)
        self.assertIsNone(self.row(jid)['calendar_end'])
        self.assertIn('250.0',p.csv_bytes(load_snapshot()['jobs']).decode('utf-8-sig'))

    def test_existing_manual_finish_visible_without_inventing_start(self):
        finish=(self.at+timedelta(hours=4)).isoformat(timespec='minutes')
        jid=self.job(expected_end=finish)
        row=self.row(jid)
        rows=p.calendar_rows([row],self.at.date(),self.at.date()+timedelta(days=1))
        self.assertEqual(rows[0]['anchor_kind'],'Fin manual')
        self.assertEqual(rows[0]['start_label'],'Pendiente')
        self.assertEqual(rows[0]['end_label'],datetime.fromisoformat(finish).strftime('%d/%m/%Y %H:%M'))
        self.assertIsNone(self.row(jid)['planned_start']);self.assertIsNone(self.row(jid)['started_at'])
