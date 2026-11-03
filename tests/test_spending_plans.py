"""Current accounts and future expenses form one coherent cash projection."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import spending_plans as plans,cash_projection as cash,expense_control as control,expenses,treasury
from tests import test_treasury as fixture


class SpendingPlansTest(unittest.TestCase):
    setUp=fixture.TreasuryTest.setUp
    sale=fixture.TreasuryTest.sale
    pay=fixture.TreasuryTest.pay

    def plan(self,**kwargs):
        args=dict(month=self.today.strftime('%Y-%m'),concept='Filamento previsto',amount=250,account_id=self.bank,request_key='plan')
        args.update(kwargs);return plans.save(**args)

    def row(self,pid):return next(r for r in plans.report(self.today.strftime('%Y-%m'))['rows'] if r['id']==pid)

    def projection(self):
        r=control.report(self.today.strftime('%Y-%m'))
        return cash.projection(r['month'],pending_cents=r['pending_cents'],pending=r['pending'])

    def funded(self):self.pay(self.sale(),1000,self.bank)

    def test_existing_accounts_are_used_immediately_and_plan_is_not_an_expense(self):
        self.funded();pid=self.plan()
        r=self.projection()
        self.assertEqual((r['cash']['total_cents'],r['projected_cents'],r['after_cents']),(100000,25000,75000))
        self.assertEqual(expenses.list_expenses(),[])
        self.assertEqual(next(a for a in r['accounts'] if a['id']==self.bank)['after_cents'],75000)
        self.assertTrue(r['cash']['estimated'])
        self.assertEqual(self.plan(),pid)

    def test_materialization_pending_preserves_projection_and_does_not_move_money(self):
        self.funded();pid=self.plan();before=self.projection()
        eid=plans.materialize(pid,expense_on=self.today,expected_revision=0,request_key='capture')
        after=self.projection()
        self.assertEqual((after['pending_cents'],after['additional_cents']),(25000,0))
        self.assertEqual(after['after_cents'],before['after_cents'])
        self.assertEqual(after['cash']['total_cents'],before['cash']['total_cents'])
        self.assertEqual(expenses.get_expense(eid)['account'],'Cuenta bancaria NIMUS')
        self.assertEqual(plans.materialize(pid,expense_on=self.today,expected_revision=0,request_key='capture'),eid)
        with self.assertRaises(ValueError):plans.materialize(pid,expense_on=self.today,expected_revision=0,request_key='another')
        self.assertEqual(len(expenses.list_expenses()),1)

    def test_materialization_paid_moves_cash_and_removes_prediction_once(self):
        self.funded();pid=self.plan();before=self.projection()
        eid=plans.materialize(pid,expense_on=self.today,paid=True,account_id=self.bank,method='Transferencia',expected_revision=0,request_key='paid')
        after=self.projection()
        self.assertEqual((after['cash']['total_cents'],after['projected_cents'],after['after_cents']),(75000,0,75000))
        self.assertEqual(after['after_cents'],before['after_cents'])
        self.assertEqual(expenses.get_expense(eid)['payment_status'],'Pagado')
        self.assertEqual(plans.materialize(pid,expense_on=self.today,paid=True,account_id=self.bank,method='Transferencia',expected_revision=0,request_key='paid'),eid)
        with self.assertRaises(ValueError):plans.materialize(pid,expense_on=self.today,paid=True,account_id=self.cash,method='Efectivo',expected_revision=0,request_key='paid')

    def test_invalid_payment_and_concurrent_conversion_are_atomic(self):
        pid=self.plan()
        with self.assertRaises(ValueError):plans.materialize(pid,expense_on=self.today,paid=True,expected_revision=0,request_key='invalid')
        self.assertEqual(self.row(pid)['status'],'Previsto');self.assertEqual(expenses.list_expenses(),[])
        def run(key):
            try:plans.materialize(pid,expense_on=self.today,expected_revision=0,request_key=key);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['a','b']))
        self.assertEqual(sum(results),1);self.assertEqual(len(expenses.list_expenses()),1)

    def test_edit_cancel_month_and_unknown_account_all_preserve_money(self):
        self.funded();pid=self.plan()
        plans.save(self.today.strftime('%Y-%m'),'Otro concepto',100,plan_id=pid,expected_revision=0,request_key='edit')
        r=self.projection();self.assertEqual((r['projected_cents'],r['unassigned_cents']),(10000,10000))
        with self.assertRaises(ValueError):plans.cancel(pid,expected_revision=0,request_key='stale')
        plans.cancel(pid,expected_revision=1,request_key='cancel')
        plans.cancel(pid,expected_revision=1,request_key='cancel')
        self.assertEqual(self.projection()['after_cents'],100000)
        self.assertEqual(self.row(pid)['status'],'Cancelado')
        for amount in (0,-1,True,float('nan')):
            with self.assertRaises(ValueError):self.plan(amount=amount,request_key='invalid')
        with self.assertRaises(ValueError):self.plan(due_on='2099-01-01',request_key='wrong-month')
        with db.connect(write=True) as conn:
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('DELETE FROM spending_plan_events')
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('DELETE FROM spending_plans')

    def test_reconciled_and_movement_based_accounts_mix_without_double_counting(self):
        self.funded();snapshot=cash.overview();bank=next(r for r in snapshot['accounts'] if r['id']==self.bank)
        cash.confirm_balances({self.bank:1200},expected={self.bank:bank['token']},request_key='confirmed')
        self.pay(self.sale('second'),100,self.cash,'cash')
        r=cash.overview();self.assertEqual(r['total_cents'],130000)
        self.assertEqual(next(a['basis'] for a in r['accounts'] if a['id']==self.bank),'Conciliado')
        self.assertEqual(next(a['basis'] for a in r['accounts'] if a['id']==self.cash),'Movimientos')
        self.assertEqual(r['confirmed_cents'],120000)

    def test_all_finance_modules_show_same_existing_accounts_and_result(self):
        self.funded();self.plan()
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        # The full summary lives in Resumen y previsión; the other finance pages show the same figures in one line.
        app.switch_page('views/budget.py').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual([(m.label,m.value) for m in app.metric[:3]],
            [('Total en cuentas','$1,000.00'),('Gastos proyectados','$250.00'),('Después de gastos','$750.00')])
        for path in ('treasury','expenses'):
            app.switch_page('views/'+path+'.py').run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            line=[m.value for m in app.markdown]
            for text in (':gray[Total en cuentas] **$1,000.00**',':gray[Gastos proyectados] **$250.00**',':gray[Después de gastos] **$750.00**'):
                self.assertIn(text,line,path)
            self.assertFalse(any(m.label=='Total en cuentas' for m in app.metric),path)

    def test_plan_form_can_create_edit_and_materialize_without_retyping(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/budget.py').run()
        app.button(key='control_planned').click().run()
        next(i for i in app.text_input if i.label=='Concepto *').set_value('Servicio previsto')
        next(i for i in app.number_input if i.label=='Importe previsto · MXN *').set_value(200)
        next(b for b in app.button if b.label=='Guardar previsión').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.session_state['expense_control_tabs']='Previsión';app.run()
        app.button(key='control_plan_materialize').click().run()
        prefix='materialize_'+app.session_state['dialog_request_key']
        app.button(key=prefix+'_save').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(expenses.list_expenses()[0]['concept'],'Servicio previsto')
        self.assertEqual(self.projection()['projected_cents'],20000)
        self.assertEqual(self.projection()['additional_cents'],0)

    def test_paying_last_bill_in_filtered_account_resets_filter_without_losing_screen(self):
        eid=control.register(concept='Pago final',amount=100,expense_on=self.today,account_id=self.bank,request_key='bill')
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/budget.py').run()
        app.session_state['expense_control_tabs']='Por pagar';app.run()
        app.selectbox(key='control_pending_account').set_value('Cuenta bancaria NIMUS').run()
        expenses.record_payment(eid,100,self.today,'Cuenta bancaria NIMUS','Transferencia',expected_revision=0,request_key='paid')
        app.run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.selectbox(key='control_pending_account').value,'Todas')

    def test_pending_without_account_requires_real_payment_account_and_never_creates_placeholder(self):
        eid=control.register(concept='Cuenta pendiente',amount=100,expense_on=self.today,request_key='unknown-account')
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/budget.py').run()
        app.session_state['expense_control_tabs']='Por pagar';app.run()
        app.button(key='control_pending_pay').click().run()
        prefix='expense_pay_'+app.session_state['dialog_request_key']
        account=app.selectbox(key=prefix+'_account')
        self.assertIsNone(account.value);self.assertNotIn('Por definir',account.options)
        next(b for b in app.button if b.label=='Guardar pago').click().run()
        self.assertEqual(expenses.get_expense(eid)['paid_cents'],0)
        self.assertFalse(any(a['name']=='Por definir' for a in treasury.accounts()))
        app.selectbox(key=prefix+'_account').set_value('Cuenta bancaria NIMUS')
        next(b for b in app.button if b.label=='Guardar pago').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(expenses.get_expense(eid)['paid_cents'],10000)


if __name__=='__main__':unittest.main()
