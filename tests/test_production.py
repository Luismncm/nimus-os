from __future__ import annotations

import csv
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import db
from services import production as s
from services.queries import dashboard, export_rows, csv_bytes, filter_jobs, load_snapshot
from utils.calculations import progress


class ProductionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        self.env = patch.dict(os.environ,{"NIMUS_DB_PATH":str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.order = s.create_order("Expo Deco","Cliente","2026-10-05","Alta")
        self.item = s.create_item(self.order,"Lámpara",10)
        self.part = s.create_part(self.item,"Base",10,"Impresión 3D")

    def snapshot(self):
        return load_snapshot()

    def job(self, job_id):
        return next(j for j in self.snapshot()["jobs"] if j["id"] == job_id)

    def edit(self, job_id, **changes):
        job = self.job(job_id)
        values = {k:job[k] for k in ("quantity","quantity_completed","status","machine_id","priority","expected_end","notes")}
        values.update(changes)
        s.update_job(job_id,**values)

    def test_split_progress_32_of_40_and_weighted_items(self):
        for name in ("Pantalla","Tapa","Placa"):
            s.create_part(self.item,name,10,"Impresión 3D")
        for index,part in enumerate(self.snapshot()["parts"]):
            jid = s.create_job(part["id"],10)
            self.edit(jid,quantity_completed=10 if index < 3 else 2)
        result = self.snapshot()
        self.assertEqual(result["orders"][0]["progress"],80)
        self.assertEqual(result["items"][0]["completed_total"],32)
        item2 = s.create_item(self.order,"Otro",1)
        s.create_part(item2,"Grande",60,"Ensamble")
        self.assertEqual(self.snapshot()["orders"][0]["progress"],32)
        self.assertEqual(progress(0,0),0)

    def test_split_4_4_2_no_double_count(self):
        for quantity,machine in ((4,1),(4,2),(2,3)):
            jid=s.create_job(self.part,quantity,machine)
            s.job_action(jid,"finish")
        result=self.snapshot()
        self.assertEqual(result["parts"][0]["quantity_completed"],10)
        self.assertEqual(result["orders"][0]["required_total"],10)
        self.assertEqual(result["orders"][0]["status"],"Listo")

    def test_capacity_and_reduction(self):
        s.create_job(self.part,6,1)
        with self.assertRaises(s.ValidationError): s.create_job(self.part,5,2)
        with self.assertRaises(s.ValidationError): s.update_part(self.part,"Base",5,"Impresión 3D")
        self.assertEqual(len(self.snapshot()["jobs"]),1)

    def test_concurrent_assignment_serialized(self):
        def create():
            try:
                s.create_job(self.part,6)
                return True
            except s.ValidationError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _:create(),range(2))),[False,True])

    def test_invalid_quantities_and_statuses_rejected(self):
        for invalid in (0,-1,1.5,True):
            with self.subTest(value=invalid):
                with self.assertRaises(s.ValidationError): s.create_job(self.part,invalid)
        jid=s.create_job(self.part,4)
        for invalid in (-1,5,1.5):
            with self.assertRaises(s.ValidationError): self.edit(jid,quantity_completed=invalid)
        with self.assertRaises(s.ValidationError): self.edit(jid,status="Listo")
        with self.assertRaises(s.ValidationError): self.edit(jid,status="Terminado",quantity_completed=2)
        self.assertEqual(self.job(jid)["quantity_completed"],0)

    def test_partial_completion_pause_release_and_finish(self):
        jid=s.create_job(self.part,10,1)
        s.job_action(jid,"start")
        first_start=self.job(jid)["started_at"]
        self.edit(jid,quantity_completed=4)
        self.assertEqual(self.snapshot()["orders"][0]["progress"],40)
        self.assertEqual(self.snapshot()["machines"][0]["status"],"Imprimiendo")
        s.job_action(jid,"pause")
        self.assertEqual(self.snapshot()["machines"][0]["status"],"Disponible")
        s.job_action(jid,"start")
        self.assertEqual(self.job(jid)["started_at"],first_start)
        s.job_action(jid,"finish")
        self.assertEqual(self.job(jid)["quantity_completed"],10)
        self.assertIsNotNone(self.job(jid)["completed_at"])
        self.assertEqual(self.snapshot()["machines"][0]["status"],"Disponible")

    def test_machine_conflicts_and_maintenance(self):
        a=s.create_job(self.part,5,1)
        b=s.create_job(self.part,5,1)
        s.job_action(a,"start")
        with self.assertRaises(s.ValidationError): s.job_action(b,"start")
        with self.assertRaises(s.ValidationError): s.update_machine(1,"Mantenimiento")
        s.job_action(a,"pause")
        s.update_machine(1,"Mantenimiento")
        with self.assertRaises(s.ValidationError): s.job_action(b,"start")
        with self.assertRaises(s.ValidationError): s.update_machine(2,"Imprimiendo")

    def test_machine_reassignment_releases_old(self):
        jid=s.create_job(self.part,5,1)
        s.job_action(jid,"start")
        self.edit(jid,machine_id=2)
        machines=self.snapshot()["machines"]
        self.assertEqual([m["status"] for m in machines[:2]],["Disponible","Imprimiendo"])

    def test_off_machine_work_and_automatic_full_completion(self):
        jid=s.create_job(self.part,10)
        s.job_action(jid,"start")
        self.edit(jid,quantity_completed=10)
        self.assertEqual(self.job(jid)["status"],"Terminado")
        self.assertTrue(all(m["status"] == "Disponible" for m in self.snapshot()["machines"]))

    def test_blocked_order_and_job(self):
        jid=s.create_job(self.part,10,1)
        s.set_order_blocked(self.order,True)
        with self.assertRaises(s.ValidationError): s.job_action(jid,"start")
        self.assertIsNone(dashboard(self.snapshot())["next_job"])
        s.set_order_blocked(self.order,False)
        s.job_action(jid,"start")
        s.job_action(jid,"block")
        self.assertEqual(self.snapshot()["orders"][0]["status"],"Bloqueado")
        self.assertEqual(self.snapshot()["machines"][0]["status"],"Disponible")
        s.job_action(jid,"unblock")
        self.assertEqual(self.snapshot()["orders"][0]["status"],"En producción")

    def test_finished_correction_reopens_order(self):
        jid=s.create_job(self.part,10)
        s.job_action(jid,"finish")
        self.edit(jid,quantity_completed=8,status="Pausado")
        self.assertEqual(self.snapshot()["orders"][0]["progress"],80)
        self.assertEqual(self.snapshot()["orders"][0]["status"],"En producción")
        self.assertIsNone(self.job(jid)["completed_at"])

    def test_manual_block_allows_recording_existing_run_but_not_new_start(self):
        jid=s.create_job(self.part,10,1)
        s.job_action(jid,"start")
        s.set_order_blocked(self.order,True)
        self.edit(jid,quantity_completed=4)
        self.assertEqual(self.job(jid)["quantity_completed"],4)
        s.job_action(jid,"pause")
        with self.assertRaises(s.ValidationError): s.job_action(jid,"start")

    def test_delivered_retained_readonly(self):
        jid=s.create_job(self.part,10)
        with self.assertRaises(s.ValidationError): s.deliver_order(self.order)
        s.job_action(jid,"finish")
        s.deliver_order(self.order)
        for kind,record_id in (("order",self.order),("item",self.item),("part",self.part),("job",jid)):
            with self.assertRaises(s.ValidationError): s.delete_record(kind,record_id)
        with self.assertRaises(s.ValidationError): self.edit(jid,quantity_completed=5,status="Pausado")
        with self.assertRaises(s.ValidationError): s.create_item(self.order,"Extra",1)
        with self.assertRaises(s.ValidationError): s.update_order(self.order,project="Cambio",client="",deadline="",priority="Baja",notes="")
        self.assertEqual(self.snapshot()["orders"][0]["status"],"Entregado")
        self.assertEqual(dashboard(self.snapshot())["metrics"]["active_orders"],0)
        self.assertEqual(export_rows(self.snapshot())[0]["order_status"],"Entregado")

    def test_item_without_parts_cannot_deliver(self):
        jid=s.create_job(self.part,10)
        s.job_action(jid,"finish")
        s.create_item(self.order,"Falta despiece",1)
        self.assertEqual(self.snapshot()["orders"][0]["progress"],100)
        with self.assertRaises(s.ValidationError): s.deliver_order(self.order)

    def test_cascade_drafts_and_non_reused_codes(self):
        jid=s.create_job(self.part,10)
        s.delete_record("job",jid)
        next_job=s.create_job(self.part,10)
        self.assertGreater(next_job,jid)
        s.delete_record("order",self.order)
        data=self.snapshot()
        self.assertTrue(all(not data[key] for key in ("orders","items","parts","jobs")))
        self.assertGreater(s.create_order("Nuevo"),self.order)

    def test_started_or_finished_jobs_delete_freely_without_inventory_or_failure_consequence(self):
        jid=s.create_job(self.part,10)
        s.job_action(jid,"start")
        s.job_action(jid,"pause")
        self.edit(jid,quantity_completed=10,status="Terminado")
        # A corrected cost (job_consumption) has no history guarantee of its own; it must not block deletion.
        from services import consumption
        row=consumption.get(jid)
        consumption.save(jid,100,60,50000,2000,expected_revision=row['revision'],expected_job_revision=self.job(jid)['updated_at'])
        self.assertTrue(consumption.get(jid)['grams'])
        # A regular custom-order job never posts to inventory, so finishing it is no longer a wall.
        s.delete_record("job",jid)
        self.assertEqual(self.snapshot()["jobs"],[])
        # Same for a whole finished branch: order, item and part all go, history and all.
        jid=s.create_job(self.part,10)
        self.edit(jid,quantity_completed=10,status="Terminado")
        s.delete_record("order",self.order)
        data=self.snapshot()
        self.assertTrue(all(not data[key] for key in ("orders","items","parts","jobs")))

    def test_a_job_that_already_moved_inventory_stays(self):
        from services import inventory
        oid=s.create_order("Origen test")
        iid=s.create_item(oid,"Lámpara",1,collection="Origen")
        pid=s.create_part(iid,"Pantalla",2,"Impresión 3D","PLA")
        jid=s.create_job(pid,2)
        self.edit(jid,quantity_completed=2,status="Terminado")
        self.assertTrue(inventory.load_inventory()["movements"])
        with self.assertRaises(s.ValidationError): s.delete_record("job",jid)
        # The order and the part above it are blocked the same way.
        with self.assertRaises(s.ValidationError): s.delete_record("part",pid)
        with self.assertRaises(s.ValidationError): s.delete_record("order",oid)

    def test_foreign_keys_and_sql_constraints(self):
        jid=s.create_job(self.part,10)
        statements = [
            ("UPDATE production_jobs SET part_id=999 WHERE id=?",(jid,)),
            ("UPDATE production_jobs SET quantity_completed=-1 WHERE id=?",(jid,)),
            ("UPDATE production_jobs SET quantity=11 WHERE id=?",(jid,)),
            ("UPDATE production_jobs SET quantity=1.5 WHERE id=?",(jid,)),
            ("UPDATE production_jobs SET status='Terminado' WHERE id=?",(jid,)),
            ("UPDATE parts SET quantity_required=9 WHERE id=?",(self.part,)),
        ]
        for sql,params in statements:
            with self.subTest(sql=sql):
                with self.assertRaises(sqlite3.IntegrityError):
                    with db.connect(write=True) as conn: conn.execute(sql,params)
        with db.connect() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_sql_protects_delivered_descendants(self):
        jid=s.create_job(self.part,10)
        s.job_action(jid,"finish")
        s.deliver_order(self.order)
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(write=True) as conn: conn.execute("DELETE FROM parts WHERE id=?",(self.part,))

    def test_stale_update_rejected(self):
        jid=s.create_job(self.part,10)
        revision=self.job(jid)["updated_at"]
        s.job_action(jid,"start",expected_revision=revision)
        with self.assertRaises(s.ValidationError): s.job_action(jid,"finish",expected_revision=revision)
        with self.assertRaises(s.ValidationError): self.edit(jid,quantity_completed=5,expected_revision=revision)

    def test_dashboard_dates_and_suggestions(self):
        a=s.create_job(self.part,3,1,expected_end="2026-10-05 09:00")
        b=s.create_job(self.part,3,2,expected_end="2026-10-05 18:00")
        c=s.create_job(self.part,4,None,expected_end="2026-10-04 18:00",priority="Baja")
        s.update_machine(1,"Mantenimiento")
        result=dashboard(self.snapshot(),datetime(2026,10,5,12))
        self.assertEqual({j["id"] for j in result["overdue"]},{a,c})
        self.assertEqual({j["id"] for j in result["due_today"]},{a,b})
        self.assertEqual(result["next_job"]["id"],b)
        s.job_action(b,"finish")
        self.assertNotIn(b,{j["id"] for j in dashboard(self.snapshot(),datetime(2026,10,6))["overdue"]})

    def test_deadline_fallback_and_filter_combination(self):
        a=s.create_job(self.part,4,1)
        s.create_job(self.part,6,None,priority="Baja")
        result=dashboard(self.snapshot(),datetime(2026,10,6,0))
        self.assertEqual(len(result["overdue"]),2)
        self.assertEqual([j["id"] for j in filter_jobs(self.snapshot()["jobs"],machine=1,status="En cola",priority="Alta",order_id=self.order,process="Impresión 3D")],[a])
        self.assertEqual(len(filter_jobs(self.snapshot()["jobs"],machine="Sin máquina")),1)

    def test_csv_includes_empty_branches_and_unicode(self):
        s.create_order('Señalética, "A"')
        s.create_job(self.part,10)
        content=csv_bytes(export_rows(self.snapshot())).decode("utf-8-sig")
        rows=list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(len(rows),2)
        self.assertIn('Señalética, "A"',[r["project"] for r in rows])
        self.assertIn("quantity_completed",rows[0])
        self.assertIn("completed_quantity",rows[0])

    def test_backup_and_idempotence(self):
        backup=db.backup_database()
        db.init_db()
        with closing(sqlite3.connect(backup)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],1)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        self.assertEqual(len(self.snapshot()["machines"]),4)

    def test_invalid_dates_names_and_missing_records(self):
        with self.assertRaises(ValueError): s.create_order("X",deadline="2026-99-99")
        with self.assertRaises(ValueError): s.create_job(self.part,1,expected_end="hoy")
        with self.assertRaises(ValueError): s.create_job(self.part,1,expected_end="2026-10-05T10:00:00+00:00")
        with self.assertRaises(s.ValidationError): s.create_order("  ")
        with self.assertRaises(s.ValidationError): s.create_part(999,"X",1,"Ensamble")
        with self.assertRaises(s.ValidationError): s.create_job(self.part,1,999)


if __name__ == "__main__":
    unittest.main()
