import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import origin,inventory,recipes,lamp_options
from services.queries import load_snapshot
from tests import test_origin as fixtures

class LampOrderTest(unittest.TestCase):
    setUp=fixtures.OriginModelsTest.setUp
    records=fixtures.OriginModelsTest.records

    def app(self):
        origin.complete_combinations()
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/origen.py').run();self.assertFalse(app.exception,[e.message for e in app.exception])
        return app

    def pick(self,app,model='STRATO',color='NEGRO NOCHE'):
        app.button(key='origin_new_order').click().run();self.assertFalse(app.exception)
        app.switch_page('views/origen.py').run()
        prefix='cart_'+app.session_state['origin_sales_cart']['token']
        app.button_group(key=prefix+'_model').set_value(model).run()
        app.button_group(key=prefix+'_base_set_id').set_value(self.bases[color]).run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        return prefix

    def receive(self,cid,qty=2):inventory.receive_manual(qty,'Stock','Stock contado',component_id=cid,request_key=f'count_{cid}')

    def test_complete_all_nine_recipes_preserves_existing_data_and_is_idempotent(self):
        before=self.records();result=origin.complete_combinations();self.assertEqual(len(result['created']),8)
        self.assertEqual(result['total'],9)
        after=self.records();appends={'catalog_products','recipe_versions','recipe_lines','origin_recipes'}
        for table,rows in before.items():
            self.assertEqual(after[table][:len(rows)],rows,table)
            if table not in appends:self.assertEqual(after[table],rows,table)
        data=origin.load();products=[p for p in data['products'] if p['origin']]
        self.assertEqual({(p['origin']['model'],p['origin']['base_set_id']) for p in products},
            {(model,base) for model in self.shades for base in self.bases.values()})
        for p in products:
            lines=[l for l in data['catalog']['lines'] if l['recipe_id']==p['recipe_id']]
            self.assertEqual(len(lines),7);self.assertEqual({l['quantity'] for l in lines},{1})
        self.assertEqual(origin.complete_combinations()['created'],[])
        self.assertEqual(self.records(),after)

    def test_bulk_creation_rolls_back_all_combinations_on_a_name_collision(self):
        recipes.create_product('STRATO · NEGRO NOCHE','NEGRO NOCHE','Origen')
        before=self.records()
        with self.assertRaisesRegex(ValueError,'Ya existe'):origin.complete_combinations()
        self.assertEqual(self.records(),before)

    def test_color_availability_uses_cap_lid_supplies_and_shared_reservations(self):
        origin.complete_combinations();data=origin.load()
        for color in ('BEIGE','GRIS NIEBLA'):
            base=next(b for b in data['bases'] if b['id']==self.bases[color])
            for key in ('base_id','cap_id','lid_id'):self.receive(base[key])
        self.receive(self.shades['CIRRUS'])
        for cid in self.supplies.values():self.receive(cid)
        colors=lamp_options.color_options(data,inventory.load_inventory(),'CIRRUS')
        self.assertEqual([c['stock']['ready'] for c in colors],[2,2,0])
        beige=next(o for o in colors if o['base']['color']=='BEIGE')['products'][0]
        gray=next(o for o in colors if o['base']['color']=='GRIS NIEBLA')['products'][0]
        recipes.create_recipe_order(beige['recipe_id'],1,client='Cliente A',request_key='a')
        gray_stock=lamp_options.availability(data,inventory.load_inventory(),gray,2)
        self.assertEqual(gray_stock['ready'],1)
        quote=recipes.quote_order(gray['recipe_id'],2)
        self.assertEqual(gray_stock['to_make'],sum(r['to_make'] for r in quote['lines']))
        self.assertEqual(gray_stock['to_buy'],sum(r['to_buy'] for r in quote['lines']))
        recipes.create_recipe_order(gray['recipe_id'],1,client='Cliente B',request_key='b')
        self.assertEqual(lamp_options.availability(data,inventory.load_inventory(),beige)['ready'],0)
        self.assertEqual(len(lamp_options.color_options(data,inventory.load_inventory(),'CIRRUS')),3)

    def test_order_picker_has_three_models_all_colors_at_zero_stock_and_creates_correct_order(self):
        app=self.app();before_orders=len(load_snapshot()['orders'])
        prefix=self.pick(app)
        self.assertEqual(app.button_group(key=prefix+'_model').options,['CIRRUS','CUMULO','STRATO'])
        self.assertEqual(len(app.button_group(key=prefix+'_base_set_id').options),3)
        app.number_input(key=prefix+'_quantity').set_value(2).run()
        app.button(key='cart_add').click().run()
        quote=app.session_state['origin_sales_cart']['plan']
        self.assertEqual(sum(r['to_make'] for e in quote['entries'] for r in e['lines']),8)
        self.assertEqual(sum(r['to_buy'] for e in quote['entries'] for r in e['lines']),6)
        app.button_group(key=prefix+'_destination').set_value('Stock').run()
        app.button(key='cart_submit').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        snapshot=load_snapshot();self.assertEqual(len(snapshot['orders']),before_orders+1)
        order=next(o for o in snapshot['orders'] if o['id']==app.session_state['open_order_id'])
        item=order['items'][0];self.assertEqual(item['quantity'],2)
        spec=origin.load()['specs'][item['recipe_id']]
        self.assertEqual(spec['model'],'STRATO');self.assertEqual(spec['base_set_id'],self.bases['NEGRO NOCHE'])
        self.assertEqual(len(item['parts']),4);self.assertEqual(len(item['requirements']),7)
        self.assertTrue(all(p['quantity_required']==2 for p in item['parts']))

    def test_stock_change_requires_refresh_before_confirming_order(self):
        app=self.app();prefix=self.pick(app,'CIRRUS','BEIGE')
        app.text_input(key=prefix+'_client').set_value('Cliente').run()
        app.button(key='cart_add').click().run()
        self.receive(self.shades['CIRRUS'],1);app.run();self.assertFalse(app.exception)
        self.assertTrue(any('existencias cambiaron' in w.value for w in app.warning))
        submit=app.button(key='cart_submit')
        self.assertTrue(submit.disabled)
        app.button(key='cart_refresh').click().run();self.assertFalse(app.exception)
        self.assertFalse(app.button(key='cart_submit').disabled)
        self.assertEqual(sum(r['reserved'] for e in app.session_state['origin_sales_cart']['plan']['entries'] for r in e['lines']),1)

    def test_generic_recipe_orders_remain_available_and_separate_from_model_picker(self):
        pid=recipes.create_product('Otro artículo');rid=recipes.publish_recipe(pid,[dict(component_id=self.shades['CIRRUS'],quantity=2)])
        app=self.app();app.switch_page('views/orders.py').run()
        app.button(key='new_recipe_order').click().run();self.assertFalse(app.exception)
        app.switch_page('views/origen.py').run()
        self.assertFalse(any(w.key=='recipe_order_product' for w in app.selectbox))
        app.button(key='cart_other_products').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='recipe_order_product').value,rid)
        self.assertEqual(len(app.selectbox(key='recipe_order_product').options),1)
