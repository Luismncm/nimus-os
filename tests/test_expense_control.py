"""Simple capture and planning preserve the existing cash/payment distinctions."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests import test_expenses as fixture, test_sheet_migration as sheet_fixture
import db
from services import expense_control as c, expenses as e, treasury, budgets, sheet_migration


class ExpenseControlTest(unittest.TestCase):
    setUp=fixture.ExpenseTest.setUp

    def register(self, key='quick', **kwargs):
        payload=dict(concept='Filamento',amount=125.50,expense_on=self.today,request_key=key)
        payload.update(kwargs)
        return c.register(**payload)

    def fingerprint(self):
        with db.connect() as conn:
            tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}

    def test_minimal_capture_is_pending_and_needs_no_budget_or_bank_guess(self):
        eid=self.register();row=e.get_expense(eid)
        self.assertEqual((row['total_cents'],row['balance_cents'],row['category'],row['account']),(12550,12550,'Sin clasificar','Por definir'))
        self.assertIsNone(row['tax_cents'])
        self.assertEqual(treasury.ledger('2026-01-01','2026-12-31')['rows'],[])
        self.assertEqual(budgets.list_months(),[])
        self.assertEqual(self.register(),eid)

    def test_paid_capture_is_atomic_idempotent_and_keeps_cash_and_bank_separate(self):
        bank=treasury.save_account('Banco de prueba','Banco');cash=treasury.save_account('Caja de prueba','Efectivo')
        first=self.register('bank',paid=True,account_id=bank,method='Transferencia')
        self.register('cash',paid=True,account_id=cash,method='Efectivo')
        self.assertEqual(self.register('bank',paid=True,account_id=bank,method='Transferencia'),first)
        ledger=treasury.ledger('2026-01-01','2026-12-31')
        self.assertEqual(ledger['outflow'],25100)
        self.assertEqual({r['account_id'] for r in ledger['rows']},{bank,cash})
        self.assertEqual(len(ledger['rows']),2)
        with self.assertRaises(ValueError):self.register('bank',paid=True,account_id=cash,method='Efectivo')

    def test_missing_or_archived_payment_account_rolls_back_whole_capture(self):
        with self.assertRaises(ValueError):self.register(paid=True,method='Efectivo')
        aid=treasury.save_account('Cuenta archivada','Banco')
        treasury.save_account('Cuenta archivada','Banco',account_id=aid,expected_revision=0,active=False)
        with self.assertRaises(ValueError):self.register(paid=True,account_id=aid,method='Transferencia')
        with self.assertRaises(ValueError):self.register(amount=0)
        self.assertEqual(e.list_expenses(),[])

    def test_monthly_payments_and_current_debt_do_not_depend_on_document_month(self):
        old=e.create(dict(e.defaults(),expense_on='2026-08-01',concept='Agosto',amount=200),request_key='old')
        e.record_payment(old,50,'2026-09-02','Efectivo / caja','Efectivo',expected_revision=0,request_key='partial')
        new=e.create(dict(e.defaults(),expense_on='2026-09-03',concept='Septiembre',amount=100),request_key='new')
        report=c.report('2026-09')
        self.assertEqual((report['registered_cents'],report['paid_cents'],report['pending_cents']),(10000,5000,25000))
        self.assertEqual({r['id'] for r in report['pending']},{old,new})
        self.assertEqual(c.report('2026-08')['pending_cents'],25000)
        self.assertEqual(c.report('2026-08')['paid_cents'],0)
        e.void_payment(e.get_expense(old)['payments'][0]['id'],'Pago incorrecto')
        self.assertEqual(c.report('2026-09')['paid_cents'],0)
        self.assertEqual(c.report('2026-09')['pending_cents'],30000)
        e.cancel(new,'Duplicado',expected_revision=0)
        self.assertEqual(c.report('2026-09')['registered_cents'],0)

    def test_partner_paid_and_undated_history_are_separate_from_cash_outflow(self):
        f=sheet_fixture.SheetMigrationTest();f.setUp()
        try:
            sheet_migration.import_snapshot(f.source)
            feb=c.report('2026-02');may=c.report('2026-05')
            self.assertEqual((feb['paid_cents'],feb['partner_cents']),(0,11600))
            self.assertEqual((may['paid_cents'],may['undated_payments'],may['pending_cents']),(10000,1,0))
        finally:f.doCleanups()

    def test_project_coverage_requires_real_cash_and_preserves_negative_results(self):
        self.assertTrue(c.project_coverage(project_cost=500)['missing'])
        r=c.project_coverage(available=1000,reserve=100,project_cost=500,pending_cents=20000)
        self.assertEqual((r['before_project_cents'],r['after_project_cents'],r['covered']),(70000,20000,True))
        r=c.project_coverage(available=100,reserve=50,project_cost=500,pending_cents=20000)
        self.assertEqual((r['after_project_cents'],r['shortfall_cents'],r['covered']),(-65000,65000,False))
        for payload in (dict(available=-1,project_cost=1),dict(available=float('nan'),project_cost=1),dict(available=True,project_cost=1),dict(available=1,project_cost=0)):
            with self.assertRaises(ValueError):c.project_coverage(**payload)

    def app(self):
        a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        return a.switch_page('views/budget.py').run()

    def test_default_screen_requires_no_plan_and_project_scenario_writes_nothing(self):
        self.register();before=self.fingerprint();a=self.app()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        self.assertEqual(len(a.get('data_editor')),0)
        self.assertFalse(any(b.label=='Guardar presupuesto' for b in a.button))
        a.session_state['expense_control_tabs']='Evaluar proyecto';a.run()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        a.toggle(key='control_project_manual').set_value(True).run()
        self.assertIsNone(a.number_input(key='control_project_available').value)
        a.number_input(key='control_project_available').set_value(1000).run()
        a.number_input(key='control_project_cost').set_value(500).run()
        self.assertTrue(any(m.label=='Después del proyecto' and m.value=='$374.50' for m in a.metric))
        self.assertEqual(self.fingerprint(),before)

    def test_quick_paid_form_keeps_entered_values_when_payment_options_change(self):
        aid=treasury.save_account('Caja de prueba','Efectivo');a=self.app()
        a.button(key='control_quick_expense').click().run()
        prefix='quick_expense_'+a.session_state['dialog_request_key']
        a.text_input(key=prefix+'_concept').set_value('Compra rápida').run()
        a.number_input(key=prefix+'_amount').set_value(80).run()
        a.button_group(key=prefix+'_state').set_value('Ya pagado').run()
        self.assertEqual(a.text_input(key=prefix+'_concept').value,'Compra rápida')
        self.assertEqual(a.number_input(key=prefix+'_amount').value,80)
        a.selectbox(key=prefix+'_account').set_value(aid).run()
        a.selectbox(key=prefix+'_method').set_value('Efectivo').run()
        a.button(key=prefix+'_save').click().run()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        self.assertEqual(e.list_expenses()[0]['payment_status'],'Pagado')
        self.assertEqual(c.report(self.today.strftime('%Y-%m'))['paid_cents'],8000)

    def test_collapsed_optional_details_are_not_lost_on_save(self):
        a=self.app();a.button(key='control_quick_expense').click().run()
        prefix='quick_expense_'+a.session_state['dialog_request_key']
        a.text_input(key=prefix+'_concept').set_value('Renta').run()
        a.number_input(key=prefix+'_amount').set_value(100).run()
        a.session_state[prefix+'_more']=True;a.run()
        a.text_input(key=prefix+'_supplier').set_value('Proveedor confirmado').run()
        a.selectbox(key=prefix+'_nature').set_value('Fijo').run()
        a.session_state[prefix+'_more']=False;a.run()
        a.button(key=prefix+'_save').click().run()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        row=e.list_expenses()[0]
        self.assertEqual((row['supplier'],row['cost_type']),('Proveedor confirmado','Fijo'))

    def test_pending_payment_shortcut_opens_existing_payment_dialog(self):
        eid=self.register();a=self.app()
        a.session_state['expense_control_tabs']='Por pagar';a.run()
        a.button(key='control_pending_pay').click().run()
        self.assertFalse(a.exception,[x.message for x in a.exception])
        self.assertEqual(a.session_state['active_dialog'][0],'expense_payment_form')
        self.assertEqual(e.get_expense(eid)['balance_cents'],12550)
