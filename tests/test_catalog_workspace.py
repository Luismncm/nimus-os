import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import recipes as r
from services.catalog_view import product_rows,filter_products,usages,editor_lines,differences
from services.queries import load_snapshot
from tests import test_recipes as fixtures
from tests.ui_helpers import enter_option

class CatalogWorkspaceTest(unittest.TestCase):
    setUp=fixtures.RecipeTest.setUp
    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/catalog.py').run()
        self.assertFalse(app.exception,[e.message for e in app.exception]);return app

    def test_filters_usage_and_changes_use_current_versions(self):
        extra=r.create_product('Lámpara adicional','Azul',collection='General')
        r.publish_recipe(self.product,[dict(component_id=self.base,quantity=4)])
        catalog=r.load_catalog();rows=product_rows(catalog)
        self.assertEqual(len(filter_products(rows,state='Sin receta')),1)
        self.assertEqual(filter_products(rows,search='AZUL')[0]['id'],extra)
        self.assertEqual(len(filter_products(rows,line='Origen')),1)
        self.assertEqual(usages(catalog,self.shade),[])
        self.assertEqual(usages(catalog,self.base)[0]['quantity'],4)
        for q in (0,-1,1.5,True,None,float('nan')):
            with self.assertRaises(ValueError):editor_lines([dict(component_id=self.base,quantity=q)])
        self.assertEqual(editor_lines([dict(component_id=self.base,quantity=2.0)])[0]['quantity'],2)
        components={c['id']:c for c in catalog['components']}
        diff=differences([dict(component_id=self.base,quantity=1)],[dict(component_id=self.shade,quantity=2)],components)
        self.assertEqual({x['change'] for x in diff},{'Agregar','Quitar'})

    def test_publication_conflict_and_variant_creation_keep_old_orders(self):
        oid=r.create_recipe_order(self.recipe,2,client='Cliente',request_key='old_order')
        before=load_snapshot()
        r.publish_recipe(self.product,[dict(component_id=self.base,quantity=3)],expected_recipe_id=self.recipe)
        with self.assertRaisesRegex(ValueError,'otra ventana'):
            r.publish_recipe(self.product,[dict(component_id=self.shade,quantity=4)],expected_recipe_id=self.recipe)
        with self.assertRaises(ValueError):
            r.duplicate_product(self.product,'Lámpara Origen','Gris','Origen',copy_recipe=True,expected_recipe_id=self.recipe)
        current=next(p for p in r.load_catalog()['products'] if p['id']==self.product)
        variant=r.duplicate_product(self.product,'Lámpara Origen','Gris','Origen',copy_recipe=True,expected_recipe_id=current['recipe_id'])
        with self.assertRaisesRegex(ValueError,'Ya existe'):
            r.duplicate_product(self.product,'Lámpara Origen','Gris','Origen',copy_recipe=True,expected_recipe_id=current['recipe_id'])
        self.assertEqual(before,load_snapshot())
        self.assertEqual(next(o for o in load_snapshot()['orders'] if o['id']==oid)['items'][0]['recipe_id'],self.recipe)
        catalog=r.load_catalog();new=next(p for p in catalog['products'] if p['id']==variant)
        self.assertEqual(new['version'],1)
        self.assertEqual(next(l for l in catalog['lines'] if l['recipe_id']==new['recipe_id'])['quantity'],3)

    def test_draft_survives_tabs_products_and_removal_then_reset(self):
        other=r.create_product('Otro producto')
        app=self.app();app.button(key='catalog_selected_edit').click().run()
        prefix=f'recipe_draft_{self.product}_1';grid=prefix+f'_grid_{self.base}_{self.shade}'
        app.session_state[grid]={'edited_rows':{0:{'quantity':3}},'added_rows':[],'deleted_rows':[]}
        app.run();self.assertFalse(app.exception)
        app.text_input(key=prefix+'_notes').set_value('Nueva base').run()
        app.session_state[f'catalog_product_tabs_{self.product}']='Costos';app.run()
        app.selectbox(key='catalog_product_selected').set_value(other).run()
        app.selectbox(key='catalog_product_selected').set_value(self.product).run()
        app.session_state[f'catalog_product_tabs_{self.product}']='Editar receta';app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[prefix+'_store']['quantities'][self.base],3)
        self.assertEqual(app.text_input(key=prefix+'_notes').value,'Nueva base')
        app.multiselect(key=prefix+'_pieces').set_value([self.shade]).run()
        app.multiselect(key=prefix+'_pieces').set_value([self.base,self.shade]).run()
        self.assertEqual(app.session_state[prefix+'_store']['quantities'][self.base],3)
        app.button(key=prefix+'_reset').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state[prefix+'_store']['quantities'][self.base],1)
        self.assertTrue(app.button(key=prefix+'_publish').disabled)

    def test_gallery_filters_components_and_context_order_navigation(self):
        other=r.create_product('Segundo producto')
        second_recipe=r.publish_recipe(other,[dict(component_id=self.base,quantity=2)])
        app=self.app();before=r.load_catalog()
        app.text_input(key='catalog_product_search').set_value('no coincide').run()
        self.assertTrue(any('No hay productos' in i.value for i in app.info))
        app.button(key='catalog_products_clear').click().run()
        app.button_group(key='catalog_product_view').set_value('Galería').run()
        app.button(key=f'catalog_gallery_open_{other}').click().run()
        self.assertEqual(app.session_state['catalog_product_selected'],other)
        app.button(key='catalog_selected_order').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='recipe_order_product').value,second_recipe)
        app.session_state['active_dialog']=None
        app.session_state['catalog_workspace']='Piezas reutilizables';app.run()
        app.selectbox(key='catalog_component_selected').set_value(self.base).run()
        app.selectbox(key=f'catalog_component_owner_{self.base}').set_value(self.product).run()
        app.button(key='catalog_component_open_product').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['catalog_product_selected'],self.product)
        self.assertEqual(before,r.load_catalog())

    def test_creating_missing_piece_returns_to_draft_without_losing_changes(self):
        app=self.app();app.button(key='catalog_selected_edit').click().run()
        prefix=f'recipe_draft_{self.product}_1'
        app.text_input(key=prefix+'_notes').set_value('Ensamble').run()
        app.button(key=prefix+'_new_piece').click().run()
        enter_option(app,'component_name','Soporte nuevo')
        next(b for b in app.button if b.label=='Guardar pieza reutilizable').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        component=next(c for c in r.load_catalog()['components'] if c['name']=='Soporte nuevo')
        self.assertIn(component['id'],app.multiselect(key=prefix+'_pieces').value)
        self.assertEqual(app.text_input(key=prefix+'_notes').value,'Ensamble')
        self.assertEqual(len(r.load_catalog()['versions']),1)
