"""The cloud API's commercial routes: quotations, direct sales, collections and documents. Postgres only."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.backends import POSTGRES

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

WRITE = {'X-NIMUS': '1'}


@unittest.skipUnless(POSTGRES and TestClient, 'La API de la nube corre sobre Postgres con FastAPI.')
class CloudCommercialTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name) / 'sales.db'), NIMUS_SECRET='s' * 40, NIMUS_INSECURE_COOKIE='1')
        env.start(); self.addCleanup(env.stop)
        import db
        from api.index import app
        from cloud import auth
        from services import treasury
        db.init_db()
        auth.create_user('admin@nimus.test', 'clave-de-prueba', role='admin')
        auth.create_user('taller@nimus.test', 'clave-de-prueba', role='taller')
        self.account = treasury.save_account('Banco', 'Banco')
        self.app = app
        self.client = self.login('admin')
        from utils.dates import now
        self.today = now().date().isoformat()

    def login(self, who):
        client = TestClient(self.app)
        self.assertEqual(client.post('/api/auth/login', json=dict(email=f'{who}@nimus.test', password='clave-de-prueba')).status_code, 200)
        return client

    def post(self, path, body=None, method='post'):
        return getattr(self.client, method)(path, json=body or {}, headers=WRITE)

    def payload(self, **extra):
        return dict(dict(client='Cliente', project='Lámparas', issued_on=self.today, valid_until=self.today, iva=True, discount=10,
                         lines=[dict(description='Lámpara', quantity=2, price=500, produce=True), dict(description='Envío', quantity=1, price=100)]), **extra)

    def test_workshop_cannot_see_sales_or_quotes(self):
        workshop = self.login('taller')
        self.assertEqual(workshop.get(f'/api/ventas?desde={self.today}&hasta={self.today}').status_code, 403)
        self.assertEqual(workshop.get('/api/cotizaciones').status_code, 403)

    def test_totals_come_from_the_service(self):
        totals = self.post('/api/comercial/calcular', dict(payload=self.payload())).json()['totals']
        # 1100 − 10% = 990, + 16% IVA = 1148.40
        self.assertEqual(totals, dict(subtotal=110000, discount=11000, tax=15840, total=114840))
        bad = self.post('/api/comercial/calcular', dict(payload=self.payload(lines=[dict(description='', quantity=1, price=1)])))
        self.assertEqual(bad.status_code, 400)

    def test_quote_to_sale_to_payment_to_order(self):
        qid = self.post('/api/cotizaciones').json()['id']
        quote = self.client.get(f'/api/cotizaciones/{qid}').json()
        self.assertEqual(self.post(f'/api/cotizaciones/{qid}', dict(payload=self.payload(), expected_revision=quote['revision'], status='Aceptada'), 'put').status_code, 200)
        stale = self.post(f'/api/cotizaciones/{qid}', dict(payload=self.payload(), expected_revision=quote['revision']), 'put')
        self.assertEqual(stale.status_code, 400)
        quote = self.client.get(f'/api/cotizaciones/{qid}').json()
        self.assertEqual((quote['status'], quote['total_cents']), ('Aceptada', 114840))
        doc = self.client.get(f'/api/cotizaciones/{qid}/documento')
        self.assertIn('text/html', doc.headers['content-type'])
        self.assertIn(quote['code'], doc.text)
        body = dict(sold_on=self.today, channel='B2B', request_key='venta-1', expected_revision=quote['revision'])
        sid = self.post(f'/api/cotizaciones/{qid}/venta', body).json()['sale_id']
        self.assertEqual(self.post(f'/api/cotizaciones/{qid}/venta', body).json()['sale_id'], sid)
        sale = self.client.get(f'/api/ventas/{sid}').json()
        pay = dict(amount=500, paid_on=self.today, method='Transferencia', concept='Anticipo', account_id=self.account, request_key='p1',
                   expected_revision=sale['revision'], expected_quote_revision=sale['quote_revision'])
        self.assertEqual(self.post(f'/api/ventas/{sid}/pagos', pay).json()['balance_cents'], 64840)
        sale = self.client.get(f'/api/ventas/{sid}').json()
        self.assertEqual([(p['amount_cents'], p['account'], p['voided']) for p in sale['payments']], [(50000, 'Banco', False)])
        self.post(f"/api/ventas/{sid}/pagos/{sale['payments'][0]['id']}/anular", dict(reason='Duplicado'))
        self.assertEqual(self.client.get(f'/api/ventas/{sid}').json()['balance_cents'], 114840)
        sale = self.client.get(f'/api/ventas/{sid}').json()
        order = self.post(f'/api/ventas/{sid}/pedido', dict(expected_revision=sale['revision'], expected_quote_revision=sale['quote_revision'])).json()['order_id']
        self.assertEqual(self.client.get(f'/api/pedidos/{order}').json()['trail']['sale']['id'], sid)
        report = self.client.get(f'/api/ventas?desde={self.today}&hasta={self.today}').json()
        self.assertEqual((report['count'], report['sold_cents']), (1, 114840))
        self.assertIn(sale['code'], self.client.get(f'/api/ventas/{sid}/documento').text)

    def test_direct_sale_due_date_and_cancel(self):
        body = dict(payload=self.payload(), sold_on=self.today, channel='Venta al público', request_key='d1')
        sid = self.post('/api/ventas', body).json()['id']
        self.assertEqual(self.post('/api/ventas', body).json()['id'], sid)
        sale = self.client.get(f'/api/ventas/{sid}').json()
        self.post(f'/api/ventas/{sid}/vencimiento', dict(due_on='2026-12-31', expected_revision=sale['revision']))
        sale = self.client.get(f'/api/ventas/{sid}').json()
        self.assertEqual(sale['due_on'], '2026-12-31')
        self.assertEqual(self.post(f'/api/ventas/{sid}/cancelar', dict(reason='', expected_revision=sale['revision'])).status_code, 400)
        self.post(f'/api/ventas/{sid}/cancelar', dict(reason='Cliente desistió', expected_revision=sale['revision']))
        self.assertEqual(self.client.get(f'/api/ventas/{sid}').json()['status'], 'Cancelada')


if __name__ == '__main__':
    unittest.main()
