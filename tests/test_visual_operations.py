import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from streamlit.testing.v1 import AppTest
import db
from services import production as p,board_moves as moves,photos,inventory,recipes,operations
from services.queries import load_snapshot
from services.order_board import tracking

class VisualOperationsTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'test.db'
        env=patch.dict(os.environ,NIMUS_DB_PATH=str(self.path));env.start();self.addCleanup(env.stop)
        db.init_db()
        self.oid=p.create_order('Pedido visual','Cliente')
        self.iid=p.create_item(self.oid,'Producto',2)
        self.pid=p.create_part(self.iid,'Base',2,'Impresión 3D','PLA')
        self.jid=p.create_job(self.pid,2)

    def order(self):return next(o for o in load_snapshot()['orders'] if o['id']==self.oid)
    def move(self,target,key='request',**kw):
        return moves.apply(self.oid,target,expected_token=moves.token(self.order()),request_key=key,**kw)
    def image(self,size=(2000,1000),mode='RGB',fmt='JPEG'):
        buf=io.BytesIO();Image.new(mode,size).save(buf,fmt);return buf.getvalue()

    def test_real_start_preparation_reopen_delivery_and_idempotency(self):
        order=self.order();token=moves.token(order)
        moves.apply(self.oid,'Producir',expected_token=token,request_key='start',job_id=self.jid)
        moves.apply(self.oid,'Producir',expected_token=token,request_key='start',job_id=self.jid)
        self.assertEqual(tracking(self.order())['lane'],'Producir')
        self.assertEqual(self.order()['completed_total'],0)
        p.job_action(self.jid,'finish')
        self.assertEqual(tracking(self.order())['lane'],'Preparar')
        self.move('Salida','prepare')
        self.assertEqual(tracking(self.order())['lane'],'Salida')
        self.assertTrue(self.order()['items'][0]['checked_at'])
        self.move('Preparar','reopen')
        self.assertFalse(self.order()['stages']['dispatch']['checked_at'])
        self.move('Salida','prepare_again');self.move('Entregados','deliver')
        self.assertEqual(self.order()['status'],'Entregado')
        self.assertEqual(len(operations.history(self.oid)),5)
        with self.assertRaises(ValueError):self.move('Preparar','delivered_readonly')

    def test_stale_blocked_incomplete_and_wrong_job_cannot_mutate(self):
        stale=moves.token(self.order());operations.update_item(self.iid,label='Caja',expected_revision=0)
        with self.assertRaisesRegex(ValueError,'otra ventana'):
            moves.apply(self.oid,'Producir',expected_token=stale,request_key='stale',job_id=self.jid)
        before=load_snapshot()
        for target in ('Preparar','Salida','Entregados','Planificar'):
            with self.assertRaises(ValueError):self.move(target,'invalid_'+target)
        with self.assertRaises(ValueError):self.move('Producir','wrong',job_id=999)
        self.assertEqual(before,load_snapshot())
        p.set_order_blocked(self.oid,True)
        with self.assertRaisesRegex(ValueError,'bloqueo'):self.move('Producir','blocked',job_id=self.jid)
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM board_requests').fetchone()[0],0)

    def test_machine_conflict_rolls_back_entire_movement(self):
        job=load_snapshot()['jobs'][0]
        p.update_job(self.jid,quantity=2,quantity_completed=0,status='En cola',machine_id=1,priority='Media',expected_revision=job['updated_at'])
        p.update_machine(1,'Mantenimiento')
        before=load_snapshot()
        with self.assertRaises(ValueError):self.move('Producir','conflict',job_id=self.jid)
        self.assertEqual(before,load_snapshot())
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM operation_events').fetchone()[0],0)

    def test_photo_validation_resize_conflicts_fallback_and_backup(self):
        cid=recipes.create_component('Pantalla','PLA','Impresión 3D')
        inventory.receive_manual(3,'Stock','Inicio',component_id=cid,request_key='entry')
        sku=inventory.load_inventory()['skus'][0]
        before=inventory.load_inventory()
        photos.save('component',cid,self.image())
        photo=photos.for_sku(sku)
        self.assertEqual((photo['width'],photo['height']),(1600,800))
        photos.save('sku',sku['id'],self.image((90,110),'RGBA','PNG'))
        own=photos.get('sku',sku['id']);self.assertEqual(own['mime'],'image/png')
        with self.assertRaises(ValueError):photos.save('sku',sku['id'],self.image())
        for content in (b'<svg/>',b'not an image',b'',b'x'*(photos.MAX_BYTES+1)):
            with self.assertRaises(ValueError):photos.save('sku',sku['id'],content,expected_revision=own['revision'])
        self.assertEqual(inventory.load_inventory(),before)
        backup=db.backup_database(label='photo-test')
        with db.connect(backup) as conn:
            self.assertEqual(conn.execute('SELECT content FROM product_photos WHERE sku_id=?',(sku['id'],)).fetchone()[0],own['content'])
        photos.remove('sku',sku['id'],expected_revision=own['revision'])
        self.assertEqual(photos.for_sku(sku)['component_id'],cid)

    def test_additive_migration_preserves_every_existing_record(self):
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE product_photos');conn.execute('DROP TABLE board_requests');conn.execute('PRAGMA user_version=16')
        before=load_snapshot();db.init_db();self.assertEqual(before,load_snapshot())
        with db.connect() as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)

    def test_stock_movement_requires_review_and_releases_reserved_pieces(self):
        cid=recipes.create_component('Base stock','PLA','Impresión 3D',collection='Origen')
        product=recipes.create_product('Lámpara stock',collection='Origen')
        rid=recipes.publish_recipe(product,[dict(component_id=cid,quantity=1)])
        inventory.receive_manual(3,'Colección','Entrada',component_id=cid,request_key='stock_entry')
        oid=recipes.create_recipe_order(rid,2,fulfillment='Stock',request_key='stock_order')
        order=next(o for o in load_snapshot()['orders'] if o['id']==oid)
        moves.apply(oid,'Salida',expected_token=moves.token(order),request_key='stock_prepare')
        order=next(o for o in load_snapshot()['orders'] if o['id']==oid)
        self.assertTrue(order['stages']['revision']['checked_at'])
        self.assertFalse(order['stages']['packing']['checked_at'])
        self.assertFalse(order['stages']['dispatch']['checked_at'])
        moves.apply(oid,'Entregados',expected_token=moves.token(order),request_key='stock_deliver')
        sku=inventory.load_inventory()['skus'][0]
        self.assertEqual((sku['stock'],sku['unassigned'],sku['reserved']),(2,1,0))

    def test_kanban_mount_and_photo_gallery_dialog(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/orders.py').run();self.assertFalse(app.exception)
        app.button_group(key='orders_view').set_value('Lista').run()
        self.assertTrue(app.button(key=f'orders_open_{self.oid}'))
        inventory.receive_manual(3,'Stock','Inicio',product='Producto',part='Base',material='PLA',process='Impresión 3D',request_key='ui_entry')
        # A Colección Origen piece: managed in Colección Origen → Inventario with the same gallery.
        app.session_state['origin_workspace']='Inventario'
        app.switch_page('views/origen.py').run();self.assertFalse(app.exception)
        app.button_group(key='origin_stock_view').set_value('Galería').run();self.assertFalse(app.exception)
        app.button(key='origin_stock_gallery_open_1').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['origin_stock_view'],'Tabla y ficha')
        self.assertEqual(app.session_state['origin_stock_selected'],1)
        app.button_group(key='origin_stock_view').set_value('Galería').run()
        app.button(key='origin_stock_gallery_photo_1').click().run();self.assertFalse(app.exception)
        self.assertTrue(app.get('file_uploader'))
