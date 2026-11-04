import os
import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import invoices as f,sales as s,quotations as q,expenses as e,sale_corrections as c
from utils.dates import now
from tests.backends import sqlite_only

PDF=b'%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n'


class InvoiceCorrectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.db'
        env=patch.dict(os.environ,{'NIMUS_DB_PATH':str(self.path)});env.start();self.addCleanup(env.stop)
        db.init_db();self.today=now().date()
        self.data=dict(q.defaults(),client='Cliente',project='Origen',iva=True,discount=10,
            lines=[dict(description='Lámpara',quantity=2,price=500,produce=True),dict(description='Error',quantity=1,price=100,produce=False)])

    def sale(self,key='one',**kwargs):return s.create_direct(self.data,self.today,request_key=key,**kwargs)
    def invoice(self,kind,identity,required=True,upload=('factura.pdf',PDF),**kwargs):
        row=f.get(kind,identity)
        return f.save(kind,identity,required,'FAC-100',upload,expected_revision=row['revision'],expected_owner_revision=row['owner_revision'],**kwargs)
    def app(self,page):return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run().switch_page(page).run()

    @sqlite_only

    def test_sale_pdf_roundtrip_and_backup_includes_bytes(self):
        sid=self.sale(invoice_required=True);self.invoice('sale',sid)
        row=f.get('sale',sid)
        self.assertEqual(row['content'],PDF);self.assertEqual(row['reference'],'FAC-100')
        self.assertEqual(f.statuses('sale')[sid],'PDF adjunto')
        self.assertEqual(s.get_sale(sid)['total_cents'],114840)
        self.assertEqual(s.get_sale(sid)['paid_cents'],0)
        backup=db.backup_database()
        with db.connect(backup) as conn:self.assertEqual(conn.execute('SELECT content FROM invoice_documents').fetchone()[0],PDF)

    def test_expense_invoice_sync_preserves_money_and_payments(self):
        eid=e.create(dict(e.defaults(),concept='Filamento',amount=100),request_key='expense')
        before=e.get_expense(eid)
        self.invoice('expense',eid)
        self.assertEqual(e.get_expense(eid)['receipt_type'],'Factura')
        self.assertEqual(e.get_expense(eid)['receipt_ref'],'FAC-100')
        self.assertEqual(e.get_expense(eid)['total_cents'],before['total_cents'])
        edited=e.editable(e.get_expense(eid));edited['receipt_type']='Sin comprobante'
        with self.assertRaises(sqlite3.IntegrityError):e.update(eid,edited,expected_revision=e.get_expense(eid)['revision'])
        self.invoice('expense',eid,False,upload=None,clear_pdf=True)
        self.assertIsNone(f.get('expense',eid)['content'])
        self.assertEqual(e.get_expense(eid)['receipt_type'],'Sin comprobante')

    def test_pdf_validation_stale_and_no_invoice_conflict_roll_back(self):
        sid=self.sale();before=f.get('sale',sid)
        for upload in [('x.html',PDF),('x.pdf',b'<html>'),('x.pdf',b'%PDF-'+b'x'*(f.MAX_BYTES+1))]:
            with self.assertRaises(ValueError):self.invoice('sale',sid,upload=upload)
        self.assertEqual(f.get('sale',sid),before)
        self.invoice('sale',sid)
        with self.assertRaises(ValueError):self.invoice('sale',sid,False,upload=None)
        with self.assertRaises(ValueError):f.save('sale',sid,True,expected_revision=0,expected_owner_revision=0)
        self.assertEqual(f.get('sale',sid)['content'],PDF)

    def test_remove_lines_recalculates_discount_tax_and_keeps_audit(self):
        sid=self.sale();c.remove_lines(sid,[1],'Duplicada',expected_revision=0)
        row=s.get_sale(sid)
        self.assertEqual(row['total_cents'],104400)
        self.assertEqual(len(row['data']['lines']),1)
        self.assertIn('Error',c.history(sid)[0]['previous_payload'])
        with self.assertRaises(ValueError):c.remove_lines(sid,[0],'Eliminar',expected_revision=row['revision'])
        with self.assertRaises(ValueError):c.remove_lines(sid,[0],'Eliminar',expected_revision=0)

    def test_paid_invoiced_quote_and_order_sales_cannot_change_lines(self):
        paid=self.sale('paid');s.record_payment(paid,10,self.today,'Efectivo','Abono',request_key='receipt',expected_revision=0)
        invoice=self.sale('invoice');self.invoice('sale',invoice)
        ordered=self.sale('order');s.create_order(ordered,expected_revision=0)
        qid=q.create_quote();q.save_quote(qid,self.data,expected_revision=0,status='Aceptada')
        quoted=s.from_quote(qid,self.today,request_key='q-sale',expected_revision=1)
        for sid in (paid,invoice,ordered,quoted):
            old=s.get_sale(sid)
            with self.assertRaises(sqlite3.IntegrityError):c.remove_lines(sid,[1],'Error',expected_revision=old['revision'])
            self.assertEqual(s.get_sale(sid)['total_cents'],old['total_cents'])

    def test_trash_restore_excludes_reports_and_keeps_pdf(self):
        sid=self.sale();self.invoice('sale',sid)
        c.remove_sale(sid,'Duplicada',expected_revision=s.get_sale(sid)['revision'])
        self.assertEqual(s.list_sales(),[])
        self.assertEqual(s.report(self.today,self.today)['sold_cents'],0)
        self.assertTrue(s.get_sale(sid)['deleted'])
        self.assertEqual(f.get('sale',sid)['content'],PDF)
        c.restore_sale(sid,expected_revision=s.get_sale(sid)['revision'])
        self.assertEqual(len(s.list_sales()),1)
        self.assertEqual(s.get_sale(sid)['status'],'Activa')
        self.assertEqual(f.get('sale',sid)['content'],PDF)

    def test_whole_deletion_blocks_live_payments_or_linked_production(self):
        sid=self.sale();s.record_payment(sid,10,self.today,'Efectivo','Abono',request_key='p',expected_revision=0)
        with self.assertRaises(ValueError):c.remove_sale(sid,'Error',expected_revision=s.get_sale(sid)['revision'])
        linked=self.sale('linked');s.create_order(linked,expected_revision=0)
        with self.assertRaises(ValueError):c.remove_sale(linked,'Error',expected_revision=s.get_sale(linked)['revision'])
        self.assertEqual(c.trash_rows(),[])

    def test_ui_invoice_flag_remove_lines_trash_restore(self):
        sid=self.sale()
        app=self.app('views/sales.py');app.button(key='sale_open').click().run()
        app.button(key=f'invoice_manage_sale_{sid}').click().run()
        prefix='invoice_'+app.session_state['dialog_request_key']
        app.radio(key=prefix+'_required').set_value('Sí')
        app.text_input(key=prefix+'_reference').set_value('FAC-DEMO')
        next(b for b in app.button if b.label=='Guardar factura').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(f.get('sale',sid)['reference'],'FAC-DEMO')
        app.button(key='sale_remove_lines').click().run()
        app.multiselect(key='sale_remove_indices').set_value([1]).run()
        next(w for w in app.text_input if w.label=='Motivo de la corrección *').set_value('Duplicada')
        next(b for b in app.button if b.label=='Eliminar partidas seleccionadas').click().run()
        self.assertEqual(s.get_sale(sid)['total_cents'],104400)
        app.button(key='sale_delete').click().run()
        next(w for w in app.text_input if w.label=='Motivo *').set_value('Prueba')
        next(b for b in app.button if b.label=='Mover a papelera').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        app.button(key=f'sale_restore_{sid}').click().run()
        self.assertFalse(app.exception,[x.message for x in app.exception])
        self.assertEqual(len(s.list_sales()),1)
