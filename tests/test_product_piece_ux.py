import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests import test_order_board as fixture
from services import production as p, operations as ops
from services.queries import load_snapshot


class ProductPieceUXTest(unittest.TestCase):
    setUp=fixture.OrderBoardTest.setUp
    order=fixture.OrderBoardTest.order

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=25).run()
        app.switch_page('views/orders.py').run()
        app.button_group(key='orders_view').set_value('Lista').run()
        return app.button(key=f'orders_open_{self.oid}').click().run()

    def test_mixed_rows_multiply_per_product_and_invalid_rows_are_atomic(self):
        rows=[dict(name='Tapa',units=2,process='Impresión 3D',material='PLA'),dict(name='Cable',units=1.0,process='Ensamble',material='Kit')]
        ids=p.create_part_rows(self.iid,rows)
        added=[r for r in load_snapshot()['parts'] if r['id'] in ids]
        self.assertEqual([r['quantity_required'] for r in added],[4,2])
        before=load_snapshot()
        for bad in ([dict(name='Bien',units=1,process='Ensamble'),dict(name='Mal',units=1.5,process='Ensamble')],rows,
                    [dict(name='Otro',units=True,process='Ensamble')]):
            with self.assertRaises(ValueError): p.create_part_rows(self.iid,bad)
            self.assertEqual(load_snapshot(),before)

    def test_bulk_review_preserves_labels_and_stale_batch_rolls_back(self):
        other=p.create_item(self.oid,'Otra lámpara',1)
        ops.update_item(self.iid,label='Caja 1',expected_revision=0)
        before=load_snapshot()
        with self.assertRaises(ValueError): ops.review_products(self.oid,{self.iid:0,other:0})
        self.assertEqual(load_snapshot(),before)
        ops.review_products(self.oid,{self.iid:1,other:0})
        self.assertTrue(all(i['checked_at'] for i in load_snapshot()['items']))
        self.assertEqual(load_snapshot()['items'][0]['label'],'Caja 1')
        self.assertEqual(load_snapshot()['jobs'],before['jobs'])
        with self.assertRaises(ValueError): ops.review_products(self.oid,{self.iid:2})

    def test_ui_stage_buttons_review_and_selected_piece(self):
        second=p.create_part(self.iid,'Base',2,'Ensamble','PLA')
        app=self.app()
        self.assertFalse(app.exception)
        # Every piece is listed with its own action and options; no selector in between.
        keys=[b.key for b in app.button]
        self.assertTrue({f'part_edit_{second}',f'part_edit_{self.pid}',f'part_split_{second}',f'part_split_{self.pid}'}<=set(keys))
        self.assertNotIn(f'piece_selected_{self.iid}',[s.key for s in app.selectbox])
        app.button(key=f'order_review_all_{self.oid}').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(self.order()['items'][0]['checked_at'])
        app.button(key=f'order_advance_{self.oid}_revision_0').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(self.order()['stages']['revision']['checked_at'])
        self.assertTrue(app.button(key=f'order_advance_{self.oid}_revision_1').disabled)

    def test_ui_grid_mode_and_job_transition_use_existing_guards(self):
        jid=p.create_job(self.pid,2)
        app=self.app()
        self.assertTrue(app.button(key=f'order_status_job_{jid}_start'))
        app.button(key=f'order_status_job_{jid}_start').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(load_snapshot()['jobs'][0]['status'],'En producción')
        app.button(key=f'item_parts_{self.iid}').click().run()
        app.button_group(key=f'parts_mode_{self.iid}').set_value('Tabla detallada').run()
        self.assertFalse(app.exception)
        self.assertTrue(any(b.label=='Agregar piezas de la tabla' for b in app.button))
        self.assertTrue(app.dataframe)
        app.session_state[f'parts_grid_{self.iid}']={
            'edited_rows':{0:{'name':'Tapa','units':2,'material':'PLA'}},
            'added_rows':[dict(name='Cable',units=1,process='Ensamble',material='Kit')],'deleted_rows':[]}
        next(b for b in app.button if b.label=='Agregar piezas de la tabla').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertFalse(app.error,[e.value for e in app.error])
        self.assertEqual([(r['name'],r['quantity_required']) for r in load_snapshot()['parts']][-2:],[('Tapa',4),('Cable',2)])
        # The first added piece is marked as new in the product's list.
        self.assertTrue(any('Nueva' in m.value and '**Tapa**' in m.value for m in app.markdown))
