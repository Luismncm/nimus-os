"""The cloud API's writes: deliver an order, split its pieces into jobs, collect a sale.

Runs on Postgres only (scripts/test_postgres.py): users and sessions exist only in the cloud schema.
Each write goes through the same service the local app calls, so these tests check the HTTP contract:
session and role, the X-NIMUS header, the same refusals as the local app, and harmless retries.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.backends import POSTGRES

try:
    from fastapi.testclient import TestClient
except ImportError:  # The local app does not install FastAPI.
    TestClient = None

WRITE = {'X-NIMUS': '1'}


@unittest.skipUnless(POSTGRES and TestClient, 'La API de la nube corre sobre Postgres con FastAPI.')
class CloudApiTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name) / 'api.db'), NIMUS_SECRET='s' * 40, NIMUS_INSECURE_COOKIE='1')
        env.start(); self.addCleanup(env.stop)
        import db
        from api.index import app
        from cloud import auth
        from services import production as p, treasury
        db.init_db()
        auth.create_user('admin@nimus.test', 'clave-de-prueba', role='admin')
        auth.create_user('taller@nimus.test', 'clave-de-prueba', role='taller')
        self.account = treasury.save_account('Caja', 'Efectivo')
        self.oid = p.create_order('Lámparas', 'Cliente', '2026-10-10', 'Alta')
        self.iid = p.create_item(self.oid, 'Lámpara', 2)
        self.pid = p.create_part(self.iid, 'Pantalla', 2, 'Impresión 3D', 'PLA')
        self.app = app

    def client(self, who='admin'):
        client = TestClient(self.app)
        response = client.post('/api/auth/login', json=dict(email=f'{who}@nimus.test', password='clave-de-prueba'))
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def prepare(self):
        from services import operations, production as p
        job = p.create_job(self.pid, 2)
        p.job_action(job, 'finish')
        operations.update_item(self.iid, checked=True, expected_revision=0)
        for stage in operations.STAGES:
            operations.set_stage(self.oid, stage, True, expected_revision=0)

    def sale(self, total=1000):
        from services import quotations as q, sales as s
        from utils.dates import now
        data = q.defaults()
        data.update(client='Cliente', project='Lámparas', lines=[dict(description='Lámpara', quantity=1, price=total, produce=False)])
        sid = s.create_direct(data, now().date(), request_key='venta-api')
        s.link_existing_order(sid, self.oid, expected_revision=s.get_sale(sid)['revision'])
        return sid

    def test_writes_need_a_session_and_the_app_header(self):
        anonymous = TestClient(self.app)
        self.assertEqual(anonymous.post(f'/api/pedidos/{self.oid}/entregar', headers=WRITE).status_code, 401)
        client = self.client()
        self.assertEqual(client.post(f'/api/pedidos/{self.oid}/entregar').status_code, 403)

    def test_delivery_follows_the_local_rule_and_points_to_the_balance(self):
        client = self.client()
        sid = self.sale()
        detail = client.get(f'/api/pedidos/{self.oid}').json()
        self.assertFalse(detail['step']['can_deliver'])
        refused = client.post(f'/api/pedidos/{self.oid}/entregar', headers=WRITE)
        self.assertEqual(refused.status_code, 400)
        self.assertIn('Solo puedes entregar un pedido listo', refused.json()['detail'])
        self.prepare()
        self.assertTrue(client.get(f'/api/pedidos/{self.oid}').json()['step']['can_deliver'])
        self.assertIn(self.oid, [r['id'] for r in client.get('/api/hoy').json()['deliver']['rows']])
        done = client.post(f'/api/pedidos/{self.oid}/entregar', headers=WRITE).json()
        self.assertEqual(done['collect']['id'], sid)
        detail = client.get(f'/api/pedidos/{self.oid}').json()
        self.assertEqual(detail['status'], 'Entregado')
        self.assertTrue(detail['step']['delivered'])

    def test_workshop_delivers_without_seeing_money(self):
        self.sale(); self.prepare()
        client = self.client('taller')
        self.assertIsNone(client.get(f'/api/pedidos/{self.oid}').json()['trail']['sale'])
        self.assertIsNone(client.post(f'/api/pedidos/{self.oid}/entregar', headers=WRITE).json()['collect'])

    def test_payment_is_admin_only_checks_revision_and_survives_a_retry(self):
        sid = self.sale()
        self.assertEqual(self.client('taller').get(f'/api/ventas/{sid}/cobro').status_code, 403)
        client = self.client()
        form = client.get(f'/api/ventas/{sid}/cobro').json()
        self.assertEqual((form['balance_cents'], form['concept']), (100000, 'Liquidación'))
        self.assertIn(self.account, [a['id'] for a in form['accounts']])
        body = dict(amount=400, paid_on='2026-10-01', method='Transferencia', concept=form['concept'], account_id=self.account,
                    request_key='cobro-1', expected_revision=form['revision'], expected_quote_revision=form['quote_revision'])
        first = client.post(f'/api/ventas/{sid}/pagos', json=body, headers=WRITE).json()
        self.assertEqual(first['balance_cents'], 60000)
        # The same click arriving twice (a slow network) records one payment.
        again = client.post(f'/api/ventas/{sid}/pagos', json=body, headers=WRITE).json()
        self.assertEqual((again['payment_id'], again['balance_cents']), (first['payment_id'], 60000))
        # A new payment with the revision the form loaded before the first one is refused.
        stale = client.post(f'/api/ventas/{sid}/pagos', json=dict(body, request_key='cobro-2'), headers=WRITE)
        self.assertEqual(stale.status_code, 400)
        self.assertIn('cambió', stale.json()['detail'])
        over = client.post(f'/api/ventas/{sid}/pagos', headers=WRITE, json=dict(
            body, request_key='cobro-3', amount=700, expected_revision=client.get(f'/api/ventas/{sid}/cobro').json()['revision']))
        self.assertIn(over.status_code, (400, 409))
        self.assertEqual(client.get(f'/api/ventas/{sid}/cobro').json()['balance_cents'], 60000)

    def test_split_suggests_and_creates_all_jobs_or_none(self):
        from services import production as p
        from services.queries import load_snapshot
        base = p.create_part(self.iid, 'Base', 3, 'Impresión 3D', 'PLA')
        client = self.client('taller')
        plan = client.get(f'/api/pedidos/{self.oid}/reparto').json()
        self.assertEqual({r['id']: r['unassigned'] for r in plan['parts']}, {self.pid: 2, base: 3})
        self.assertEqual(sum(r['quantity'] for r in plan['suggestion']), 5)
        machine = plan['machines'][0]['id']
        too_many = [dict(part_id=self.pid, machine_id=machine, quantity=2), dict(part_id=base, machine_id=None, quantity=4)]
        self.assertEqual(client.post(f'/api/pedidos/{self.oid}/reparto', json=dict(allocations=too_many), headers=WRITE).status_code, 400)
        self.assertEqual(load_snapshot()['jobs'], [])
        fits = [dict(part_id=self.pid, machine_id=machine, quantity=2), dict(part_id=base, machine_id=None, quantity=3)]
        self.assertEqual(client.post(f'/api/pedidos/{self.oid}/reparto', json=dict(allocations=fits), headers=WRITE).json()['jobs'], 2)
        self.assertEqual(client.get(f'/api/pedidos/{self.oid}/reparto').json()['parts'], [])


if __name__ == '__main__':
    unittest.main()
