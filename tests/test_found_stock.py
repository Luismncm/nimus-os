import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import inventory, recipes
from tests import test_origin as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class FoundStockTest(unittest.TestCase):
    setUp = fixture.OriginModelsTest.setUp

    def component(self):
        return recipes.load_catalog()['components'][0]

    def sku(self, component_id):
        return next(s for s in inventory.load_inventory()['skus'] if s['component_id'] == component_id)

    def test_several_found_pieces_add_up_in_one_reversible_save(self):
        first, second = recipes.load_catalog()['components'][:2]
        ids = inventory.receive_found([dict(component_id=first['id'], quantity=3, destination='Colección'),
                                       dict(component_id=first['id'], quantity=2, destination='Colección'),
                                       dict(component_id=second['id'], quantity=4, destination='Stock')], request_key='found-1')
        # The same piece and place add up into one entry; a repeated request saves nothing new.
        self.assertEqual(len(ids), 2)
        self.assertEqual(inventory.receive_found([dict(component_id=first['id'], quantity=5, destination='Colección'),
                                                  dict(component_id=second['id'], quantity=4, destination='Stock')], request_key='found-1'), ids)
        self.assertEqual((self.sku(first['id'])['available_collection'], self.sku(second['id'])['available_stock']), (5, 4))
        movement = next(m for m in inventory.load_inventory()['movements'] if m['id'] == ids[0])
        self.assertEqual((movement['kind'], movement['notes']), ('Entrada manual', 'Stock encontrado'))
        inventory.reverse_movement(ids[0], 'Conteo equivocado')
        self.assertEqual(self.sku(first['id'])['available_collection'], 0)

    def test_every_line_needs_a_piece_and_a_whole_quantity(self):
        cid = self.component()['id']
        for entries in ([], [dict(component_id=None, quantity=1)], [dict(component_id=cid, quantity=0)], [dict(component_id=cid, quantity=1.5)]):
            with self.assertRaises(ValueError):
                inventory.receive_found(entries, request_key='bad')

    def test_inventory_page_opens_found_stock_and_saves_the_preset_piece(self):
        c = self.component()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/collection.py').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.button_group(key='collection_workspace').value, 'Existencias')
        app.button(key='inventory_found').click().run()
        self.assertEqual(app.session_state['active_dialog'][0], 'found_stock_form')
        # Opened from a piece, the first line already has it.
        app.session_state['active_dialog'] = ('found_stock_form', (dict(component_id=c['id']),), {})
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.button(key='found_' + app.session_state['dialog_request_key'] + '_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(self.sku(c['id'])['available_collection'], 1)
        # Sections keep working through the emoji switch.
        app.button_group(key='collection_workspace').set_value('Movimientos').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])


if __name__ == '__main__':
    unittest.main()
