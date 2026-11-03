import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import inbound,inventory,restock,notifications
from tests import test_restock as fixture
from utils.dates import now


class InboundTest(unittest.TestCase):
    setUp=fixture.RestockTest.setUp
    publish=fixture.RestockTest.publish
    order=fixture.RestockTest.order

    def create(self,qty=12,key='incoming',**kw):
        return inbound.create(qty,'Stock','Pedido de cable',component_id=self.supplies['cable_id'],request_key=key,**kw)
    def receive(self,pid,qty,key='receive',**kw):
        return inbound.receive(pid,qty,expected_token=inbound.get(pid)['token'],request_key=key,**kw)
    def count(self,table):
        with db.connect() as c:return c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    def stock(self):
        return next((s['stock'] for s in inventory.load_inventory()['skus'] if s['component_id']==self.supplies['cable_id']),0)
    def fingerprint(self):
        with db.connect() as c:
            return {r[0]:[tuple(x) for x in c.execute(f'SELECT * FROM {r[0]} ORDER BY rowid')] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}

    def test_create_tracks_incoming_without_stock_reservations_expenses_or_payments(self):
        self.order(3);before=restock.rows();pid=self.create()
        row=inbound.get(pid)
        self.assertEqual((row['quantity'],row['received'],row['pending'],row['status']),(12,0,12,'Solicitado'))
        self.assertEqual(self.stock(),0)
        current=next(r for r in restock.rows() if r['id']==self.supplies['cable_id'])
        prior=next(r for r in before if r['id']==current['id'])
        self.assertEqual((current['net'],current['on_order']),(prior['net'],12))
        self.assertTrue(current['critical'])
        for t in ('inventory_movements','expenses','sales','sale_payments','expense_payments'):self.assertEqual(self.count(t),0)

    def test_create_retry_is_idempotent_and_changed_payload_rejected(self):
        pid=self.create();self.assertEqual(self.create(),pid)
        with self.assertRaises(ValueError):self.create(13)
        self.assertEqual(self.count('inventory_inbound_orders'),1)

    def test_partial_final_receipts_post_once_and_complete(self):
        pid=self.create();token=inbound.get(pid)['token']
        movement=self.receive(pid,5)
        self.assertEqual(inbound.receive(pid,5,expected_token=token,request_key='receive'),movement)
        self.assertEqual((self.stock(),inbound.get(pid)['pending'],inbound.get(pid)['status']),(5,7,'Recibido parcial'))
        self.receive(pid,7,'last')
        self.assertEqual((self.stock(),inbound.get(pid)['status']),(12,'Recibido'))
        self.assertEqual(self.count('inventory_movements'),2)
        with self.assertRaises(ValueError):self.receive(pid,1,'over')

    def test_reverse_receipt_reopens_order_and_reservations_still_protect_stock(self):
        pid=self.create();mid=self.receive(pid,12)
        inventory.reverse_movement(mid,'Error de recepción')
        row=inbound.get(pid)
        self.assertEqual((row['received'],row['pending'],row['status'],self.stock()),(0,12,'Solicitado',0))
        self.assertTrue(row['events'][0]['reversed'])
        self.receive(pid,12,'again');self.order(2)
        last=next(e['movement_id'] for e in reversed(inbound.get(pid)['events']) if e['movement_id'])
        with self.assertRaises(ValueError):inventory.reverse_movement(last,'Ya reservado')

    def test_cancel_remainder_keeps_received_stock_and_retry_is_safe(self):
        pid=self.create();self.receive(pid,5);token=inbound.get(pid)['token']
        eid=inbound.cancel(pid,'Proveedor sin existencias',expected_token=token,request_key='cancel')
        self.assertEqual(inbound.cancel(pid,'Proveedor sin existencias',expected_token=token,request_key='cancel'),eid)
        row=inbound.get(pid)
        self.assertEqual((row['status'],row['pending'],row['received'],self.stock()),('Cancelado',0,5,5))
        self.assertEqual(next(r for r in restock.rows() if r['id']==self.supplies['cable_id'])['on_order'],0)
        with self.assertRaises(ValueError):self.receive(pid,1,'cancelled')

    def test_followup_dates_and_stale_or_invalid_operations_leave_stock_unchanged(self):
        pid=self.create();old=inbound.get(pid);eta=now().date()+timedelta(days=3)
        inbound.follow_up(pid,supplier='Proveedor nuevo',expected_on=eta,notes='Guía 123',expected_token=old['token'],request_key='follow')
        row=inbound.get(pid);self.assertEqual((row['supplier'],row['expected_on']),('Proveedor nuevo',eta.isoformat()))
        with self.assertRaises(ValueError):inbound.receive(pid,1,expected_token=old['token'],request_key='stale')
        for qty,day in ((13,None),(1,now().date()+timedelta(days=1)),(1,now().date()-timedelta(days=1))):
            with self.subTest(qty=qty,day=day),self.assertRaises(ValueError):self.receive(pid,qty,'bad',received_on=day)
        self.assertEqual((self.stock(),self.count('inventory_movements')),(0,0))

    def test_failed_event_rolls_back_receipt_and_concurrent_receipt_cannot_duplicate(self):
        pid=self.create()
        with patch.object(inbound,'_event',side_effect=ValueError('Falla de prueba')),self.assertRaises(ValueError):self.receive(pid,5)
        self.assertEqual((self.stock(),self.count('inventory_movements')),(0,0))
        token=inbound.get(pid)['token']
        def receive(key):
            try:inbound.receive(pid,8,expected_token=token,request_key=key);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(receive,['a','b']))
        self.assertEqual(sum(results),1);self.assertEqual(self.stock(),8)

    def test_immutable_history_and_migration_from_22_preserve_all_original_rows(self):
        self.create()
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c:c.execute('DELETE FROM inventory_inbound_orders')
        with db.connect(write=True) as c:
            c.execute('DROP TABLE inventory_inbound_events');c.execute('DROP TABLE inventory_inbound_orders');c.execute('PRAGMA user_version=22')
        original=self.fingerprint();db.init_db();db.init_db()
        current=self.fingerprint()
        for table,rows in original.items():self.assertEqual(current[table],rows,table)
        with db.connect() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_notification_tracks_pending_and_disappears_on_receipt(self):
        pid=self.create(expected_on=now().date())
        row=next(r for r in notifications.load()['items'] if r['record_kind']=='Pedido de inventario')
        self.assertEqual((row['record_id'],row['label']),(pid,'Llega hoy'))
        self.receive(pid,12)
        self.assertFalse(any(r['record_kind']=='Pedido de inventario' for r in notifications.load()['items']))


class InboundUITest(unittest.TestCase):
    setUp=InboundTest.setUp
    publish=InboundTest.publish
    create=InboundTest.create
    receive=InboundTest.receive
    stock=InboundTest.stock
    fingerprint=InboundTest.fingerprint
    def app(self):return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/collection.py').run()
    def clean(self,a):self.assertFalse(a.exception,[e.message for e in a.exception])
    def screen(self,a):a.session_state['collection_workspace']='Compras';a.run();return a

    def test_new_order_then_partial_and_final_receipts_use_fresh_quantities(self):
        a=self.app();a.button(key='inventory_receive').click().run()
        next(x for x in a.button_group if x.label=='Registrar como').set_value('Pedido').run();self.clean(a)
        next(x for x in a.button_group if x.label=='Referencia').set_value('Pieza del catálogo').run()
        next(x for x in a.selectbox if x.label=='Pieza del catálogo').set_value(self.supplies['cable_id']).run()
        next(x for x in a.number_input if x.label=='Unidades pedidas').set_value(12)
        next(x for x in a.text_input if x.label=='Referencia del pedido *').set_value('Compra UI')
        next(x for x in a.number_input if x.label=='Total del pedido · MXN *').set_value(120)
        next(x for x in a.button if x.label=='Guardar pedido').click().run();self.clean(a)
        pid=inbound.list_orders()[0]['id'];self.assertEqual(a.session_state['collection_workspace'],'Compras');self.assertEqual(self.stock(),0)
        a.button(key='inbound_receive').click().run();self.clean(a)
        next(x for x in a.number_input if x.label=='Unidades recibidas').set_value(5)
        next(x for x in a.button if x.label=='Confirmar recepción').click().run();self.clean(a)
        self.assertEqual((self.stock(),inbound.get(pid)['pending']),(5,7))
        a.button(key='inbound_receive').click().run();self.clean(a)
        self.assertEqual(next(x for x in a.number_input if x.label=='Unidades recibidas').value,7)
        next(x for x in a.button if x.label=='Confirmar recepción').click().run();self.clean(a)
        self.assertEqual((self.stock(),inbound.get(pid)['status']),(12,'Recibido'))

    def test_sidebar_opens_exact_incoming_order_without_writing(self):
        pid=self.create();before=self.fingerprint();a=self.app()
        a.sidebar.button(key='notifications_open').click().run()
        next(x for x in a.button_group if x.key=='notifications_category').set_value('Pedidos').run()
        a.button(key=f'notification_open_Pedido de inventario:{pid}').click().run();self.clean(a)
        self.assertEqual(a.session_state['collection_workspace'],'Compras')
        self.assertEqual(a.session_state['inbound_selected'],pid)
        self.assertEqual(self.fingerprint(),before)

    def test_followup_and_cancel_partial_order_keep_received_units(self):
        pid=self.create();self.receive(pid,5);a=self.screen(self.app())
        a.button(key='inbound_follow').click().run();self.clean(a)
        next(x for x in a.text_input if x.label=='Proveedor').set_value('Proveedor UI')
        next(x for x in a.text_area if x.label=='Nota de seguimiento').set_value('Guía de paquetería')
        next(x for x in a.radio if x.label=='Estado').set_value('En camino')
        next(x for x in a.button if x.label=='Guardar seguimiento').click().run();self.clean(a)
        # Receipts outrank the manual stage: the order shows as partially received, the stage is kept.
        self.assertEqual((inbound.get(pid)['supplier'],inbound.get(pid)['stage'],inbound.get(pid)['status']),('Proveedor UI','En camino','Recibido parcial'))
        a.button(key='inbound_cancel').click().run();self.clean(a)
        next(x for x in a.text_input if x.label=='Motivo de cancelación *').set_value('No surtirán el resto')
        next(x for x in a.button if x.label=='Confirmar cancelación').click().run();self.clean(a)
        self.assertEqual((inbound.get(pid)['status'],self.stock()),('Cancelado',5))

    def test_origin_receipt_also_supports_pending_order(self):
        a=self.app().switch_page('views/origen.py').run()
        a.session_state['origin_workspace']='Componentes';a.session_state['origin_definition_group']='Insumos';a.run()
        next(x for x in a.selectbox if x.label=='Componente para gestionar').set_value(self.supplies['cable_id']).run()
        a.button(key='origin_supplies_receive').click().run()
        next(x for x in a.button_group if x.label=='Registrar como').set_value('Pedido').run();self.clean(a)
        next(x for x in a.number_input if x.label=='Unidades pedidas').set_value(4)
        a.text_input(key='origin_receipt_reason').set_value('Pedido Origen UI')
        next(x for x in a.number_input if x.label=='Total del pedido · MXN *').set_value(80)
        next(x for x in a.button if x.label=='Guardar pedido').click().run();self.clean(a)
        self.assertEqual((inbound.list_orders()[0]['pending'],self.stock()),(4,0))

