import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
from services import production as p, inventory as inv
from services.catalog import saved_values


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'NIMUS_DB_PATH': str(Path(self.temp.name) / 'catalog.db')})
        env.start()
        self.addCleanup(env.stop)
        db.init_db()

    def test_saved_properties_deduplicate_without_merging_different_materials(self):
        order = p.create_order('Lote')
        item = p.create_item(order, 'Origen', 3, collection='Origen')
        for material in ['PLA negro', ' pla   NEGRO ', 'PLA blanco']:
            part = p.create_part(item, 'Base', 1, 'Impresión 3D', material)
            p.job_action(p.create_job(part, 1), 'finish')
        self.assertEqual(saved_values('material'), ['PLA blanco', 'PLA negro'])
        self.assertEqual(saved_values('part'), ['Base'])
        self.assertEqual(saved_values('product'), ['Origen'])
        rows = inv.load_inventory()['skus']
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(row['produced'] for row in rows), [1, 2])

    def test_b2b_client_remains_reusable_after_reversal(self):
        order = p.create_order('Lote', ' Tienda   Norte ')
        item = p.create_item(order, 'Origen', 2, collection='Origen')
        part = p.create_part(item, 'Base', 2, 'Impresión 3D', 'PLA')
        p.job_action(p.create_job(part, 2), 'finish')
        movement = inv.distribute(1, 'Colección', 'B2B', 1, client='tienda norte')
        inv.reverse_movement(movement, 'Corrección')
        self.assertEqual(saved_values('client'), ['Tienda Norte'])
        self.assertEqual(inv.load_inventory()['clients'], [])
