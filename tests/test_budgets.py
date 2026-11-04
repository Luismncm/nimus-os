import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

import db
from services import budgets as b, expenses as e, treasury, sheet_migration
from datetime import date
from tests import test_sheet_migration as fixtures
from tests.backends import sqlite_only


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.db'
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)})
        self.env.start(); self.addCleanup(self.env.stop)
        db.init_db()
        self.header=dict(receipts_cents=5800000,net_sales_cents=5000000,margin_bps=4000,notes='Base editable')
        self.lines=[dict(b.line_defaults('Instalaciones / servicios'),fixed_cents=1160000,variable_cents=116000,tax_bps=1600),
            dict(b.line_defaults('Producción / materiales'),variable_cents=2000000),
            dict(b.line_defaults('Equipo / activos'),variable_cents=500000)]

    def save(self,month='2026-10',header=None,lines=None,revision=None,key='one'):
        return b.save_month(month,header or self.header,self.lines if lines is None else lines,expected_revision=revision,request_key=key)

    def test_plan_is_independent_idempotent_and_keeps_revisions(self):
        self.save(); self.save()
        self.assertEqual(b.get_month('2026-10')['revision'],0)
        self.assertEqual(e.list_expenses(),[])
        self.assertEqual(treasury.ledger('2026-01-01','2026-12-31')['rows'],[])
        with self.assertRaises(ValueError): self.save(header=dict(self.header,notes='Changed'))
        with self.assertRaises(ValueError): self.save(key='stale')
        self.save(revision=0,key='update',header=dict(self.header,receipts_cents=6000000))
        self.assertEqual(b.get_month('2026-10')['revision'],1)
        history=b.history('2026-10')
        self.assertEqual(len(history),2)
        self.assertEqual(json.loads(history[1]['snapshot'])['receipts_cents'],5800000)

    def test_profitability_tax_variable_scale_direct_costs_and_investments(self):
        self.save()
        plan=b.get_month('2026-10'); scenario=b.profitability(plan)
        self.assertEqual(scenario['profit_cents'],900000)
        self.assertEqual(scenario['break_even_cents'],2631579)
        self.assertEqual(b.profitability(plan,sales_factor=.5)['profit_cents'],-50000)
        self.assertEqual(b.forecast('2026-10',count=1)[0]['net_cents'],2024000)

    def test_missing_profit_assumptions_and_nonpositive_contribution(self):
        plan=dict(self.header,lines=self.lines)
        plan['lines'][0]['tax_bps']=None
        self.assertIn('IVA de Instalaciones / servicios',b.profitability(plan)['missing'])
        plan['lines'][0]['tax_bps']=0
        plan['margin_bps']=100
        self.assertIsNone(b.profitability(plan)['break_even_cents'])
        with self.assertRaises(ValueError): b.profitability(plan,sales_factor=float('nan'))

    def test_missing_months_and_receipts_are_not_assumed_zero(self):
        self.save()
        self.save(month='2026-12',key='dec')
        forecast=b.forecast('2026-10',count=3)
        self.assertEqual(forecast[0]['cumulative_cents'],2024000)
        self.assertIsNone(forecast[1]['total_cents'])
        self.assertIsNone(forecast[2]['cumulative_cents'])
        self.save(month='2026-11',key='nov',header=dict(self.header,receipts_cents=None))
        self.assertIsNone(b.forecast('2026-11',count=1)[0]['net_cents'])

    def test_cut_only_affects_adjustable_operation_not_essential_or_direct(self):
        lines=self.lines+[dict(b.line_defaults('Marketing / contenido'),fixed_cents=100000,tax_bps=0)]
        plan=dict(self.header,lines=lines)
        self.assertEqual(b.profitability(plan)['profit_cents'],800000)
        self.assertEqual(b.profitability(plan,adjustable_cut=.5)['profit_cents'],850000)
        with self.assertRaises(ValueError): b.profitability(plan,adjustable_cut=1.1)

    def test_invalid_amounts_categories_and_dates_rollback(self):
        for line in [dict(self.lines[0],fixed_cents=-1),dict(self.lines[0],tax_bps=1500),dict(self.lines[0],fixed_cents=True)]:
            with self.assertRaises(ValueError): self.save(lines=[line])
        with self.assertRaises(ValueError): self.save(lines=[self.lines[0],self.lines[0]])
        with self.assertRaises(ValueError): self.save(month='2026-13')
        self.assertEqual(b.list_months(),[])
        self.assertEqual(b.shift('2026-12',1),'2027-01')

    def test_actual_payments_use_payment_date_partner_separate_and_unbudgeted_visible(self):
        category='Software / SaaS'
        eid=e.create(dict(e.defaults(),expense_on='2026-08-01',concept='Suscripción',category=category,amount=200),request_key='expense',
            payment=dict(amount=200,paid_on='2026-09-02',account='Cuenta bancaria NIMUS',method='Transferencia'))
        self.save(month='2026-09',lines=[dict(b.line_defaults(category),variable_cents=10000)],key='sep')
        row=next(r for r in b.comparison('2026-09')['rows'] if r['category']==category)
        self.assertEqual((row['paid_cents'],row['registered_cents'],row['over_cents']),(20000,0,10000))
        self.assertEqual(next(r for r in b.comparison('2026-08')['rows'] if r['category']==category)['paid_cents'],0)
        e.void_payment(e.get_expense(eid)['payments'][0]['id'],'Error')
        self.assertEqual(b.comparison('2026-09')['paid_cents'],0)

    def test_partner_spend_not_paid_and_undated_not_assigned_to_month(self):
        fixture=fixtures.SheetMigrationTest(); fixture.setUp()
        try:
            sheet_migration.import_snapshot(fixture.source)
            result=b.comparison('2026-05')
            self.assertEqual(result['paid_cents'],10000)
            self.assertEqual(result['undated_count'],1)
            self.assertEqual(sum(r['partner_cents'] for r in result['rows']),0)
            self.assertEqual(sum(r['registered_cents'] for r in result['rows']),10000)
            february=b.comparison('2026-02')
            self.assertEqual(sum(r['partner_cents'] for r in february['rows']),11600)
            self.assertEqual(february['paid_cents'],0)
        finally: fixture.doCleanups()

    def test_suggestions_do_not_repeat_unique_templates_or_create_expenses(self):
        data=dict(e.defaults(),concept='Renta',category='Instalaciones / servicios',amount=12000,cost_type='Fijo')
        e.save_template('Renta',data,'Mensual',request_key='rent')
        e.save_template('Máquina',dict(data,cost_type='Desarrollo / único'),'Único',request_key='unique')
        lines=b.suggestion('2026-10','recurrentes')
        self.assertEqual(sum(r['fixed_cents'] for r in lines),1200000)
        self.assertEqual(b.list_months(),[])
        self.assertEqual(e.list_expenses(),[])

    @sqlite_only

    def test_migrate_v14_preserves_financial_records_and_is_idempotent(self):
        e.create(dict(e.defaults(),concept='Original',amount=123.45),request_key='old')
        with db.connect(write=True) as c:
            before=[tuple(r) for r in c.execute('SELECT * FROM expenses')]
            for table in ('budget_events','budget_lines','budget_months'): c.execute(f'DROP TABLE {table}')
            c.execute('PRAGMA user_version=14')
        db.init_db(); db.init_db()
        with db.connect() as c:
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM expenses')])
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
        self.assertTrue(list((self.path.parent/'backups').glob('*pre-presupuesto-v15*')))

    def test_ui_save_edit_reload_and_profitability(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/budget.py').run()
        app.toggle(key='budget_advanced_open').set_value(True).run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        draft=app.session_state['budget_draft']; month=draft['month']; key=f"budget_{month}_{draft['token']}"
        app.number_input(key=key+'_receipts').set_value(58000)
        app.number_input(key=key+'_net').set_value(50000)
        app.number_input(key=key+'_margin').set_value(40)
        index=next(i for i,r in enumerate(draft['lines']) if r['category']=='Instalaciones / servicios')
        app.session_state[key+'_lines']={'edited_rows':{index:{'Fijo':11600.0,'Variable':1160.0,'IVA':'IVA 16%'}},'added_rows':[],'deleted_rows':[]}
        next(x for x in app.button if x.label=='Guardar presupuesto').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(b.get_month(month)['receipts_cents'],5800000)
        self.assertEqual(b.profitability(b.get_month(month))['profit_cents'],900000)
        self.assertTrue(any(x.label=='Resultado operativo estimado' and x.value=='$9,000.00' for x in app.metric))
        app.slider(key='budget_sales_factor').set_value(50).run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertTrue(any(x.label=='Resultado operativo estimado' and x.value=='$-500.00' for x in app.metric))
        following=b.shift(month,1)
        app.date_input(key='budget_month').set_value(date.fromisoformat(following+'-01')).run()
        app.button(key='budget_copy').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(b.get_month(following)['revision'],None)
        next(x for x in app.button if x.label=='Guardar presupuesto').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(b.get_month(following)['lines'],b.get_month(month)['lines'])
        self.assertEqual(e.list_expenses(),[])

    def test_ui_live_drafts_survive_switching_month_without_saving(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/budget.py').run()
        app.toggle(key='budget_advanced_open').set_value(True).run()
        old=app.session_state['budget_draft']; month=old['month']; key=f"budget_{month}_{old['token']}"
        app.number_input(key=key+'_receipts').set_value(42000).run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(app.session_state['budget_draft']['header']['receipts_cents'],4200000)
        following=b.shift(month,1)
        app.date_input(key='budget_month').set_value(date.fromisoformat(following+'-01')).run()
        next_draft=app.session_state['budget_draft']; next_key=f"budget_{following}_{next_draft['token']}"
        app.number_input(key=next_key+'_receipts').set_value(50000).run()
        app.date_input(key='budget_month').set_value(date.fromisoformat(month+'-01')).run()
        self.assertEqual(app.number_input(key=key+'_receipts').value,42000)
        self.assertEqual(b.list_months(),[])


if __name__=='__main__': unittest.main()
