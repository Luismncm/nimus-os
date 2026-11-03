import copy
import json
import sqlite3
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import db
from services import expenses as e,treasury as t,sheet_migration as m,reconciliation as r
from tests import test_sheet_migration,test_treasury


class ReconciliationTest(unittest.TestCase):
    setUp=test_sheet_migration.SheetMigrationTest.setUp

    def imported(self):
        m.import_snapshot(self.source)
        return e.list_expenses()

    def test_authorized_injection_preclaimed_idempotent_unknown_date(self):
        rows=self.imported()
        self.source['sheets']['SOCIOS']['values'].append(['','','Inyección a cuenta NIMUS','Capital','Ali','','',60,'Aportación de socio','',0,'Cuenta bancaria NIMUS','Entrada'])
        stats=m.import_partner_injections(self.source)
        self.assertEqual((stats['imported'],stats['amount_cents'],stats['undated']),(2,106000,1))
        self.assertEqual(m.import_partner_injections(self.source)['imported'],0)
        self.assertEqual(e.list_expenses(),rows)
        alltime=t.ledger('0001-01-01','9999-12-31',include_undated=True)
        self.assertEqual((alltime['income'],alltime['outflow']),(106000,17000))
        self.assertEqual(t.ledger('2026-01-01','2026-12-31')['income'],100000)
        self.assertTrue(all(x['account_kind']=='Banco' for x in alltime['rows'] if x['source']=='capital'))
        self.assertEqual(len(t.ledger('0001-01-01','9999-12-31',include_undated=True,category='Aportación de socio')['rows']),2)

    def test_import_invalid_and_changed_row_roll_back(self):
        self.imported()
        bad=copy.deepcopy(self.source)
        bad['sheets']['SOCIOS']['values'][15][7]=999
        with self.assertRaises(ValueError): m.import_partner_injections(bad)
        self.assertEqual(len([x for x in m.partner_rows() if x['sign']==1]),0)

    def test_expense_total_and_full_payment_atomic_audited(self):
        row=next(x for x in self.imported() if x['concept']=='Compra')
        before=r.state('expense_document',row['id']); payload=dict(e.editable(row),amount=90)
        with self.assertRaises(ValueError): r.correct_expense(row['id'],payload,expected=r.token(before),reason='Comprobante')
        self.assertEqual(r.state('expense_document',row['id']),before)
        r.correct_expense(row['id'],payload,expected=r.token(before),reason='Comprobante',sync_payment=True)
        row=e.get_expense(row['id'])
        self.assertEqual((row['total_cents'],row['paid_cents'],row['balance_cents']),(9000,9000,0))
        self.assertEqual(len(r.history('expense_document',row['id'])),1)
        with self.assertRaises(ValueError): r.correct_expense(row['id'],payload,expected=r.token(before),reason='Obsoleto',sync_payment=True)
        self.assertEqual(t.ledger('0001-01-01','9999-12-31',include_undated=True)['outflow'],16000)

    def test_expense_rollback_when_invoice_guard_fails_after_payment_change(self):
        row=next(x for x in self.imported() if x['concept']=='Compra')
        before=r.state('expense_document',row['id'])
        # A failing final document write must also roll back its earlier payment correction.
        with db.connect(write=True) as conn:
            conn.execute("CREATE TRIGGER test_reject BEFORE UPDATE ON expenses BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            r.correct_expense(row['id'],dict(e.editable(row),amount=90),expected=r.token(before),reason='Prueba',sync_payment=True)
        self.assertEqual(r.state('expense_document',row['id']),before)
        self.assertEqual(r.history('expense_document',row['id']),[])

    def test_partner_expense_amount_tax_and_date_no_treasury_outflow(self):
        row=next(x for x in self.imported() if x['category']=='Compras pagadas por socio')
        flow=t.ledger('0001-01-01','9999-12-31',include_undated=True)
        before=r.state('expense_document',row['id'])
        r.correct_expense(row['id'],dict(e.editable(row),amount=200,tax=32),expected=r.token(before),reason='Factura socio',partner_day='2026-02-01')
        corrected=e.get_expense(row['id'])
        self.assertEqual((corrected['total_cents'],corrected['paid_cents']),(23200,23200))
        purchase=next(x for x in m.partner_rows() if x['linked_expense_id']==row['id'])
        self.assertEqual((purchase['amount_cents'],purchase['moved_on']),(23200,'2026-02-01'))
        self.assertEqual(t.ledger('0001-01-01','9999-12-31',include_undated=True),flow)

    def test_payment_edit_date_amount_account_balances_and_stale(self):
        row=next(x for x in self.imported() if not x['expense_on'])
        p=e.get_expense(row['id'])['payments'][0]
        before=r.state('expense',p['id'])
        data=dict(amount=40,paid_on='2026-05-01',account_id=1,method='Transferencia',reference='Estado de cuenta')
        r.correct_movement('expense',p['id'],data,expected=r.token(before),reason='Banco')
        self.assertEqual(e.get_expense(row['id'])['balance_cents'],1000)
        self.assertEqual(r.state('expense',p['id'])['account'],'Cuenta bancaria NIMUS')
        self.assertEqual(t.ledger('0001-01-01','9999-12-31',kind='Efectivo',include_undated=True)['outflow'],0)
        with self.assertRaises(ValueError): r.correct_movement('expense',p['id'],data,expected=r.token(before),reason='Obsoleto')
        current=r.state('expense',p['id'])
        with self.assertRaises(ValueError): r.correct_movement('expense',p['id'],dict(data,amount=60),expected=r.token(current),reason='Excede')
        self.assertEqual(r.state('expense',p['id']),current)
        self.assertNotIn('Fecha del pago',next(x for x in t.review_expenses() if x['id']==row['id'])['issues'])

    def test_injection_edit_preserves_source_and_import_does_not_overwrite(self):
        self.imported();m.import_partner_injections(self.source)
        capital=next(x for x in m.partner_rows() if x['sign']==1)
        before=r.state('capital',capital['id'])
        data=dict(amount=1100,paid_on='2026-05-01',account_id=1,partner='Ali',concept='Aportación verificada')
        r.correct_movement('capital',capital['id'],data,expected=r.token(before),reason='Estado de cuenta')
        m.import_partner_injections(self.source)
        self.assertEqual(r.state('capital',capital['id'])['amount_cents'],110000)
        audit=r.history('capital',capital['id'])[0]
        self.assertEqual(json.loads(audit['before_json'])['amount_cents'],100000)
        with db.connect(write=True) as conn:
            with self.assertRaises(sqlite3.IntegrityError): conn.execute('DELETE FROM reconciliation_events')
        self.assertEqual(t.ledger('2026-05-01','2026-05-01')['income'],110000)

    def test_invalid_date_reason_and_archived_account_leave_no_changes(self):
        self.imported();m.import_partner_injections(self.source)
        c=next(x for x in m.partner_rows() if x['sign']==1); before=r.state('capital',c['id'])
        data=dict(amount=1000,paid_on='2026-05-01',account_id=1)
        for changes,reason in [({'paid_on':'2099-01-01'},'Futuro'),({},''),({'amount':0},'Cero'),({'account_id':None},'Cuenta')]:
            with self.assertRaises(ValueError): r.correct_movement('capital',c['id'],dict(data,**changes),expected=r.token(before),reason=reason)
        t.save_account('Cuenta bancaria NIMUS','Banco',account_id=1,expected_revision=0,active=False)
        with self.assertRaises(ValueError): r.correct_movement('capital',c['id'],data,expected=r.token(before),reason='Archivada')
        self.assertEqual(r.state('capital',c['id']),before)

    def test_partner_classification_and_reimbursement_stay_in_sync(self):
        rows=self.imported()
        purchase=next(x for x in rows if x['category']=='Compras pagadas por socio')
        e.update(purchase['id'],dict(e.editable(purchase),concept='Equipo corregido'),expected_revision=purchase['revision'])
        self.assertEqual(next(x for x in m.partner_rows() if x['linked_expense_id']==purchase['id'])['concept'],'Equipo corregido')
        reimbursement=next(x for x in rows if x['concept']=='DEVOLUCION CLIMA')
        pid=e.get_expense(reimbursement['id'])['payments'][0]['id']
        before=r.state('expense',pid)
        r.correct_movement('expense',pid,dict(amount=15,paid_on='2026-09-01',account_id=1),expected=r.token(before),reason='Reembolso real')
        partner=next(x for x in m.partner_rows() if x['movement']=='Reembolso al socio')
        self.assertEqual((partner['amount_cents'],partner['reimbursed_cents'],partner['moved_on']),(1500,1500,'2026-09-01'))
        self.assertEqual(len(r.history('expense',pid)),1)

    def test_ui_edit_injection_and_expense(self):
        rows=self.imported();m.import_partner_injections(self.source)
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/treasury.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        capital=next(x for x in m.partner_rows() if x['sign']==1)
        app.selectbox(key='treasury_source').set_value(f"capital:{capital['id']}").run()
        app.button(key='treasury_reconcile').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        next(x for x in app.number_input if x.label=='Importe · MXN').set_value(1100.)
        next(x for x in app.text_input if x.label=='Motivo de la corrección *').set_value('UI comprobada')
        next(x for x in app.button if x.label=='Guardar conciliación').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(r.state('capital',capital['id'])['amount_cents'],110000)
        app.switch_page('views/expenses.py').run()
        row=next(x for x in rows if x['concept']=='Compra')
        app.session_state['open_expense_id']=row['id'];app.run()
        app.button(key='expense_reconcile').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        next(x for x in app.number_input if x.label=='Importe · MXN').set_value(90.)
        next(x for x in app.checkbox if x.label=='Ajustar también el importe del pago completo').check()
        next(x for x in app.text_input if x.label=='Motivo de la corrección *').set_value('Factura UI')
        next(x for x in app.button if x.label=='Guardar conciliación del gasto').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(e.get_expense(row['id'])['paid_cents'],9000)


class ReceiptCorrectionTest(unittest.TestCase):
    setUp=test_treasury.TreasuryTest.setUp
    sale=test_treasury.TreasuryTest.sale
    pay=test_treasury.TreasuryTest.pay

    def test_sale_and_converted_quote_receipts(self):
        from services import sales as s,quotations as q
        sid=self.sale();pid=self.pay(sid,100,self.bank)
        before=r.state('sale',pid)
        r.correct_movement('sale',pid,dict(amount=150,paid_on=str(self.today),account_id=self.cash),expected=r.token(before),reason='Banco a caja')
        self.assertEqual(s.get_sale(sid)['balance_cents'],85000)
        qid=q.create_quote();q.save_quote(qid,self.payload,expected_revision=0,status='Aceptada')
        qpid=q.record_payment(qid,100,self.today,'Transferencia','Anticipo',account_id=self.bank,request_key='q1',expected_revision=1)
        linked=s.from_quote(qid,self.today,request_key='conversion',expected_revision=2)
        before=r.state('quote',qpid)
        r.correct_movement('quote',qpid,dict(amount=200,paid_on=str(self.today),account_id=self.bank),expected=r.token(before),reason='Anticipo correcto')
        self.assertEqual(s.get_sale(linked)['balance_cents'],80000)
        report=t.ledger(self.today,self.today)
        self.assertEqual((report['income'],len(report['rows'])),(35000,2))


if __name__=='__main__': unittest.main()
