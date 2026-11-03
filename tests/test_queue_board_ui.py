import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import production as p
from services.queries import load_snapshot

class QueueBoardUITest(unittest.TestCase):
    def test_busy_machine_context_survives_filters_and_view_changes(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(tmp)/'test.db')}):
            db.init_db()
            oid=p.create_order('Origen','Cliente')
            iid=p.create_item(oid,'Lámpara',6);pid=p.create_part(iid,'Base',6,'Impresión 3D','PLA')
            first=p.create_job(pid,2,1);second=p.create_job(pid,2,1);external=p.create_job(pid,2)
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run().switch_page('views/queue.py').run()
            app.button(key=f'queue_{first}_start').click().run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            app.selectbox(key='queue_status').set_value('En cola').run()
            self.assertTrue(app.button(key=f'queue_{second}_start').disabled)
            self.assertTrue(any('En marcha fuera de estos filtros' in w.value for w in app.info))
            self.assertFalse(app.button(key=f'queue_{external}_start').disabled)
            app.text_input(key='queue_search').set_value('PLA').run()
            app.session_state['queue_view']='Calendario';app.run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            app.session_state['queue_view']='Operar';app.run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(app.button(key=f'queue_{second}_start').disabled)
            app.session_state['queue_view']='Tabla';app.run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertEqual(len(app.dataframe[0].value),2)
            app.switch_page('views/development.py').run();app.switch_page('views/queue.py').run()
            self.assertEqual(app.text_input(key='queue_search').value,'PLA')
            self.assertEqual(app.session_state['queue_view'],'Tabla')
            self.assertEqual(sum(j['status']=='En producción' for j in load_snapshot()['jobs']),1)
