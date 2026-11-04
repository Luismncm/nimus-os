import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from streamlit.testing.v1 import AppTest
import db
from services import treasury as t, sales as s, quotations as q, expenses as e, production as p
from services.workbench import operating_board, visible
from services.queries import load_snapshot
from utils.dates import now
from tests.backends import sqlite_only


class TreasuryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.db'
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)})
        self.env.start();self.addCleanup(self.env.stop)
        db.init_db()
        self.today=now().date()
        self.bank,self.cash,self.card=[r['id'] for r in t.accounts()]
        self.payload=dict(q.defaults(),client='Cliente Origen',project='Lámparas',iva=False,discount=0,
                          lines=[dict(description='Lámpara',quantity=2,price=500,produce=True)])

    def sale(self,key='sale',due=''):
        return s.create_direct(self.payload,self.today,due,request_key=key)

    def pay(self,sid,amount,account,key='receipt'):
        row=s.get_sale(sid)
        return s.record_payment(sid,amount,self.today,'Efectivo' if account==self.cash else 'Transferencia','Abono',
            account_id=account,request_key=key,expected_revision=row['revision'],expected_quote_revision=row['quote_revision'])

    def expense(self,key='expense'):
        return e.create(dict(e.defaults(),concept='Filamento',amount=200,account='Cuenta bancaria NIMUS'),request_key=key)

    def report(self,**kw): return t.ledger(self.today,self.today,**kw)

    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        return app

    def test_bank_cash_and_actual_expense_account(self):
        sid=self.sale()
        self.pay(sid,100,self.bank)
        self.pay(sid,200,self.cash,'cash')
        eid=self.expense()
        e.record_payment(eid,50,self.today,'Efectivo / caja','Efectivo',request_key='expense-payment',expected_revision=0)
        r=self.report()
        self.assertEqual((r['income'],r['outflow'],r['net']),(30000,5000,25000))
        self.assertEqual(self.report(kind='Efectivo')['net'],15000)
        self.assertEqual(self.report(account_id=self.bank)['net'],10000)
        self.assertEqual(s.get_sale(sid)['payments'][1]['account_name'],'Efectivo / caja')

    def test_quote_receipt_conversion_and_void_do_not_duplicate(self):
        qid=q.create_quote();q.save_quote(qid,self.payload,expected_revision=0,status='Aceptada')
        pid=q.record_payment(qid,100,self.today,'Transferencia','Anticipo',account_id=self.bank,request_key='q1',expected_revision=1)
        self.assertEqual(self.report()['rows'][0]['record_kind'],'Cotización')
        sid=s.from_quote(qid,self.today,request_key='conversion',expected_revision=2)
        self.pay(sid,200,self.cash,'q2')
        self.assertEqual(self.report()['income'],30000)
        self.assertEqual(len(self.report()['rows']),2)
        self.assertEqual({r['record_kind'] for r in self.report()['rows']},{'Venta'})
        s.void_payment(sid,pid,'Captura corregida')
        self.assertEqual(self.report()['income'],20000)

    def test_account_retry_mismatch_and_archive_atomicity(self):
        sid=self.sale();pid=self.pay(sid,100,self.bank)
        self.assertEqual(self.pay(sid,100,self.bank),pid)
        # Same values except account must not silently change an existing receipt.
        row=s.get_sale(sid)
        with self.assertRaisesRegex(ValueError,'otra cuenta'):
            s.record_payment(sid,100,self.today,'Transferencia','Abono',account_id=self.cash,request_key='receipt',expected_revision=row['revision'])
        t.save_account('Banco principal','Banco',account_id=self.bank,expected_revision=0,active=False)
        before=s.get_sale(sid)
        with self.assertRaises(ValueError): self.pay(sid,100,self.bank,'inactive')
        self.assertEqual(s.get_sale(sid),before)
        self.assertEqual(self.report()['rows'][0]['account_name'],'Banco principal')
        self.assertNotIn(self.bank,[a['id'] for a in t.accounts(active_only=True)])

    def test_cancellation_requires_review_of_actual_receipts(self):
        sid=self.sale();pid=self.pay(sid,100,self.cash)
        with self.assertRaises(sqlite3.IntegrityError):
            s.cancel(sid,'Pedido cancelado',expected_revision=s.get_sale(sid)['revision'])
        self.assertEqual(self.report()['income'],10000)
        s.void_payment(sid,pid,'Captura anulada')
        self.assertEqual(self.report()['income'],0)

    def test_archived_expense_account_rolls_back_payment(self):
        eid=self.expense()
        t.save_account('Efectivo / caja','Efectivo',account_id=self.cash,expected_revision=0,active=False)
        with self.assertRaises(ValueError):
            e.record_payment(eid,50,self.today,'Efectivo / caja','Efectivo',request_key='bad',expected_revision=0)
        self.assertEqual(e.get_expense(eid)['paid_cents'],0)

    @sqlite_only

    def test_v9_migration_keeps_rows_and_does_not_guess_receipt_account(self):
        sid=self.sale();self.pay(sid,100,None)
        eid=self.expense()
        e.record_payment(eid,50,self.today,'Efectivo / caja','Efectivo',request_key='oldexpense',expected_revision=0)
        with db.connect(write=True) as conn:
            conn.execute('DROP TRIGGER extra_expense_order')
            for table in ('material_availability','machine_maintenance_due','production_alert_state','production_alert_settings','order_extra_costs','job_consumption','print_reprints','production_failures','production_metrics'):
                conn.execute(f'DROP TABLE {table}')
            # Reconstruct the prior schema; these tables/triggers did not exist in v9.
            for table in ('print_plans','sale_events','sales_trash','invoice_documents'):
                conn.execute(f'DROP TABLE {table}')
            for trigger in ('sale_identity_fixed','sale_content_guard','expense_invoice_guard'):
                conn.execute(f'DROP TRIGGER {trigger}')
            conn.execute("CREATE TRIGGER sale_fixed BEFORE UPDATE OF payload,total_cents ON sales BEGIN SELECT RAISE(ABORT,'Venta confirmada'); END")
            conn.execute('DROP TABLE payment_accounts');conn.execute('DROP TABLE treasury_accounts')
            conn.execute('PRAGMA user_version=9')
            tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before={name:[tuple(r) for r in conn.execute(f'SELECT * FROM {name} ORDER BY rowid')] for name in tables}
        db.init_db()
        with db.connect() as conn:
            after={name:[tuple(r) for r in conn.execute(f'SELECT * FROM {name} ORDER BY rowid')] for name in tables}
            self.assertEqual(before,after)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(self.report()['unassigned'],1)
        self.assertEqual(self.report(kind='Efectivo')['outflow'],5000)
        self.assertEqual(self.report(account_id=None)['income'],10000)

    def test_workbench_priority_filters_and_exclusions(self):
        future=self.sale('future',self.today+timedelta(days=5))
        due=self.sale('due',self.today)
        paid=self.sale('paid');self.pay(paid,1000,self.cash)
        cancel=self.sale('cancel');s.cancel(cancel,'Error',expected_revision=0)
        board=operating_board(load_snapshot(),s.list_sales(),e.list_expenses())
        self.assertEqual([r['id'] for r in board['collections']],[due,future])
        self.assertEqual(board['to_collect'],200000)
        self.assertTrue(visible(board['collections'][0],'origen','Vencidos y hoy',date_field='due_on',fields=['client']))
        self.assertFalse(visible(board['collections'][1],'','Vencidos y hoy',date_field='due_on',fields=['client']))

    def test_assign_historical_account_preserves_amount_and_blocks_reassignment(self):
        sid=self.sale();pid=self.pay(sid,100,None)
        original=s.get_sale(sid)
        t.assign_account('sale',pid,self.cash)
        t.assign_account('sale',pid,self.cash)
        self.assertEqual(s.get_sale(sid)['paid_cents'],original['paid_cents'])
        self.assertEqual(s.get_sale(sid)['revision'],original['revision'])
        self.assertEqual(self.report(kind='Efectivo')['income'],10000)
        with self.assertRaises(ValueError):t.assign_account('sale',pid,self.bank)

    def test_ui_cobrar_keeps_context_and_maps_cash(self):
        sid=self.sale();app=self.app()
        app.session_state['today_front']='Cobrar';app.run()
        app.text_input(key='today_search').set_value('Origen').run()
        app.button(key=f'hub_collect_{sid}').click().run()
        prefix='sale_payment_'+app.session_state['dialog_request_key']
        app.selectbox(key=prefix+'_account').set_value(self.cash)
        app.selectbox(key=prefix+'_method').set_value('Efectivo')
        app.number_input(key=prefix+'_amount').set_value(100)
        next(b for b in app.button if b.label=='Guardar pago recibido').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(app.session_state['today_front'],'Cobrar')
        self.assertEqual(app.text_input(key='today_search').value,'Origen')
        self.assertEqual(self.report(kind='Efectivo')['income'],10000)
        app.switch_page('views/treasury.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.switch_page('views/today.py').run()
        self.assertEqual(app.text_input(key='today_search').value,'Origen')

    def test_ui_pagar_and_delivery_fronts(self):
        eid=self.expense();app=self.app()
        app.session_state['today_front']='Pagar';app.run()
        app.button(key=f'hub_pay_{eid}').click().run()
        prefix='expense_pay_'+app.session_state['dialog_request_key']
        app.number_input(key=prefix+'_amount').set_value(50)
        next(b for b in app.button if b.label=='Guardar pago').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(self.report()['outflow'],5000)
        oid=p.create_order('Prueba taller','Cliente')
        iid=p.create_item(oid,'Lámpara',1);pid=p.create_part(iid,'Base',1,'Impresión 3D','PLA')
        p.job_action(p.create_job(pid,1),'finish')
        app.session_state['today_front']='Entregar';app.run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.button(key=f'hub_delivery_advance_{oid}_revision_0').click().run()
        self.assertTrue(load_snapshot()['orders'][0]['stages']['revision']['checked_at'])

    def test_ui_filters_continue_and_reuse_sale(self):
        sid=self.sale();self.pay(sid,100,self.cash)
        app=self.app();app.switch_page('views/sales.py').run()
        app.text_input(key='sales_search').set_value('Origen').run()
        app.button(key='sale_open').click().run()
        app.switch_page('views/today.py').run()
        app.button(key='today_continue').click().run()
        self.assertEqual(app.session_state['open_sale_id'],sid)
        self.assertTrue(any(b.key=='sale_back' for b in app.button))
        # AppTest retains the previously selected route after programmatic switch_page.
        app.switch_page('views/sales.py').run()
        app.button(key='sale_back').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertTrue(any(w.key=='sales_search' for w in app.text_input),[(w.key,w.label) for w in app.button])
        self.assertEqual(app.text_input(key='sales_search').value,'Origen')
        app.button(key='sale_open').click().run();app.button(key='sale_reuse').click().run()
        prefix='sale_new_'+app.session_state['dialog_request_key']
        self.assertEqual(app.text_input(key=prefix+'_project').value,'Lámparas')
        next(b for b in app.button if b.label=='Registrar venta').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        new=s.get_sale(app.session_state['open_sale_id'])
        self.assertNotEqual(new['id'],sid)
        self.assertEqual(new['paid_cents'],0)
        self.assertIsNone(new['order_id']);self.assertIsNone(new['quote_id'])
        self.assertEqual(new['total_cents'],100000)

    def test_ui_manage_accounts(self):
        app=self.app();app.switch_page('views/treasury.py').run()
        app.button(key='treasury_new_account').click().run()
        next(w for w in app.text_input if w.label=='Nombre *').set_value('Caja tienda')
        next(w for w in app.selectbox if w.label=='Tipo de cuenta').set_value('Efectivo')
        next(b for b in app.button if b.label=='Guardar cuenta').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(t.accounts()[-1]['name'],'Caja tienda')
