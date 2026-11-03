import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import origin,commerce,sales,quotations as q
from services.queries import load_snapshot
from tests import test_origin as fixtures

class CommercialUITest(unittest.TestCase):
    setUp=fixtures.OriginModelsTest.setUp

    def app(self):
        origin.complete_combinations()
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/origen.py').run()
        app.button(key='origin_new_order').click().run()
        app.switch_page('views/origen.py').run()
        self.assert_clean(app)
        return app

    def assert_clean(self,app):self.assertFalse(app.exception,[e.message for e in app.exception])
    def prefix(self,app):return 'cart_'+app.session_state['origin_sales_cart']['token']
    def add(self,app,model='CIRRUS',color='BEIGE'):
        prefix=self.prefix(app)
        app.button_group(key=prefix+'_model').set_value(model).run()
        app.button_group(key=prefix+'_base_set_id').set_value(self.bases[color]).run()
        app.button(key='cart_add').click().run();self.assert_clean(app)
        return app.session_state['origin_sales_cart']['entries'][-1]

    def test_basket_edits_multiple_variants_and_survives_navigation(self):
        app=self.app();prefix=self.prefix(app)
        first=self.add(app);second=self.add(app,'STRATO','GRIS NIEBLA')
        app.number_input(key=prefix+'_'+first['uid']+'_quantity').set_value(3).run()
        app.text_input(key=prefix+'_client').set_value('Cliente con varios modelos').run()
        app.button(key='cart_duplicate_'+second['uid']).click().run()
        entries=app.session_state['origin_sales_cart']['entries'];self.assertEqual(len(entries),3)
        self.assertEqual(sum(e['quantity'] for e in entries),5)
        app.switch_page('views/sales.py').run();app.switch_page('views/origen.py').run()
        self.assert_clean(app);self.assertEqual(app.text_input(key=prefix+'_client').value,'Cliente con varios modelos')
        self.assertEqual(app.number_input(key=prefix+'_'+first['uid']+'_quantity').value,3)
        app.button(key='cart_remove_'+second['uid']).click().run()
        self.assertEqual(len(app.session_state['origin_sales_cart']['entries']),2)
        self.assertFalse(load_snapshot()['orders'])

    def test_quote_requires_explicit_prices_and_saves_frozen_recipes_without_payment(self):
        app=self.app();prefix=self.prefix(app);entry=self.add(app)
        app.button_group(key=prefix+'_mode').set_value('Cotización').run()
        self.assertIsNone(app.number_input(key=prefix+'_'+entry['uid']+'_price').value)
        app.text_input(key=prefix+'_client').set_value('Cliente cotizado').run()
        self.assertTrue(app.button(key='cart_submit').disabled)
        app.number_input(key=prefix+'_'+entry['uid']+'_price').set_value(900.0).run()
        self.assertFalse(app.button(key='cart_submit').disabled)
        app.button(key='cart_submit').click().run();self.assert_clean(app)
        qid=app.session_state['open_quote_id'];quote=q.get_quote(qid)
        self.assertEqual(quote['total_cents'],90000);self.assertEqual(quote['paid_cents'],0)
        self.assertEqual(quote['data']['lines'][0]['recipe_id'],entry['recipe_id'])
        self.assertEqual(commerce.profile('quote',qid)['data']['minimum_mode'],'Sin mínimo')
        app.switch_page('views/quotations.py').run();self.assert_clean(app)
        self.assertFalse(load_snapshot()['orders'])

    def test_confirmed_sale_authorization_and_reuse_keep_prices_and_recipes(self):
        app=self.app();prefix=self.prefix(app);entry=self.add(app)
        app.button_group(key=prefix+'_mode').set_value('Venta confirmada').run()
        app.text_input(key=prefix+'_client').set_value('Cliente venta').run()
        app.number_input(key=prefix+'_'+entry['uid']+'_price').set_value(950.0).run()
        app.checkbox(key=prefix+'_terms_authorized').check().run()
        app.button(key='cart_submit').click().run();self.assert_clean(app)
        sid=app.session_state['open_sale_id'];self.assertTrue(commerce.state('sale',sid)['production_allowed'])
        app.switch_page('views/sales.py').run();self.assert_clean(app)
        app.button(key=f'commerce_terms_sale_{sid}').click().run();self.assert_clean(app)
        token=app.session_state['dialog_request_key']
        app.selectbox(key='commercial_terms_'+token+'_minimum').set_value('Porcentaje').run()
        app.number_input(key='commercial_terms_'+token+'_amount').set_value(30.0).run()
        app.text_input(key='commercial_terms_reason').set_value('Anticipo acordado').run()
        app.button(key='commercial_terms_save').click().run();self.assert_clean(app)
        self.assertEqual(commerce.state('sale',sid)['minimum_cents'],28500)
        self.assertFalse(commerce.state('sale',sid)['production_allowed'])
        app.button(key='sale_reuse').click().run();app.switch_page('views/origen.py').run();self.assert_clean(app)
        copy=app.session_state['origin_sales_cart'];self.assertEqual(copy['entries'][0]['recipe_id'],entry['recipe_id'])
        self.assertEqual(copy['entries'][0]['price'],950.0)
        self.assertEqual(len(sales.list_sales()),1)
