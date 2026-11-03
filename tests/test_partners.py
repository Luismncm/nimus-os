import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import partners as p,treasury as t,reconciliation as r,expenses as e,sales,budgets
from utils.dates import now


class PartnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'partners.db'
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)})
        self.env.start();self.addCleanup(self.env.stop);db.init_db()
        self.bank=next(a['id'] for a in t.accounts() if a['kind']=='Banco')
        self.day=now().date().isoformat()

    def create(self,**overrides):
        args=dict(partner='Ali',amount=5000,moved_on=self.day,account_id=self.bank,reference='DEP-123',request_key='one')
        return p.register_injection(**(args|overrides))

    def test_manual_injection_idempotent_in_account_and_not_sales_or_expenses(self):
        cid=self.create();self.assertEqual(self.create(),cid)
        row=r.state('capital',cid)
        self.assertIsNone(row['origin'])
        self.assertEqual(row['reference'],'DEP-123')
        ledger=t.ledger(self.day,self.day)
        self.assertEqual((ledger['income'],len(ledger['rows'])),(500000,1))
        self.assertEqual(ledger['rows'][0]['reference'],'DEP-123')
        self.assertEqual(ledger['rows'][0]['account_id'],self.bank)
        self.assertEqual(e.list_expenses(),[]);self.assertEqual(sales.list_sales(),[])
        self.assertEqual(len(r.history('capital',cid)),1)
        control=budgets.comparison(self.day[:7])
        self.assertEqual((control['receipts_cents'],control['capital_cents']),(0,500000))

    def test_bank_reference_duplicate_guard_and_invalid_values(self):
        self.create()
        with self.assertRaisesRegex(ValueError,'Ya existe'):self.create(request_key='duplicate')
        for overrides in ({'amount':0},{'amount':-1},{'partner':''},{'account_id':None},{'moved_on':str(now().date()+timedelta(days=1))},{'request_key':''}):
            with self.assertRaises(ValueError):self.create(**overrides)
        self.assertEqual(t.ledger(self.day,self.day)['income'],500000)

    def test_correction_void_audit_and_retry_do_not_replace_current_values(self):
        cid=self.create();before=r.state('capital',cid)
        r.correct_movement('capital',cid,dict(amount=5500,paid_on=self.day,account_id=self.bank,reference='DEP-124'),expected=r.token(before),reason='Estado de cuenta')
        self.assertEqual(self.create(),cid)
        self.assertEqual(t.ledger(self.day,self.day)['income'],550000)
        with self.assertRaises(ValueError):p.void_injection(cid,'Duplicado',expected=r.token(before))
        p.void_injection(cid,'Captura equivocada',expected=r.token(r.state('capital',cid)))
        self.assertEqual(t.ledger(self.day,self.day)['income'],0)
        self.assertEqual(len(r.history('capital',cid)),3)
        self.assertTrue(r.state('capital',cid)['voided_at'])
        with self.assertRaises(ValueError):r.correct_movement('capital',cid,dict(amount=1,paid_on=self.day,account_id=self.bank),expected=r.token(r.state('capital',cid)),reason='No editar anulado')

    def test_ui_capture_focus_and_void(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run().switch_page('views/partners.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.button(key='partner_new').click().run()
        key='partner_new_'+app.session_state['dialog_request_key']
        app.text_input(key=key+'_partner').set_value('Ali')
        app.number_input(key=key+'_amount').set_value(5000)
        app.text_input(key=key+'_reference').set_value('DEP-UI')
        next(x for x in app.button if x.label=='Registrar aportación').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertFalse(app.error,[x.value for x in app.error])
        self.assertEqual(t.ledger(self.day,self.day)['income'],500000)
        self.assertEqual(app.selectbox(key='partner_status').value,'Vigentes')
        self.assertTrue(any(x.label=='Aportaciones a cuenta' and x.value=='$5,000.00' for x in app.metric))
        app.button(key='partner_void').click().run()
        next(x for x in app.text_input if x.label=='Motivo *').set_value('Registro duplicado')
        next(x for x in app.button if x.label=='Confirmar anulación').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertFalse(app.error,[x.value for x in app.error])
        self.assertEqual(t.ledger(self.day,self.day)['income'],0)
        app.selectbox(key='partner_status').set_value('Anulados').run()
        self.assertTrue(app.button(key='partner_edit').disabled)


if __name__=='__main__':unittest.main()
