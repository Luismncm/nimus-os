import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import db
from services import inventory as inv
from services import production as p
from services.queries import load_snapshot
from tests.ui_helpers import enter_option


class InventoryUITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'NIMUS_DB_PATH': str(Path(self.temp.name) / 'ui.db')})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)

    def clean(self):
        self.assertFalse(self.app.exception, [exc.message for exc in self.app.exception])

    def click(self, label):
        next(b for b in self.app.button if b.label == label).click().run()
        self.clean()

    def seed(self):
        # Ten pieces of the general inventory: a print straight to inventory, outside Colección Origen.
        from services import stock_runs
        p.job_action(stock_runs.launch('Base', 10, product='Lámpara Origen', material='PLA', request_key='seed'), 'finish')

    def test_empty_inventory_view(self):
        self.app.run().switch_page('views/collection.py').run()
        self.clean()
        self.assertTrue(any('inventario está vacío' in i.value for i in self.app.info))
        self.assertFalse(self.app.button(key='inventory_receive').disabled)

    def test_item_collection_checkbox_and_automatic_receipt(self):
        order = p.create_order('Lote Origen')
        self.app.run().switch_page('views/orders.py').run()
        self.app.button_group(key='orders_view').set_value('Lista').run()
        self.app.button(key='orders_open_1').click().run()
        self.app.button(key='order_add_item_1').click().run()
        enter_option(self.app, 'item_name', 'Lámpara Origen')
        self.app.number_input(key='item_quantity').set_value(10)
        self.app.checkbox(key='item_collection').check()
        self.click('Guardar producto')
        self.assertEqual(load_snapshot()['items'][0]['collection'], 'Origen')
        part = p.create_part(1, 'Base', 10, 'Impresión 3D')
        p.job_action(p.create_job(part, 10), 'finish')
        # Colección Origen pieces are counted in its own inventory, not in the general one.
        self.app.switch_page('views/collection.py').run()
        self.clean()
        self.assertEqual(self.app.metric[0].value, '0')
        self.app.session_state['origin_workspace'] = 'Inventario'
        self.app.switch_page('views/origen.py').run()
        self.clean()
        self.assertEqual(self.app.metric[0].value, '10')
        self.assertTrue(self.app.button(key='origin_stock_distribute'))

    def test_distribution_b2b_stock_reverse_and_filters(self):
        self.seed()
        self.app.run().switch_page('views/collection.py').run()
        self.app.button(key='inventory_distribute').click().run()
        self.app.selectbox(key='distribute_1_Colección_destination').set_value('B2B').run()
        self.app.number_input(key='distribute_1_quantity').set_value(4)
        enter_option(self.app, 'distribute_1_client', 'Cliente B2B')
        self.click('Guardar movimiento')
        self.assertEqual(inv.load_inventory()['skus'][0]['b2b'], 4)
        self.app.button(key='inventory_distribute').click().run()
        self.app.selectbox(key='distribute_1_Colección_destination').set_value('Stock').run()
        self.app.number_input(key='distribute_1_quantity').set_value(3)
        self.click('Guardar movimiento')
        self.assertEqual(inv.load_inventory()['skus'][0]['stock'], 3)
        self.app.button_group(key='collection_workspace').set_value('Movimientos').run()
        self.app.selectbox(key='inventory_reverse_selected').set_value(2).run()
        self.app.button(key='inventory_reverse').click().run()
        self.app.text_input(key='inventory_reversal_reason').set_value('Cliente cambió su pedido')
        self.click('Confirmar reversión')
        self.assertEqual(inv.load_inventory()['clients'], [])
        self.app.button_group(key='collection_workspace').set_value('Existencias').run()
        self.app.text_input(key='inventory_search').set_value('No existe').run()
        self.clean()
        self.assertFalse(any(b.key == 'inventory_distribute' for b in self.app.button))

    def test_oversized_distribution_shows_error_without_mutation(self):
        self.seed()
        self.app.run().switch_page('views/collection.py').run()
        self.app.button(key='inventory_distribute').click().run()
        self.app.number_input(key='distribute_1_quantity').set_value(11)
        self.click('Guardar movimiento')
        self.assertTrue(any('Solo hay 10' in error.value for error in self.app.error))
        self.assertEqual(len(inv.load_inventory()['movements']), 1)

    def test_assignment_reopens_clean_and_uses_stock_when_collection_is_empty(self):
        self.seed()
        self.app.run().switch_page('views/collection.py').run()
        self.app.button(key='inventory_distribute').click().run()
        self.app.selectbox(key='distribute_1_Colección_destination').set_value('B2B').run()
        self.app.number_input(key='distribute_1_quantity').set_value(4)
        enter_option(self.app, 'distribute_1_client', 'Tienda Norte')
        self.click('Guardar movimiento')
        self.app.button(key='inventory_distribute').click().run()
        self.assertEqual(self.app.number_input(key='distribute_1_quantity').value, 1)
        self.app.selectbox(key='distribute_1_Colección_destination').set_value('B2B').run()
        self.assertIsNone(self.app.selectbox(key='distribute_1_client').value)
        self.assertIn('Tienda Norte', self.app.selectbox(key='distribute_1_client').options)
        self.app.selectbox(key='distribute_1_client').set_value('Tienda Norte')
        self.click('Guardar movimiento')
        inv.distribute(1, 'Colección', 'Stock', 5)
        self.app.run()
        self.app.button(key='inventory_distribute').click().run()
        self.clean()
        self.assertEqual(self.app.selectbox(key='distribute_1_source').value, 'Stock')
        row = inv.load_inventory()['skus'][0]
        self.assertEqual((row['produced'], row['unassigned'], row['stock'], row['b2b']), (10, 0, 5, 5))

    def test_filter_changes_selected_piece_before_assignment(self):
        self.seed()
        from services import stock_runs
        p.job_action(stock_runs.launch('Pantalla', 8, product='Lámpara Origen', material='PLA blanco', request_key='shade'), 'finish')
        skus = inv.load_inventory()['skus']
        shade = next(row['id'] for row in skus if row['part'] == 'Pantalla')
        self.app.run().switch_page('views/collection.py').run()
        self.app.selectbox(key='inventory_selected').set_value(shade).run()
        self.app.text_input(key='inventory_search').set_value('Base').run()
        self.assertEqual(self.app.selectbox(key='inventory_selected').value, 1)
        self.app.button(key='inventory_distribute').click().run()
        self.app.number_input(key='distribute_1_quantity').set_value(2)
        self.click('Guardar movimiento')
        rows = {row['part']: row for row in inv.load_inventory()['skus']}
        self.assertEqual(rows['Base']['stock'], 2)
        self.assertEqual(rows['Pantalla']['stock'], 0)
