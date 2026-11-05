import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from streamlit.testing.v1 import AppTest
import db
from services import restock,origin,recipes,recipe_cart,inventory,production as p,alerts
from services.queries import load_snapshot
from tests import test_origin as fixture


class RestockTest(unittest.TestCase):
    setUp=fixture.OriginTest.setUp
    publish=fixture.OriginTest.publish

    def row(self,cid=None):return next(r for r in restock.rows() if r['id']==(cid or self.supplies['cable_id']))
    def minimum(self,value,cid=None):
        row=self.row(cid);restock.save_minimums([dict(component_id=row['id'],minimum=value,expected_revision=row['minimum_revision'])])
    def receive(self,qty,key='receipt',cid=None):return inventory.receive_manual(qty,'Stock','Reposición',component_id=cid or self.supplies['cable_id'],request_key=key)
    def order(self,qty,key='order'):return recipes.create_recipe_order(self.rid,qty,client='Cliente',request_key=key)

    def test_zero_without_minimum_is_quiet_and_negative_is_always_critical(self):
        self.assertFalse(self.row()['attention']);self.minimum(2)
        self.assertEqual((self.row()['state'],self.row()['net']),('Reponer',0))
        self.minimum(0);self.order(3)
        self.assertEqual((self.row()['net'],self.row()['physical'],self.row()['score']),(-3,0,100))
        self.assertEqual(inventory.load_inventory()['skus'],[])

    def test_minimum_boundary_and_disable_do_not_disable_negative_alerts(self):
        self.receive(3);self.minimum(2)
        self.assertFalse(self.row()['attention']);self.order(1)
        self.assertEqual((self.row()['net'],self.row()['state'],self.row()['replenish']),(2,'Reponer',1))
        self.minimum(0);self.assertFalse(self.row()['attention'])
        self.order(3,'more');self.assertTrue(self.row()['critical'])

    def test_multiple_orders_and_basket_commit_missing_units_once_and_retry_does_not_duplicate(self):
        self.receive(2);oid=self.order(4)
        self.assertEqual(self.order(4),oid)
        row=self.row();self.assertEqual((row['physical'],row['reserved'],row['pending'],row['net']),(2,2,2,-2))
        plan=recipe_cart.quote([dict(recipe_id=self.rid,quantity=3),dict(recipe_id=self.rid,quantity=2)])
        preview=next(r for r in restock.projection(plan) if r['id']==row['id'])
        self.assertEqual((preview['needed'],preview['net_after']),(5,-7))
        recipe_cart.create_order([dict(recipe_id=self.rid,quantity=3),dict(recipe_id=self.rid,quantity=2)],client='Otro',request_key='basket')
        self.assertEqual(self.row()['net'],-7)
        self.assertEqual(self.row()['committed'],9)

    def test_receipt_reservation_reversal_and_draft_deletion_recalculate_without_double_deduction(self):
        oid=self.order(4);self.assertEqual(self.row()['net'],-4)
        mid=self.receive(5);self.assertEqual(self.row()['net'],1)
        origin.reserve_supplies(oid)
        row=self.row();self.assertEqual((row['reserved'],row['pending'],row['net']),(4,0,1))
        with self.assertRaises(ValueError):inventory.reverse_movement(mid,'Ya reservado')
        p.delete_record('order',oid);self.assertEqual(self.row()['net'],5)
        inventory.reverse_movement(mid,'Entrada corregida');self.assertEqual(self.row()['net'],0)

    def test_concurrent_orders_both_issue_and_reserve_only_existing_physical_units(self):
        self.receive(1)
        with ThreadPoolExecutor(2) as pool:orders=list(pool.map(lambda k:self.order(2,k),('a','b')))
        self.assertEqual(len(set(orders)),2)
        row=self.row();self.assertEqual((row['physical'],row['reserved'],row['net']),(1,1,-3))
        with db.connect() as conn:self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_cancelled_order_releases_commitment_and_delivered_order_is_not_counted_again(self):
        oid=self.order(2)
        from utils.dates import timestamp
        with db.connect(write=True) as conn:conn.execute('INSERT INTO order_cancellations VALUES(?,?,?)',(oid,'Prueba',timestamp()))
        self.assertEqual(self.row()['net'],0)
        # A fulfilled order releases its demand when delivered; its physical outflow remains.
        other=self.order(1,'deliver')
        for component in next(o for o in load_snapshot()['orders'] if o['id']==other)['items'][0]['requirements']:
            inventory.receive_manual(1,'Stock','Completar',component_id=component['component_id'],request_key=f"complete-{component['component_id']}")
        origin.reserve_supplies(other)
        order=next(o for o in load_snapshot()['orders'] if o['id']==other)
        item=order['items'][0]
        # Finish manufactured components via normal jobs.
        for part in item['parts']:p.job_action(p.create_job(part['id'],part['quantity_required']),'finish')
        from services import board_moves
        order=next(o for o in load_snapshot()['orders'] if o['id']==other)
        board_moves.apply(other,'Salida',expected_token=board_moves.token(order),request_key='assembled')
        p.deliver_order(other)
        self.assertEqual(self.row()['net'],0)

    def test_minimum_edits_are_validated_and_stale_batch_rolls_back(self):
        rows=restock.rows();first=rows[0];second=rows[1]
        self.minimum(2,second['id'])
        with self.assertRaises(ValueError):restock.save_minimums([dict(component_id=first['id'],minimum=4,expected_revision=0),dict(component_id=second['id'],minimum=5,expected_revision=0)])
        self.assertEqual(self.row(first['id'])['minimum'],0)
        for bad in (True,-1,1.2,None):
            with self.assertRaises(ValueError):self.minimum(bad)
        with self.assertRaises(ValueError):restock.save_minimums([dict(component_id=self.shade,minimum=4,expected_revision=0)])

    def test_critical_signal_has_higher_priority_and_resolves_after_replenishment(self):
        self.minimum(2,self.supplies['bulb_id']);self.receive(3,'bulbs',self.supplies['bulb_id']);self.order(1)
        feed=[r for r in alerts.feed(load_snapshot()) if r['record_kind']=='Insumo']
        self.assertEqual([r['severity'] for r in feed],['red','red','orange'])
        self.assertGreater(feed[0]['score'],feed[-1]['score'])
        first=feed[0];alerts.resolve(first['identity'])
        changed=self.order(1,'another')
        current=next(r for r in alerts.feed(load_snapshot()) if r['record_kind']=='Insumo' and r['record_id']==first['record_id'])
        self.assertNotEqual(current['identity'],first['identity']);self.assertEqual(current['state'],'Pendiente')
        for cid in self.supplies.values():self.receive(5,f'refill-{cid}',cid)
        self.assertFalse(any(r['record_kind']=='Insumo' for r in alerts.feed(load_snapshot())))


class RestockUITest(unittest.TestCase):
    setUp=RestockTest.setUp
    publish=RestockTest.publish
    order=RestockTest.order
    row=RestockTest.row
    minimum=RestockTest.minimum
    def restock_screen(self):
        # Insumos share the general Inventario's "Insumos y consumibles" tab with consumibles.
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.session_state['collection_workspace']='Insumos y consumibles'
        return app.switch_page('views/collection.py').run()
    def test_restock_tab_works_with_empty_ledger_and_minimum_grid_saves(self):
        app=self.restock_screen()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        import hashlib,json
        draft=app.session_state['restock_minimum_draft']
        version=hashlib.sha256(json.dumps([(r['id'],r['minimum_revision']) for r in draft]).encode()).hexdigest()[:12]
        key='restock_editor_'+version
        app.session_state[key]={'edited_rows':{0:{'minimum':5}},'added_rows':[],'deleted_rows':[]}
        next(b for b in app.button if b.label=='Guardar mínimos').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertFalse(app.error,[e.value for e in app.error])
        self.assertTrue(any(r['minimum']==5 for r in restock.rows()),str([(r['id'],r['minimum']) for r in restock.rows()]))
        self.assertEqual(inventory.load_inventory()['skus'],[])

    def test_quiet_indicator_opens_restock_and_form_still_issues_negative_order(self):
        self.order(3)
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/collection.py').run()
        app.sidebar.button(key='notifications_open').click().run()
        app.button(key='sidebar_supplies_open').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.session_state['collection_workspace'],'Insumos y consumibles')
        self.assertFalse(app.warning);self.assertFalse(app.error)
        self.assertTrue(any('En negativo' in str(frame.value) for frame in app.dataframe))

    def test_cart_can_issue_order_with_negative_supply_balance(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.session_state['origin_cart_request']=dict(product_id=self.pid)
        app.switch_page('views/origen.py').run()
        app.button(key='cart_add').click().run()
        token=app.session_state['origin_sales_cart']['token']
        app.text_input(key='cart_'+token+'_client').set_value('Cliente sin insumos').run()
        self.assertFalse(app.button(key='cart_submit').disabled)
        app.button(key='cart_submit').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception]);self.assertFalse(app.error)
        self.assertEqual(len(load_snapshot()['orders']),1)
        self.assertEqual(self.row()['net'],-1)

    def test_stale_minimum_grid_preserves_external_change(self):
        app=self.restock_screen()
        draft=app.session_state['restock_minimum_draft'];self.minimum(2,draft[0]['id'])
        import hashlib,json
        version=hashlib.sha256(json.dumps([(r['id'],r['minimum_revision']) for r in draft]).encode()).hexdigest()[:12]
        app.session_state['restock_editor_'+version]={'edited_rows':{0:{'minimum':5}},'added_rows':[],'deleted_rows':[]}
        next(b for b in app.button if b.label=='Guardar mínimos').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertTrue(any('otra ventana' in e.value for e in app.error));self.assertEqual(self.row(draft[0]['id'])['minimum'],2)
