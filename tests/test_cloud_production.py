"""The cloud API's production routes: operate the queue, schedule, machines, control and development.

Postgres only, like tests/test_cloud_api.py. The services are tested on their own; these check what the
screens rely on: revisions refuse stale writes, retries are harmless, and the rows carry what to show.
"""
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from tests.backends import POSTGRES

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

WRITE = {'X-NIMUS': '1'}


@unittest.skipUnless(POSTGRES and TestClient, 'La API de la nube corre sobre Postgres con FastAPI.')
class CloudProductionTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, NIMUS_DB_PATH=str(Path(temp.name) / 'prod.db'), NIMUS_SECRET='s' * 40, NIMUS_INSECURE_COOKIE='1')
        env.start(); self.addCleanup(env.stop)
        import db
        from api.index import app
        from cloud import auth
        from services import production as p
        db.init_db()
        auth.create_user('admin@nimus.test', 'clave-de-prueba', role='admin')
        auth.create_user('taller@nimus.test', 'clave-de-prueba', role='taller')
        self.oid = p.create_order('Lámparas', 'Cliente', '2026-12-10', 'Alta')
        self.iid = p.create_item(self.oid, 'Lámpara', 4)
        self.pid = p.create_part(self.iid, 'Pantalla', 4, 'Impresión 3D', 'PLA')
        self.job = p.create_job(self.pid, 4, 1)
        self.app = app

    def client(self, who='taller'):
        client = TestClient(self.app)
        self.assertEqual(client.post('/api/auth/login', json=dict(email=f'{who}@nimus.test', password='clave-de-prueba')).status_code, 200)
        return client

    def row(self, client, job=None):
        return next(j for j in client.get('/api/cola').json()['jobs'] if j['id'] == (job or self.job))

    def test_queue_operates_a_print_and_refuses_a_stale_click(self):
        client = self.client()
        data = client.get('/api/cola').json()
        job = self.row(client)
        self.assertEqual((job['status'], job['remaining'], job['destination']['kind']), ('En cola', 4, 'Pedido'))
        self.assertTrue(job['can_start'])
        self.assertIn('Adherencia', data['causes'])
        start = client.post(f'/api/cola/{self.job}/accion', json=dict(action='start', expected_revision=job['revision']), headers=WRITE)
        self.assertEqual(start.status_code, 200, start.text)
        # The same click from a screen loaded before the start is refused, not applied twice.
        stale = client.post(f'/api/cola/{self.job}/accion', json=dict(action='pause', expected_revision=job['revision']), headers=WRITE)
        self.assertEqual(stale.status_code, 400)
        job = self.row(client)
        self.assertEqual(job['status'], 'En producción')
        self.assertEqual(client.post(f'/api/cola/{self.job}/avance', json=dict(quantity_completed=2, expected_revision=job['revision']),
                                     headers=WRITE).status_code, 200)
        job = self.row(client)
        self.assertEqual((job['completed'], job['remaining']), (2, 2))
        machine = next(m for m in client.get('/api/cola').json()['machines'] if m['id'] == 1)
        self.assertEqual((machine['status'], machine['current']['id']), ('Imprimiendo', self.job))
        bad = client.post(f'/api/cola/{self.job}/accion', json=dict(action='explode', expected_revision=job['revision']), headers=WRITE)
        self.assertEqual(bad.status_code, 400)
        client.post(f'/api/cola/{self.job}/accion', json=dict(action='finish', expected_revision=job['revision']), headers=WRITE)
        self.assertNotIn(self.job, [j['id'] for j in client.get('/api/cola').json()['jobs']])
        self.assertIn(self.job, [j['id'] for j in client.get('/api/cola?terminados=true').json()['jobs']])

    def test_failure_pauses_the_print_once_per_form(self):
        client = self.client()
        job = self.row(client)
        client.post(f'/api/cola/{self.job}/accion', json=dict(action='start', expected_revision=job['revision']), headers=WRITE)
        job = self.row(client)
        body = dict(rejected_units=1, cause='Adherencia', request_key='falla-1', expected_revision=job['revision'])
        first = client.post(f'/api/cola/{self.job}/falla', json=body, headers=WRITE).json()
        again = client.post(f'/api/cola/{self.job}/falla', json=body, headers=WRITE).json()
        self.assertEqual(first['failure_id'], again['failure_id'])
        self.assertEqual(self.row(client)['status'], 'Pausado')
        failures = self.client('admin').get('/api/control').json()['failures']
        self.assertEqual([(f['job'], f['cause'], f['rejected']) for f in failures], [(job['code'], 'Adherencia', 1)])

    def test_schedule_books_the_machine_and_batch_reports_what_it_skipped(self):
        from utils.dates import now
        client = self.client()
        form = client.get(f'/api/cola/{self.job}/horario').json()
        self.assertIsNone(form['planned_start'])
        start = (now() + timedelta(hours=1)).replace(second=0, microsecond=0).isoformat(timespec='minutes')
        saved = client.post(f'/api/cola/{self.job}/horario', headers=WRITE, json=dict(
            planned_start=start, duration_minutes=90, estimated_grams=40, expected_revision=form['revision'], expected_job_revision=form['job_revision']))
        self.assertEqual(saved.status_code, 200, saved.text)
        job = self.row(client)
        self.assertEqual((job['slot']['state'], job['slot']['minutes']), ('Reservada', 90))
        # A second form loaded before that save is refused.
        stale = client.post(f'/api/cola/{self.job}/horario', headers=WRITE, json=dict(
            planned_start=None, duration_minutes=30, expected_revision=form['revision'], expected_job_revision=form['job_revision']))
        self.assertEqual(stale.status_code, 400)
        from services import production as p
        other = p.create_job(p.create_part(self.iid, 'Base', 4, 'Impresión 3D', 'PLA'), 4, None)
        result = client.post('/api/cola/programar', json=dict(job_ids=[other]), headers=WRITE).json()
        self.assertEqual(result['scheduled'], 0)
        self.assertIn('máquina', result['skipped'][0]['reason'])

    def test_machines_status_material_and_archive(self):
        client = self.client()
        data = client.get('/api/maquinas').json()
        self.assertIn('Mantenimiento', data['statuses'])
        new = client.post('/api/maquinas', json=dict(code='x9', name='Prueba'), headers=WRITE).json()['id']
        dup = client.post('/api/maquinas', json=dict(code='X9', name='Otra'), headers=WRITE)
        self.assertEqual(dup.status_code, 400)
        self.assertEqual(client.post(f'/api/maquinas/{new}/filamento', json=dict(material='PETG negro'), headers=WRITE).status_code, 200)
        client.put(f'/api/maquinas/{new}', json=dict(code='X9', name='Prueba', status='Mantenimiento'), headers=WRITE)
        row = next(m for m in client.get('/api/maquinas').json()['machines'] if m['id'] == new)
        self.assertEqual((row['code'], row['material'], row['status']), ('X9', 'PETG negro', 'Mantenimiento'))
        # A machine with pending prints cannot be archived.
        self.assertEqual(client.post('/api/maquinas/1/archivo', json=dict(archived=True), headers=WRITE).status_code, 400)
        client.post(f'/api/maquinas/{new}/archivo', json=dict(archived=True), headers=WRITE)
        self.assertIn(new, [m['id'] for m in client.get('/api/maquinas').json()['archived']])

    def test_control_notices_can_be_marked_seen(self):
        client = self.client()
        data = client.get('/api/control?minutos=60').json()
        self.assertEqual(data['minutes'], 60)
        self.assertTrue(data['capacity'])
        notice = next(n for n in data['notices'] if n['state'] == 'Pendiente')
        client.post(f"/api/control/avisos/{notice['identity']}", json={}, headers=WRITE)
        again = next(n for n in client.get('/api/control').json()['notices'] if n['identity'] == notice['identity'])
        self.assertEqual(again['state'], 'Visto')
        self.assertEqual(client.get('/api/control?minutos=0').status_code, 400)

    def test_development_projects_launch_prints_and_hide_money_from_the_workshop(self):
        admin, workshop = self.client('admin'), self.client()
        pid = admin.post('/api/desarrollo', json=dict(name='Lámpara nueva', goal='Probar difusor', budget=500), headers=WRITE).json()['id']
        # The workshop edits the goal without seeing the budget: the budget stays.
        workshop.put(f'/api/desarrollo/{pid}', json=dict(goal='Probar difusor opal'), headers=WRITE)
        body = dict(piece='Difusor', quantity=2, material='PLA', machine_id=2, duration_minutes=60, request_key='proto-1')
        first = workshop.post(f'/api/desarrollo/{pid}/impresion', json=body, headers=WRITE).json()['job_id']
        self.assertEqual(workshop.post(f'/api/desarrollo/{pid}/impresion', json=body, headers=WRITE).json()['job_id'], first)
        project = next(r for r in workshop.get('/api/desarrollo').json()['projects'] if r['id'] == pid)
        self.assertIsNone(project['money'])
        self.assertEqual([(j['part'], j['status']) for j in project['jobs']], [('Difusor', 'En cola')])
        seen = next(r for r in admin.get('/api/desarrollo').json()['projects'] if r['id'] == pid)
        self.assertEqual((seen['goal'], seen['money']['budget_cents']), ('Probar difusor opal', 50000))
        ignored = workshop.post('/api/desarrollo', json=dict(name='Otra', budget=900), headers=WRITE).json()['id']
        self.assertIsNone(next(r for r in admin.get('/api/desarrollo').json()['projects'] if r['id'] == ignored)['money']['budget_cents'])
        self.assertEqual(self.row(workshop, first)['destination']['kind'], 'Prototipo')
        refused = workshop.post(f'/api/desarrollo/{pid}/cerrar', headers=WRITE)
        self.assertEqual(refused.status_code, 400)
        self.assertIn('sin terminar', refused.json()['detail'])


if __name__ == '__main__':
    unittest.main()
