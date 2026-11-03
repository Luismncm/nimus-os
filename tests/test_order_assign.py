import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import production as p
from services.order_progress import breakdown, piece_rows
from services.queries import load_snapshot
from tests import test_order_board as fixture


class OrderAssignTest(unittest.TestCase):
    setUp=fixture.OrderBoardTest.setUp
    order=fixture.OrderBoardTest.order

    def jobs(self):return [(j['part_id'],j['machine_id'],j['quantity']) for j in load_snapshot()['jobs']]

    def test_breakdown_states_add_up_for_part_item_and_order(self):
        base=p.create_part(self.iid,'Base',10,'Impresión 3D','PLA')
        running=p.create_job(base,4,1);p.job_action(running,'start')
        job=next(j for j in load_snapshot()['jobs'] if j['id']==running)
        p.record_progress(running,1,expected_revision=job['updated_at'])
        p.create_job(base,3,2)
        order=self.order();part=next(x for i in order['items'] for x in i['parts'] if x['id']==base)
        self.assertEqual({k:breakdown(part)[k] for k in ('required','completed','running','queued','unassigned')},
                         dict(required=10,completed=1,running=3,queued=3,unassigned=3))
        for record in (part,order['items'][0],order):
            b=breakdown(record)
            self.assertEqual(b['completed']+b['running']+b['queued']+b['unassigned'],b['required'])
        row=next(r for r in piece_rows(order['items'][0]) if r['name']=='Base')
        self.assertEqual((row['to_make'],row['completed'],row['running'],row['queued'],row['unassigned']),(10,1,3,3,3))

    def test_order_jobs_are_created_together_or_not_at_all(self):
        base=p.create_part(self.iid,'Base',4,'Impresión 3D','PLA')
        p.create_order_jobs(self.oid,[dict(part_id=self.pid,machine_id=1,quantity=2),dict(part_id=base,machine_id=1,quantity=1),
                                      dict(part_id=base,machine_id=None,quantity=3)])
        self.assertEqual(self.jobs(),[(self.pid,1,2),(base,1,1),(base,None,3)])
        tapa=p.create_part(self.iid,'Tapa',2,'Impresión 3D','PLA')
        other=p.create_part(p.create_item(p.create_order('Otro'),'Objeto',1),'Pieza',1,'Ensamble')
        before=load_snapshot()
        # Tapa fits, but Base is already fully assigned: neither job may be saved.
        with self.assertRaises(ValueError):
            p.create_order_jobs(self.oid,[dict(part_id=tapa,machine_id=1,quantity=2),dict(part_id=base,machine_id=2,quantity=1)])
        self.assertEqual(load_snapshot(),before)
        with self.assertRaises(ValueError):p.create_order_jobs(self.oid,[dict(part_id=other,machine_id=None,quantity=1)])
        with self.assertRaises(ValueError):p.create_order_jobs(self.oid,[dict(part_id=tapa,machine_id=1,quantity=0)])
        self.assertEqual(load_snapshot(),before)

    def test_bulk_window_assigns_every_pending_piece_of_the_order(self):
        base=p.create_part(self.iid,'Base',4,'Impresión 3D','PLA')
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=25).run()
        app.switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{self.oid}').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.button(key=f'order_step_next_{self.oid}').label,'Repartir piezas')
        self.assertIn(f'item_bulk_split_{self.iid}',[b.key for b in app.button])
        app.button(key=f'order_step_next_{self.oid}').click().run()
        scope=f'bulk_split_{self.oid}_all'
        app.button(key=scope+'_auto').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key=scope+'_save').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        order=self.order()
        self.assertEqual(breakdown(order)['unassigned'],0)
        self.assertEqual(sum(q for part,_,q in self.jobs() if part==base),4)
        self.assertNotIn(f'item_bulk_split_{self.iid}',[b.key for b in app.button])


if __name__=='__main__':
    unittest.main()
