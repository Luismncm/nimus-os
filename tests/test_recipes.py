import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import db
from services import production as p, inventory as inv, recipes as r, machines as m
from services.queries import load_snapshot
from services.templates import clone_item, reusable_items


class RecipeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'NIMUS_DB_PATH':str(Path(self.temp.name)/'recipes.db')})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.base = r.create_component('Base','PLA negro','Impresión 3D',collection='Origen')
        self.shade = r.create_component('Pantalla','PLA natural','Impresión 3D',collection='Origen')
        self.product = r.create_product('Lámpara Origen',collection='Origen')
        self.recipe = r.publish_recipe(self.product,[dict(component_id=self.base,quantity=1),dict(component_id=self.shade,quantity=2)])

    def order(self, quantity=5, **kwargs):
        return r.create_recipe_order(self.recipe,quantity,client='Cliente Norte',**kwargs)

    def snapshot_order(self, oid):
        return next(o for o in load_snapshot()['orders'] if o['id']==oid)

    def produce(self, oid):
        jobs = []
        for item in self.snapshot_order(oid)['items']:
            for part in item['parts']:
                jid = p.create_job(part['id'],part['quantity_unassigned'],None)
                p.job_action(jid,'finish')
                jobs.append(jid)
        return jobs

    def seed_stock(self, quantity=3):
        oid = self.order(quantity,fulfillment='Stock',use_stock=False)
        self.produce(oid)
        p.deliver_order(oid)
        return oid

    def assert_conserved(self):
        for row in inv.load_inventory()['skus']:
            self.assertEqual(row['produced'],row['unassigned']+row['stock']+row['b2b']+row['delivered'])
            self.assertGreaterEqual(row['available_collection'],0)
            self.assertGreaterEqual(row['available_stock'],0)

    def test_shortages_reservations_production_and_delivery(self):
        self.seed_stock(3)
        plan = r.quote_order(self.recipe,5)
        self.assertEqual([v['to_make'] for v in plan['lines']],[2,4])
        oid = self.order(5,expected_fingerprint=plan['fingerprint'])
        order = self.snapshot_order(oid)
        self.assertEqual((order['required_total'],order['completed_total']),(15,9))
        self.assertEqual([v['quantity_required'] for v in order['items'][0]['parts']],[2,4])
        self.assertEqual(sum(v['reserved'] for v in inv.load_inventory()['skus']),9)
        for sku in inv.load_inventory()['skus']:
            with self.assertRaises(ValueError):
                inv.distribute(sku['id'],'Stock','B2B',1,client='Otro')
        self.produce(oid)
        self.assertEqual(self.snapshot_order(oid)['status'],'Listo')
        p.deliver_order(oid)
        self.assertEqual(self.snapshot_order(oid)['completed_total'],15)
        self.assertEqual(sum(v['delivered'] for v in inv.load_inventory()['skus']),15)
        self.assertEqual(inv.load_inventory()['reservations'],[])
        with self.assertRaises(ValueError):
            p.deliver_order(oid)
        self.assert_conserved()

    def test_all_stock_no_fake_parts_or_jobs_and_draft_delete_releases(self):
        self.seed_stock(5)
        oid = self.order(3)
        order = self.snapshot_order(oid)
        self.assertEqual(order['status'],'Listo')
        self.assertFalse(order['items'][0]['parts'])
        p.delete_record('order',oid)
        self.assertEqual(sum(s['available_stock'] for s in inv.load_inventory()['skus']),15)
        self.assertFalse(inv.load_inventory()['reservations'])

    def test_delete_partially_reserved_draft_with_queued_jobs(self):
        self.seed_stock(2)
        oid = self.order(4)
        part = self.snapshot_order(oid)['items'][0]['parts'][0]
        p.create_job(part['id'],part['quantity_required'],1)
        p.delete_record('order',oid)
        self.assertEqual(sum(s['available_stock'] for s in inv.load_inventory()['skus']),6)

    def test_parallel_reservations_and_stale_preview(self):
        self.seed_stock(5)
        plan = r.quote_order(self.recipe,4)
        def reserve():
            try:
                return self.order(4,expected_fingerprint=plan['fingerprint'])
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:reserve(),range(2)))
        self.assertEqual(sum(v is not None for v in results),1)
        self.assertEqual(sum(s['available_stock'] for s in inv.load_inventory()['skus']),3)
        self.assert_conserved()

    def test_double_submit_reuses_order_and_rejects_changed_payload(self):
        oid = self.order(4,request_key='once')
        self.assertEqual(self.order(4,request_key='once'),oid)
        with self.assertRaises(ValueError):
            self.order(5,request_key='once')
        self.assertEqual(len(load_snapshot()['orders']),1)

    def test_produced_components_reserved_and_correction_reduces_coverage(self):
        oid = self.order(2)
        job = self.produce(oid)[0]
        self.assertEqual(sum(s['reserved'] for s in inv.load_inventory()['skus']),6)
        for sku in inv.load_inventory()['skus']:
            with self.assertRaises(ValueError):
                inv.distribute(sku['id'],'Colección','Stock',1)
        row = next(j for j in load_snapshot()['jobs'] if j['id']==job)
        p.update_job(job,quantity=row['quantity'],quantity_completed=1,status='Pausado',machine_id=None,
                     priority='Media',expected_revision=row['updated_at'])
        self.assertEqual(self.snapshot_order(oid)['completed_total'],5)
        self.assertEqual(sum(s['reserved'] for s in inv.load_inventory()['skus']),5)
        p.job_action(job,'finish')
        p.deliver_order(oid)
        with self.assertRaises(ValueError):
            p.record_progress(job,0,expected_revision=load_snapshot()['jobs'][0]['updated_at'])
        self.assert_conserved()

    def test_new_versions_do_not_change_existing_orders(self):
        oid = self.order(2)
        latest = r.publish_recipe(self.product,[dict(component_id=self.base,quantity=7)])
        self.assertNotEqual(latest,self.recipe)
        order = self.snapshot_order(oid)
        self.assertEqual(order['required_total'],6)
        self.assertEqual(order['items'][0]['recipe_version'],1)
        with self.assertRaises(sqlite3.IntegrityError), db.connect(write=True) as conn:
            conn.execute('UPDATE recipe_lines SET quantity=99 WHERE recipe_id=?',(self.recipe,))
        with self.assertRaises(ValueError):
            p.create_item(oid,'Extra',1)
        with self.assertRaises(ValueError):
            p.delete_record('part',order['items'][0]['parts'][0]['id'])

    def test_legacy_stock_needs_explicit_compatible_link(self):
        oid = p.create_order('Anterior')
        iid = p.create_item(oid,'Modelo anterior',5,collection='Origen')
        pid = p.create_part(iid,'Base',5,'Impresión 3D','PLA negro')
        jid = p.create_job(pid,5,None)
        p.job_action(jid,'finish')
        sku = inv.load_inventory()['skus'][0]['id']
        self.assertEqual(r.quote_order(self.recipe,2)['lines'][0]['reserved'],0)
        with self.assertRaises(ValueError):
            r.link_inventory(sku,self.shade)
        r.link_inventory(sku,self.base)
        order = self.order(2)
        self.assertEqual(self.snapshot_order(order)['completed_total'],2)
        before = load_snapshot()
        job = next(j for j in before['jobs'] if j['id']==jid)
        with self.assertRaises(ValueError):
            p.update_job(jid,quantity=5,quantity_completed=1,status='Pausado',machine_id=None,priority='Media',expected_revision=job['updated_at'])
        self.assertEqual(load_snapshot(),before)
        self.assert_conserved()

    def test_stock_closure_is_free_and_cannot_reverse_historical_order(self):
        oid = self.seed_stock(3)
        self.assertEqual(sum(s['available_stock'] for s in inv.load_inventory()['skus']),9)
        movements = [v for v in inv.load_inventory()['movements'] if v['order_id']==oid]
        with self.assertRaises(ValueError):
            inv.reverse_movement(movements[0]['id'],'Reabrir')
        second = self.order(2,fulfillment='Stock')
        p.deliver_order(second)
        self.assertEqual(sum(s['available_stock'] for s in inv.load_inventory()['skus']),9)
        self.assert_conserved()

    def test_general_components_and_clone_import(self):
        oid = p.create_order('Personalizado')
        iid = p.create_item(oid,'Soporte',2)
        p.create_part(iid,'Soporte central',4,'Impresión 3D','PETG')
        rid = r.import_item_recipe(iid)
        copy = clone_item(oid,iid,3)
        self.assertEqual(next(i for i in load_snapshot()['items'] if i['id']==copy)['required_total'],6)
        self.assertEqual(len(reusable_items()),2)
        new = r.create_recipe_order(rid,2,fulfillment='Stock',use_stock=False)
        self.produce(new)
        p.deliver_order(new)
        self.assertEqual(inv.load_inventory()['skus'][0]['collection'],'General')
        self.assert_conserved()


class MachineTest(unittest.TestCase):
    setUp = RecipeTest.setUp
    order = RecipeTest.order
    snapshot_order = RecipeTest.snapshot_order
    def test_machine_lifecycle_and_history(self):
        mid = m.save_machine(' p5 ','Bambu A1')
        m.save_machine('P5','Bambu A1 Mini','Mantenimiento',machine_id=mid)
        with self.assertRaises(ValueError):
            m.save_machine('p5','Duplicada')
        oid = self.order(1)
        part = self.snapshot_order(oid)['items'][0]['parts'][0]
        jid = p.create_job(part['id'],1,mid)
        with self.assertRaises(ValueError):
            m.remove_machine(mid)
        with self.assertRaises(ValueError):
            m.archive_machine(mid)
        m.save_machine('P5','Bambu A1','Disponible',machine_id=mid)
        p.job_action(jid,'start')
        with self.assertRaises(ValueError):
            m.save_machine('P5','Bambu A1','Disponible',machine_id=mid)
        p.job_action(jid,'finish')
        m.archive_machine(mid)
        self.assertNotIn(mid,[row['id'] for row in load_snapshot()['machines']])
        self.assertEqual(next(j for j in load_snapshot()['jobs'] if j['id']==jid)['machine_code'],'P5')
        m.archive_machine(mid,False)
        other = m.save_machine('P6','Eliminar')
        m.remove_machine(other)
        self.assertNotIn(other,[row['id'] for row in load_snapshot()['all_machines']])
