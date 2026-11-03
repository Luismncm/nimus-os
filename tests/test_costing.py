import json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import costing as c,recipes as r,sales,quotations as q,production,planning,sale_corrections
from utils.dates import now


class CostingTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(tmp.name)/'cost.db')});env.start();self.addCleanup(env.stop)
        db.init_db()
        self.cid=r.create_component('BASE','PLA','Impresión 3D',variant='BEIGE',collection='Origen')
        self.pid=r.create_product('Origen',collection='Origen')
        self.rid=r.publish_recipe(self.pid,[dict(component_id=self.cid,quantity=2)])

    def cost(self,value=1000):
        old=c.component_profile(self.cid)
        return c.save_component(self.cid,dict(c.defaults(),mode='Costo unitario',direct_cents=value),source='Comprobante',expected_id=old['id'] if old else None)

    def extras(self,**kw):
        old=c.extras_profile(self.rid)
        return c.save_extras(self.rid,{k:0 for k in c.EXTRAS}|kw,source='Confirmados',expected_id=old['id'] if old else None)

    def sale(self,lines=None,discount=0,iva=False):
        return sales.create_direct(dict(q.defaults(),client='Cliente',discount=discount,iva=iva,
            lines=lines or [dict(description='Origen',quantity=2,price=100,produce=False)]),now().date(),request_key='sale')

    def assign(self,sid,assignments=None):
        context=c.sale_context(sid);cost=c.recipe_cost(self.rid)
        return c.assign_sale(sid,assignments or [dict(recipe_id=self.rid,recipe_fingerprint=cost['fingerprint'])],
            expected_fingerprint=context['fingerprint'],expected_id=context['prior']['id'] if context['prior'] else None,source='Costeo aprobado')

    def test_cap_math_batch_machine_and_incomplete(self):
        cap=dict(c.defaults(),grams=17.5,material_rate_cents=44000,fixed_cents=900)
        self.assertEqual(c.component_amount(cap)['total_cents'],1670)
        batch=dict(cap,mode='Material + máquina',lot_minutes=120,lot_units=4,machine_rate_cents=2000)
        self.assertEqual(c.component_amount(batch)['total_cents'],2670)
        self.assertIsNone(c.component_amount(dict(batch,fixed_cents=None))['total_cents'])
        self.assertEqual(c.component_amount(dict(batch,fixed_cents=0))['total_cents'],1770)
        with self.assertRaises(ValueError):c.component_amount(dict(cap,grams=float('nan')))
        with self.assertRaises(ValueError):c.component_amount(dict(batch,lot_units=0))

    def test_recipe_quantity_extras_missing_and_version_isolation(self):
        self.cost();self.extras(assembly_cents=None)
        cost=c.recipe_cost(self.rid)
        self.assertIsNone(cost['total_cents']);self.assertEqual(cost['known_cents'],2000)
        self.assertIn('Ensamble / mano de obra',cost['missing'])
        self.extras(assembly_cents=500,packaging_cents=200)
        self.assertEqual(c.recipe_cost(self.rid)['total_cents'],2700)
        v2=r.publish_recipe(self.pid,[dict(component_id=self.cid,quantity=3)])
        self.assertIsNone(c.recipe_cost(v2)['total_cents'])
        self.assertEqual(c.recipe_cost(self.rid)['total_cents'],2700)

    def test_gross_profit_discount_excludes_tax_and_not_receipts(self):
        self.cost();self.extras()
        sid=self.sale(discount=10,iva=True);self.assign(sid)
        report=c.sale_margin(sid)
        self.assertEqual((report['net_revenue_cents'],report['cost_cents'],report['profit_cents']),(18000,4000,14000))
        self.assertAlmostEqual(report['margin_percent'],77.7777777778)
        before=c.sale_context(sid)['fingerprint']
        sales.record_payment(sid,50,now().date(),'Efectivo','Anticipo',account_id=2,request_key='receipt',expected_revision=0)
        self.assertEqual(c.sale_context(sid)['fingerprint'],before)
        self.assertEqual(c.sale_margin(sid)['profit_cents'],14000)

    def test_historical_margin_frozen_and_explicit_recost(self):
        self.cost();self.extras();sid=self.sale();self.assign(sid)
        self.cost(2000)
        self.assertEqual(c.sale_margin(sid)['cost_cents'],4000)
        self.assign(sid)
        self.assertEqual(c.sale_margin(sid)['cost_cents'],8000)
        with db.connect(write=True) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sale_cost_versions').fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('DELETE FROM sale_cost_versions')

    def test_missing_cost_never_shows_full_profit(self):
        sid=self.sale();self.assign(sid)
        self.assertFalse(c.sale_margin(sid)['complete']);self.assertIsNone(c.sale_margin(sid)['profit_cents'])
        self.assign(sid,[dict(recipe_id=None,manual_cents=0)])
        self.assertEqual(c.sale_margin(sid)['profit_cents'],20000)

    def test_stale_sale_and_recipe_rejected_without_partial_write(self):
        self.cost();self.extras();sid=self.sale(lines=[dict(description='Uno',quantity=1,price=100),dict(description='Dos',quantity=1,price=50)])
        self.assign(sid,[dict(recipe_id=None,manual_cents=1000),dict(recipe_id=None,manual_cents=500)])
        sale_corrections.remove_lines(sid,[1],'Corrección',expected_revision=0)
        self.assertTrue(c.sale_margin(sid)['stale']);self.assertIsNone(c.sale_margin(sid)['profit_cents'])
        context=c.sale_context(sid);old=c.recipe_cost(self.rid);self.cost(5000)
        with self.assertRaises(ValueError):c.assign_sale(sid,[dict(recipe_id=self.rid,recipe_fingerprint=old['fingerprint'])],expected_fingerprint=context['fingerprint'],expected_id=context['prior']['id'],source='Obsoleto')
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM sale_cost_versions').fetchone()[0],1)

    def test_concurrent_profile_and_invalid_amount_preserve_prior(self):
        self.cost();prior=c.component_profile(self.cid)
        with self.assertRaises(ValueError):c.save_component(self.cid,dict(c.defaults(),direct_cents=1),source='Otro',expected_id=None)
        with self.assertRaises(ValueError):c.save_component(self.cid,dict(c.defaults(),direct_cents=-1),source='Otro',expected_id=prior['id'])
        self.assertEqual(c.component_profile(self.cid),prior)

    def test_publish_printing_lot_divides_material_and_time(self):
        oid=r.create_recipe_order(self.rid,2,client='Cliente',use_stock=False)
        with db.connect() as conn:part=conn.execute('SELECT p.id FROM parts p JOIN items i ON i.id=p.item_id WHERE i.order_id=?',(oid,)).fetchone()[0]
        jid=production.create_job(part,4,None,plan=dict(planning.defaults(),duration_minutes=120,estimated_grams=400,material_rate_cents=40000,machine_rate_cents=2000))
        ref=c.job_reference(jid)
        c.publish_job_cost(jid,expected_revision=ref['revision'],expected_job_revision=ref['job_revision'],expected_profile_id=None,fixed_cents=500,source='Lote de prueba')
        self.assertEqual(c.component_amount(c.component_profile(self.cid)['data'])['total_cents'],5500)
        with self.assertRaises(ValueError):c.publish_job_cost(jid,expected_revision=99,expected_job_revision=ref['job_revision'],expected_profile_id=None,fixed_cents=0,source='Obsoleto')

    def test_ui_cost_editor_and_sale_assignment(self):
        self.cost();self.extras();sid=self.sale()
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/costs.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.button(key='cost_recipe_edit').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        next(x for x in app.number_input if x.label=='Costo unitario manual · MXN').set_value(12.)
        next(x for x in app.text_input if x.label=='Fuente o motivo *').set_value('Captura UI')
        next(x for x in app.button if x.label=='Guardar costo de pieza').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(c.recipe_cost(self.rid)['total_cents'],2400)
        app.button(key=f'sale_cost_edit_{sid}').click().run()
        next(x for x in app.selectbox if x.label=='Receta de esta partida').set_value(self.rid).run()
        next(x for x in app.text_input if x.label=='Motivo o referencia del costeo *').set_value('Venta UI')
        next(x for x in app.button if x.label=='Guardar costeo de venta').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(c.sale_margin(sid)['profit_cents'],15200)
        app.switch_page('views/catalog.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.switch_page('views/sales.py').run();app.session_state['open_sale_id']=sid;app.run()
        self.assertFalse(app.exception,[x.message for x in app.exception])

    def test_v13_upgrade_keeps_existing_records(self):
        self.cost()
        with db.connect(write=True) as conn:
            for table in ('component_cost_versions','recipe_cost_extras','sale_cost_versions','budget_events','budget_lines','budget_months'):conn.execute(f'DROP TABLE {table}')
            conn.execute('PRAGMA user_version=13')
        original=r.load_catalog();db.init_db()
        self.assertEqual(r.load_catalog(),original)
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
