import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import db
from services import production as s
from services.queries import load_snapshot
from services.workflow import due_label, even_split, next_step


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"NIMUS_DB_PATH": str(Path(self.temp.name) / "workflow.db")})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.order = s.create_order("Expo Deco", priority="Alta")

    def step(self):
        return next_step(load_snapshot()["orders"][0])["action"]

    def test_next_step_follows_complete_workflow(self):
        self.assertEqual(self.step(), "item")
        item = s.create_item(self.order, "Lámpara", 10)
        self.assertEqual(self.step(), "parts")
        part = s.create_parts(item, ["Base"], 1, "Impresión 3D")[0]
        self.assertEqual(self.step(), "split")
        jobs = s.create_jobs(part, [{"machine_id": 1, "quantity": 4}, {"machine_id": 2, "quantity": 4}, {"machine_id": 3, "quantity": 2}])
        self.assertEqual(self.step(), "queue")
        self.assertEqual([j["priority"] for j in load_snapshot()["jobs"]], ["Alta"] * 3)
        for job in jobs:
            s.job_action(job, "finish")
        self.assertEqual(self.step(), "deliver")
        s.deliver_order(self.order)
        self.assertEqual(self.step(), "history")
        with self.assertRaises(s.ValidationError):
            s.create_parts(item, ["Extra"], 1, "Ensamble")

    def test_batch_assignment_rolls_back_every_insert(self):
        item = s.create_item(self.order, "Lámpara", 10)
        part = s.create_part(item, "Base", 10, "Impresión 3D")
        for invalid in (6, -1, 0, 1.5, True):
            with self.assertRaises(s.ValidationError):
                s.create_jobs(part, [{"quantity": 5, "machine_id": 1}, {"quantity": invalid, "machine_id": 2}])
            self.assertEqual(load_snapshot()["jobs"], [])
        with self.assertRaises(s.ValidationError):
            s.create_jobs(part, [{"quantity": 5}, {"quantity": 5, "machine_id": 999}])
        self.assertEqual(load_snapshot()["jobs"], [])
        with self.assertRaises(s.ValidationError):
            s.create_jobs(part, [])
        s.create_job(part, 7)
        with self.assertRaises(s.ValidationError):
            s.create_jobs(part, [{"quantity": 2}, {"quantity": 2}])
        self.assertEqual(len(load_snapshot()["jobs"]), 1)

    def test_batch_parts_quantity_and_duplicates(self):
        item = s.create_item(self.order, "Lámpara", 10)
        s.create_parts(item, ["Base", "Pantalla", "Tapa", "Placa"], 1, "Impresión 3D", "PLA")
        result = load_snapshot()
        self.assertEqual(result["orders"][0]["required_total"], 40)
        self.assertEqual([p["material"] for p in result["parts"]], ["PLA"] * 4)
        for names in ([], ["Extra", "extra"], ["Valid", " "]):
            with self.assertRaises(s.ValidationError):
                s.create_parts(item, names, 1, "Ensamble")
        self.assertEqual(len(load_snapshot()["parts"]), 4)

    def test_progress_revision_and_machine_release(self):
        item = s.create_item(self.order, "Lámpara", 10)
        part = s.create_part(item, "Base", 10, "Impresión 3D")
        job = s.create_job(part, 10, 1)
        s.job_action(job, "start")
        revision = load_snapshot()["jobs"][0]["updated_at"]
        s.record_progress(job, 3, expected_revision=revision)
        self.assertEqual(load_snapshot()["orders"][0]["progress"], 30)
        with self.assertRaises(s.ValidationError):
            s.record_progress(job, 10, expected_revision=revision)
        revision = load_snapshot()["jobs"][0]["updated_at"]
        with self.assertRaises(s.ValidationError):
            s.record_progress(job, 11, expected_revision=revision)
        s.record_progress(job, 10, expected_revision=revision)
        result = load_snapshot()
        self.assertEqual(result["orders"][0]["status"], "Listo")
        self.assertEqual(result["machines"][0]["status"], "Disponible")

    def test_due_and_even_split(self):
        today = date(2026, 10, 5)
        self.assertEqual(due_label("2026-10-04", today), ("1 d de atraso", "red"))
        self.assertEqual(due_label("2026-10-05", today)[0], "Entrega hoy")
        self.assertEqual(due_label("bad", today)[0], "Revisar fecha")
        self.assertEqual(due_label(None, today)[0], "Sin fecha")
        self.assertEqual(even_split(10, [1, 2, 3]), {1: 4, 2: 3, 3: 3})
        self.assertEqual(even_split(2, [1, 2, 3, 4]), {1: 1, 2: 1, 3: 0, 4: 0})
        self.assertEqual(even_split(10, []), {})
