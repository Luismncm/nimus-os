import unittest
from datetime import timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import assign_suggest as a, production as p
from services.queries import load_snapshot
from tests import test_development as fixture
from views.live_floor import progress_of
from tests.backends import sqlite_only


class AssignSuggestTest(unittest.TestCase):
    setUp=fixture.DevelopmentTest.setUp

    def plan(self,start,minutes):
        return dict(planned_start=start.isoformat(),duration_minutes=minutes,estimated_grams=None,actual_grams=None,material_rate_cents=None,machine_rate_cents=None)

    def test_loaded_filament_wins_unless_another_printer_frees_much_earlier(self):
        a.set_loaded(2,'PLA Prueba');a.set_loaded(1,'PETG Negro')
        self.assertEqual({m['id']:m['loaded_material'] for m in load_snapshot()['machines']}[2],'PLA Prueba')
        best=a.best(load_snapshot(),'pla prueba',60)
        self.assertEqual((best['machine']['id'],best['match']),(2,True))
        self.assertIn('material cargado',a.reason(best))
        # Machine 2 busy for 3 h: waiting is worse than a one-hour spool change elsewhere.
        oid=p.create_order('Lote','Cliente');iid=p.create_item(oid,'Pieza',1);pid=p.create_part(iid,'Base',1,'Impresión 3D','PLA Prueba')
        soon=(self.start-timedelta(hours=2)).replace(second=0,microsecond=0)
        p.create_job(pid,1,2,plan=self.plan(soon,180))
        best=a.best(load_snapshot(),'PLA Prueba',60)
        self.assertNotEqual(best['machine']['id'],2)
        self.assertTrue(best['change'])

    def test_machines_down_are_never_suggested_and_progress_is_estimated(self):
        p.update_machine(1,'Mantenimiento')
        self.assertNotIn(1,[r['machine']['id'] for r in a.rank(load_snapshot(),'PLA Prueba',30)])
        start=self.start-timedelta(hours=3)
        job=dict(current_run_started_at=start.isoformat(),estimated_finish=(start+timedelta(hours=4)).isoformat())
        done,left=progress_of(job,start+timedelta(hours=1))
        self.assertEqual((round(done,2),round(left)),(0.25,180))

    @sqlite_only

    def test_migration_from_29_adds_loadout(self):
        with db.connect(write=True) as conn:conn.execute('DROP TABLE machine_loadout');conn.execute('PRAGMA user_version=29')
        db.init_db();db.init_db()
        with db.connect() as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-filamento-cargado-v30*')))


class AssignSuggestUITest(unittest.TestCase):
    setUp=fixture.DevelopmentTest.setUp

    def test_floor_tiles_grouping_and_assign_all_to_suggested(self):
        a.set_loaded(3,'PLA Prueba')
        oid=p.create_order('Lote','Cliente');iid=p.create_item(oid,'Pieza',4);pid=p.create_part(iid,'Base',4,'Impresión 3D','PLA Prueba')
        p.create_job(pid,1,1)
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/queue.py').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertTrue(any('estimado por tiempo' in c.value for c in app.caption))
        app.button_group(key='queue_group').set_value('Estado').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertTrue(any(m.value.startswith('**:material/schedule: En cola**') for m in app.markdown))
        app.switch_page('views/orders.py').run();app.session_state['open_order_id']=oid;app.run()
        app.button(key=f'part_split_{pid}').click().run()
        app.button(key=f'order_assign_{oid}_split_{pid}').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        best=next(b for b in app.button if (b.label or '').startswith('Asignar todo a'))
        self.assertEqual(best.label,'Asignar todo a P3')
        best.click().run()
        self.assertEqual(app.number_input(key=f'split_{pid}_3').value,3)


if __name__=='__main__':
    unittest.main()
