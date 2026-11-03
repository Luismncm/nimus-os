import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import consumables as c, alert_inputs, expenses, production as p
from services.queries import load_snapshot


class ConsumablesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'c.db')});env.start();self.addCleanup(env.stop)
        db.init_db()
        self.pla=c.save_item('PLA Matte Ivory',spec='PLA',minimum=500)

    def item(self,iid):return next(r for r in c.items(load_snapshot()['jobs']) if r['id']==iid)
    def reading(self,name):return next((r for r in alert_inputs.readings() if r['identity']==c.identity(name)),None)

    def test_units_follow_the_category_and_convert_on_entry(self):
        row=self.item(self.pla)
        self.assertEqual((row['unit'],row['package_label'],row['package_size']),('g','Carrete',1000))
        resin=c.save_item('Resina gris',category='Resina');screws=c.save_item('Tornillo M3×8',category='Tornillería')
        self.assertEqual((self.item(resin)['unit'],self.item(screws)['unit']),('ml','pza'))
        self.assertEqual(c.to_base(1.5,'kg','g'),1500);self.assertEqual(c.to_base(2,'L','ml'),2000)
        with self.assertRaises(ValueError):c.to_base(1,'kg','ml')
        self.assertEqual((c.quantity_text(1250,'g'),c.quantity_text(800,'ml'),c.quantity_text(1,'pza'),c.quantity_text(12,'pza')),('1.25 kg','800 ml','1 pza','12 pzas'))
        with self.assertRaises(ValueError):c.receive(screws,2.5,request_key='half')
        c.receive(screws,100,request_key='box')
        self.assertEqual(self.item(screws)['balance'],100)
        # Only filament feeds the production alerts reading.
        self.assertIsNone(self.reading('Tornillo M3×8'))

    def test_ledger_counts_and_never_goes_negative(self):
        c.receive(self.pla,2000,request_key='in');c.receive(self.pla,2000,request_key='in')
        c.consume(self.pla,300,request_key='use')
        with self.assertRaises(ValueError):c.consume(self.pla,1,job_code='JOB-9999',request_key='no-job')
        with self.assertRaises(ValueError):c.consume(self.pla,5000,request_key='too-much')
        c.count(self.pla,1500,request_key='count')
        self.assertEqual([m['kind'] for m in c.movements(self.pla)],['Ajuste','Consumo','Entrada'])
        self.assertEqual([m['balance_after'] for m in c.movements(self.pla)],[1500,1700,2000])
        with self.assertRaises(ValueError):c.count(self.pla,1500,request_key='same')
        self.assertEqual(self.reading('PLA Matte Ivory')['available_grams'],1500)
        with db.connect(write=True) as conn,self.assertRaises(sqlite3.DatabaseError):
            conn.execute('UPDATE consumable_movements SET quantity=1')

    def test_control_reading_is_a_count_in_the_same_ledger(self):
        alert_inputs.save_material('PLA Matte Ivory',800,300)
        alert_inputs.save_material('PETG Negro',1200)
        row=self.item(self.pla)
        self.assertEqual((row['balance'],row['minimum'],c.movements(self.pla)[0]['kind']),(800,300,'Ajuste'))
        petg=next(r for r in c.items([]) if r['name']=='PETG Negro')
        self.assertEqual((petg['balance'],petg['category']),(1200,'Filamento'))
        self.assertEqual(self.reading('PETG Negro')['available_grams'],1200)

    def test_previous_readings_become_opening_balances(self):
        with db.connect(write=True) as conn:
            conn.execute("INSERT INTO material_availability VALUES('pla rojo','PLA Rojo',650,100,'2026-10-01T10:00:00')")
            for table in ('consumable_order_events','consumable_movements','consumable_orders','consumables'):conn.execute(f'DROP TABLE {table}')
            conn.execute('PRAGMA user_version=26')
        db.init_db();db.init_db()
        row=next(r for r in c.items([]) if r['name']=='PLA Rojo')
        self.assertEqual((row['balance'],row['minimum'],c.movements(row['id'])[0]['kind']),(650,100,'Saldo inicial'))
        with db.connect() as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)

    def test_order_status_flow_receipts_and_expense(self):
        oid=c.create_order(self.pla,2,supplier='Proveedor',financial=dict(amount=900,paid=False),request_key='order')
        self.assertEqual(c.create_order(self.pla,2,supplier='Proveedor',financial=dict(amount=900,paid=False),request_key='order'),oid)
        row=c.list_orders()[0]
        self.assertEqual((row['code'],row['status'],self.item(self.pla)['on_order']),('CON-0001','Solicitado',2000))
        self.assertEqual(expenses.get_expense(row['expense_id'])['balance_cents'],90000)
        c.set_stage(oid,'En camino',expected_token=row['token'],request_key='stage')
        row=c.list_orders()[0];self.assertEqual(row['status'],'En camino')
        c.receive_order(oid,1,expected_token=row['token'],request_key='r1')
        row=c.list_orders()[0]
        self.assertEqual((row['status'],self.item(self.pla)['balance'],self.item(self.pla)['on_order']),('Recibido parcial',1000,1000))
        with self.assertRaises(ValueError):c.receive_order(oid,1,expected_token='stale',request_key='r2')
        c.cancel_order(oid,'Sin existencia',expected_token=row['token'],request_key='cancel')
        self.assertEqual((c.list_orders()[0]['status'],self.item(self.pla)['balance']),('Cancelado',1000))
        # Something arrived, so the bill stays to adjust it by hand.
        self.assertEqual(expenses.get_expense(row['expense_id'])['status'],'Activo')
        other=c.create_order(self.pla,1,financial=dict(amount=450,paid=False),request_key='other')
        row=next(r for r in c.list_orders() if r['id']==other)
        c.cancel_order(other,'Ya no se necesita',expected_token=row['token'],request_key='cancel-other')
        self.assertEqual(expenses.get_expense(row['expense_id'])['status'],'Cancelado')

    def test_queue_demand_marks_filament_that_will_not_last(self):
        c.receive(self.pla,400,request_key='in')
        oid=p.create_order('Lámparas','Cliente');iid=p.create_item(oid,'Origen',2)
        pid=p.create_part(iid,'Base',2,'Impresión 3D','PLA MATTE IVORY')
        plan=dict(planned_start=None,duration_minutes=60,estimated_grams=650,actual_grams=None,material_rate_cents=None,machine_rate_cents=None)
        p.create_job(pid,2,1,plan=plan)
        row=self.item(self.pla)
        self.assertEqual((row['committed'],row['free_after'],row['state'],row['attention']),(650,-250,'No alcanza para la cola',True))
        p.create_part(iid,'Tapa',2,'Impresión 3D','PETG Azul');p.create_job(load_snapshot()['parts'][-1]['id'],2,1)
        self.assertEqual(c.unregistered(load_snapshot()['jobs']),['PETG Azul'])


class ConsumableCostTest(unittest.TestCase):
    setUp=ConsumablesTest.setUp
    item=ConsumablesTest.item

    def order(self):
        oid=p.create_order('Lámparas','Cliente');iid=p.create_item(oid,'Origen',1)
        pid=p.create_part(iid,'Base',1,'Impresión 3D','PLA Matte Ivory');jid=p.create_job(pid,1,1)
        return oid,next(j['code'] for j in load_snapshot()['jobs'] if j['id']==jid)

    def report(self,oid):
        from services import order_costs
        return next(r for r in order_costs.reports(load_snapshot()) if r['order_id']==oid)

    def edit(self,iid,cost):
        row=self.item(iid)
        c.save_item(row['name'],category=row['category'],unit=row['unit'],spec=row['spec'],package_label=row['package_label'],
                    package_size=row['package_size'],package_cost=cost,item_id=iid,expected_revision=row['revision'])

    def test_consumption_freezes_its_cost_and_charges_the_order_once(self):
        oid,job=self.order();self.edit(self.pla,420)
        paint=c.save_item('Pintura blanca',category='Pintura',package_cost=100)
        c.receive(self.pla,1000,request_key='in');c.receive(paint,250,request_key='paint-in')
        self.assertEqual((self.item(self.pla)['unit_cost'],self.item(self.pla)['stock_value_cents'],c.material_rate('PLA MATTE IVORY')),(42.0,42000,42000))
        c.consume(paint,50,order_id=oid,request_key='paint')
        c.consume(self.pla,100,job_code=job,request_key='job')
        self.edit(paint,200)
        moves={m['request_key']:m for m in c.movements(paint)+c.movements(self.pla)}
        # Price changes later do not rewrite what was already consumed: 50 ml × $100/250 ml = $20.
        self.assertEqual((moves['paint']['cost_cents'],moves['job']['cost_cents'],moves['job']['order_code']),(2000,4200,'ORD-0001'))
        used=c.by_order()[oid]
        # The job's filament is listed but not charged again: the job's real consumption already costs it.
        self.assertEqual((used['cost_cents'],used['unknown'],[r['charged'] for r in used['rows']]),(2000,0,[True,False]))
        report=self.report(oid)
        self.assertEqual((report['consumables_cents'],report['actual_known_cents']),(2000,2000))
        with self.assertRaises(ValueError):c.consume(paint,1,job_code=job,order_id=oid+99,request_key='bad')

    def test_unknown_cost_keeps_the_margin_provisional_and_purchases_set_the_price(self):
        oid,_=self.order()
        glue=c.save_item('Pegamento',category='Adhesivo')
        c.receive(glue,100,request_key='in');c.consume(glue,10,order_id=oid,request_key='use')
        self.assertEqual((self.report(oid)['consumables_unknown'],self.report(oid)['complete']),(1,False))
        purchase=c.create_order(glue,2,financial=dict(amount=180,paid=False),request_key='buy')
        row=next(r for r in c.list_orders() if r['id']==purchase)
        c.receive_order(purchase,1,expected_token=row['token'],request_key='arrive')
        # $180 for 2 bottles → $90 per bottle becomes the reference cost.
        self.assertEqual(self.item(glue)['package_cost_cents'],9000)

    def test_migration_from_27_adds_cost_columns_and_backup(self):
        with db.connect(write=True) as conn:conn.execute('PRAGMA user_version=27')
        db.init_db();db.init_db()
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertIn('cost_cents',{r[1] for r in conn.execute('PRAGMA table_info(consumable_movements)')})
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-costos-consumibles-v28*')))


class ConsumablesUITest(unittest.TestCase):
    setUp=ConsumablesTest.setUp
    item=ConsumablesTest.item

    def test_empty_catalog_starts_with_generic_filaments_without_stock(self):
        names={r['name']:r for r in c.items([])}
        self.assertTrue({'PLA Genérico','PETG Genérico','TPU Genérico'}<=set(names))
        self.assertEqual({names[n]['balance'] for n in ('PLA Genérico','PETG Genérico','TPU Genérico')},{0})
        self.assertEqual(names['PLA Genérico']['unit'],'g')

    def test_every_dialog_name_is_unique(self):
        # Opening a dialog by a name another module also uses would show the wrong form; the guard refuses it.
        import importlib,pkgutil,views
        from views import common
        for module in pkgutil.iter_modules(views.__path__):
            if module.name.endswith(('_forms','_ui')) or module.name in ('common','consumables_ui','inbound_ui'):
                importlib.import_module('views.'+module.name)
        self.assertEqual(common._OWNERS['order_form'],'views.common')
        self.assertEqual(common._OWNERS['consumable_receive_order_form'],'views.consumables_ui')
        self.assertEqual(common._OWNERS['manual_entry_form'],'views.collection_forms')
        def order_form():pass
        order_form.__module__='tests.duplicate'
        with self.assertRaises(RuntimeError):common.managed_dialog('Copia')(order_form)

    def test_tab_registers_counts_and_orders(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/collection.py').run()
        app.session_state['collection_workspace']='Filamento y consumibles';app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key='consumable_count').click().run()
        prefix='consumable_move_'+app.session_state['dialog_request_key']
        app.button_group(key=prefix+'_entry_unit').set_value('kg').run()
        app.number_input(key=prefix+'_amount_kg').set_value(2.5)
        next(b for b in app.button if b.label=='Guardar conteo').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(self.item(app.session_state['consumables_selected'])['balance'],2500)
        app.session_state['collection_workspace']='Compras';app.session_state['orders_kind']='Filamento y consumibles';app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key='consumable_orders_new').click().run()
        # The same "Agregar inventario" dialog as pieces, already on consumables, with the same purchase expense.
        self.assertEqual(next(x for x in app.button_group if x.label=='Qué agregas').value,'Filamento y consumibles')
        self.assertEqual(next(x for x in app.button_group if x.label=='Registrar como').value,'Pedido')
        next(x for x in app.number_input if x.label=='Total del pedido · MXN *').set_value(300)
        next(b for b in app.button if b.label=='Guardar pedido').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        order=c.list_orders()[0]
        self.assertEqual((order['status'],expenses.get_expense(order['expense_id'])['total_cents']),('Solicitado',30000))

    def test_today_shows_supply_needs_and_opens_the_same_order_dialog(self):
        ConsumableCostTest.order(self)
        # The queue needs 650 g of a filament with no stock: Hoy must ask to order it.
        with db.connect(write=True) as conn:conn.execute("INSERT INTO print_plans(job_id,estimated_grams,updated_at) VALUES(1,650,'2026-10-21T10:00')")
        from services.supply_board import board
        need=next(r for r in board(load_snapshot()['jobs'])['to_order'] if r['kind']=='Consumible')
        self.assertEqual((need['record_id'],need['action'],need['state']),(self.pla,'Pedir','Sin existencias'))
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.session_state['today_front']='Abastecer';app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key=f"today_supply_{need['identity']}").click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(next(x for x in app.button_group if x.label=='Qué agregas').value,'Filamento y consumibles')
        self.assertEqual(app.selectbox(key='receipt_'+app.session_state['dialog_request_key']+'_consumable').value,self.pla)

    def test_order_detail_records_a_consumable_charged_to_that_order(self):
        oid,_=ConsumableCostTest.order(self)
        row=self.item(self.pla);c.save_item(row['name'],package_cost=500,item_id=self.pla,expected_revision=row['revision'])
        c.receive(self.pla,1000,request_key='in')
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id']=oid;app.run()
        app.button(key=f'order_consumable_{oid}').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        prefix='consumable_use_'+app.session_state['dialog_request_key']
        app.selectbox(key=prefix+'_item').set_value(self.pla).run()
        app.number_input(key=prefix+'_amount_g').set_value(40)
        next(b for b in app.button if b.label=='Registrar consumo').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        # $500 per 1 kg spool → 40 g cost $20, charged to the order.
        self.assertEqual(c.by_order()[oid]['cost_cents'],2000)


if __name__=='__main__':
    unittest.main()

