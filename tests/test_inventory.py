import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import db
from services import inventory as inv
from services import production as p
from services.queries import csv_bytes, load_snapshot


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'inventory.db'
        self.env = patch.dict(os.environ, {'NIMUS_DB_PATH': str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.order = p.create_order('Producción Origen')
        self.item = p.create_item(self.order, 'Lámpara Origen', 10, collection='Origen')
        self.part = p.create_part(self.item, 'Base', 10, 'Impresión 3D', 'PLA negro')
        self.job = p.create_job(self.part, 10, 1)

    def complete(self):
        p.job_action(self.job, 'finish')
        return inv.load_inventory()['skus'][0]['id']

    def edit(self, completed):
        job = next(j for j in load_snapshot()['jobs'] if j['id'] == self.job)
        p.update_job(self.job, quantity=job['quantity'], quantity_completed=completed,
                     status='Pausado', machine_id=job['machine_id'], priority=job['priority'], expected_revision=job['updated_at'])

    def assert_balances(self, collection, stock, b2b, produced=10):
        data = inv.load_inventory()
        self.assertEqual(len(data['skus']), 1)
        row = data['skus'][0]
        self.assertEqual((row['unassigned'], row['stock'], row['b2b'], row['produced']), (collection, stock, b2b, produced))
        self.assertEqual(row['produced'], row['unassigned'] + row['stock'] + row['b2b'])

    def test_partial_receipts_finish_and_no_duplicates(self):
        p.job_action(self.job, 'start')
        job = load_snapshot()['jobs'][0]
        p.record_progress(self.job, 3, expected_revision=job['updated_at'])
        self.assert_balances(3, 0, 0, 3)
        p.job_action(self.job, 'pause')
        p.job_action(self.job, 'start')
        self.assertEqual(len(inv.load_inventory()['movements']), 1)
        p.job_action(self.job, 'finish')
        self.assert_balances(10, 0, 0)
        self.assertEqual(sorted(m['quantity'] for m in inv.load_inventory()['movements']), [3, 7])
        with self.assertRaises(ValueError):
            p.job_action(self.job, 'finish')
        self.assertEqual(len(inv.load_inventory()['movements']), 2)

    def test_stock_b2b_and_stock_to_client(self):
        sku = self.complete()
        inv.distribute(sku, 'Colección', 'Stock', 4)
        inv.distribute(sku, 'Colección', 'B2B', 3, client='Tienda Norte', notes='Pedido B2B-1')
        inv.distribute(sku, 'Stock', 'B2B', 2, client=' tienda norte ')
        self.assert_balances(3, 2, 5)
        self.assertEqual(len(inv.load_inventory()['clients']), 1)
        self.assertEqual(inv.load_inventory()['clients'][0]['quantity'], 5)
        inv.distribute(sku, 'Stock', 'Colección', 2)
        self.assert_balances(5, 0, 5)

    def test_transfer_validation_and_double_submit(self):
        sku = self.complete()
        for invalid in (-1, 0, 1.5, True, 11):
            with self.assertRaises(ValueError):
                inv.distribute(sku, 'Colección', 'Stock', invalid)
        with self.assertRaises(ValueError):
            inv.distribute(sku, 'Colección', 'B2B', 1, client=' ')
        with self.assertRaises(ValueError):
            inv.distribute(sku, 'Colección', 'Colección', 1)
        with self.assertRaises(ValueError):
            inv.distribute(999, 'Colección', 'Stock', 1)
        first = inv.distribute(sku, 'Colección', 'Stock', 4, request_key='save-once')
        self.assertEqual(inv.distribute(sku, 'Colección', 'Stock', 4, request_key='save-once'), first)
        with self.assertRaises(ValueError):
            inv.distribute(sku, 'Colección', 'Stock', 5, request_key='save-once')
        self.assert_balances(6, 4, 0)

    def test_concurrent_distribution_cannot_overdraw(self):
        sku = self.complete()
        def transfer():
            try:
                inv.distribute(sku, 'Colección', 'Stock', 6)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: transfer(), range(2))), [False, True])
        self.assert_balances(4, 6, 0)

    def test_correction_requires_return_and_rolls_back_production(self):
        sku = self.complete()
        stock_move = inv.distribute(sku, 'Colección', 'Stock', 4)
        client_move = inv.distribute(sku, 'Colección', 'B2B', 3, client='Cliente')
        before = load_snapshot()
        with self.assertRaisesRegex(ValueError, 'Devuélvelas'):
            self.edit(2)
        self.assertEqual(load_snapshot(), before)
        self.assert_balances(3, 4, 3)
        inv.reverse_movement(stock_move, 'Corregir producción')
        inv.reverse_movement(client_move, 'Corregir producción')
        self.edit(2)
        self.assert_balances(2, 0, 0, 2)
        self.assertEqual(load_snapshot()['orders'][0]['progress'], 20)
        self.assertEqual(inv.load_inventory()['clients'], [])
        p.job_action(self.job, 'finish')
        self.assert_balances(10, 0, 0)

    def test_reverse_keeps_history_and_checks_destination(self):
        sku = self.complete()
        stock_move = inv.distribute(sku, 'Colección', 'Stock', 8)
        client_move = inv.distribute(sku, 'Stock', 'B2B', 5, client='Cliente')
        with self.assertRaisesRegex(ValueError, 'posteriores'):
            inv.reverse_movement(stock_move, 'Volver a colección')
        with self.assertRaises(ValueError):
            inv.reverse_movement(client_move, '')
        reversal = inv.reverse_movement(client_move, 'Cambio de asignación')
        self.assertEqual(inv.reverse_movement(client_move, 'Reintento'), reversal)
        inv.reverse_movement(stock_move, 'Volver a colección')
        self.assert_balances(10, 0, 0)
        self.assertEqual(len(inv.load_inventory()['movements']), 5)
        with self.assertRaises(ValueError):
            inv.reverse_movement(1, 'No revertir ingresos directamente')

    def test_same_model_combines_orders_but_material_and_process_separate(self):
        self.complete()
        other_order = p.create_order('Otro lote')
        other_item = p.create_item(other_order, ' lámpara ORIGEN ', 3, collection='Origen')
        for material, process in (('PLA negro', 'Impresión 3D'), ('PLA blanco', 'Impresión 3D'), ('PLA negro', 'Resina')):
            part = p.create_part(other_item, 'base', 3, process, material)
            p.job_action(p.create_job(part, 3), 'finish')
        rows = inv.load_inventory()['skus']
        self.assertEqual(len(rows), 3)
        self.assertEqual(sorted(row['produced'] for row in rows), [3, 3, 13])

    def test_normal_orders_and_non_printed_parts_do_not_enter(self):
        item = p.create_item(self.order, 'Normal Origen en nombre', 1)
        part = p.create_part(item, 'Base', 1, 'Impresión 3D')
        p.job_action(p.create_job(part, 1), 'finish')
        part = p.create_part(self.item, 'Empaque', 10, 'Empaque')
        p.job_action(p.create_job(part, 10), 'finish')
        self.assertEqual(inv.load_inventory()['skus'], [])

    def test_identity_changes_do_not_relabel_existing_inventory(self):
        p.update_item(self.item, 'Lámpara Origen', 10, collection='')
        p.update_item(self.item, 'Lámpara Origen', 10, collection='Origen')
        self.complete()
        for name, collection in (('Otro modelo', 'Origen'), ('Lámpara Origen', '')):
            with self.assertRaises(ValueError):
                p.update_item(self.item, name, 10, collection=collection)
        for name, process, material in (('Otra', 'Impresión 3D', 'PLA negro'), ('Base', 'Resina', 'PLA negro'), ('Base', 'Impresión 3D', 'PLA blanco')):
            with self.assertRaises(ValueError):
                p.update_part(self.part, name, 10, process, material)
        p.update_item(self.item, 'Lámpara Origen', 10, 'Nota actualizada')
        p.update_part(self.part, 'Base', 12, 'Impresión 3D', 'PLA negro', 'Solo cantidad')
        self.edit(0)
        with self.assertRaises(ValueError):
            p.update_item(self.item, 'Otro', 10)
        self.assert_balances(0, 0, 0, 0)

    def test_existing_normal_production_cannot_be_silently_imported(self):
        item = p.create_item(self.order, 'Normal', 1)
        part = p.create_part(item, 'Base', 1, 'Impresión 3D')
        p.job_action(p.create_job(part, 1), 'finish')
        with self.assertRaises(ValueError):
            p.update_item(item, 'Normal', 1, collection='Origen')
        self.assertEqual(inv.load_inventory()['skus'], [])

    def test_distribution_after_order_delivery_does_not_change_history(self):
        sku = self.complete()
        p.deliver_order(self.order)
        before = load_snapshot()
        inv.distribute(sku, 'Colección', 'B2B', 4, client='Cliente final')
        self.assertEqual(load_snapshot(), before)
        self.assert_balances(6, 0, 4)

    def test_sql_guards_and_csv_traceability(self):
        sku = self.complete()
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(write=True) as conn:
                conn.execute("UPDATE inventory_movements SET quantity=99 WHERE id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(write=True) as conn:
                conn.execute("DELETE FROM inventory_movements")
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connect(write=True) as conn:
                conn.execute("""INSERT INTO inventory_movements(sku_id,kind,source,destination,quantity,created_at)
                    VALUES(?,'Traslado','Colección','Stock',11,'now')""", (sku,))
        data = inv.load_inventory()
        self.assertEqual(data['movements'][0]['job_code'], 'JOB-0001')
        self.assertEqual(data['movements'][0]['order_code'], 'ORD-0001')
        text = csv_bytes(data['movements'], inv.MOVEMENT_FIELDS).decode('utf-8-sig')
        self.assertIn('Lámpara Origen', text)
        self.assertIn('job_code', text)


class InventoryMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'schema2.db'
        with db.connect(self.path, write=True) as conn:
            db._create_schema(conn)
            conn.execute("INSERT INTO orders VALUES(1,'ORD-0001','Cliente','Anterior','a','b',NULL,'Alta','En producción','Notas',0)")
            conn.execute("INSERT INTO items VALUES(1,1,'Lámpara anterior',10,'Conservar','a')")
            conn.execute("INSERT INTO parts VALUES(1,1,'Base',10,'Impresión 3D','PLA','Nota pieza','a')")
            conn.execute("INSERT INTO machines VALUES(1,'P1','Impresora P1','Disponible','','a')")
            conn.execute("INSERT INTO production_jobs VALUES(1,'JOB-0001',1,1,10,2,'Pausado','Alta','a',NULL,NULL,'Trabajo','a','b')")
            db._create_guards(conn)
            conn.execute('PRAGMA user_version=2')
        self.before = self.original_rows()

    def original_rows(self):
        with db.connect(self.path) as conn:
            return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table}')]
                    for table in ('orders', 'items', 'parts', 'production_jobs', 'machines')}

    def test_v2_migration_preserves_rows_and_does_not_invent_stock(self):
        db.init_db(self.path)
        after = self.original_rows()
        for table in after:
            if self.before[table]:
                after[table] = [row[:len(self.before[table][0])] for row in after[table]]
        self.assertEqual(after, self.before)
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
            self.assertEqual(conn.execute('SELECT collection FROM items').fetchone()[0], '')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM inventory_movements').fetchone()[0], 0)
        backups = list((self.path.parent / 'backups').glob('*pre-v04*.db'))
        self.assertEqual(len(backups), 1)
        db.init_db(self.path)
        self.assertEqual(len(list((self.path.parent / 'backups').glob('*pre-v04*.db'))), 1)

    def test_v2_migration_failure_rolls_back_added_schema(self):
        from models.inventory_schema import create_inventory_schema
        def fail(conn):
            create_inventory_schema(conn)
            raise sqlite3.OperationalError('Simulated failure')
        with patch('models.inventory_schema.create_inventory_schema', side_effect=fail):
            with self.assertRaises(RuntimeError):
                db.init_db(self.path)
        self.assertEqual(self.original_rows(), self.before)
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_movements'").fetchone())
