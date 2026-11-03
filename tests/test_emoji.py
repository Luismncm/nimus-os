import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from views.emoji import EMOJI, STATUS, status, tag
from tests import test_origin as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class EmojiTest(unittest.TestCase):
    setUp = fixture.OriginModelsTest.setUp

    def test_words_get_one_picture_and_unknown_words_stay(self):
        self.assertEqual((tag('Movimientos'), tag('En cola'), tag('Algo nuevo')), ('🧾 Movimientos', '⏳ En cola', 'Algo nuevo'))
        self.assertEqual((status('Terminado'), status(None), status(3)), ('✅ Terminado', None, 3))
        # Every picture is a short emoji, never a long text.
        self.assertTrue(all(0 < len(v) <= 2 for v in (*EMOJI.values(), *STATUS.values())))

    def test_tabs_and_switches_keep_their_plain_values(self):
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/expenses.py').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # The tab shows 🧾 through CSS; its value stays the word other pages and tests use.
        self.assertEqual(app.session_state['expense_tabs'], 'Movimientos')
        self.assertTrue(any('stTab' in (h.proto.body if hasattr(h.proto, 'body') else '') for h in app.get('html')))
        app.switch_page('views/orders.py').run()
        self.assertEqual(app.button_group(key='orders_scope').value, 'Activos')


if __name__ == '__main__':
    unittest.main()
