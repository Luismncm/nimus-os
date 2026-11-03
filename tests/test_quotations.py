import copy
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

import db
from services import quotations as q
from services.quotation_document import document
from services.queries import load_snapshot
from utils.dates import now


class QuotationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'NIMUS_DB_PATH': str(Path(self.tmp.name)/'test.db')})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.qid = q.create_quote()
        self.data = q.defaults()
        self.data.update(client='Cliente Norte', project='Lote lámparas', iva=True, discount=10,
            lines=[dict(description='Lámpara',quantity=10,price=100,produce=True),dict(description='Diseño',quantity=1,price=250,produce=False)],
            tiers=[dict(minimum=1,maximum=9,price=100,reference_discount=0,note='Inicial'),dict(minimum=10,maximum=None,price=80,reference_discount=20,note='Volumen')])

    def save(self, status='Aceptada'):
        q.save_quote(self.qid, self.data, expected_revision=0, status=status)
        return q.get_quote(self.qid)

    def test_printable_quotation_layout(self):
        quote = self.save(status='Enviada')
        html = document(quote).decode()
        # Key facts on top, lines, totals with the discount, volume prices and the client's acceptance.
        for text in ('Cotización', quote['code'], 'Válida hasta', 'Partidas', '2 · 11 unidades', 'Cliente Norte', 'Lote lámparas',
                     'Descuento (10%)', 'IVA 16%', 'Total MXN', 'Precios por volumen', 'Nombre y firma de aceptación del cliente', '@page{size:A4'):
            self.assertIn(text, html)
        receipt = document(quote, receipt=True).decode()
        self.assertIn('Pendiente de pago', receipt)
        self.assertNotIn('Nombre y firma de aceptación', receipt)  # A receipt is not signed by the client.
        self.data['discount'] = 0
        q.save_quote(self.qid, self.data, expected_revision=quote['revision'], status='Enviada')
        self.assertNotIn('Descuento (', document(q.get_quote(self.qid)).decode())  # No empty discount line.

    def test_volume_discount_tax_and_cent_rounding(self):
        data = q.apply_volume(self.data, 0)
        self.assertEqual(data['lines'][0]['price'],80)
        self.assertEqual(data['totals'], dict(subtotal=105000,discount=10500,tax=15120,total=109620))
        # Reference discount is informational, not applied a second time.
        data['iva'] = False
        self.assertEqual(q.calculate(data)['totals']['total'],94500)
        self.assertEqual(q.cents('1.005'),101)
        q.save_quote(self.qid,self.data,expected_revision=0,volume_line=0)
        self.assertEqual(q.get_quote(self.qid)['total_cents'],109620)

    def test_invalid_values_overlapping_ranges_and_missing_tier(self):
        for invalid in (-1, float('nan'), float('inf'), True):
            d = copy.deepcopy(self.data)
            d['lines'][0]['price'] = invalid
            with self.assertRaises(ValueError): q.calculate(d)
        d = copy.deepcopy(self.data)
        d['tiers'][0]['maximum'] = 10
        with self.assertRaises(ValueError): q.calculate(d)
        d = copy.deepcopy(self.data)
        d['discount'] = 101
        with self.assertRaises(ValueError): q.calculate(d)
        d = copy.deepcopy(self.data)
        d['lines'][0]['quantity'] = 1.5
        with self.assertRaises(ValueError): q.calculate(d)
        d['lines'][0]['produce'] = False
        self.assertEqual(q.calculate(d)['lines'][0]['quantity'],1.5)
        d['tiers'] = []
        with self.assertRaises(ValueError): q.apply_volume(d,0)

    def test_stale_save_and_duplicate_preserve_original(self):
        saved = self.save()
        with self.assertRaises(ValueError): q.save_quote(self.qid,self.data,expected_revision=0)
        clone = q.get_quote(q.create_quote(self.qid))
        self.assertEqual(clone['status'],'Borrador')
        self.assertNotEqual(clone['code'],saved['code'])
        self.assertEqual(clone['data']['lines'],saved['data']['lines'])

    def test_payments_idempotence_partial_void_and_document(self):
        saved = self.save('Borrador')
        pid = q.record_payment(self.qid,500,now().date().isoformat(),'Transferencia','Anticipo',request_key='once',expected_revision=1)
        self.assertEqual(q.record_payment(self.qid,500,now().date().isoformat(),'Transferencia','Anticipo',request_key='once',expected_revision=1),pid)
        saved = q.get_quote(self.qid)
        self.assertEqual(saved['paid_cents'],50000)
        self.assertEqual(saved['balance_cents'],80500)
        with self.assertRaises(ValueError): q.record_payment(self.qid,1000,now().date().isoformat(),'Efectivo','Liquidación',request_key='too-much',expected_revision=saved['revision'])
        with self.assertRaises(ValueError): q.save_quote(self.qid,self.data,expected_revision=saved['revision'])
        q.set_status(self.qid,'Aceptada',expected_revision=saved['revision'])
        html = document(q.get_quote(self.qid),receipt=True).decode()
        self.assertIn('Pago parcial',html)
        self.assertIn('REC-0001',html)
        q.void_payment(pid,'Duplicado en captura')
        self.assertEqual(q.get_quote(self.qid)['paid_cents'],0)
        self.assertIn('Anulado: Duplicado en captura',document(q.get_quote(self.qid),receipt=True).decode())
        with self.assertRaises(sqlite3.IntegrityError),db.connect(write=True) as c:
            c.execute('DELETE FROM quotation_payments')

    def test_concurrent_payments_cannot_overpay(self):
        self.save()
        def pay(i):
            try:
                q.record_payment(self.qid,900,now().date().isoformat(),'Efectivo','Abono',request_key=f'p{i}',expected_revision=1)
                return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(pay,range(2))),[False,True])
        self.assertEqual(q.get_quote(self.qid)['paid_cents'],90000)

    def test_convert_once_only_manufacturing_lines_no_stock_or_payments(self):
        self.save()
        oid = q.convert_to_order(self.qid,expected_revision=1)
        self.assertEqual(q.convert_to_order(self.qid,expected_revision=1),oid)
        snap = load_snapshot()
        self.assertEqual(len(snap['orders']),1)
        self.assertEqual([(i['name'],i['quantity']) for i in snap['items']],[('Lámpara',10)])
        self.assertEqual(snap['orders'][0]['undefined_items'],1)
        self.assertEqual(snap['jobs'],[])
        self.assertEqual(q.get_quote(self.qid)['paid_cents'],0)
        with db.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM inventory_movements').fetchone()[0],0)
        with self.assertRaises(ValueError): q.set_status(self.qid,'Cancelada',expected_revision=2)

    def test_unaccepted_and_service_only_quotes_cannot_convert(self):
        self.save('Enviada')
        with self.assertRaises(ValueError): q.convert_to_order(self.qid,expected_revision=1)
        self.data['lines'][0]['produce'] = False
        q.save_quote(self.qid,self.data,expected_revision=1,status='Aceptada')
        with self.assertRaises(ValueError): q.convert_to_order(self.qid,expected_revision=2)
        self.assertEqual(load_snapshot()['orders'],[])

    def test_document_escapes_values_and_receipt_does_not_infer_payment(self):
        self.data['client'] = '<script>alert(1)</script>'
        self.save()
        html = document(q.get_quote(self.qid),receipt=True).decode()
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('Pendiente de pago',html)
        self.assertIn('width=device-width',html)

    def test_ui_all_quote_tabs_and_payment_flow(self):
        self.save()
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=25)
        app.run().switch_page('views/quotations.py').run()
        app.button(key=f'quote_open_{self.qid}').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertFalse(app.button(key='quote_convert').disabled)
        app.button(key='quote_payment').click().run()
        prefix = 'payment_'+app.session_state['dialog_request_key']
        app.number_input(key=prefix+'_amount').set_value(500)
        app.text_input(key=prefix+'_concept').set_value('Anticipo')
        next(b for b in app.button if b.label=='Guardar pago recibido').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(q.get_quote(self.qid)['paid_cents'],50000)
        app.button(key='quote_duplicate').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.session_state['open_quote_id'],2)
        self.assertEqual(q.get_quote(2)['paid_cents'],0)
