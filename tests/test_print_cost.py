import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import costing as c,inventory,recipes
from tests import test_costing as fixture,test_origin as origin_fixture


class PrintCalculationTest(unittest.TestCase):
    def inputs(self,**kw):
        return c.printing_inputs(**(dict(grams=100,price_per_gram=.44,minutes=150,hourly_rate=20)|kw))

    def test_material_time_and_total_without_requiring_fixed_cost(self):
        result=c.component_amount(self.inputs())
        self.assertEqual((result['material_cents'],result['machine_cents'],result['total_cents']),(4400,5000,9400))
        self.assertEqual(result['missing'],[])

    def test_subcent_gram_price_is_not_rounded_to_whole_cents_per_gram(self):
        data=self.inputs(grams=10,price_per_gram=.075,minutes=0)
        self.assertEqual(data['material_rate_cents'],7500)
        self.assertEqual(c.component_amount(data)['total_cents'],75)
        self.assertEqual(c.gram_rate(.12345),12345)

    def test_lot_divides_material_and_time_once_and_adds_extras_per_piece(self):
        data=self.inputs(grams=400,minutes=120,hourly_rate=40,units=4,per_lot=True,fixed_cents=500)
        self.assertEqual((data['grams'],data['lot_units']),(100,4))
        result=c.component_amount(data)
        self.assertEqual((result['material_cents'],result['machine_cents'],result['total_cents']),(4400,2000,6900))

    def test_unknown_parameters_stay_pending_but_explicit_zero_is_valid(self):
        for field in ('grams','price_per_gram','minutes','hourly_rate'):
            with self.subTest(field=field):self.assertIsNone(c.component_amount(self.inputs(**{field:None}))['total_cents'])
        self.assertEqual(c.component_amount(self.inputs(minutes=0,hourly_rate=0))['total_cents'],4400)

    def test_invalid_inputs_rejected(self):
        for field,value in (('grams',-1),('price_per_gram',float('nan')),('hourly_rate',True),('minutes',float('inf')),('units',0),('units',1.5)):
            with self.subTest(field=field),self.assertRaises(ValueError):self.inputs(**{field:value})


class PrintCostUITest(unittest.TestCase):
    setUp=fixture.CostingTest.setUp
    extras=fixture.CostingTest.extras
    sale=fixture.CostingTest.sale
    assign=fixture.CostingTest.assign

    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/costs.py').run()
    def clean(self,a):self.assertFalse(a.exception,[x.message for x in a.exception])
    def values(self,a,**kw):
        labels={'grams':'Gramos por pieza','price':'Filamento · MXN/kg','hours':'Tiempo · horas','mins':'Tiempo · minutos','rate':'Máquina · MXN/h'}
        for key,value in kw.items():next(x for x in a.number_input if x.label==labels[key]).set_value(value)

    def test_default_print_editor_preview_save_recipe_and_frozen_sale(self):
        self.extras();a=self.app();a.button(key='cost_recipe_edit').click().run();self.clean(a)
        self.assertEqual(next(s for s in a.selectbox if s.label=='Cálculo').value,c.PRINT_MODE)
        self.values(a,grams=100.,price=440.,hours=2,mins=30.,rate=20.)
        next(b for b in a.button if b.label=='Calcular costo').click().run();self.clean(a)
        self.assertEqual(next(m for m in a.metric if m.label=='Costo por pieza').value,'$94.00')
        self.assertIsNone(c.component_profile(self.cid))
        next(b for b in a.button if b.label=='Guardar costo de pieza').click().run();self.clean(a)
        self.assertEqual(c.recipe_cost(self.rid)['total_cents'],18800)
        sid=self.sale();self.assign(sid);prior=c.sale_margin(sid)['cost_cents']
        profile=c.component_profile(self.cid)
        c.save_component(self.cid,c.printing_inputs(grams=100,price_per_gram=.50,minutes=150,hourly_rate=20),source='Nuevo filamento',expected_id=profile['id'])
        self.assertEqual(c.sale_margin(sid)['cost_cents'],prior)
        self.assertEqual(len(c.history('component',self.cid)),2)

    def test_existing_kg_profile_converts_to_gram_and_lot_without_changing_amount(self):
        old=dict(c.defaults(),mode='Material + máquina',grams=100,material_rate_cents=44000,lot_units=4,lot_minutes=120,machine_rate_cents=2000,fixed_cents=500)
        c.save_component(self.cid,old,source='Anterior',expected_id=None)
        a=self.app();a.button(key='cost_recipe_edit').click().run()
        next(s for s in a.selectbox if s.label=='Cálculo').set_value(c.PRINT_MODE).run();self.clean(a)
        self.assertEqual(next(x for x in a.number_input if x.label=='Filamento · MXN/kg').value,440.)
        self.assertEqual(next(x for x in a.number_input if x.label=='Gramos del lote').value,400.)
        next(b for b in a.button if b.label=='Calcular costo').click().run();self.clean(a)
        self.assertEqual(next(m for m in a.metric if m.label=='Costo por pieza').value,'$59.00')
        self.assertEqual(c.component_profile(self.cid)['data'],c.normalize(old))

    def test_inventory_opens_calculator_and_keeps_physical_counts(self):
        inventory.receive_manual(4,'Stock','Entrada',component_id=self.cid,request_key='print-cost-stock')
        before=inventory.load_inventory()
        # Colección Origen pieces are managed in its own inventory; the others in the general one.
        if next(s for s in before['skus'] if s['component_id']==self.cid)['collection']=='Origen':
            a=self.app();a.session_state['origin_workspace']='Inventario';a.switch_page('views/origen.py').run();key='origin_stock_component_cost'
        else:
            a=self.app().switch_page('views/collection.py').run();key='inventory_component_cost'
        a.button(key=key).click().run();self.clean(a)
        self.values(a,grams=10.,price=75.,hours=0,mins=30.,rate=10.)
        next(b for b in a.button if b.label=='Guardar costo de pieza').click().run();self.clean(a)
        self.assertEqual(c.component_amount(c.component_profile(self.cid)['data'])['total_cents'],575)
        self.assertEqual(inventory.load_inventory(),before)

    def test_gcode_fills_the_piece_cost_and_price_defaults_to_the_spool(self):
        a=self.app();a.button(key='cost_recipe_edit').click().run();self.clean(a)
        # No saved rate: the same filament price a print would use (380 MXN/kg when the spool is not registered).
        self.assertEqual(next(x for x in a.number_input if x.label=='Filamento · MXN/kg').value,380.)
        prefix='component_cost_'+a.session_state['dialog_request_key']
        text='; total filament weight [g] : 50\n; total estimated time: 1h 30m 0s\n'
        a.file_uploader(key=prefix+'_gcode').set_value(('base.gcode',text.encode('utf-8'),'text/plain')).run();self.clean(a)
        self.assertEqual([next(x for x in a.number_input if x.label==l).value for l in ('Gramos por pieza','Tiempo · horas','Tiempo · minutos')],[50.,1,30.])
        self.assertTrue(any('base.gcode' in s.value for s in a.success))
        self.assertEqual(next(t for t in a.text_input if t.label=='Fuente o motivo *').value,'G-code: base.gcode')
        self.values(a,rate=20.)
        next(b for b in a.button if b.label=='Guardar costo de pieza').click().run();self.clean(a)
        # 50 g × $380/kg = $19 + 1.5 h × $20/h = $30.
        profile=c.component_profile(self.cid)
        self.assertEqual((c.component_amount(profile['data'])['total_cents'],profile['source']),(4900,'G-code: base.gcode'))

    def test_unreadable_gcode_warns_and_leaves_fields(self):
        a=self.app();a.button(key='cost_recipe_edit').click().run()
        prefix='component_cost_'+a.session_state['dialog_request_key']
        a.file_uploader(key=prefix+'_gcode').set_value(('vacio.gcode',b'G1 X10 Y10\n','text/plain')).run();self.clean(a)
        self.assertTrue(a.warning)
        self.assertIsNone(next(x for x in a.number_input if x.label=='Gramos por pieza').value)

    def test_excessive_time_shows_validation_without_writing_or_crashing(self):
        a=self.app();a.button(key='cost_recipe_edit').click().run()
        self.values(a,grams=100.,price=440.,hours=16666,mins=59.,rate=20.)
        next(b for b in a.button if b.label=='Guardar costo de pieza').click().run();self.clean(a)
        self.assertTrue(a.error)
        self.assertIsNone(c.component_profile(self.cid))


class OriginPrintCostUITest(unittest.TestCase):
    setUp=origin_fixture.OriginTest.setUp
    publish=origin_fixture.OriginTest.publish

    def test_shade_and_base_components_can_open_cost_editor(self):
        c.save_component(self.shade,dict(c.defaults(),grams=100,material_rate_cents=44000,fixed_cents=500),source='Anterior',expected_id=None)
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/origen.py').run()
        a.session_state['origin_workspace']='Componentes';a.run()
        a.button(key=f'origin_shade_cost_{self.shade}').click().run()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        self.assertTrue(any(s.label=='Cálculo' and s.value==c.PRINT_MODE for s in a.selectbox))
        self.assertEqual(c.component_profile(self.shade)['data']['mode'],'Material + fijo')

    def test_base_cap_and_lid_have_direct_cost_access(self):
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/origen.py').run()
        a.session_state['origin_workspace']='Componentes';a.session_state['origin_definition_group']='Base y colores';a.run()
        buttons=[b for b in a.button if (b.key or '').startswith('origin_base_cost_')]
        self.assertEqual(len(buttons),3)
        buttons[1].click().run()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        self.assertTrue(any(s.label=='Cálculo' and s.value==c.PRINT_MODE for s in a.selectbox))
