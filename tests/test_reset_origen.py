import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from cotejo import reset_origen as reset
import db
from services import production as p, inventory as inv


class ResetOrigenTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        env=patch.dict(os.environ,NIMUS_DB_PATH=str(Path(temp.name)/'db.sqlite'))
        env.start();self.addCleanup(env.stop);db.init_db()
        oid=p.create_order('EXPO DECO');iid=p.create_item(oid,'CUMULO GRIS',1,collection='Origen')
        pid=p.create_part(iid,'Base',1,'Impresión 3D','PLA');p.job_action(p.create_job(pid,1),'finish');p.deliver_order(oid)
        for title in ('Reconocimientos','TAP BAR','Otro'):
            oid=p.create_order(title);iid=p.create_item(oid,title,1)
            pid=p.create_part(iid,'Pieza general',1,'Ensamble');p.job_action(p.create_job(pid,1),'finish')
            if oid==3: p.deliver_order(oid)
        oid=p.create_order('CUMULO GRIS');iid=p.create_item(oid,'CUMULO GRIS',1,collection='Origen')
        pid=p.create_part(iid,'Pantalla',1,'Impresión 3D','PLA');p.job_action(p.create_job(pid,1,1),'start')
        with db.connect(write=True) as c:c.execute("UPDATE orders SET fulfillment='Stock' WHERE id=5")
        mid=inv.receive_manual(2,'Stock','Conteo',sku_id=1,request_key='manual')
        inv.reverse_movement(mid,'Corregido')
        inv.receive_manual(4,'Stock','General',collection='General',product='Reconocimientos',part='Placa',process='Ensamble',request_key='general')

    def test_scoped_reset_preserves_other_rows_and_restores_guards(self):
        with db.connect() as c: plan=reset.plan(c);before=reset.retained(c,plan)
        with db.connect(write=True) as c: result=reset.execute(c,plan)
        self.assertEqual(result['removed']['orders'],2)
        with db.connect() as c:
            self.assertEqual(reset.retained(c,plan),before)
            self.assertEqual({r['id'] for r in c.execute('SELECT id FROM orders')},{2,3,4})
            self.assertEqual(c.execute("SELECT COUNT(*) FROM inventory_skus WHERE collection='Origen'").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT status FROM machines WHERE id=1").fetchone()[0],'Disponible')
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c:c.execute('DELETE FROM inventory_movements')
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c:c.execute('DELETE FROM orders WHERE id=3')

    def test_changed_scope_aborts_without_removing_guards(self):
        with db.connect() as c:plan=reset.plan(c)
        with db.connect(write=True) as c:c.execute("UPDATE orders SET notes='Cambio' WHERE id=5")
        with self.assertRaises(ValueError),db.connect(write=True) as c:reset.execute(c,plan)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],5)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='inventory_immutable_delete'").fetchone()[0],1)
