"""The cloud API's profitability routes: costs and the performance report. Postgres only."""
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


@unittest.skipUnless(POSTGRES and TestClient, 'La API de la nube corre sobre Postgres con FastAPI.')
class CloudProfitabilityTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name) / 'profit.db'), NIMUS_SECRET='s' * 40, NIMUS_INSECURE_COOKIE='1')
        env.start(); self.addCleanup(env.stop)
        import db
        from api.index import app
        from cloud import auth
        from services import production as p, quotations as q, recipes, sales
        from utils.dates import now
        db.init_db()
        auth.create_user('admin@nimus.test', 'clave-de-prueba', role='admin')
        auth.create_user('taller@nimus.test', 'clave-de-prueba', role='taller')
        comp = recipes.create_component('Base', 'PLA', 'Impresión 3D')
        product = recipes.create_product('Lámpara')
        recipes.publish_recipe(product, [dict(component_id=comp, quantity=2)])
        data = q.defaults(); data.update(client='Cliente', project='Venta', lines=[dict(description='Lámpara', quantity=1, price=800, produce=False)])
        self.sale = sales.create_direct(data, now().date(), request_key='v1')
        p.create_order('Pedido')
        self.app = app

    def login(self, who):
        client = TestClient(self.app)
        self.assertEqual(client.post('/api/auth/login', json=dict(email=f'{who}@nimus.test', password='clave-de-prueba')).status_code, 200)
        return client

    def test_costs_and_performance(self):
        workshop = self.login('taller')
        self.assertEqual(workshop.get('/api/costos').status_code, 403)
        self.assertEqual(workshop.get('/api/rendimiento').status_code, 403)
        admin = self.login('admin')
        costs = admin.get('/api/costos').json()
        self.assertEqual([r['name'] for r in costs['recipes']], ['Lámpara'])
        self.assertEqual(costs['recipes'][0]['lines'][0]['quantity'], 2)
        sale = next(s for s in costs['sales'] if s['id'] == self.sale)
        self.assertEqual((sale['net_cents'], sale['state']), (80000, 'Pendiente'))
        self.assertTrue(costs['orders'])
        report = admin.get('/api/rendimiento').json()
        self.assertEqual(report['current']['sold_cents'], 80000)
        self.assertIn('prior', report)
        self.assertEqual(admin.get('/api/rendimiento?periodo=Siempre').status_code, 400)
        for name in report['periods']:
            self.assertEqual(admin.get(f'/api/rendimiento?periodo={name}').status_code, 200, name)


if __name__ == '__main__':
    unittest.main()
