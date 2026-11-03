"""Cash snapshots never invent balances, payments, or duplicate projections."""
import sqlite3
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import cash_projection as cash,treasury,expense_control as control,expenses,sales,quotations
from tests import test_treasury as fixture


class CashProjectionTest(unittest.TestCase):
    setUp=fixture.TreasuryTest.setUp
    sale=fixture.TreasuryTest.sale
    pay=fixture.TreasuryTest.pay
    expense=fixture.TreasuryTest.expense

    def confirm(self,bank=1000,cash_amount=0,key='balance'):
        snap=cash.overview()
        values={r['id']:bank if r['id']==self.bank else cash_amount if r['id']==self.cash else 0 for r in snap['accounts']}
        expected={r['id']:r['token'] for r in snap['accounts']}
        cash.confirm_balances(values,expected=expected,request_key=key)
        return values,expected

    def fingerprint(self):
        with db.connect() as conn:
            tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}

    def test_existing_movements_supply_registered_balances_without_inventing_confirmations(self):
        self.pay(self.sale(),100,self.bank)
        report=cash.overview()
        self.assertFalse(report['complete']);self.assertEqual(report['total_cents'],10000)
        self.assertEqual(report['confirmed_cents'],0)
        self.assertEqual(len(report['missing']),3)
        self.assertEqual(cash.projection('2026-10',pending_cents=20000)['after_cents'],-10000)
        self.assertTrue(report['estimated'])
        self.assertEqual({r['basis'] for r in report['accounts']},{'Movimientos'})
        self.assertEqual(self.fingerprint()['treasury_balance_snapshots'],[])

    def test_confirmed_balance_includes_history_and_only_new_movements_change_it(self):
        sid=self.sale();self.pay(sid,100,self.bank)
        self.confirm(bank=1000,cash_amount=200)
        self.assertEqual(cash.overview()['total_cents'],120000)
        self.pay(sid,50,self.bank,'second')
        row=expenses.get_expense(self.expense())
        expenses.record_payment(row['id'],20,self.today,'Efectivo / caja','Efectivo',expected_revision=row['revision'],request_key='out')
        result=cash.overview();balances={r['id']:r['balance_cents'] for r in result['accounts']}
        self.assertEqual((balances[self.bank],balances[self.cash],result['total_cents']),(105000,18000,123000))
        # Reconfirmation resets the baseline, including the new payment once.
        self.confirm(bank=1050,cash_amount=180,key='reconfirm')
        self.assertEqual(cash.overview()['total_cents'],123000)

    def test_voided_new_payment_restores_balance_and_pending_without_double_subtraction(self):
        self.confirm();eid=self.expense()
        month=self.today.strftime('%Y-%m')
        before=cash.projection(month,pending_cents=control.report(month)['pending_cents'])
        self.assertEqual(before['after_cents'],80000)
        pid=expenses.record_payment(eid,50,self.today,'Cuenta bancaria NIMUS','Transferencia',expected_revision=0,request_key='part')
        partial=cash.projection(month,pending_cents=control.report(month)['pending_cents'])
        self.assertEqual((partial['cash']['total_cents'],partial['pending_cents'],partial['after_cents']),(95000,15000,80000))
        expenses.void_payment(pid,'Captura equivocada')
        self.assertEqual(cash.overview()['total_cents'],100000)
        self.assertEqual(control.report(month)['pending_cents'],20000)

    def test_quote_conversion_does_not_duplicate_balance(self):
        self.confirm();qid=quotations.create_quote()
        quotations.save_quote(qid,self.payload,expected_revision=0,status='Aceptada')
        quotations.record_payment(qid,100,self.today,'Transferencia','Anticipo',account_id=self.bank,request_key='q',expected_revision=1)
        self.assertEqual(cash.overview()['total_cents'],110000)
        sales.from_quote(qid,self.today,request_key='conversion',expected_revision=2)
        self.assertEqual(cash.overview()['total_cents'],110000)

    def test_new_account_uses_its_movements_and_archiving_excludes_only_that_account(self):
        self.confirm(bank=1000,cash_amount=200)
        aid=treasury.save_account('Otra caja','Efectivo')
        self.assertEqual(cash.overview()['total_cents'],120000)
        self.assertFalse(cash.overview()['complete'])
        self.assertEqual(cash.overview()['confirmed_cents'],120000)
        treasury.save_account('Otra caja','Efectivo',account_id=aid,expected_revision=0,active=False)
        self.assertEqual(cash.overview()['total_cents'],120000)
        treasury.save_account('Efectivo / caja','Efectivo',account_id=self.cash,expected_revision=0,active=False)
        self.assertEqual(cash.overview()['total_cents'],100000)

    def test_confirmation_is_atomic_idempotent_and_rejects_stale_form(self):
        values,expected=self.confirm();before=self.fingerprint()
        self.pay(self.sale(),100,self.bank)
        cash.confirm_balances(values,expected=expected,request_key='balance')
        self.assertEqual(len(self.fingerprint()['treasury_balance_snapshots']),3)
        with self.assertRaises(ValueError):cash.confirm_balances(values|{self.bank:1001},expected=expected,request_key='balance')
        with self.assertRaises(ValueError):cash.confirm_balances(values,expected=expected,request_key='stale')
        self.assertEqual(self.fingerprint()['treasury_balance_snapshots'],before['treasury_balance_snapshots'])

    def test_negative_balance_is_preserved_and_unsafe_numbers_rejected(self):
        self.confirm(bank=-100,cash_amount=20)
        r=cash.projection('2026-10',pending_cents=5000)
        self.assertEqual((r['cash']['total_cents'],r['after_cents']),(-8000,-13000))
        scenario=control.project_coverage(available=-80,project_cost=10,pending_cents=5000,allow_negative_available=True)
        self.assertEqual(scenario['after_project_cents'],-14000)
        for value in (True,None,float('nan'),float('inf'),-1000000001):
            with self.assertRaises(ValueError):
                cash.confirm_balances({self.bank:value},expected={},request_key='invalid')

    def test_forecast_adds_only_remaining_extra_and_never_writes_an_expense(self):
        self.confirm(bank=10000,cash_amount=1000);before=self.fingerprint()
        pid=cash.save_forecast('2026-10',500,notes='Aún no registrado',request_key='plan')
        self.assertEqual(cash.save_forecast('2026-10',500,notes='Aún no registrado',request_key='plan'),pid)
        result=cash.projection('2026-10',pending_cents=200000)
        self.assertEqual((result['projected_cents'],result['after_cents']),(250000,850000))
        self.assertEqual(cash.projection('2026-09',pending_cents=200000)['projected_cents'],200000)
        current=self.fingerprint()
        for table,rows in before.items():
            if table!='expense_cash_forecasts':self.assertEqual(current[table],rows,table)
        with self.assertRaises(ValueError):cash.save_forecast('2026-10',501,request_key='plan')
        with self.assertRaises(ValueError):cash.save_forecast('2026-10',600,request_key='stale')
        cash.save_forecast('2026-10',0,expected_id=pid,request_key='clear')
        self.assertEqual(cash.projection('2026-10',pending_cents=200000)['projected_cents'],200000)
        for bad in (-1,None,True,float('nan')):
            with self.assertRaises(ValueError):cash.save_forecast('2026-10',bad,request_key='bad')

    def test_history_is_immutable_and_migration_preserves_every_original_row(self):
        self.confirm();cash.save_forecast('2026-10',100,request_key='plan')
        for table in ('treasury_balance_snapshots','expense_cash_forecasts'):
            with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as conn:conn.execute(f'DELETE FROM {table}')
        self.sale();self.expense()
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE treasury_balance_snapshots');conn.execute('DROP TABLE expense_cash_forecasts');conn.execute('PRAGMA user_version=23')
        original=self.fingerprint();db.init_db();db.init_db();current=self.fingerprint()
        for table,rows in original.items():self.assertEqual(current[table],rows,table)
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertTrue(list((self.path.parent/'backups').glob('*pre-saldos-v24*')))

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        return app.switch_page('views/budget.py').run()

    def test_cards_use_registered_balances_and_only_explicit_confirmation_writes_a_snapshot(self):
        app=self.app();self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual([(m.label,m.value) for m in app.metric[:3]],
                         [('Total en cuentas','$0.00'),('Gastos proyectados','$0.00'),('Después de gastos','$0.00')])
        before=self.fingerprint();app.button(key='control_balance').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(len(app.number_input),3)
        self.assertTrue(all(i.value==0 for i in app.number_input))
        self.assertEqual(self.fingerprint(),before)
        for widget in app.number_input:widget.set_value(100)
        next(b for b in app.button if b.label=='Confirmar saldos').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(cash.overview()['total_cents'],30000)

    def test_cards_and_project_use_same_cash_and_forecast_without_manual_reentry(self):
        self.confirm(bank=10000,cash_amount=1000)
        eid=expenses.create(dict(expenses.defaults(),concept='Compra pendiente',amount=2000),request_key='bill')
        cash.save_forecast(self.today.strftime('%Y-%m'),500,request_key='plan')
        app=self.app();self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual([(m.label,m.value) for m in app.metric[:3]],
                         [('Total en cuentas','$11,000.00'),('Gastos proyectados','$2,500.00'),('Después de gastos','$8,500.00')])
        app.session_state['expense_control_tabs']='Evaluar proyecto';app.run()
        self.assertFalse(any(i.key=='control_project_available' for i in app.number_input))
        app.number_input(key='control_project_cost').set_value(1000).run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertTrue(any(m.label=='Después del proyecto' and m.value=='$7,500.00' for m in app.metric))

    def test_forecast_dialog_updates_projection_and_keeps_payments_untouched(self):
        self.confirm();before=self.fingerprint();app=self.app()
        app.session_state['expense_control_tabs']='Previsión';app.run()
        app.session_state['control_plan_history']=True;app.run()
        app.button(key='control_forecast').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        next(i for i in app.number_input if i.label=='Adicional por gastar · MXN').set_value(250)
        next(b for b in app.button if b.label=='Guardar previsión').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual([(m.label,m.value) for m in app.metric[:3]],
                         [('Total en cuentas','$1,000.00'),('Gastos proyectados','$250.00'),('Después de gastos','$750.00')])
        current=self.fingerprint()
        for table,rows in before.items():
            if table!='expense_cash_forecasts':self.assertEqual(current[table],rows,table)


if __name__=='__main__':unittest.main()
