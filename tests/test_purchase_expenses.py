"""A purchase, its expense and any initial payment form one atomic operation."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import inbound,expenses,expense_control,treasury,cash_projection
from tests import test_inbound as fixture
from utils.dates import now


class PurchaseExpenseTest(unittest.TestCase):
    setUp=fixture.InboundTest.setUp
    stock=fixture.InboundTest.stock
    fingerprint=fixture.InboundTest.fingerprint
    publish=fixture.InboundTest.publish
    count=fixture.InboundTest.count

    def create(self,key='purchase',**extra):
        financial=dict(amount=321.45,paid=False,account_id=1);financial.update(extra)
        return inbound.create(5,'Stock','Compra de prueba',supplier='Proveedor A',component_id=self.supplies['cable_id'],financial=financial,request_key=key)

    def report(self):return cash_projection.workspace(now().strftime('%Y-%m'))

    def test_unpaid_purchase_becomes_one_pending_expense_before_stock_arrives(self):
        pid=self.create();row=inbound.get(pid);e=expenses.get_expense(row['expense_id'])
        self.assertEqual((row['status'],row['expense_status'],self.stock()),('Solicitado','Por pagar',0))
        self.assertEqual((e['total_cents'],e['balance_cents'],e['supplier'],e['account']),(32145,32145,'Proveedor A','Cuenta bancaria NIMUS'))
        self.assertIn(row['code'],e['concept'])
        self.assertEqual(self.report()[1]['projected_cents'],32145)
        self.assertEqual(treasury.ledger('0001-01-01','9999-12-31',include_undated=True)['outflow'],0)
        self.assertEqual(self.create(),pid)
        self.assertEqual((self.count('expenses'),self.count('inventory_inbound_expenses')),(1,1))

    def test_paid_purchase_posts_one_payment_and_receipts_never_duplicate_costs(self):
        pid=self.create(paid=True,method='Transferencia');row=inbound.get(pid)
        self.assertEqual((row['expense_status'],row['expense_balance_cents']),('Pagado',0))
        self.assertEqual(self.report()[1]['cash']['total_cents'],-32145)
        self.assertEqual(self.report()[1]['projected_cents'],0)
        for quantity,key in ((2,'first'),(3,'last')):
            inbound.receive(pid,quantity,expected_token=inbound.get(pid)['token'],request_key=key)
        self.assertEqual((self.stock(),inbound.get(pid)['status']),(5,'Recibido'))
        self.assertEqual((self.count('expenses'),self.count('expense_payments')),(1,1))
        self.assertEqual(self.report()[1]['cash']['total_cents'],-32145)
        self.assertEqual(self.create(paid=True,method='Transferencia'),pid)

    def test_later_partial_payment_is_visible_on_purchase_and_keeps_projected_result(self):
        pid=self.create();row=inbound.get(pid);before=self.report()[1]['after_cents']
        expenses.record_payment(row['expense_id'],100,now().date(),'Cuenta bancaria NIMUS','Transferencia',expected_revision=0,request_key='partial')
        fresh=inbound.get(pid)
        self.assertEqual((fresh['expense_status'],fresh['expense_paid_cents'],fresh['expense_balance_cents']),('Pago parcial',10000,22145))
        self.assertEqual(self.report()[1]['after_cents'],before)

    def test_invalid_payment_and_failed_link_roll_back_order_sku_expense_and_cash(self):
        before=self.fingerprint()
        for extra in (dict(paid=True,account_id=None),dict(paid=True,method=''),dict(amount=0),dict(amount=None)):
            with self.assertRaises(ValueError):self.create(**extra)
            self.assertEqual(self.fingerprint(),before)
        with patch.object(inbound,'_link',side_effect=ValueError('Falla al vincular')),self.assertRaises(ValueError):
            self.create(paid=True,method='Transferencia')
        self.assertEqual(self.fingerprint(),before)

    def test_retry_rejects_changed_cost_or_payment_without_adding_records(self):
        self.create();before=self.fingerprint()
        for extra in (dict(amount=320),dict(paid=True,method='Transferencia'),dict(account_id=2)):
            with self.assertRaises(ValueError):self.create(**extra)
            self.assertEqual(self.fingerprint(),before)

    def test_cancelling_unreceived_unpaid_purchase_cancels_its_pending_bill(self):
        pid=self.create();row=inbound.get(pid)
        event=inbound.cancel(pid,'Ya no se comprará',expected_token=row['token'],request_key='cancel')
        self.assertEqual(inbound.cancel(pid,'Ya no se comprará',expected_token=row['token'],request_key='cancel'),event)
        fresh=inbound.get(pid)
        self.assertEqual((fresh['status'],fresh['expense_status'],self.stock()),('Cancelado','Cancelado',0))
        self.assertEqual(self.report()[1]['projected_cents'],0)
        self.assertEqual(fresh['expense_balance_cents'],0)

    def test_failed_cancellation_rolls_back_bill_and_order_together(self):
        pid=self.create();before=self.fingerprint();row=inbound.get(pid)
        with patch.object(inbound,'_event',side_effect=ValueError('Falla de registro')),self.assertRaises(ValueError):
            inbound.cancel(pid,'Prueba de cancelación',expected_token=row['token'],request_key='cancel')
        self.assertEqual(self.fingerprint(),before)

    def test_migration_from_25_preserves_all_prior_rows_and_does_not_guess_old_cost_links(self):
        self.create(paid=True,method='Transferencia')
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE inventory_inbound_expenses');conn.execute('PRAGMA user_version=25')
        before=self.fingerprint();db.init_db();db.init_db();after=self.fingerprint()
        for table,rows in before.items():self.assertEqual(after[table],rows,table)
        self.assertEqual(self.count('inventory_inbound_expenses'),0)
        self.assertEqual((self.count('expenses'),self.count('expense_payments')),(1,1))
        with db.connect() as conn:
            # Version 25 now continues through every later migration.
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-compras-gastos-v26*')))

    def test_cancellation_keeps_real_payments_and_received_stock(self):
        pid=self.create(paid=True,method='Transferencia');row=inbound.get(pid)
        inbound.cancel(pid,'Proveedor canceló',expected_token=row['token'],request_key='cancel-paid')
        self.assertEqual(inbound.get(pid)['expense_status'],'Pagado')
        self.assertEqual(self.report()[1]['cash']['total_cents'],-32145)
        other=self.create('partial-order')
        inbound.receive(other,2,expected_token=inbound.get(other)['token'],request_key='receive-part')
        inbound.cancel(other,'No llegará el resto',expected_token=inbound.get(other)['token'],request_key='cancel-part')
        self.assertEqual((self.stock(),inbound.get(other)['expense_status']),(2,'Por pagar'))

    def test_existing_expense_can_link_without_reposting_money_or_being_used_twice(self):
        pid=inbound.create(5,'Stock','Compra anterior',component_id=self.supplies['cable_id'],request_key='legacy')
        eid=expense_control.register(concept='Compra ya capturada',amount=100,expense_on=now().date(),paid=True,account_id=1,method='Transferencia',request_key='bill')
        before=self.report()[1]['cash']['total_cents'];token=inbound.get(pid)['token']
        args=dict(existing_expense_id=eid,expected_expense_revision=expenses.get_expense(eid)['revision'],expected_token=token,request_key='link')
        self.assertEqual(inbound.attach_expense(pid,**args),eid);self.assertEqual(inbound.attach_expense(pid,**args),eid)
        self.assertEqual((self.count('expenses'),self.count('expense_payments')),(1,1))
        self.assertEqual(self.report()[1]['cash']['total_cents'],before)
        self.assertEqual(inbound.purchase_for_expense(eid)['id'],pid)
        self.assertEqual(inbound.create(5,'Stock','Compra anterior',component_id=self.supplies['cable_id'],request_key='legacy'),pid)
        other=inbound.create(1,'Stock','Otra compra',component_id=self.supplies['cable_id'],request_key='other')
        with self.assertRaises(ValueError):inbound.attach_expense(other,**(args|dict(expected_token=inbound.get(other)['token'],request_key='reuse')))

    def test_concurrent_cost_capture_for_legacy_order_posts_one_expense(self):
        pid=inbound.create(5,'Stock','Sin precio anterior',component_id=self.supplies['cable_id'],request_key='legacy')
        token=inbound.get(pid)['token']
        def link(key):
            try:inbound.attach_expense(pid,financial=dict(amount=100),expected_token=token,request_key=key);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(link,['a','b']))
        self.assertEqual(sum(results),1);self.assertEqual(self.count('expenses'),1)

    def test_native_creation_paid_state_keeps_fields_and_opens_bidirectional_expense(self):
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/collection.py').run()
        a.button(key='inventory_receive').click().run()
        prefix='receipt_'+a.session_state['dialog_request_key']
        a.button_group(key=prefix+'_operation').set_value('Pedido').run()
        a.button_group(key=prefix+'_mode').set_value('Pieza del catálogo').run()
        a.selectbox(key=prefix+'_component').set_value(self.supplies['cable_id']).run()
        a.text_input(key=prefix+'_reason').set_value('Compra pagada UI')
        a.number_input(key=prefix+'_total').set_value(160)
        a.button_group(key=prefix+'_payment_state').set_value('Ya pagado')
        a.selectbox(key=prefix+'_account').set_value(1)
        a.selectbox(key=prefix+'_method').set_value('Transferencia')
        next(b for b in a.button if b.label=='Guardar pedido').click().run()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        pid=inbound.list_orders()[0]['id'];self.assertEqual(inbound.get(pid)['expense_status'],'Pagado')
        a.button(key='inbound_expense_open').click().run()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        a.button(key='expense_purchase').click().run()
        self.assertFalse(a.exception,[e.message for e in a.exception])
        self.assertEqual(a.session_state['inbound_selected'],pid)


if __name__=='__main__':unittest.main()
