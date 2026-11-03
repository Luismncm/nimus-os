import json,unittest
from tests import test_origin as fixtures
import db
from services import origin,recipe_cart,commerce,quotations as q,sales,inventory,production,commercial_preview,costing,board_moves
from services.queries import load_snapshot,dashboard
from utils.dates import now

class CommercialFlowTest(unittest.TestCase):
    setUp=fixtures.OriginModelsTest.setUp
    records=fixtures.OriginModelsTest.records

    def entries(self):
        origin.complete_combinations();data=origin.load()
        return [dict(recipe_id=next(p['recipe_id'] for p in data['products'] if p['origin'] and p['origin']['model']=='CIRRUS' and p['origin']['base_set_id']==self.bases[color]),
            quantity=1,price=1000,label='CIRRUS · '+color) for color in ('BEIGE','GRIS NIEBLA')]
    def payload(self):return dict(q.defaults(),client='Cliente del carrito',project='Pedido conjunto')
    def sale(self,terms=None):
        return commerce.create_document('sale',self.entries(),self.payload(),terms or commerce.defaults(),request_key='sale')
    def authorize(self,sid,**changes):
        p=commerce.profile('sale',sid)
        commerce.save('sale',sid,dict(p['data'],production_authorized=True,**changes),expected_id=p['id'],reason='Acuerdo con cliente')

    def test_pooled_basket_reserves_shared_units_once_and_creates_one_order(self):
        entries=self.entries()
        inventory.receive_manual(1,'Stock','Pantalla contada',component_id=self.shades['CIRRUS'],request_key='screen')
        plan=recipe_cart.quote(entries)
        self.assertEqual(sum(l['reserved'] for p in plan['entries'] for l in p['lines'] if l['role']=='Pantalla'),1)
        self.assertEqual(sum(l['to_make'] for p in plan['entries'] for l in p['lines'] if l['role']=='Pantalla'),1)
        oid=recipe_cart.create_order(entries,client='Cliente',expected_fingerprint=plan['fingerprint'],request_key='cart')
        self.assertEqual(recipe_cart.create_order(entries,client='Cliente',request_key='cart'),oid)
        order=next(o for o in load_snapshot()['orders'] if o['id']==oid)
        self.assertEqual(len(order['items']),2)
        self.assertEqual(sum(l['covered'] for i in order['items'] for l in i['requirements']),1)

    def test_quote_sale_payments_and_recipe_order_share_one_flow(self):
        entries=self.entries();qid=commerce.create_document('quote',entries,self.payload(),commerce.defaults(),request_key='quote')
        self.assertEqual(commerce.create_document('quote',entries,self.payload(),commerce.defaults(),request_key='quote'),qid)
        quoted=q.get_quote(qid);self.assertEqual([l['recipe_id'] for l in quoted['data']['lines']],[e['recipe_id'] for e in entries])
        q.set_status(qid,'Aceptada',expected_revision=quoted['revision'])
        quoted=q.get_quote(qid);sid=sales.from_quote(qid,now().date().isoformat(),request_key='confirmed',expected_revision=quoted['revision'])
        with self.assertRaisesRegex(ValueError,'autorización'):sales.create_order(sid,expected_revision=sales.get_sale(sid)['revision'],expected_quote_revision=q.get_quote(qid)['revision'])
        self.authorize(sid,minimum_mode='Porcentaje',minimum_value=50)
        sale=sales.get_sale(sid)
        sales.record_payment(sid,1000,now().date().isoformat(),'Efectivo','Anticipo',request_key='pay',expected_revision=sale['revision'],expected_quote_revision=q.get_quote(qid)['revision'])
        sale=sales.get_sale(sid);self.assertEqual(sale['paid_cents'],100000)
        self.assertTrue(commerce.state('sale',sid)['production_allowed'])
        oid=sales.create_order(sid,expected_revision=sale['revision'],expected_quote_revision=q.get_quote(qid)['revision'])
        order=next(o for o in load_snapshot()['orders'] if o['id']==oid)
        self.assertEqual(len(order['items']),2);self.assertTrue(all(i['recipe_id'] for i in order['items']))
        with db.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM sale_payments').fetchone()[0],0)

    def test_rules_can_be_changed_without_fixed_minimum_and_retries_are_exact(self):
        sid=self.sale();self.assertFalse(commerce.state('sale',sid)['production_allowed'])
        self.authorize(sid);self.assertTrue(commerce.state('sale',sid)['production_allowed'])
        before=self.records()
        self.assertEqual(commerce.create_document('sale',self.entries(),self.payload(),commerce.defaults(),request_key='sale'),sid)
        self.assertEqual(self.records(),before)
        with self.assertRaises(ValueError):commerce.create_document('sale',self.entries(),self.payload(),dict(commerce.defaults(),delivery_paid=True),request_key='sale')

    def test_cancellation_releases_reservations_without_erasing_order(self):
        inventory.receive_manual(1,'Stock','Pantalla',component_id=self.shades['CIRRUS'],request_key='stock')
        sid=self.sale();self.authorize(sid);sale=sales.get_sale(sid)
        oid=sales.create_order(sid,expected_revision=sale['revision'])
        request=commerce.request('sale',sid,'Cancelación','Cliente canceló')
        commerce.resolve(request,'Cancelado antes de producir',apply_cancel=True)
        snapshot=load_snapshot();order=next(o for o in snapshot['orders'] if o['id']==oid)
        self.assertTrue(order['commercial_cancelled']);self.assertEqual(sales.get_sale(sid)['status'],'Cancelada')
        self.assertEqual(sum(s['reserved'] for s in inventory.load_inventory()['skus']),0)
        with self.assertRaisesRegex(ValueError,'cancelado'):production.set_order_blocked(oid,False)
        self.assertEqual(dashboard(snapshot)['metrics']['active_orders'],0)

    def test_paid_cancellation_remains_pending_and_keeps_real_receipts(self):
        sid=self.sale();sale=sales.get_sale(sid)
        sales.record_payment(sid,100,now().date().isoformat(),'Efectivo','Anticipo',request_key='realpay',expected_revision=sale['revision'])
        rid=commerce.request('sale',sid,'Cancelación','Revisar devolución')
        before=self.records()
        with self.assertRaisesRegex(ValueError,'cobros reales'):commerce.resolve(rid,'Por devolver',apply_cancel=True)
        self.assertEqual(self.records(),before);self.assertEqual(sales.get_sale(sid)['paid_cents'],10000)
        self.assertTrue(commerce.state('sale',sid)['pending_cancellation'])

    def test_old_records_survive_migration_and_financial_incomplete_costs_stay_pending(self):
        entries=self.entries();before=self.records()
        with db.connect(write=True) as conn:conn.execute('PRAGMA user_version=19')
        db.init_db();self.assertEqual(self.records(),before)
        report=commercial_preview.prices(entries)
        self.assertIsNone(report['profit_cents']);self.assertIsNone(report['margin'])
        forecast=commercial_preview.forecast(entries,commerce.defaults())
        self.assertIsNone(forecast['estimated_on']);self.assertTrue(forecast['missing'])

    def test_authorization_changes_protect_start_quick_finish_and_stale_terms(self):
        sid=self.sale();self.authorize(sid)
        oid=sales.create_order(sid,expected_revision=sales.get_sale(sid)['revision'])
        part=next(o for o in load_snapshot()['orders'] if o['id']==oid)['items'][0]['parts'][0]
        jid=production.create_job(part['id'],1)
        p=commerce.profile('sale',sid)
        commerce.save('sale',sid,dict(p['data'],production_authorized=False),expected_id=p['id'],reason='Pendiente de aprobación')
        with self.assertRaisesRegex(ValueError,'autorización'):production.job_action(jid,'start')
        with self.assertRaisesRegex(ValueError,'autorización'):production.job_action(jid,'finish')
        with self.assertRaisesRegex(ValueError,'otra ventana'):commerce.save('sale',sid,p['data'],expected_id=p['id'],reason='Cambio anterior')
        self.authorize(sid);production.job_action(jid,'start')
        p=commerce.profile('sale',sid)
        commerce.save('sale',sid,dict(p['data'],production_authorized=False),expected_id=p['id'],reason='Pausar nuevos trabajos')
        production.job_action(jid,'finish')
        self.assertEqual(next(j for j in load_snapshot()['jobs'] if j['id']==jid)['quantity_completed'],1)

    def test_delivery_waits_for_agreed_payment_and_consumes_pooled_stock_once(self):
        entries=self.entries();quantities={}
        for plan in recipe_cart.quote(entries)['entries']:
            for line in plan['lines']:quantities[line['component_id']]=quantities.get(line['component_id'],0)+line['needed']
        for cid,qty in quantities.items():inventory.receive_manual(qty,'Stock','Conteo',component_id=cid,request_key=str(cid))
        sid=commerce.create_document('sale',entries,self.payload(),dict(commerce.defaults(),production_authorized=True,delivery_paid=True),request_key='delivery')
        oid=sales.create_order(sid,expected_revision=sales.get_sale(sid)['revision'])
        order=next(o for o in load_snapshot()['orders'] if o['id']==oid)
        board_moves.apply(oid,'Salida',expected_token=board_moves.token(order),request_key='prepare')
        before=self.records()
        with self.assertRaisesRegex(ValueError,'liquidar'):production.deliver_order(oid)
        self.assertEqual(self.records(),before)
        sales.record_payment(sid,2000,now().date().isoformat(),'Efectivo','Liquidación',request_key='paid',expected_revision=sales.get_sale(sid)['revision'])
        production.deliver_order(oid)
        self.assertEqual(sum(s['delivered'] for s in inventory.load_inventory()['skus']),14)

    def test_complete_costs_freeze_per_sale_including_free_shipping_cost(self):
        entries=self.entries();components=set()
        for p in recipe_cart.quote(entries)['entries']:components.update(l['component_id'] for l in p['lines'])
        for cid in components:costing.save_component(cid,dict(costing.defaults(),mode='Costo unitario',direct_cents=1000),source='Confirmado',expected_id=None)
        for e in entries:costing.save_extras(e['recipe_id'],dict(assembly_cents=2000,other_cents=0),source='Ensamble',expected_id=None)
        preview=commercial_preview.prices(entries,shipping_cost=50)
        self.assertEqual(preview['profit_cents'],177000)
        sid=commerce.create_document('sale',entries,self.payload(),dict(commerce.defaults(),shipping_cost=50),request_key='costed')
        frozen=costing.sale_margin(sid)
        self.assertTrue(frozen['complete']);self.assertEqual(frozen['profit_cents'],preview['profit_cents'])
        cid=next(iter(components));p=costing.component_profile(cid)
        costing.save_component(cid,dict(p['data'],direct_cents=2000),source='Nuevo costo',expected_id=p['id'])
        self.assertEqual(costing.sale_margin(sid)['profit_cents'],177000)
