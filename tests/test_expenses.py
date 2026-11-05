import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import db
from tests.backends import sqlite_only
from services import expenses as e
from services import sales as s, quotations as q
from services.queries import load_snapshot
from utils.dates import now


class ExpenseTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'expenses.db'
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.today=now().date()
        self.data=dict(e.defaults(),concept='Filamento PLA',supplier='Proveedor A',amount=1000,tax_mode='Subtotal + IVA 16%')

    def create(self,**kwargs): return e.create(self.data,request_key=kwargs.pop('key','one'),**kwargs)

    def pay(self,eid,amount=100,key='pay',on=None,revision=None,account='Efectivo / caja'):
        row=e.get_expense(eid)
        return e.record_payment(eid,amount,on or self.today,account,'Efectivo',request_key=key,
            expected_revision=row['revision'] if revision is None else revision)

    def test_amount_modes_rounding_and_undisclosed_tax(self):
        self.assertEqual(e.amounts('Sin desglose',1160),dict(subtotal_cents=None,tax_cents=None,total_cents=116000))
        self.assertEqual(e.amounts('Subtotal + IVA 16%',1000),dict(subtotal_cents=100000,tax_cents=16000,total_cents=116000))
        self.assertEqual(e.amounts('Total con IVA 16%',1160),dict(subtotal_cents=100000,tax_cents=16000,total_cents=116000))
        self.assertEqual(e.amounts('Desglose manual',1000,80)['total_cents'],108000)
        self.assertEqual(e.amounts('Total con IVA 16%',.01),dict(subtotal_cents=1,tax_cents=0,total_cents=1))
        for amount in (0,-1,float('inf'),float('nan'),True):
            with self.assertRaises(ValueError): e.amounts('Sin desglose',amount)

    def test_new_pending_expense_no_implicit_payment_stock_or_sale(self):
        row=e.get_expense(self.create())
        self.assertEqual(row['payment_status'],'Por pagar')
        self.assertEqual(row['total_cents'],116000)
        self.assertEqual(row['paid_cents'],0)
        self.assertEqual(row['control'],'Comprobante pendiente')
        self.assertEqual(s.list_sales(),[])
        self.assertEqual(load_snapshot()['orders'],[])
        with db.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM inventory_movements').fetchone()[0],0)

    def test_atomic_paid_creation_idempotence_and_invalid_payment_rollback(self):
        payment=dict(amount=1160,paid_on=self.today,account='Efectivo / caja',method='Efectivo')
        eid=self.create(payment=payment)
        self.assertEqual(self.create(payment=payment),eid)
        self.assertEqual(e.get_expense(eid)['payment_status'],'Pagado')
        with self.assertRaises(ValueError): self.create(payment=dict(payment,amount=100))
        with self.assertRaises(sqlite3.IntegrityError): self.create(key='over',payment=dict(payment,amount=1200))
        self.assertEqual(len(e.list_expenses()),1)
        with db.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM expense_payments').fetchone()[0],1)

    def test_partial_payments_void_cancel_and_guards(self):
        eid=self.create()
        pid=self.pay(eid,100)
        self.assertEqual(self.pay(eid,100,revision=0),pid)
        with self.assertRaises(ValueError): self.pay(eid,200)
        with self.assertRaises(sqlite3.IntegrityError): self.pay(eid,2000,key='over')
        with self.assertRaises(sqlite3.IntegrityError): e.cancel(eid,'Duplicado',expected_revision=1)
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c: c.execute('DELETE FROM expense_payments')
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c: c.execute('UPDATE expense_payments SET amount_cents=1')
        e.void_payment(pid,'Pago capturado por error')
        row=e.get_expense(eid)
        self.assertEqual(row['paid_cents'],0)
        self.assertTrue(row['money_locked'])
        e.cancel(eid,'Duplicado',expected_revision=row['revision'])
        self.assertEqual(e.report(self.today,self.today)['total_cents'],0)
        with self.assertRaises(sqlite3.IntegrityError): self.pay(eid,key='cancelled')

    def test_edit_financial_lock_classification_and_audit(self):
        eid=self.create()
        e.update(eid,dict(self.data,amount=2000),expected_revision=0)
        self.assertEqual(e.get_expense(eid)['total_cents'],232000)
        with self.assertRaises(ValueError): e.update(eid,self.data,expected_revision=0)
        self.pay(eid)
        row=e.get_expense(eid)
        with self.assertRaises(sqlite3.IntegrityError): e.update(eid,self.data,expected_revision=row['revision'])
        e.update(eid,dict(e.editable(row),category='Operación / oficina',receipt_type='Factura',receipt_ref='F-100'),expected_revision=row['revision'])
        saved=e.get_expense(eid)
        self.assertEqual(saved['control'],'Completo')
        self.assertEqual(saved['receipt_ref'],'F-100')
        self.assertEqual(len(saved['events']),4)
        self.assertIn('Filamento PLA',saved['events'][-1]['snapshot'])

    def test_invoice_missing_breakdown_and_saved_properties(self):
        self.data.update(tax_mode='Sin desglose',receipt_type='Factura',category='Nueva categoría',unit='Nueva unidad')
        row=e.get_expense(self.create())
        self.assertEqual(row['control'],'Revisar desglose IVA')
        self.assertIn('Proveedor A',e.saved_values('supplier'))
        self.assertIn('Nueva categoría',e.saved_values('category'))
        self.assertIn('Nueva unidad',e.saved_values('unit'))
        self.pay(row['id'],account='Nueva cuenta')
        self.assertIn('Nueva cuenta',e.saved_values('account'))

    def test_specific_expense_label_matches_category_and_filters(self):
        data=dict(self.data,category='Producción / materiales',subtype='Filamento / materia prima')
        eid=e.create(data,request_key='labeled')
        self.assertEqual(e.get_expense(eid)['subtype'],'Filamento / materia prima')
        self.assertEqual(len(e.report(self.today,self.today,subtype='Filamento / materia prima')['rows']),1)
        self.assertEqual(e.report(self.today,self.today,subtype='Dominios')['rows'],[])
        with self.assertRaisesRegex(ValueError,'no corresponde'):
            e.create(dict(data,subtype='Dominios'),request_key='wrong-label')

    def test_invalid_dates_required_fields_and_foreign_order(self):
        for field,value in [('concept',''),('category',''),('account',''),('unit',''),('expense_on',str(self.today+timedelta(days=1))),('due_on',str(self.today-timedelta(days=1)))]:
            with self.assertRaises(ValueError): e.create(dict(self.data,**{field:value}),request_key='bad')
        with self.assertRaises(sqlite3.IntegrityError): e.create(dict(self.data,order_id=999),request_key='order')
        eid=self.create()
        with self.assertRaises(ValueError): self.pay(eid,on=self.today+timedelta(days=1))
        self.assertEqual(len(e.list_expenses()),1)

    def test_concurrent_payments_prevent_overpay(self):
        eid=self.create()
        def attempt(i):
            try:
                self.pay(eid,800,key=f'parallel{i}',revision=0)
                return True
            except (ValueError,sqlite3.IntegrityError): return False
        with ThreadPoolExecutor(max_workers=2) as pool: self.assertEqual(sorted(pool.map(attempt,range(2))),[False,True])
        self.assertEqual(e.get_expense(eid)['paid_cents'],80000)

    def test_report_expense_date_vs_cash_date_pending_and_filters(self):
        old=self.today-timedelta(days=45)
        eid=e.create(dict(self.data,expense_on=str(old),due_on=str(old)),request_key='old')
        self.pay(eid,200)
        current=self.create()
        self.pay(current,300,key='current')
        report=e.report(self.today,self.today)
        self.assertEqual(report['total_cents'],116000)
        self.assertEqual(report['paid_cents'],50000)
        self.assertEqual(report['balance_cents'],86000)
        self.assertEqual(report['all_balance_cents'],182000)
        self.assertEqual(report['overdue_cents'],96000)
        self.assertEqual(report['pending'][0]['id'],eid)
        self.assertEqual(e.report(self.today,self.today,unit='No existe')['rows'],[])
        self.assertEqual(e.report(self.today,self.today,search='Filamento')['paid_cents'],50000)

    def test_template_monthly_equivalent_no_payments_and_unique_generation(self):
        tid=e.save_template('Suscripción anual',dict(self.data,cost_type='Fijo'),'Anual',request_key='annual')
        row=e.templates()[0]
        self.assertEqual(row['monthly_cents'],9667)
        self.assertEqual(e.list_expenses(),[])
        eid=e.generate(tid,self.today,'',expected_revision=0,request_key='generated')
        self.assertEqual(e.get_expense(eid)['payment_status'],'Por pagar')
        with self.assertRaises(ValueError): e.generate(tid,self.today,'',expected_revision=0,request_key='twice')
        e.save_template('Suscripción anual',dict(self.data,amount=2000,cost_type='Fijo'),'Anual',request_key='edit',template_id=tid,expected_revision=0)
        self.assertEqual(e.get_expense(eid)['total_cents'],116000)
        self.assertEqual(e.templates()[0]['total_cents'],232000)

    def test_templates_archive_one_time_and_stale_edit(self):
        with self.assertRaises(ValueError): e.save_template('Desarrollo',dict(self.data,cost_type='Desarrollo / único'),'Mensual',request_key='invalid')
        tid=e.save_template('Desarrollo',dict(self.data,cost_type='Desarrollo / único'),'Único',request_key='once')
        self.assertEqual(e.templates()[0]['monthly_cents'],0)
        e.save_template('Desarrollo',dict(self.data,cost_type='Desarrollo / único'),'Único',request_key='archive',template_id=tid,expected_revision=0,active=False)
        with self.assertRaises(ValueError): e.generate(tid,self.today,'',expected_revision=1,request_key='inactive')
        with self.assertRaises(ValueError): e.save_template('Desarrollo',self.data,'Mensual',request_key='stale',template_id=tid,expected_revision=0)

    def test_csv_safety_and_tax_unknown_not_reported_as_zero(self):
        self.data.update(concept='=SUM(1+1)',tax_mode='Sin desglose')
        self.create()
        text=e.export_csv(e.list_expenses()).decode('utf-8-sig')
        self.assertIn("'=SUM(1+1)",text)
        self.assertIn(',,,1000.00,0.00,1000.00',text)

    def test_v8_migration_keeps_sales_and_no_expenses_inferred(self):
        old=Path(self.tmp.name)/'v8.db'
        from models.inventory_schema import create_inventory_schema
        from models.recipe_schema import create_recipe_schema
        from models.operations_schema import create_operations_schema
        from models.manual_inventory_schema import create_manual_inventory_schema
        from models.quotation_schema import create_quotation_schema
        from models.sales_schema import create_sales_schema
        with db.connect(old,write=True) as c:
            db._create_schema(c)
            for make in (create_inventory_schema,create_recipe_schema,create_operations_schema,create_manual_inventory_schema,create_quotation_schema,create_sales_schema): make(c)
            c.execute("INSERT INTO sales(code,payload,total_cents,sold_on,channel,request_key,created_at,updated_at) VALUES('VEN-OLD','{}',10000,'2026-01-01','B2B','old','a','a')")
            c.execute('PRAGMA user_version=8')
            before=[tuple(r) for r in c.execute('SELECT * FROM sales')]
        db.init_db(old)
        with db.connect(old) as c:
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM sales')])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM expenses').fetchone()[0],0)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)

    @sqlite_only
    def test_migration_from_33_replaces_the_keep_triggers_with_a_backup(self):
        old=Path(self.tmp.name)/'v33.db'
        db.init_db(old)
        with db.connect(old,write=True) as c:
            eid=c.execute("""INSERT INTO expenses(code,expense_on,concept,category,cost_type,unit,account,tax_mode,
                total_cents,receipt_type,request_key,request_payload,created_at,updated_at)
                VALUES('GAS-OLD','2026-01-01','Viejo','Materiales','Variable','NIMUS','Efectivo / caja','Sin desglose',
                1000,'Pendiente','old','{}','a','a')""").lastrowid
            c.execute('DROP TRIGGER expense_keep')
            c.execute("""CREATE TRIGGER expense_keep BEFORE DELETE ON expenses BEGIN
                SELECT RAISE(ABORT,'Cancela el gasto para conservar su historial.'); END""")
            c.execute('DROP TRIGGER expense_payment_keep')
            c.execute("""CREATE TRIGGER expense_payment_keep BEFORE DELETE ON expense_payments BEGIN
                SELECT RAISE(ABORT,'Anula el pago para conservar el historial.'); END""")
            c.execute('DROP TABLE expense_delete_unlock')
            c.execute('PRAGMA user_version=33')
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM expenses WHERE id=?',(eid,))
        db.init_db(old)
        with db.connect(old) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual(c.execute('SELECT concept FROM expenses WHERE id=?',(eid,)).fetchone()[0],'Viejo')
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
        self.assertTrue(list((old.parent/'backups').glob('*pre-eliminar-gastos-v34*')))
        with patch.dict(os.environ,{'NIMUS_DB_PATH':str(old)}):
            e.delete(eid,'Ya migrado, ahora sí se puede',expected_revision=e.get_expense(eid)['revision'])
            self.assertEqual(e.list_expenses(),[])

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=25)
        return app.run().switch_page('views/expenses.py').run()

    def test_delete_removes_the_expense_its_payments_and_its_events(self):
        eid=self.create()
        self.pay(eid,100)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM expense_payments WHERE expense_id=?',(eid,)).fetchone()[0],1)
            self.assertGreater(c.execute('SELECT COUNT(*) FROM expense_events WHERE expense_id=?',(eid,)).fetchone()[0],0)
        e.delete(eid,'Captura duplicada',expected_revision=e.get_expense(eid)['revision'])
        self.assertEqual(e.list_expenses(),[])
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM expenses WHERE id=?',(eid,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM expense_payments WHERE expense_id=?',(eid,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM expense_events WHERE expense_id=?',(eid,)).fetchone()[0],0)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_delete_requires_a_reason_and_the_current_revision(self):
        eid=self.create()
        with self.assertRaises(ValueError):e.delete(eid,'',expected_revision=0)
        with self.assertRaises(ValueError):e.delete(eid,'Prueba',expected_revision=99)
        self.assertEqual(len(e.list_expenses()),1)

    def test_delete_is_blocked_when_a_partner_covered_it(self):
        eid=self.create()
        with db.connect(write=True) as c:
            row=c.execute('SELECT total_cents FROM expenses WHERE id=?',(eid,)).fetchone()
            c.execute('INSERT INTO partner_expense_settlements VALUES(?,?,?,?,?,?)',
                (eid,'Luis',row['total_cents'],self.today.isoformat(),'test-origin',now().isoformat()))
        with self.assertRaises(ValueError) as ctx:e.delete(eid,'Prueba',expected_revision=e.get_expense(eid)['revision'])
        self.assertIn('socio',str(ctx.exception))
        self.assertEqual(len(e.list_expenses()),1)
        # Covered by a partner, it is locked even against cancelling (partner_expense_cancel trigger).
        with self.assertRaises(sqlite3.IntegrityError):e.cancel(eid,'Prueba',expected_revision=e.get_expense(eid)['revision'])

    def test_delete_is_blocked_when_linked_to_an_orders_extra_cost(self):
        from services import production as p,order_costs
        oid=p.create_order('Pedido test','Cliente')
        eid=e.create(dict(self.data,order_id=oid),request_key='linked')
        order_costs.add(oid,'Flete','Envío',expense_id=eid,request_key='extra1',expected_expense_revision=e.get_expense(eid)['revision'])
        with self.assertRaises(ValueError) as ctx:e.delete(eid,'Prueba',expected_revision=e.get_expense(eid)['revision'])
        self.assertIn('costo adicional',str(ctx.exception))
        self.assertEqual(len(e.list_expenses()),1)

    def test_ui_delete_from_detail_returns_to_the_list(self):
        eid=self.create()
        app=self.app()
        app.button(key='expense_open').click().run()
        self.assertEqual(app.session_state['open_expense_id'],eid)
        app.button(key='expense_delete').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(app.session_state['active_dialog'][0],'expense_delete_form')
        next(w for w in app.text_input if w.label=='Motivo *').set_value('Prueba duplicada')
        next(b for b in app.button if b.label=='Eliminar definitivamente').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertIsNone(app.session_state.get('open_expense_id'))
        self.assertEqual(e.list_expenses(),[])

    def test_ui_capture_preview_and_paid_creation(self):
        app=self.app()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        app.button(key='expense_new').click().run()
        prefix='expense_'+app.session_state['dialog_request_key']
        app.text_input(key=prefix+'_concept').set_value('Compra rápida')
        app.number_input(key=prefix+'_amount').set_value(1160)
        app.selectbox(key=prefix+'_taxmode').set_value('Total con IVA 16%')
        app.checkbox(key=prefix+'_paid').check()
        next(b for b in app.button if b.label=='Calcular total').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(e.list_expenses(),[])
        self.assertEqual(app.text_input(key=prefix+'_concept').value,'Compra rápida')
        self.assertTrue(any('$1,160.00' in message.value for message in app.success))
        app.button(key=prefix+'_save').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        row=e.get_expense(app.session_state['open_expense_id'])
        self.assertEqual(row['payment_status'],'Pagado')
        self.assertEqual(row['tax_cents'],16000)
        app.button(key='expense_back').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])

    def test_ui_category_limits_specific_label(self):
        app=self.app()
        app.button(key='expense_new').click().run()
        prefix='expense_'+app.session_state['dialog_request_key']
        app.selectbox(key=prefix+'_category').set_value('Software / SaaS').run()
        self.assertIn('IA / productividad',app.selectbox(key=prefix+'_subtype').options)
        self.assertNotIn('Filamento / materia prima',app.selectbox(key=prefix+'_subtype').options)
        app.selectbox(key=prefix+'_subtype').set_value('IA / productividad').run()
        app.text_input(key=prefix+'_concept').set_value('ChatGPT Pro')
        app.number_input(key=prefix+'_amount').set_value(399)
        app.button(key=prefix+'_save').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        row=e.get_expense(app.session_state['open_expense_id'])
        self.assertEqual((row['category'],row['subtype']),('Software / SaaS','IA / productividad'))

    def test_ui_partial_pay_edit_locked_and_reuse_no_copied_payment(self):
        eid=self.create()
        app=self.app()
        app.button(key='expense_open').click().run()
        app.button(key='expense_payment').click().run()
        prefix='expense_pay_'+app.session_state['dialog_request_key']
        app.number_input(key=prefix+'_amount').set_value(100)
        next(b for b in app.button if b.label=='Guardar pago').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(e.get_expense(eid)['paid_cents'],10000)
        app.button(key='expense_edit').click().run()
        prefix='expense_'+app.session_state['dialog_request_key']
        self.assertTrue(app.number_input(key=prefix+'_amount').disabled)
        app.selectbox(key=prefix+'_receipt').set_value('Factura')
        app.text_input(key=prefix+'_ref').set_value('FACT-1')
        next(b for b in app.button if b.label=='Guardar cambios').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(e.get_expense(eid)['control'],'Completo')
        app.button(key='expense_reuse').click().run()
        prefix='expense_'+app.session_state['dialog_request_key']
        self.assertFalse(app.checkbox(key=prefix+'_paid').value)
        self.assertEqual(app.text_input(key=prefix+'_ref').value,'')
        next(b for b in app.button if b.label=='Registrar gasto').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(e.get_expense(app.session_state['open_expense_id'])['paid_cents'],0)
        self.assertEqual(len(e.list_expenses()),2)

    def test_ui_cost_template_generation_and_report_chart(self):
        app=self.app()
        app.button(key='expense_template_new').click().run()
        prefix='expense_template_'+app.session_state['dialog_request_key']
        app.text_input(key=prefix+'_name').set_value('Renta taller')
        app.text_input(key=prefix+'_concept').set_value('Renta mensual')
        app.number_input(key=prefix+'_amount').set_value(8000)
        next(b for b in app.button if b.label=='Guardar costo').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(e.list_expenses(),[])
        tid=e.templates()[0]['id']
        app.button(key=f'expense_generate_{tid}').click().run()
        next(b for b in app.button if b.label=='Registrar y abrir gasto').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertEqual(e.get_expense(app.session_state['open_expense_id'])['total_cents'],800000)
        app.button(key='expense_back').click().run()
        self.assertFalse(app.exception,[v.message for v in app.exception])
        self.assertTrue(any(m.label=='Registrado' and m.value=='$8,000.00' for m in app.metric))
