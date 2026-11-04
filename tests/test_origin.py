import os,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import origin,recipes as r,production as p,inventory,costing as cost
from services.queries import load_snapshot
from tests.backends import sqlite_only

class OriginTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'origin.db'
        env=patch.dict(os.environ,NIMUS_DB_PATH=str(self.path));env.start();self.addCleanup(env.stop)
        db.init_db()
        self.shade=origin.create_component('Pantalla',material='PLA ivory',color='Ivory',shape='Modelo futuro')
        self.base=origin.create_base_set('Beige','PLA beige')
        self.supplies={field:origin.create_component(role,material='Insumo',variant='Estándar') for role,field in (('Cable','cable_id'),('Foco','bulb_id'),('Empaque','packaging_id'))}
        self.pid=self.publish();self.product=next(p for p in origin.load()['products'] if p['id']==self.pid);self.rid=self.product['recipe_id']

    def publish(self,base=None,name='Lámpara futura'):
        return origin.publish_lamp(None,name=name,shade_id=self.shade,base_set_id=base or self.base,expected_recipe_id=None,**self.supplies)
    def get_order(self,oid):return next(o for o in load_snapshot()['orders'] if o['id']==oid)
    def receive(self,cid,qty=1,key=None):
        inventory.receive_manual(qty,'Stock','Conteo',component_id=cid,request_key=key or f'entry_{cid}')

    def test_matched_sets_shared_shade_future_model_and_general_articles(self):
        self.assertEqual(origin.create_base_set('beige','PLA beige'),self.base)
        other=origin.create_base_set('Gris','PLA gris');pid=self.publish(other,'Lámpara futura')
        data=origin.load();products=[p for p in data['products'] if p['origin']]
        self.assertEqual(len(products),2)
        self.assertEqual({p['origin']['shade_id'] for p in products},{self.shade})
        self.assertEqual(len(data['components']),10)
        bases={b['id']:b for b in data['bases']}
        with self.assertRaises(ValueError),db.connect(write=True) as conn:
            origin._base_set(conn,bases[self.base]['base_id'],bases[other]['cap_id'],bases[self.base]['lid_id'])
        with self.assertRaises(ValueError):self.publish(other,'Duplicado por nombre')
        article=r.create_product('Artículo futuro',collection='Origen')
        r.publish_recipe(article,[dict(component_id=self.shade,quantity=2)])
        self.assertIsNone(next(p for p in origin.load()['products'] if p['id']==article)['origin'])

    def test_only_print_parts_create_jobs_supplies_reserve_and_delivery_consumes_all(self):
        quote=r.quote_order(self.rid,2)
        self.assertEqual(sum(x['to_make'] for x in quote['lines']),8)
        self.assertEqual(sum(x['to_buy'] for x in quote['lines']),6)
        oid=r.create_recipe_order(self.rid,2,client='Cliente',request_key='order')
        self.assertEqual(len(self.get_order(oid)['items'][0]['parts']),4)
        for part in self.get_order(oid)['items'][0]['parts']:p.job_action(p.create_job(part['id'],part['quantity_required']),'finish')
        self.assertNotEqual(self.get_order(oid)['status'],'Listo')
        with self.assertRaises(ValueError):p.deliver_order(oid)
        for cid in self.supplies.values():self.receive(cid,2)
        self.assertEqual(origin.reserve_supplies(oid),6)
        self.assertEqual(origin.reserve_supplies(oid),0)
        self.assertEqual(self.get_order(oid)['status'],'Listo')
        self.assertEqual(self.get_order(oid)['completed_total'],14)
        with self.assertRaises(ValueError):p.deliver_order(oid)
        from services import board_moves
        order=self.get_order(oid)
        board_moves.apply(oid,'Salida',expected_token=board_moves.token(order),request_key='assemble')
        p.deliver_order(oid)
        self.assertEqual(sum(s['delivered'] for s in inventory.load_inventory()['skus']),14)
        self.assertEqual(sum(s['available_stock']+s['available_collection'] for s in inventory.load_inventory()['skus']),0)
        with self.assertRaises(ValueError):origin.reserve_supplies(oid)

    def test_shared_inventory_and_bought_reservations_do_not_duplicate(self):
        self.receive(self.shade,2)
        for cid in self.supplies.values():self.receive(cid,1)
        a=r.create_recipe_order(self.rid,1,client='A',request_key='a')
        b=r.create_recipe_order(self.rid,1,client='B',request_key='b')
        self.assertEqual(sum(x['covered'] for x in self.get_order(a)['items'][0]['requirements']),4)
        self.assertEqual(sum(x['covered'] for x in self.get_order(b)['items'][0]['requirements']),1)
        self.assertEqual(origin.reserve_supplies(b),0)
        self.receive(self.supplies['cable_id'],1,'more_cable');self.assertEqual(origin.reserve_supplies(b),1)

    def test_complete_recipe_guard_and_price_not_counted_twice(self):
        lines=[l for l in r.load_catalog()['lines'] if l['recipe_id']==self.rid]
        with self.assertRaises(ValueError):r.publish_recipe(self.pid,lines[:-1],expected_recipe_id=self.rid)
        extras={k:99900 for k in cost.EXTRAS};extras.update(assembly_cents=4000,other_cents=500)
        cost.save_extras(self.rid,extras,source='Referencia anterior',expected_id=None)
        for line in lines:
            cost.save_component(line['component_id'],dict(cost.defaults(),mode='Costo unitario',direct_cents=1000),source='Costo confirmado',expected_id=None)
        result=cost.recipe_cost(self.rid)
        self.assertEqual(result['total_cents'],7*1000+4000+500)
        self.assertEqual(len(result['included_extra_keys']),3)
        new=r.publish_recipe(self.pid,lines,'Actualización',expected_recipe_id=self.rid)
        self.assertIn(new,origin.load()['specs'])
        self.assertEqual(cost.recipe_cost(new)['total_cents'],result['total_cents'])
        gray=origin.create_base_set('Gris','PLA gris')
        with self.assertRaises(ValueError):origin.publish_lamp(self.pid,name='x',shade_id=self.shade,base_set_id=gray,expected_recipe_id=new,**self.supplies)

    @sqlite_only

    def test_legacy_bridge_appends_seven_piece_recipe_and_preserves_original(self):
        # A legacy four-piece lamp using the existing shared base.
        base=origin.load()['bases'][0];pid=r.create_product('Lámpara legada',collection='Origen')
        old=r.publish_recipe(pid,[dict(component_id=cid,quantity=1) for cid in (self.shade,base['base_id'],base['cap_id'],base['lid_id'])])
        with db.connect() as conn:old_rows=[tuple(x) for x in conn.execute('SELECT * FROM recipe_lines WHERE recipe_id=?',(old,))]
        # Bootstrap recognizes legacy naming, not this explicit future screen's metadata;
        # existing registered definitions remain stable across a repeated schema check.
        with db.connect(write=True) as conn:
            conn.execute('PRAGMA user_version=17')
        db.init_db()
        with db.connect() as conn:
            self.assertEqual([tuple(x) for x in conn.execute('SELECT * FROM recipe_lines WHERE recipe_id=?',(old,))],old_rows)
        self.assertTrue(next(p for p in origin.load()['products'] if p['id']==pid)['origin'])

    def test_origin_ui_tabs_configuration_receipt_and_context_order(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/origen.py').run();self.assertFalse(app.exception,[e.message for e in app.exception])
        for panel in ('Componentes','Inventario','Pedidos','Otros artículos','Crear receta','Recetas'):
            app.session_state['origin_workspace']=panel;app.run();self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key='origin_new_lamp').click().run();self.assertFalse(app.exception)
        self.assertTrue(any(w.label=='Color de base' and not w.disabled for w in app.button_group))
        self.assertEqual(len([w for w in app.selectbox if w.label in ('Cable','Foco','Empaque')]),3)
        app.session_state['origin_workspace']='Recetas';app.run()
        app.button(key='origin_create_order').click().run();self.assertFalse(app.exception)
        app.switch_page('views/origen.py').run()
        draft=app.session_state['origin_sales_cart']
        spec=origin.load()['specs'][self.rid]
        self.assertEqual((draft['model'],draft['base_set_id']),(spec['model'],spec['base_set_id']))
        app.session_state['active_dialog']=None
        app.session_state['origin_workspace']='Componentes';app.session_state['origin_definition_group']='Insumos';app.run()
        app.button(key='origin_supplies_cost').click().run();self.assertFalse(app.exception)
        self.assertTrue(any(w.label=='Costo de compra por unidad · MXN' for w in app.number_input))
        self.assertFalse(any(w.label=='Gramos por pieza' for w in app.number_input))
        app.session_state['active_dialog']=None;app.run()
        app.button(key='origin_supplies_receive').click().run();self.assertFalse(app.exception)
        app.text_input(key='origin_receipt_reason').set_value('Conteo real')
        next(b for b in app.button if b.label=='Registrar entrada').click().run();self.assertFalse(app.exception)
        self.assertEqual(sum(s['stock'] for s in inventory.load_inventory()['skus']),1)


class OriginModelsTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'models.db'
        env=patch.dict(os.environ,NIMUS_DB_PATH=str(self.path));env.start();self.addCleanup(env.stop)
        db.init_db()
        self.shades={shape:origin.create_component('Pantalla',material='PLA MATTE IVORY',color='IVORY',shape=shape)
            for shape in ('CIRRUS','CUMULO','STRATO')}
        self.bases={color:origin.create_base_set(color,'PLA '+color) for color in ('BEIGE','GRIS NIEBLA','NEGRO NOCHE')}
        self.supplies={field:origin.create_component(role,material='Insumo') for role,field in (('Cable','cable_id'),('Foco','bulb_id'),('Empaque','packaging_id'))}
        self.pid=origin.publish_lamp(None,name='Cirrus beige',shade_id=self.shades['CIRRUS'],base_set_id=self.bases['BEIGE'],expected_recipe_id=None,**self.supplies)

    @sqlite_only

    def test_migration_retires_only_generic_ivory_preserving_history_and_stock(self):
        generic=r.create_component('PANTALLA','PLA MATTE IVORY','Impresión 3D','IVORY','Origen')
        with db.connect(write=True) as conn:origin._register(conn,generic,'Pantalla','IVORY')
        old_pid=r.create_product('Referencia histórica',collection='Origen')
        old_rid=r.publish_recipe(old_pid,[dict(component_id=generic,quantity=1)])
        movement=inventory.receive_manual(2,'Stock','Existencias anteriores',component_id=generic,request_key='legacy')
        with db.connect(write=True) as conn:
            for table in ('origin_base_colors','origin_base_models','catalog_component_retirements'):conn.execute(f'DROP TABLE {table}')
            conn.execute('PRAGMA user_version=18')
            tables=[x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before={t:[tuple(x) for x in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}
        db.init_db()
        with db.connect() as conn:
            for t,rows in before.items():self.assertEqual([tuple(x) for x in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')],rows,t)
            self.assertEqual([x[0] for x in conn.execute('SELECT component_id FROM catalog_component_retirements')],[generic])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        data=origin.load();self.assertEqual(data['shade_models'],['CIRRUS','CUMULO','STRATO'])
        self.assertEqual(len(data['base_models']),1);self.assertEqual(len(data['bases']),3)
        self.assertEqual(len({b['model_id'] for b in data['bases']}),1)
        self.assertNotIn(generic,{c['id'] for c in data['catalog']['components']})
        self.assertEqual({c['material'] for c in data['components'] if c['role']=='Pantalla'},{'PLA MATTE IVORY'})
        self.assertTrue(any(l['recipe_id']==old_rid and l['component_id']==generic for l in data['catalog']['lines']))
        self.assertTrue(next(p for p in data['catalog']['products'] if p['id']==old_pid)['has_retired_components'])
        self.assertTrue(any(m['id']==movement for m in inventory.load_inventory()['movements']))
        for operation in (
            lambda:r.create_component('PANTALLA','PLA MATTE IVORY','Impresión 3D','IVORY','Origen'),
            lambda:r.publish_recipe(old_pid,[dict(component_id=generic,quantity=1)]),
            lambda:r.create_recipe_order(old_rid,1,client='Cliente',request_key='blocked'),
            lambda:inventory.receive_manual(1,'Stock','Entrada',component_id=generic,request_key='blocked'),
        ):
            with self.assertRaisesRegex(ValueError,'retirada'):operation()
        with db.connect() as conn:
            migrated={t:[tuple(x) for x in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables+['origin_base_colors','origin_base_models','catalog_component_retirements']}
        db.init_db()
        with db.connect() as conn:
            for t,rows in migrated.items():self.assertEqual([tuple(x) for x in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')],rows,t)
        # Historical product remains reviewable, with an editor that can replace the retired piece.
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/catalog.py').run()
        app.session_state['catalog_product_selected']=old_pid
        from views.catalog_workspace import open_product
        # Apply the same focus request used by the dialog, before widgets are rendered.
        app.session_state['catalog_focus_request']=dict(kind='product',identity=old_pid)
        app.run();self.assertFalse(app.exception,[e.message for e in app.exception])
        app.session_state[f'catalog_product_tabs_{old_pid}']='Editar receta';app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])

    def test_unpublished_strato_and_color_selection_prepare_correct_lamp(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/origen.py').run()
        self.assertEqual(app.button_group(key='origin_model_filter').options,['CIRRUS','CUMULO','STRATO'])
        app.button_group(key='origin_model_filter').set_value('STRATO')
        app.button_group(key='origin_color_filter').set_value('NEGRO NOCHE').run()
        app.button(key='origin_create_combination').click().run();self.assertFalse(app.exception,[e.message for e in app.exception])
        shade=next(w for w in app.button_group if w.label=='Modelo de pantalla')
        base=next(w for w in app.button_group if w.label=='Color de base')
        self.assertEqual(shade.value,'STRATO');self.assertEqual(base.value,self.bases['NEGRO NOCHE'])
        app.button(key='origin_builder_publish').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        data=origin.load();self.assertEqual(len([p for p in data['products'] if p['origin']]),2)
        self.assertEqual(len(data['base_models']),1);self.assertEqual(len(data['bases']),3)
        self.assertEqual(app.session_state['origin_product'],next(p['id'] for p in data['products'] if p['origin']['model']=='STRATO'))

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/origen.py').run();self.assertFalse(app.exception)
        return app

    def records(self):
        with db.connect() as conn:
            return {r[0]:[tuple(x) for x in conn.execute(f'SELECT * FROM {r[0]} ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

    def test_continuous_selection_survives_navigation_and_component_card_choices(self):
        from services.origin_builder import composition
        app=self.app();before=self.records()
        app.button(key='origin_new_lamp').click().run()
        self.assertTrue(app.button(key='origin_builder_publish').disabled)
        next(w for w in app.button_group if w.label=='Color de base').set_value(self.bases['NEGRO NOCHE']).run()
        next(w for w in app.button_group if w.label=='Modelo de pantalla').set_value('STRATO').run()
        draft=app.session_state['origin_recipe_draft'];plan=composition(origin.load(),draft)
        self.assertTrue(plan['complete']);self.assertEqual(plan['count'],7)
        self.assertEqual({r['component']['color'] for r in plan['rows'] if r['role'] in ('Base','CAP','Tapa')},{'NEGRO NOCHE'})
        name=next(w for w in app.text_input if w.label=='Nombre personalizado (opcional)')
        name.set_value('Strato de estudio').run()
        self.assertTrue(any(s.value=='Strato de estudio' for s in app.subheader))
        app.switch_page('views/catalog.py').run();app.switch_page('views/origen.py').run()
        app.session_state['origin_workspace']='Crear receta';app.run();self.assertFalse(app.exception)
        self.assertEqual(next(w for w in app.button_group if w.label=='Color de base').value,self.bases['NEGRO NOCHE'])
        self.assertEqual(next(w for w in app.button_group if w.label=='Modelo de pantalla').value,'STRATO')
        app.session_state['origin_workspace']='Componentes';app.session_state['origin_definition_group']='Base y colores';app.run()
        app.button(key=f"origin_use_base_{self.bases['GRIS NIEBLA']}").click().run();self.assertFalse(app.exception,[e.message for e in app.exception])
        draft=app.session_state['origin_recipe_draft'];self.assertEqual(draft['model'],'STRATO');self.assertEqual(draft['name'],'Strato de estudio')
        app.session_state['origin_workspace']='Componentes';app.session_state['origin_definition_group']='Pantallas';app.run()
        app.button(key=f"origin_use_shade_{self.shades['CUMULO']}").click().run();self.assertFalse(app.exception)
        draft=app.session_state['origin_recipe_draft'];self.assertEqual(draft['model'],'CUMULO');self.assertEqual(draft['base_set_id'],self.bases['GRIS NIEBLA'])
        self.assertEqual(self.records(),before)

    def test_duplicate_combination_opens_existing_recipe_without_writing(self):
        app=self.app();before=self.records();app.button(key='origin_new_lamp').click().run()
        next(w for w in app.button_group if w.label=='Modelo de pantalla').set_value('CIRRUS').run()
        next(w for w in app.button_group if w.label=='Color de base').set_value(self.bases['BEIGE']).run()
        self.assertFalse(any(b.key=='origin_builder_publish' for b in app.button))
        app.button(key='origin_builder_existing').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['origin_product'],self.pid)
        self.assertEqual(self.records(),before)

    def test_catalog_routes_edit_to_builder_and_publishes_new_version_preserving_orders(self):
        cable=origin.create_component('Cable',material='Insumo',variant='Cable de otra longitud')
        current=next(p for p in origin.load()['products'] if p['id']==self.pid);rid=current['recipe_id']
        oid=r.create_recipe_order(rid,1,client='Pedido anterior',request_key='historical')
        app=self.app();app.switch_page('views/catalog.py').run()
        app.button(key='catalog_selected_edit').click().run();self.assertFalse(app.exception,[e.message for e in app.exception])
        # AppTest keeps its explicitly selected source page after an internal switch_page.
        app.switch_page('views/origen.py').run()
        self.assertTrue(next(w for w in app.button_group if w.label=='Modelo de pantalla').disabled)
        self.assertTrue(next(w for w in app.button_group if w.label=='Color de base').disabled)
        self.assertTrue(app.button(key='origin_builder_publish').disabled)
        next(w for w in app.selectbox if w.label=='Cable').set_value(cable).run()
        self.assertFalse(app.button(key='origin_builder_publish').disabled)
        app.button(key='origin_builder_publish').click().run();self.assertFalse(app.exception,[e.message for e in app.exception])
        changed=next(p for p in origin.load()['products'] if p['id']==self.pid)
        self.assertNotEqual(changed['recipe_id'],rid)
        self.assertEqual(next(o for o in load_snapshot()['orders'] if o['id']==oid)['items'][0]['recipe_id'],rid)
        self.assertNotIn('origin_recipe_draft',app.session_state)

    def test_builder_detects_concurrent_recipe_change_and_can_reload(self):
        cable=origin.create_component('Cable',material='Insumo',variant='Otro cable')
        app=self.app();app.button(key='origin_configure').click().run()
        draft=app.session_state['origin_recipe_draft'];rid=draft['expected_recipe_id']
        next(w for w in app.selectbox if w.label=='Cable').set_value(cable).run()
        lines=[l for l in r.load_catalog()['lines'] if l['recipe_id']==rid]
        fresh=r.publish_recipe(self.pid,lines,expected_recipe_id=rid)
        app.run();self.assertFalse(app.exception)
        self.assertTrue(app.button(key='origin_builder_publish').disabled)
        self.assertTrue(any('otra ventana' in w.value for w in app.warning))
        self.assertEqual(app.session_state['origin_recipe_draft']['cable_id'],cable)
        app.button(key='origin_builder_reload').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['origin_recipe_draft']['expected_recipe_id'],fresh)
