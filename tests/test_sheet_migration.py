import copy
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import db
from services import expenses, treasury, sheet_migration as migration
from streamlit.testing.v1 import AppTest


class SheetMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(Path(self.tmp.name)/'test.db')})
        self.env.start(); self.addCleanup(self.env.stop)
        db.init_db()
        self.source=dict(spreadsheet_id='control',url='https://docs.google.com/spreadsheets/d/control/edit',sheets={
            'MOVIMIENTOS':dict(values=[['Fecha'],
                [46146,'Egreso','Operación general','Compra','Proveedor','Cuenta bancaria NIMUS','','',100,'Sin comprobante'],
                ['','Egreso','','Servicio','','Efectivo / caja','','',50],
                [46250,'Egreso','Equipo / mantenimiento','DEVOLUCION CLIMA','','Cuenta bancaria NIMUS','','',20],
                [46170,'Egreso','Otros egresos','TEST — REGISTRO ANULADO','','Cuenta bancaria NIMUS','','',0]]),
            'SOCIOS':dict(values=[[]]*14+[
                [46059,'Ali','Compra pagada por socio','Equipo','Proveedor',100,16,116,'Aportación de socio','',0,'','No impacta'],
                [46140,'Ali','Inyección a cuenta NIMUS','Capital','','','',1000,'Aportación de socio','',0,'Cuenta bancaria NIMUS','Entrada'],
                [46245,'Ali','Reembolso al socio','CLIMA','','','',20,'Reembolso',20,0,'','No impacta']]),
            'VENTAS':dict(values=[[],[],[],[46140,'Business','Cliente','','','Cuenta bancaria NIMUS',100,16,116]])})

    def test_expenses_paid_socios_no_income_and_no_double_reimbursement(self):
        counts=migration.import_snapshot(self.source)
        self.assertEqual((counts['expenses'],counts['partner_expenses'],counts['excluded_income']),(3,1,1))
        rows=expenses.list_expenses()
        self.assertEqual(sum(r['total_cents'] for r in rows),28600)
        self.assertTrue(all(r['payment_status']=='Pagado' and r['balance_cents']==0 for r in rows))
        partner=next(r for r in rows if r['category']=='Compras pagadas por socio')
        self.assertTrue(partner['money_locked'])
        report=treasury.ledger('2026-01-01','2026-12-31')
        self.assertEqual((report['income'],report['outflow']),(0,12000))
        self.assertEqual(expenses.report('2026-01-01','2026-12-31')['paid_cents'],23600)
        self.assertEqual(len([r for r in rows if not r['expense_on']]),1)
        with db.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sale_payments').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT SUM(amount_cents) FROM expense_payments WHERE voided_at IS NULL').fetchone()[0],17000)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM capital_movements WHERE sign=1').fetchone()[0],0)
        reembolso=next(r for r in migration.partner_rows() if r['movement']=='Reembolso al socio')
        self.assertIsNotNone(reembolso['linked_expense_id'])
        self.assertEqual(reembolso['sign'],0)
        with self.assertRaises(sqlite3.IntegrityError):
            expenses.record_payment(partner['id'],1,'2026-05-01','Cuenta bancaria NIMUS','Transferencia',request_key='double',expected_revision=partner['revision'])
        with self.assertRaises(sqlite3.IntegrityError):
            expenses.update(partner['id'],dict(expenses.editable(partner),amount=200),expected_revision=partner['revision'])

    def test_retry_and_changed_source_are_atomic(self):
        migration.import_snapshot(self.source)
        self.assertEqual(migration.import_snapshot(self.source)['expenses'],0)
        changed=copy.deepcopy(self.source)
        changed['sheets']['MOVIMIENTOS']['values'][1][8]=101
        with self.assertRaises(ValueError): migration.import_snapshot(changed)
        self.assertEqual(len(expenses.list_expenses()),4)

    def test_invalid_row_rolls_back_whole_import(self):
        self.source['sheets']['MOVIMIENTOS']['values'][2][5]=''
        with self.assertRaises(ValueError): migration.import_snapshot(self.source)
        self.assertEqual(expenses.list_expenses(),[])
        with db.connect() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) FROM sheet_import_rows').fetchone()[0],0)

    def test_ui_historical_and_partner_detail(self):
        migration.import_snapshot(self.source)
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/treasury.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.switch_page('views/expenses.py').run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        undated=next(r for r in expenses.list_expenses() if not r['expense_on'])
        app.session_state['open_expense_id']=undated['id']; app.run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.button(key='expense_edit').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
