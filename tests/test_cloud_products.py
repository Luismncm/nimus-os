"""The cloud API's product and stock routes: inventory ledger, supplies, catalog, recipe orders and Origen.

Postgres only, like tests/test_cloud_api.py.
"""
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
class CloudProductsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name) / 'stock.db'), NIMUS_SECRET='s' * 40, NIMUS_INSECURE_COOKIE='1')
        env.start(); self.addCleanup(env.stop)
        import db
        from api.index import app
        from cloud import auth
        db.init_db()
        auth.create_user('taller@nimus.test', 'clave-de-prueba', role='taller')
        self.client = TestClient(app)
        self.assertEqual(self.client.post('/api/auth/login', json=dict(email='taller@nimus.test', password='clave-de-prueba')).status_code, 200)

    def post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers=WRITE)

    def piece(self, component):
        return next(p for p in self.client.get('/api/inventario').json()['pieces'] if p['component_id'] == component)

    def test_catalog_recipe_order_reserves_stock_and_makes_the_rest(self):
        from services import recipes
        comp = self.post('/api/catalogo/componentes', dict(name='Pantalla', material='PLA', variant='Test')).json()['id']
        # The same piece twice is the same catalog piece, not a duplicate.
        self.assertEqual(self.post('/api/catalogo/componentes', dict(name='Pantalla', material='PLA', variant='Test')).json()['id'], comp)
        product = self.post('/api/catalogo/productos', dict(name='Lámpara prueba')).json()['id']
        recipes.publish_recipe(product, [dict(component_id=comp, quantity=2)])
        # Three pieces found on the shelf: entering them twice with the same form key counts once.
        entry = dict(component_id=comp, quantity=3, destination='Stock', reason='Encontradas', request_key='entrada-1')
        self.assertEqual(self.post('/api/inventario/entrada', entry).json(), self.post('/api/inventario/entrada', entry).json())
        self.assertEqual(self.piece(comp)['stock_free'], 3)
        catalog = self.client.get('/api/catalogo').json()
        row = next(p for p in catalog['products'] if p['id'] == product)
        self.assertEqual([(l['component_id'], l['quantity']) for l in row['lines']], [(comp, 2)])
        self.assertEqual(next(c for c in catalog['components'] if c['id'] == comp)['used_in'], ['Lámpara prueba'])
        plan = self.client.get(f"/api/catalogo/recetas/{row['recipe_id']}/plan?cantidad=2").json()
        self.assertEqual([(l['needed'], l['reserved'], l['to_make']) for l in plan['lines']], [(4, 3, 1)])
        body = dict(quantity=2, client='Cliente', expected_fingerprint=plan['fingerprint'], request_key='pedido-1')
        order = self.post(f"/api/catalogo/recetas/{row['recipe_id']}/pedido", body).json()['order_id']
        self.assertEqual(self.post(f"/api/catalogo/recetas/{row['recipe_id']}/pedido", body).json()['order_id'], order)
        piece = self.piece(comp)
        self.assertEqual((piece['reserved'], piece['free']), (3, 0))
        detail = self.client.get(f'/api/pedidos/{order}').json()
        self.assertEqual(sum(p['unassigned'] for i in detail['items'] for p in i['parts']), 1)
        # Stock changed since the plan was drawn: the next order asks to recalculate.
        stale = self.post(f"/api/catalogo/recetas/{row['recipe_id']}/pedido", dict(body, request_key='pedido-2'))
        self.assertEqual(stale.status_code, 400)
        self.assertIn('Recalcular', stale.json()['detail'])

    def test_moves_and_reversals_keep_the_ledger(self):
        comp = self.post('/api/catalogo/componentes', dict(name='Base', material='PLA')).json()['id']
        self.post('/api/inventario/entrada', dict(component_id=comp, quantity=5, destination='Colección', reason='Inicial', request_key='e1'))
        sku = self.piece(comp)['id']
        too_many = self.post('/api/inventario/mover', dict(sku_id=sku, source='Colección', destination='Stock', quantity=9, request_key='m0'))
        self.assertEqual(too_many.status_code, 400)
        moved = self.post('/api/inventario/mover', dict(sku_id=sku, source='Colección', destination='B2B', quantity=2, client='Tienda', request_key='m1')).json()
        piece = self.piece(comp)
        self.assertEqual((piece['collection_free'], piece['b2b']), (3, 2))
        data = self.client.get('/api/inventario').json()
        self.assertEqual(data['clients'], [dict(client='Tienda', part='Base', product=data['clients'][0]['product'], quantity=2)])
        row = next(m for m in data['movements'] if m['id'] == moved['movement_id'])
        self.assertTrue(row['reversible'])
        self.assertEqual(self.post(f"/api/inventario/movimientos/{row['id']}/revertir", dict(reason='')).status_code, 400)
        self.post(f"/api/inventario/movimientos/{row['id']}/revertir", dict(reason='Error de captura'))
        self.assertEqual(self.piece(comp)['b2b'], 0)
        row = next(m for m in self.client.get('/api/inventario').json()['movements'] if m['id'] == moved['movement_id'])
        self.assertEqual((row['state'], row['reversible']), ('Revertido', False))

    def test_supplies_in_use_and_count(self):
        from services import consumables
        item = consumables.save_item('PLA negro', category='Filamento', unit='g')
        for kind, amount, key in (('Entrada', 1000, 'c1'), ('Consumo', 150, 'c2'), ('Consumo', 150, 'c2')):
            self.assertEqual(self.post(f'/api/consumibles/{item}/movimiento', dict(kind=kind, amount=amount, request_key=key)).status_code, 200)
        supply = next(s for s in self.client.get('/api/inventario').json()['supplies'] if s['id'] == item)
        self.assertEqual(supply['balance'], 850)
        self.assertIsNone(supply['value_cents'])  # The workshop role sees quantities, not money.
        self.post(f'/api/consumibles/{item}/movimiento', dict(kind='Conteo', amount=800, request_key='c3'))
        self.assertEqual(next(s for s in self.client.get('/api/inventario').json()['supplies'] if s['id'] == item)['balance'], 800)
        self.assertEqual(self.post(f'/api/consumibles/{item}/movimiento', dict(kind='Robo', amount=1, request_key='c4')).status_code, 400)

    def test_origin_lists_lamps_and_orders(self):
        data = self.client.get('/api/origen').json()
        self.assertIsInstance(data['lamps'], list)
        self.assertIsInstance(data['orders'], list)


if __name__ == '__main__':
    unittest.main()
