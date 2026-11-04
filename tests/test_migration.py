import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import db
from services import production as s
from services.queries import load_snapshot
from tests.fixtures import legacy_v01 as legacy
from tests.backends import sqlite_only


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"old.db"
        self.env=patch.dict(os.environ,{"NIMUS_DB_PATH":str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        legacy.DATA_DIR=self.path.parent
        legacy.DB_PATH=self.path
        legacy.init_db()
        self.order=legacy.create_order("EXPO DECO","PURPLE","2026-10-06","Alta","Original")
        self.item=legacy.create_item(self.order,"BASES",10)
        self.part=legacy.create_part(self.item,"BASE",10,"Impresión 3D","PLA")

    @sqlite_only

    def test_migration_preserves_quantities_codes_notes_and_backup(self):
        jid=legacy.create_job(self.part,4,1,"Imprimiendo")
        legacy.update_job(jid,"Imprimiendo",2,1)
        db.init_db()
        snapshot=load_snapshot()
        self.assertEqual(snapshot["orders"][0]["notes"],"Original")
        self.assertEqual(snapshot["jobs"][0]["code"],"JOB-0001")
        self.assertEqual(snapshot["jobs"][0]["quantity_completed"],2)
        self.assertEqual(snapshot["orders"][0]["progress"],20)
        self.assertEqual(snapshot["machines"][0]["status"],"Imprimiendo")
        backups=list((self.path.parent/"backups").glob("*.db"))
        self.assertEqual(len(backups),1)
        with closing(sqlite3.connect(backups[0])) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT completed_quantity FROM production_jobs").fetchone()[0],2)
        db.init_db()
        self.assertEqual(len(list((self.path.parent/"backups").glob("*.db"))),1)

    @sqlite_only

    def test_partial_listo_not_invented(self):
        jid=legacy.create_job(self.part,10,None,"Listo")
        legacy.update_job(jid,"Listo",3,None)
        db.init_db()
        job=load_snapshot()["jobs"][0]
        self.assertEqual((job["status"],job["quantity_completed"]),("Pausado",3))
        self.assertIn("Migración",job["notes"])

    @sqlite_only

    def test_invalid_legacy_capacity_rolls_back_everything(self):
        legacy.create_job(self.part,8,1)
        legacy.create_job(self.part,8,2)
        with self.assertRaisesRegex(RuntimeError,"sobreasignadas"):
            db.init_db()
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM production_jobs").fetchone()[0],2)
            self.assertEqual(conn.execute("SELECT status FROM orders").fetchone()[0],"Abierto")
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        self.assertTrue(list((self.path.parent/"backups").glob("*.db")))

    @sqlite_only

    def test_duplicate_running_machine_aborts(self):
        legacy.create_job(self.part,5,1,"Imprimiendo")
        legacy.create_job(self.part,5,1,"Imprimiendo")
        with self.assertRaises(RuntimeError): db.init_db()
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM production_jobs").fetchone()[0],2)

    @sqlite_only

    def test_delivered_legacy_remains_historical_even_if_incomplete(self):
        legacy.update_order_status(self.order,"Entregado")
        db.init_db()
        self.assertEqual(load_snapshot()["orders"][0]["status"],"Entregado")

    @sqlite_only

    def test_preserves_deleted_id_sequence(self):
        oid=legacy.create_order("Borrador")
        with legacy.connect() as conn:
            conn.execute("DELETE FROM orders WHERE id=?",(oid,))
        db.init_db()
        self.assertGreater(s.create_order("Después"),oid)


if __name__ == "__main__":
    unittest.main()
