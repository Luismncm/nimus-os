"""The cloud API's finance routes: summary, expenses and payments, treasury and partner capital. Postgres only."""
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
class CloudFinanceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name) / 'money.db'), NIMUS_SECRET='s' * 40, NIMUS_INSECURE_COOKIE='1')
        env.start(); self.addCleanup(env.stop)
        import db
        from api.index import app
        from cloud import auth
        from utils.dates import now
        db.init_db()
        auth.create_user('admin@nimus.test', 'clave-de-prueba', role='admin')
        auth.create_user('taller@nimus.test', 'clave-de-prueba', role='taller')
        self.app = app
        self.client = self.login('admin')
        self.today = now().date().isoformat()

    def login(self, who):
        client = TestClient(self.app)
        self.assertEqual(client.post('/api/auth/login', json=dict(email=f'{who}@nimus.test', password='clave-de-prueba')).status_code, 200)
        return client

    def post(self, path, body=None, method='post'):
        return getattr(self.client, method)(path, json=body or {}, headers=WRITE)

    def test_finance_is_admin_only(self):
        workshop = self.login('taller')
        for path in ('/api/resumen', f'/api/gastos?desde={self.today}&hasta={self.today}', '/api/socios'):
            self.assertEqual(workshop.get(path).status_code, 403, path)

    def test_expense_payment_void_and_cancel(self):
        data = self.client.get(f'/api/gastos?desde={self.today}&hasta={self.today}').json()
        category = next(iter(data['options']['categories']))
        payload = dict(expense_on=self.today, concept='Filamento', category=category, supplier='Proveedor', account=data['options']['accounts'][0],
                       tax_mode='Total con IVA 16%', amount=1160)
        body = dict(payload=payload, request_key='g1')
        eid = self.post('/api/gastos', body).json()['id']
        self.assertEqual(self.post('/api/gastos', body).json()['id'], eid)
        row = self.client.get(f'/api/gastos/{eid}').json()
        self.assertEqual((row['total_cents'], row['subtotal_cents'], row['tax_cents']), (116000, 100000, 16000))
        pay = dict(amount=600, paid_on=self.today, account=row['account'], method='Transferencia', request_key='p1', expected_revision=row['revision'])
        self.post(f'/api/gastos/{eid}/pagos', pay)
        row = self.client.get(f'/api/gastos/{eid}').json()
        self.assertEqual((row['balance_cents'], row['payment_status']), (56000, 'Pago parcial'))
        stale = self.post(f'/api/gastos/{eid}/pagos', dict(pay, request_key='p2'))
        self.assertEqual(stale.status_code, 400)
        self.post(f"/api/gastos/pagos/{row['payments'][0]['id']}/anular", dict(reason='Error'))
        row = self.client.get(f'/api/gastos/{eid}').json()
        self.assertEqual(row['balance_cents'], 116000)
        self.post(f'/api/gastos/{eid}/cancelar', dict(reason='Duplicado', expected_revision=row['revision']))
        self.assertEqual(self.client.get(f'/api/gastos/{eid}').json()['status'], 'Cancelado')
        paid = self.post('/api/gastos', dict(payload=dict(payload, concept='Cable'), request_key='g2', paid=True, account=row['account'])).json()['id']
        self.assertEqual(self.client.get(f'/api/gastos/{paid}').json()['payment_status'], 'Pagado')

    def test_treasury_accounts_and_partner_capital(self):
        acc = self.post('/api/tesoreria/cuentas', dict(name='Banco prueba', kind='Banco')).json()['id']
        body = dict(partner='Socio Uno', amount=5000, moved_on=self.today, account_id=acc, request_key='s1')
        cid = self.post('/api/socios', body).json()['id']
        self.assertEqual(self.post('/api/socios', body).json()['id'], cid)
        data = self.client.get('/api/socios').json()
        self.assertEqual(data['injected_cents'], 500000)
        ledger = self.client.get(f'/api/tesoreria?desde={self.today}&hasta={self.today}').json()
        self.assertEqual((ledger['income_cents'], ledger['net_cents']), (500000, 500000))
        self.assertIn('Banco prueba', [a['name'] for a in ledger['accounts']])
        row = next(r for r in data['rows'] if r['id'] == cid)
        self.assertEqual(self.post(f'/api/socios/{cid}/anular', dict(reason='Error', expected='otro')).status_code, 400)
        self.post(f'/api/socios/{cid}/anular', dict(reason='Error de captura', expected=row['token']))
        self.assertEqual(self.client.get('/api/socios').json()['injected_cents'], 0)
        summary = self.client.get('/api/resumen').json()
        self.assertIn('verdict', summary['health'])
        self.assertTrue(summary['trend'])


if __name__ == '__main__':
    unittest.main()
