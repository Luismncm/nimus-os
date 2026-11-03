import os
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import db
from services import production as p,planning,resources,quality,consumption,runtime,order_costs,alerts,sales,quotations,expenses
from services.queries import load_snapshot
from utils.dates import now

class ProductionControlTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'test.db')});env.start();self.addCleanup(env.stop)
        db.init_db()
        self.oid=p.create_order('Origen','Cliente',str(now().date()+timedelta(days=3)))
        self.iid=p.create_item(self.oid,'Lámpara',20)
        self.pid=p.create_part(self.iid,'Base',20,'Impresión 3D','PLA')
        self.at=now().replace(second=0,microsecond=0)+timedelta(hours=1)
        self.plan=dict(planned_start=self.at.isoformat(),duration_minutes=120,estimated_grams=250,actual_grams=None,material_rate_cents=40000,machine_rate_cents=2000)
    def row(self,jid):return next(j for j in load_snapshot()['jobs'] if j['id']==jid)
    def job(self,qty=2,machine=1,plan=None):return p.create_job(self.pid,qty,machine,plan=plan)
    def save(self,jid,data):
        row=self.row(jid);planning.save(jid,data,expected_revision=row['plan_revision'],expected_job_revision=row['updated_at'])
    def failure(self,jid,**kw):
        return quality.record_failure(jid,kw.pop('units',1),'Atasco',request_key=kw.pop('key','failure'),expected_revision=self.row(jid)['updated_at'],**kw)
    def actual(self,jid,g=250,minutes=120):
        row=consumption.get(jid)
        consumption.save(jid,g,minutes,40000,2000,expected_revision=row['revision'],expected_job_revision=row['job_revision'])
    def action_at(self,jid,action,at):
        with patch('utils.dates.now',return_value=at),patch('services.resources.now',return_value=at):p.job_action(jid,action)

    def test_booking_rejects_overlap_allows_adjacent_and_parallel_and_rolls_back(self):
        first=self.job(plan=self.plan)
        before=load_snapshot()
        with self.assertRaisesRegex(ValueError,'Horario ocupado'):self.job(plan=dict(self.plan,planned_start=(self.at+timedelta(minutes=30)).isoformat()))
        self.assertEqual(load_snapshot(),before)
        adjacent=self.job(plan=dict(self.plan,planned_start=(self.at+timedelta(hours=2)).isoformat()))
        parallel=self.job(machine=2,plan=self.plan)
        self.assertEqual(len(load_snapshot()['jobs']),3)
        with db.connect() as conn:
            slot=resources.next_free(conn,1,self.at,90)
        self.assertEqual(slot,self.at+timedelta(hours=4))
        self.assertNotEqual(first,adjacent);self.assertNotEqual(first,parallel)

    def test_concurrent_reservations_have_one_winner(self):
        one=self.job();two=self.job()
        def reserve(jid):
            try:self.save(jid,self.plan);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,[one,two]))
        self.assertEqual(sorted(results),[False,True])

    def test_machine_move_and_early_start_cannot_cross_other_reservations(self):
        occupied=self.job(plan=dict(self.plan,planned_start=(now()+timedelta(minutes=30)).isoformat(timespec='minutes')))
        candidate=self.job(machine=2,plan=self.plan)
        row=self.row(candidate)
        with self.assertRaises(ValueError):p.update_job(candidate,quantity=2,quantity_completed=0,status='En cola',machine_id=1,priority='Media',expected_revision=row['updated_at'])
        self.assertEqual(self.row(candidate)['machine_id'],2)
        unknown=self.job()
        with self.assertRaises(ValueError):p.job_action(unknown,'start')
        self.assertEqual(self.row(unknown)['status'],'En cola')
        self.assertIsNone(self.row(unknown)['started_at'])

    def test_clock_excludes_pause_and_forecast_moves_with_resume(self):
        jid=self.job(plan=self.plan)
        self.action_at(jid,'start',self.at)
        self.action_at(jid,'pause',self.at+timedelta(minutes=30))
        self.action_at(jid,'start',self.at+timedelta(hours=3))
        self.assertEqual(self.row(jid)['estimated_finish'],(self.at+timedelta(hours=4,minutes=30)).isoformat(timespec='minutes'))
        self.action_at(jid,'finish',self.at+timedelta(hours=4))
        self.assertAlmostEqual(consumption.get(jid)['automatic_minutes'],90)

    def test_resume_does_not_treat_expired_past_reservation_as_future_conflict(self):
        jid=self.job(plan=self.plan)
        self.job(plan=dict(self.plan,planned_start=(self.at+timedelta(hours=3)).isoformat(),duration_minutes=60))
        self.action_at(jid,'start',self.at)
        self.action_at(jid,'pause',self.at+timedelta(minutes=30))
        self.action_at(jid,'start',self.at+timedelta(hours=4))
        self.assertEqual(self.row(jid)['status'],'En producción')

    def test_unknown_live_finish_blocks_future_slot(self):
        jid=self.job();p.job_action(jid,'start')
        with db.connect() as conn:self.assertIsNone(resources.next_free(conn,1,self.at,120))
        self.assertEqual(resources.capacity(load_snapshot())[0]['unplanned'],1)
        candidate=self.job()
        with self.assertRaises(ValueError):self.save(candidate,self.plan)

    def test_failure_good_counts_reprint_keeps_assignment_and_costs_include_waste_once(self):
        jid=self.job(qty=4,plan=self.plan)
        self.action_at(jid,'start',self.at)
        with patch('utils.dates.now',return_value=self.at+timedelta(minutes=15)):
            p.record_progress(jid,2,expected_revision=self.row(jid)['updated_at'])
        with patch('utils.dates.now',return_value=self.at+timedelta(minutes=30)):
            fid=self.failure(jid,waste_grams=50)
        self.assertEqual(self.row(jid)['quantity_completed'],2)
        self.assertEqual(self.row(jid)['status'],'Pausado')
        row=self.row(jid)
        quality.prepare_reprint(jid,fid,2,dict(self.plan,planned_start=(self.at+timedelta(hours=3)).isoformat()),request_key='reprint',expected_job_revision=row['updated_at'],expected_plan_revision=row['plan_revision'])
        self.assertEqual(len(load_snapshot()['jobs']),1)
        self.assertEqual(load_snapshot()['parts'][0]['quantity_assigned'],4)
        self.action_at(jid,'start',self.at+timedelta(hours=3))
        self.action_at(jid,'finish',self.at+timedelta(hours=4))
        with patch('utils.dates.now',return_value=self.at+timedelta(hours=4,minutes=1)):
            self.actual(jid,g=300,minutes=90)
        row=consumption.get(jid)
        self.assertEqual(row['waste_grams'],50)
        self.assertEqual(row['actual_cost_cents'],15000)
        self.assertEqual(self.row(jid)['reprint_status'],'Finalizada')

    def test_reject_previously_good_reopens_quantity_with_inventory_guard(self):
        jid=self.job(qty=4);p.job_action(jid,'finish')
        self.failure(jid,units=1,previously_good=True)
        self.assertEqual(self.row(jid)['quantity_completed'],3)
        self.assertEqual(self.row(jid)['quantity_remaining'],1)
        self.assertEqual(self.row(jid)['status'],'Pausado')

    def test_failure_correction_cannot_remove_collection_units_already_distributed(self):
        from services import inventory
        iid=p.create_item(self.oid,'Origen inventario',2,collection='Origen')
        pid=p.create_part(iid,'Pantalla',2,'Impresión 3D','PLA')
        jid=p.create_job(pid,2);p.job_action(jid,'finish')
        with db.connect() as conn:sku=conn.execute('SELECT id FROM inventory_skus').fetchone()[0]
        inventory.distribute(sku,'Colección','Stock',2,request_key='stock')
        before=load_snapshot()
        with self.assertRaises(ValueError):self.failure(jid,units=1,previously_good=True)
        self.assertEqual(load_snapshot(),before)
        self.assertEqual(quality.failures(jid),[])

    def test_margin_partial_until_final_consumption_and_no_double_count_quote(self):
        jid=self.job(qty=20);p.job_action(jid,'finish')
        payload=dict(quotations.defaults(),client='Cliente',lines=[dict(description='Lámpara',quantity=1,price=1000,produce=False)],iva=True)
        sid=sales.create_direct(payload,now().date(),request_key='sale')
        sales.link_existing_order(sid,self.oid,expected_revision=0)
        self.assertIsNone(order_costs.reports(load_snapshot())[0]['margin_cents'])
        self.actual(jid,g=250,minutes=120)
        order_costs.add(self.oid,'Empaque','Empaque',100,request_key='cost')
        report=order_costs.reports(load_snapshot())[0]
        self.assertEqual(report['revenue_cents'],100000)
        self.assertEqual(report['actual_known_cents'],24000)
        self.assertEqual(report['margin_cents'],76000)
        self.assertAlmostEqual(report['margin_percent'],76)

    def test_linked_expense_net_value_and_unclassified_tax_keeps_margin_provisional(self):
        eid=expenses.create(dict(expenses.defaults(),concept='Servicio',amount=100,order_id=self.oid),request_key='expense')
        order_costs.add(self.oid,'Servicio','Servicio externo',expense_id=eid,request_key='link',expected_expense_revision=0)
        with self.assertRaises(ValueError):order_costs.add(self.oid,'Servicio','Servicio externo',expense_id=eid,request_key='link2',expected_expense_revision=0)
        report=order_costs.reports(load_snapshot())[0]
        self.assertTrue(report['tax_unknown']);self.assertEqual(report['extras_cents'],10000)

    def test_alert_ack_and_snooze_are_context_specific(self):
        jid=self.job(plan=dict(self.plan,planned_start=(now()-timedelta(hours=3)).isoformat()))
        snapshot=load_snapshot();rows=alerts.feed(snapshot)
        late=next(r for r in rows if r['kind']=='Horario vencido')
        alerts.resolve(late['identity'])
        self.assertEqual(next(r for r in alerts.feed(snapshot) if r['identity']==late['identity'])['state'],'Visto')
        alerts.resolve(late['identity'],snooze_minutes=30)
        self.assertEqual(next(r for r in alerts.feed(snapshot) if r['identity']==late['identity'])['state'],'Pospuesto')

    def test_material_shortage_and_maintenance_use_explicit_inputs(self):
        from services import alert_inputs
        jid=self.job(plan=self.plan)
        initial=alerts.feed(load_snapshot())
        self.assertTrue(any(r['kind']=='Existencias por confirmar' for r in initial))
        alert_inputs.save_material('PLA',100,50)
        alert_inputs.save_maintenance(1,now().date().isoformat(),'Limpieza')
        rows=alerts.feed(load_snapshot())
        self.assertTrue(any(r['kind']=='Material insuficiente' for r in rows))
        self.assertTrue(any(r['kind']=='Mantenimiento pendiente' for r in rows))
        alert_inputs.save_material('PLA',300,50)
        self.assertFalse(any(r['kind']=='Material insuficiente' for r in alerts.feed(load_snapshot())))
