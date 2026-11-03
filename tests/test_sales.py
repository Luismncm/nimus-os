import copy
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
from services import sales as s, quotations as q
from services.catalog import saved_values
from services.quotation_document import document
from services.queries import load_snapshot
from utils.dates import now


class SalesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'sales.db'
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.today=now().date()
        self.data=q.defaults()
        self.data.update(client='Cliente ventas',project='Origen',iva=True,discount=10,
            lines=[dict(description='Lámpara',quantity=2,price=500,produce=True),dict(description='Envío',quantity=1,price=100,produce=False)])

    def direct(self, **kwargs):
        return s.create_direct(self.data,self.today,request_key=kwargs.pop('key','sale1'),**kwargs)

    def quote(self):
        qid=q.create_quote()
        q.save_quote(qid,self.data,expected_revision=0,status='Aceptada')
        return qid

    def pay(self,sid,amount=100,key='pay1',on=None,revision=None):
        row=s.get_sale(sid)
        return s.record_payment(sid,amount,on or self.today,'Efectivo','Abono',request_key=key,
            expected_revision=row['revision'] if revision is None else revision,expected_quote_revision=row['quote_revision'])

    def test_direct_totals_no_quote_or_implicit_stock_order_payment(self):
        sid=self.direct()
        row=s.get_sale(sid)
        self.assertEqual(row['total_cents'],114840)
        self.assertEqual(row['paid_cents'],0)
        self.assertEqual(row['origin'],'Directa')
        self.assertEqual(q.list_quotes(),[])
        self.assertEqual(load_snapshot()['orders'],[])
        with db.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM inventory_movements').fetchone()[0],0)
        self.assertIn('Cliente ventas',saved_values('client'))

    def test_due_date_set_later_makes_balance_overdue_and_keeps_history(self):
        from services import sale_corrections
        sid=self.direct()
        self.assertFalse(s.get_sale(sid)['overdue'])
        row=s.get_sale(sid)
        with self.assertRaises(ValueError):s.set_due_date(sid,(self.today-timedelta(days=1)).isoformat(),expected_revision=row['revision'])
        with self.assertRaises(ValueError):s.set_due_date(sid,self.today.isoformat(),expected_revision=row['revision']+1)
        s.set_due_date(sid,self.today.isoformat(),expected_revision=row['revision'])
        self.assertEqual(s.get_sale(sid)['due_on'],self.today.isoformat())
        self.assertIn('sin fecha →',sale_corrections.history(sid)[0]['detail'])
        # A due date reached with money still owed reads as overdue the next day.
        with patch('services.sales.now',return_value=now()+timedelta(days=1)):
            self.assertTrue(s.get_sale(sid)['overdue'])

    def test_duplicate_submit_and_changed_payload(self):
        sid=self.direct()
        self.assertEqual(self.direct(),sid)
        self.data['client']='Otro'
        with self.assertRaises(ValueError): self.direct()
        self.assertEqual(len(s.list_sales()),1)

    def test_invalid_sale_dates_client_empty_items_and_future_payments(self):
        with self.assertRaises(ValueError): self.direct(due_on=self.today-timedelta(days=1))
        with self.assertRaises(ValueError): s.create_direct(self.data,self.today+timedelta(days=1),request_key='future')
        for field,value in [('client',''),('lines',[])]:
            d=dict(self.data,**{field:value})
            with self.assertRaises(ValueError): s.create_direct(d,self.today,request_key=field)
        sid=self.direct()
        with self.assertRaises(ValueError): self.pay(sid,on=self.today+timedelta(days=1))

    def test_direct_payment_idempotence_overpay_void_and_cancel(self):
        sid=self.direct()
        pid=self.pay(sid,100)
        self.assertEqual(self.pay(sid,100,revision=0),pid)
        self.assertEqual(s.get_sale(sid)['paid_cents'],10000)
        with self.assertRaises((ValueError,sqlite3.IntegrityError)): self.pay(sid,1200,key='over')
        with self.assertRaises(sqlite3.IntegrityError): s.cancel(sid,'Error',expected_revision=1)
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c:
            c.execute('DELETE FROM sale_payments')
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c:
            c.execute('UPDATE sale_payments SET amount_cents=1')
        s.void_payment(sid,pid,'Duplicado')
        self.assertEqual(s.get_sale(sid)['balance_cents'],114840)
        s.cancel(sid,'Captura duplicada',expected_revision=2)
        row=s.get_sale(sid)
        self.assertEqual(row['status'],'Cancelada')
        self.assertIn('Venta cancelada',document(row,receipt=True,sale=True).decode())
        with self.assertRaises(ValueError): self.pay(sid,key='cancelled')
        self.assertEqual(s.report(self.today,self.today)['sold_cents'],0)

    def test_concurrent_direct_payments_reject_stale_capture(self):
        sid=self.direct()
        def pay(i):
            try:
                self.pay(sid,800,key=f'parallel{i}',revision=0)
                return True
            except (ValueError,sqlite3.IntegrityError): return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(pay,range(2))),[False,True])
        self.assertEqual(s.get_sale(sid)['paid_cents'],80000)

    def test_quote_preserves_prepayment_and_shares_future_payments_and_voids(self):
        qid=self.quote()
        pid=q.record_payment(qid,300,self.today,'Transferencia','Anticipo',request_key='before',expected_revision=1)
        sid=s.from_quote(qid,self.today,request_key='fromquote',expected_revision=2)
        self.assertEqual(s.from_quote(qid,self.today,request_key='double',expected_revision=2),sid)
        self.assertEqual(s.get_sale(sid)['paid_cents'],30000)
        self.assertEqual(q.get_quote(qid)['sale_id'],sid)
        self.pay(sid,200,key='fromsales')
        self.assertEqual(q.get_quote(qid)['paid_cents'],50000)
        q.record_payment(qid,100,self.today,'Efectivo','Abono',request_key='fromquote',expected_revision=q.get_quote(qid)['revision'])
        self.assertEqual(s.get_sale(sid)['paid_cents'],60000)
        s.void_payment(sid,pid,'Corregir anticipo')
        self.assertEqual(q.get_quote(qid)['paid_cents'],30000)
        self.assertEqual(s.report(self.today,self.today)['collected_cents'],30000)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sale_payments').fetchone()[0],0)

    def test_quote_conversion_lock_stale_acceptance_and_cancellation(self):
        qid=q.create_quote()
        with self.assertRaises(ValueError): s.from_quote(qid,self.today,request_key='draft',expected_revision=0)
        q.save_quote(qid,self.data,expected_revision=0,status='Aceptada')
        with self.assertRaises(ValueError): s.from_quote(qid,self.today,request_key='stale',expected_revision=0)
        sid=s.from_quote(qid,self.today,request_key='ready',expected_revision=1)
        row=q.get_quote(qid)
        self.assertTrue(row['locked'])
        with self.assertRaises((ValueError,sqlite3.IntegrityError)):
            q.save_quote(qid,dict(self.data,client='Cambio'),expected_revision=row['revision'])
        with self.assertRaises((ValueError,sqlite3.IntegrityError)):
            q.set_status(qid,'Cancelada',expected_revision=row['revision'])
        s.cancel(sid,'Captura duplicada',expected_revision=0)
        with self.assertRaises(sqlite3.IntegrityError):
            q.record_payment(qid,100,self.today,'Efectivo','Abono',request_key='blocked',expected_revision=row['revision'])
        with self.assertRaises((ValueError,sqlite3.IntegrityError)): q.convert_to_order(qid,expected_revision=row['revision'])
        self.assertEqual(load_snapshot()['orders'],[])

    def test_order_conversion_direct_and_quote_each_once(self):
        sid=self.direct()
        oid=s.create_order(sid,expected_revision=0)
        self.assertEqual(s.create_order(sid,expected_revision=0),oid)
        self.assertEqual([(r['name'],r['quantity']) for r in load_snapshot()['items']],[('Lámpara',2)])
        qid=self.quote()
        qoid=q.convert_to_order(qid,expected_revision=1)
        qsid=s.from_quote(qid,self.today,request_key='converted',expected_revision=2)
        self.assertEqual(s.get_sale(qsid)['order_id'],qoid)
        self.assertEqual(s.create_order(qsid,expected_revision=0,expected_quote_revision=3),qoid)
        self.assertEqual(len(load_snapshot()['orders']),2)

    def test_reports_distinguish_sale_date_and_payment_date_and_filters(self):
        previous=self.today-timedelta(days=45)
        sid=s.create_direct(self.data,previous,due_on=previous,channel='B2B',request_key='old')
        self.pay(sid,100,key='recent')
        fresh=self.direct()
        self.pay(fresh,200,key='fresh')
        report=s.report(self.today,self.today)
        self.assertEqual(report['count'],1)
        self.assertEqual(report['sold_cents'],114840)
        self.assertEqual(report['collected_cents'],30000)
        self.assertEqual(report['balance_cents'],94840)
        self.assertEqual(report['total_balance_cents'],199680)
        self.assertEqual(report['overdue_cents'],104840)
        self.assertEqual(s.report(self.today,self.today,channel='B2B')['collected_cents'],10000)
        self.assertEqual(s.report(self.today,self.today,channel='B2B')['count'],0)
        self.assertEqual(s.report(self.today,self.today,search='missing')['rows'],[])

    def test_full_payment_zero_price_service_and_exports(self):
        sid=self.direct()
        self.pay(sid,1148.40)
        self.assertEqual(s.get_sale(sid)['payment_status'],'Liquidada')
        self.data['client']='=SUM(1+1)'
        self.data['lines']=[dict(description='<script>unsafe</script>',quantity=1.5,price=0,produce=False)]
        zero=self.direct(key='zero')
        with self.assertRaises(ValueError): s.create_order(zero,expected_revision=0)
        html=document(s.get_sale(zero),receipt=True,sale=True).decode()
        self.assertIn('Comprobante de venta',html)
        self.assertNotIn('<script>unsafe',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn("'=SUM(1+1)",s.export_csv(s.list_sales()).decode('utf-8-sig'))

    def test_v7_migration_preserves_quotes_payments_orders_and_no_inferred_sales(self):
        old=Path(self.tmp.name)/'v7.db'
        from models.inventory_schema import create_inventory_schema
        from models.recipe_schema import create_recipe_schema
        from models.operations_schema import create_operations_schema
        from models.manual_inventory_schema import create_manual_inventory_schema
        from models.quotation_schema import create_quotation_schema
        with db.connect(old,write=True) as c:
            db._create_schema(c)
            for create in (create_inventory_schema,create_recipe_schema,create_operations_schema,create_manual_inventory_schema,create_quotation_schema): create(c)
            c.execute("INSERT INTO quotations(code,status,payload,total_cents,created_at,updated_at) VALUES('COT-OLD','Aceptada','{}',10000,'old','old')")
            c.execute("INSERT INTO quotation_payments(code,quote_id,amount_cents,paid_on,method,concept,request_key,created_at) VALUES('REC-OLD',1,5000,'2026-01-01','Efectivo','Anticipo','old','old')")
            c.execute('PRAGMA user_version=7')
            before=[tuple(r) for r in c.execute('SELECT * FROM quotation_payments')]
        db.init_db(old)
        with db.connect(old) as c:
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM quotation_payments')])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sales').fetchone()[0],0)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=25)
        return app.run().switch_page('views/sales.py').run()

    def test_ui_empty_and_new_direct_form_preserves_fields_and_registers(self):
        app=self.app()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key='sale_new').click().run()
        prefix='sale_new_'+app.session_state['dialog_request_key']
        app.text_input(key=prefix+'_project').set_value('Venta rápida')
        app.session_state[prefix+'_lines']={'edited_rows':{0:{'description':'Servicio','quantity':1.0,'price':120.0}},'added_rows':[],'deleted_rows':[]}
        next(b for b in app.button if b.label=='Calcular total').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(s.list_sales(),[])
        self.assertEqual(app.text_input(key=prefix+'_project').value,'Venta rápida')
        self.assertIn('$120.00',app.success[0].value)
        # AppTest does not drive data_editor; emulate the browser's delta on each submit.
        app.session_state[prefix+'_lines']={'edited_rows':{0:{'description':'Servicio','quantity':1.0,'price':120.0}},'added_rows':[],'deleted_rows':[]}
        next(b for b in app.button if b.label=='Registrar venta').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(s.get_sale(app.session_state['open_sale_id'])['total_cents'],12000)

    def test_ui_direct_payment_receipt_and_return_to_register(self):
        sid=self.direct()
        app=self.app()
        app.button(key='sale_open').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key='sale_payment').click().run()
        prefix='sale_payment_'+app.session_state['dialog_request_key']
        app.number_input(key=prefix+'_amount').set_value(100)
        next(b for b in app.button if b.label=='Guardar pago recibido').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(s.get_sale(sid)['paid_cents'],10000)
        app.button(key='sale_back').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.metric[0].value,'$1,148.40')

    def test_ui_quote_to_sale_and_link_back(self):
        qid=self.quote()
        app=self.app()
        app.button(key='sale_from_quote').click().run()
        next(b for b in app.button if b.label=='Confirmar y abrir venta').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.button(key='sale_quote_open').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.session_state['open_quote_id'],qid)
        self.assertTrue(any(b.key=='quote_sale_open' for b in app.button))
