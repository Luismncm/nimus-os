"""Color count sheets reflect physical stock, reservations and real receipts."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests import test_origin as fixture
import db
from services import origin, inventory, recipes, production, inbound, base_inventory as bases


class BaseInventoryTest(unittest.TestCase):
    setUp=fixture.OriginTest.setUp
    publish=fixture.OriginTest.publish
    get_order=fixture.OriginTest.get_order

    def base(self):
        return next(b for b in origin.load()['bases'] if b['id']==self.base_id)

    def row(self, color='Beige', material='PLA beige'):
        return next(r for r in bases.load_counts()['rows'] if r['color']==color and r['material']==material)

    def receive(self, cid, qty, location='Stock', key=None):
        return inventory.receive_manual(qty,location,'Conteo de prueba',component_id=cid,request_key=key or f'entry-{cid}')

    def definitions(self):
        return next(b for b in origin.load()['bases'] if b['id']==self.base)

    def test_zero_colors_and_material_variants_are_visible_without_creating_inventory(self):
        origin.create_base_set('Gris niebla','PLA gris')
        origin.create_base_set('Negro noche','PLA negro')
        origin.create_base_set('Beige','PETG beige')
        rows=bases.load_counts()['rows']
        self.assertEqual(len(rows),4)
        for row in rows:
            self.assertEqual((row['pieces']['Base']['physical'],row['pieces']['CAP']['free'],row['pieces']['Tapa']['reserved'],row['kits_available']),(0,0,0,0))
        self.assertEqual(inventory.load_inventory()['skus'],[])
        self.assertEqual(inventory.load_inventory()['movements'],[])

    def test_reservations_and_b2b_are_not_double_counted_or_counted_as_free(self):
        b=self.definitions()
        self.receive(b['base_id'],10)
        self.receive(b['cap_id'],7,'Colección')
        self.receive(b['lid_id'],6)
        recipes.create_recipe_order(self.rid,2,client='Cliente')
        sku=next(s for s in inventory.load_inventory()['skus'] if s['component_id']==b['cap_id'])
        inventory.distribute(sku['id'],'Colección','B2B',2,client='Tienda',request_key='b2b')
        row=self.row()
        self.assertEqual([row['pieces'][r]['physical'] for r in bases.ROLES],[10,5,6])
        self.assertEqual([row['pieces'][r]['reserved'] for r in bases.ROLES],[2,2,2])
        self.assertEqual([row['pieces'][r]['free'] for r in bases.ROLES],[8,3,4])
        self.assertEqual(row['pieces']['CAP']['b2b'],2)
        self.assertEqual(row['kits_available'],3)
        self.assertEqual(bases.matrix([row],'free')[0]['CAP'],3)

    def test_shared_recipes_and_other_colors_do_not_multiply_counts(self):
        b=self.definitions()
        other=origin.create_base_set('Negro noche','PLA negro')
        self.publish(other,'Lámpara negra')
        self.receive(b['base_id'],4)
        for index in range(3):
            pid=recipes.create_product('Otra receta '+str(index),collection='Origen')
            recipes.publish_recipe(pid,[dict(component_id=b['base_id'],quantity=1)])
        self.assertEqual(self.row()['pieces']['Base']['physical'],4)
        self.assertEqual(self.row('Negro noche','PLA negro')['pieces']['Base']['physical'],0)
        self.assertEqual(sum(r['pieces']['Base']['physical'] for r in bases.load_counts()['rows']),4)

    def test_pending_orders_and_reversed_entries_do_not_inflate_stock(self):
        b=self.definitions()
        mid=self.receive(b['base_id'],5)
        inventory.reverse_movement(mid,'Conteo equivocado')
        self.assertEqual(self.row()['pieces']['Base']['physical'],0)
        oid=inbound.create(4,'Stock','Pedido de bases',component_id=b['base_id'],request_key='pending')
        self.assertEqual(self.row()['pieces']['Base']['physical'],0)
        inbound.receive(oid,2,expected_token=inbound.get(oid)['token'],request_key='partial')
        self.assertEqual(self.row()['pieces']['Base']['free'],2)
        self.assertEqual(inbound.get(oid)['pending'],2)

    def test_printed_recipe_receipt_updates_physical_and_reserved_counts(self):
        b=self.definitions()
        oid=recipes.create_recipe_order(self.rid,2,client='Cliente',use_stock=False)
        part=next(p for p in self.get_order(oid)['items'][0]['parts'] if p['component_id']==b['base_id'])
        production.job_action(production.create_job(part['id'],2),'finish')
        count=self.row()['pieces']['Base']
        self.assertEqual((count['physical'],count['reserved'],count['free']),(2,2,0))

    def fingerprint(self):
        with db.connect() as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {t:[tuple(r) for r in c.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}

    def app(self):
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        # Bases by color live in Colección Origen → Inventario.
        a.session_state['origin_workspace']='Inventario';a.session_state['origin_inventory_view']='Bases por color'
        a.switch_page('views/origen.py').run()
        return a

    def test_native_ui_can_filter_zero_colors_without_writing_records(self):
        origin.create_base_set('Negro noche','PLA negro')
        before=self.fingerprint()
        a=self.app()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        frame=next(d.value for d in a.dataframe if 'Juegos libres' in d.value.columns)
        self.assertEqual(set(frame['Color']),{'Beige','Negro noche'})
        a.text_input(key='base_inventory_search').set_value('negro').run()
        a.button_group(key='base_inventory_measure').set_value('Reservadas').run()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        self.assertEqual(a.selectbox(key='base_inventory_color').options,['Negro noche · PLA negro'])
        self.assertEqual(self.fingerprint(),before)

    def test_native_receipt_is_prefilled_and_returns_to_color_count(self):
        b=self.definitions();a=self.app()
        a.button_group(key='base_inventory_role').set_value('CAP').run()
        a.button(key='base_inventory_receive').click().run()
        prefix='receipt_'+a.session_state['dialog_request_key']
        self.assertEqual(a.selectbox(key=prefix+'_component').value,b['cap_id'])
        a.number_input(key=prefix+'_qty').set_value(5)
        a.text_input(key=prefix+'_reason').set_value('Conteo real')
        next(button for button in a.button if button.label=='Registrar entrada').click().run()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        self.assertEqual(a.session_state['origin_inventory_view'],'Bases por color')
        self.assertEqual(a.button_group(key='base_inventory_role').value,'CAP')
        frame=next(d.value for d in a.dataframe if 'Juegos libres' in d.value.columns)
        self.assertEqual((int(frame.iloc[0]['Base']),int(frame.iloc[0]['CAP']),int(frame.iloc[0]['Tapa'])),(0,5,0))

    def test_native_planned_order_leaves_color_counts_unchanged(self):
        a=self.app();a.button(key='base_inventory_order').click().run()
        prefix='receipt_'+a.session_state['dialog_request_key']
        self.assertEqual(a.button_group(key=prefix+'_operation').value,'Pedido')
        a.number_input(key=prefix+'_qty').set_value(3)
        a.text_input(key=prefix+'_reason').set_value('Bases encargadas')
        a.number_input(key=prefix+'_total').set_value(150)
        next(b for b in a.button if b.label=='Guardar pedido').click().run()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        self.assertEqual(inbound.list_orders()[0]['pending'],3)
        self.assertEqual(self.row()['pieces']['Base']['physical'],0)
