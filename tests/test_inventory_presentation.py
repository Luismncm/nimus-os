import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests import test_inventory_ui as fixture
from services import inventory as inv, inventory_view as view, recipes


class InventoryPresentationTest(unittest.TestCase):
    setUp=fixture.InventoryUITest.setUp
    seed=fixture.InventoryUITest.seed

    def prepare(self):
        self.seed()
        self.component=recipes.create_component('Base de catálogo','PLA','Impresión 3D',collection='General')
        product=recipes.create_product('Lámpara de prueba',collection='General')
        recipe=recipes.publish_recipe(product,[dict(component_id=self.component,quantity=1)])
        inv.receive_manual(5,'Stock','Conteo',component_id=self.component,request_key='catalog')
        self.order_id=recipes.create_recipe_order(recipe,2,client='Cliente',fulfillment='Cliente',request_key='recipe')
        self.catalog_sku=next(r['id'] for r in inv.load_inventory()['skus'] if r['component_id']==self.component)
        inv.distribute(self.catalog_sku,'Stock','B2B',2,client='Tienda',request_key='client')

    def test_physical_and_reserved_are_not_double_counted(self):
        self.prepare()
        rows=view.present(inv.load_inventory()['skus'])
        self.assertEqual(view.totals(rows),dict(physical=13,free=11,reserved=2,b2b=2))
        self.assertEqual(len(view.query(rows,state='Con reservas')),1)
        self.assertEqual(view.query(rows,search='catálogo')[0]['id'],self.catalog_sku)
        self.assertEqual(view.query(rows,line='Origen'),[])
        self.assertEqual({r['part'] for r in view.query(rows,search='base')},{'Base','Base de catálogo'})

    def test_zero_balance_reference_and_movement_labels(self):
        mid=inv.receive_manual(2,'Stock','Conteo',product='Placa',part='Placa',process='Grabado',collection='General',request_key='receipt')
        reversal=inv.reverse_movement(mid,'Corrección')
        data=inv.load_inventory()
        self.assertEqual(len(view.query(view.present(data['skus']),state='Sin saldo')),1)
        self.assertEqual(view.movement_state(next(r for r in data['movements'] if r['id']==mid)),'Revertido')
        self.assertEqual(view.movement_state(next(r for r in data['movements'] if r['id']==reversal)),'Reversión')

    def test_filters_selection_reservations_navigation_and_no_mutation(self):
        self.prepare()
        before=inv.load_inventory()
        app=self.app.run()
        app.session_state['collection_workspace']='Inventario'
        app.switch_page('views/collection.py').run()
        self.assertEqual(app.session_state['collection_workspace'],'Existencias')
        app.selectbox(key='inventory_state').set_value('Con reservas').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.selectbox(key='inventory_selected').value,self.catalog_sku)
        app.button(key='inventory_clear').click().run()
        self.assertEqual(app.selectbox(key='inventory_state').value,'Todos')
        # Only the open section is built: reservations live in their own.
        app.button_group(key='collection_workspace').set_value('Reservas y clientes').run()
        app.button(key='inventory_reserved_open').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.session_state['open_order_id'],self.order_id)
        self.assertEqual(inv.load_inventory(),before)

    def test_new_entry_focus_clears_filters_and_keeps_correct_reference(self):
        self.seed()
        app=self.app.run().switch_page('views/collection.py').run()
        app.text_input(key='inventory_search').set_value('Inexistente').run()
        app.button(key='inventory_receive').click().run()
        prefix='receipt_'+app.session_state['dialog_request_key']
        app.number_input(key=prefix+'_qty').set_value(3)
        app.text_input(key=prefix+'_reason').set_value('Conteo adicional')
        next(b for b in app.button if b.label=='Registrar entrada').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.text_input(key='inventory_search').value,'')
        self.assertEqual(app.selectbox(key='inventory_selected').value,1)
        self.assertEqual(inv.load_inventory()['skus'][0]['unassigned'],13)

    def test_empty_inventory_has_two_clear_starting_paths(self):
        app=self.app.run().switch_page('views/collection.py').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='inventory_empty_receive'))
        self.assertTrue(any('catálogo' in e.value.casefold() for e in app.caption))
