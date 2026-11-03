from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

import db
from services import production as p, recipes as r, machines as m
from services.queries import load_snapshot
from tests import test_recipes as fixtures
from tests.ui_helpers import enter_option


class RecipeUITest(unittest.TestCase):
    setUp = fixtures.RecipeTest.setUp
    order = fixtures.RecipeTest.order
    snapshot_order = fixtures.RecipeTest.snapshot_order

    def app(self, page='views/orders.py'):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20)
        return app.run().switch_page(page).run()

    def clean(self,app):
        self.assertFalse(app.exception,[e.message for e in app.exception])

    def click(self,app,label):
        next(b for b in app.button if b.label==label).click().run()
        self.clean(app)

    def test_recipe_order_create_preview_and_detail(self):
        app = self.app()
        app.button(key='new_recipe_order').click().run()
        app.number_input(key='recipe_order_qty').set_value(4).run()
        self.clean(app)
        self.assertEqual(sum(app.dataframe[0].value['A fabricar']),12)
        enter_option(app,'recipe_order_client','Cliente demo')
        self.click(app,'Crear pedido y reservar piezas')
        order = load_snapshot()['orders'][0]
        self.assertEqual(order['required_total'],12)
        app.switch_page('views/orders.py').run()
        self.clean(app)
        self.assertTrue(any(m.value.startswith('**Piezas ·') for m in app.markdown))
        self.assertTrue(any((b.key or '').startswith('part_split_') for b in app.button))
        self.assertFalse(any(b.key==f'order_add_item_{order["id"]}' for b in app.button))

    def test_save_another_piece_retains_material_and_focus(self):
        oid = p.create_order('Demo')
        iid = p.create_item(oid,'Lámpara',10)
        app = self.app()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{oid}').click().run()
        app.button(key=f'item_add_part_{iid}').click().run()
        enter_option(app,'part_name','Base')
        enter_option(app,'part_material','PLA azul')
        self.click(app,'Guardar y agregar otra')
        self.assertEqual(app.selectbox(key='part_material').value,'PLA azul')
        self.assertIsNone(app.selectbox(key='part_name').value)
        self.assertTrue(app.session_state[f'item_panel_{iid}'])
        enter_option(app,'part_name','Tapa')
        self.click(app,'Guardar pieza')
        self.assertEqual([(part['name'],part['material']) for part in load_snapshot()['parts']],[('Base','PLA azul'),('Tapa','PLA azul')])

    def test_reuse_piece_and_complete_product(self):
        oid = p.create_order('Demo')
        iid = p.create_item(oid,'Modelo',2)
        p.create_part(iid,'Base especial',4,'Resina','Resina gris')
        app = self.app()
        app.button_group(key='orders_view').set_value('Lista').run()
        app.button(key=f'orders_open_{oid}').click().run()
        app.button(key=f'order_add_item_{oid}').click().run()
        app.segmented_control(key='item_mode').set_value('Reutilizar despiece').run()
        app.number_input(key='reuse_item_quantity').set_value(5)
        self.click(app,'Agregar producto con sus piezas')
        copy = load_snapshot()['items'][-1]
        self.assertEqual(copy['required_total'],10)
        app.button(key=f'item_add_part_{copy["id"]}').click().run()
        app.segmented_control(key='part_mode').set_value('Reutilizar pieza').run()
        self.clean(app)
        from services.templates import reusable_parts
        app.selectbox(key='part_template').set_value(reusable_parts()[0]['key']).run()
        self.click(app,'Agregar pieza')
        self.assertEqual(load_snapshot()['parts'][-1]['material'],'Resina gris')
        self.assertEqual(load_snapshot()['parts'][-1]['quantity_required'],10)

    def test_catalog_version_and_draft_survive_selections(self):
        app = self.app('views/catalog.py')
        self.clean(app)
        prefix=f'recipe_draft_{self.product}_1'
        app.button(key='catalog_selected_edit').click().run()
        grid=prefix+f'_grid_{self.base}_{self.shade}'
        app.session_state[grid]={'edited_rows':{0:{'quantity':3}},'added_rows':[],'deleted_rows':[]}
        app.run()
        app.multiselect(key=prefix+'_pieces').set_value([self.base]).run()
        self.assertEqual(app.session_state[prefix+'_store']['quantities'][self.base],3)
        app.button(key=prefix+'_publish').click().run()
        self.clean(app)
        self.assertEqual(r.load_catalog()['products'][0]['version'],2)
        self.assertEqual(r.quote_order(r.load_catalog()['products'][0]['recipe_id'],2)['lines'][0]['needed'],6)

    def test_machines_create_edit_delete_and_empty_views(self):
        app = self.app('views/machines.py')
        app.button(key='machine_add').click().run()
        app.text_input(key='machine_edit_code').set_value('TEST')
        app.text_input(key='machine_edit_name').set_value('Impresora de prueba')
        app.button(key='machine_details_save').click().run()
        self.clean(app)
        mid=next(m['id'] for m in load_snapshot()['machines'] if m['code']=='TEST')
        app.button(key=f'machine_edit_{mid}').click().run()
        app.text_input(key='machine_edit_name').set_value('Impresora editada')
        app.button(key='machine_details_save').click().run()
        self.clean(app)
        self.assertEqual(next(m for m in load_snapshot()['machines'] if m['id']==mid)['name'],'Impresora editada')
        app.button(key=f'machine_remove_{mid}').click().run()
        app.button(key='machine_remove_confirm').click().run()
        self.clean(app)
        for machine in load_snapshot()['machines']:
            m.remove_machine(machine['id'])
        for page in ('views/today.py','views/machines.py','views/queue.py'):
            app.switch_page(page).run()
            self.clean(app)
        self.assertEqual(load_snapshot()['machines'],[])
