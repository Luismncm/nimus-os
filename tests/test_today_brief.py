import unittest
from datetime import datetime, timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import production as p, sales, expenses
from services.queries import load_snapshot
from services.workbench import operating_board
from services.supply_board import board as supply_board
from views.today_brief import agenda_items, agenda_html, day_words, greeting, headline
from tests import test_development as fixture

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class TodayBriefTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp
    launch = fixture.DevelopmentTest.launch

    def board(self):
        snapshot = load_snapshot()
        return snapshot, operating_board(snapshot, sales.list_sales(), expenses.list_expenses())

    def test_greeting_and_date_read_in_words(self):
        self.assertEqual(day_words(datetime(2026, 11, 2, 9)), 'Lunes 2 de noviembre')
        self.assertEqual([greeting(datetime(2026, 1, 1, h)) for h in (8, 15, 21)], ['Buenos días', 'Buenas tardes', 'Buenas noches'])

    def test_headline_says_the_floor_and_what_is_late(self):
        snapshot, board = self.board()
        line = headline(board, snapshot, supply_board(snapshot['jobs']))
        self.assertIn(f"0 de {len(snapshot['machines'])} impresoras trabajando", line)
        self.assertTrue(line.endswith('.'))

    def test_agenda_lists_todays_prints_in_time_order_with_a_now_line(self):
        start = self.start
        # Only prints that start today land on today's agenda.
        if start.date() != datetime.now().date():
            self.skipTest('The fixture print is booked for tomorrow at this hour.')
        self.launch()
        self.launch('later', planned_start=(start + timedelta(hours=3)).isoformat())
        snapshot, board = self.board()
        timed, allday = agenda_items(snapshot, board)
        self.assertEqual([e['label'] for e in timed], ['Inicia', 'Inicia'])
        self.assertLess(timed[0]['at'], timed[1]['at'])
        page = agenda_html(timed, allday)
        self.assertIn('Pantalla v3 ×2', page)
        self.assertIn('ag-now', page)

    def test_hoy_opens_on_its_briefing_and_the_pulse_leads_to_each_area(self):
        p.create_order('Lámparas', 'Cliente')
        app = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state['today_front'], 'Resumen')
        for front in ('Producir', 'Entregar', 'Abastecer', 'Cobrar', 'Pagar'):
            self.assertTrue(app.button(key=f'today_pulse_{front}'))
        app.button(key='today_pulse_Entregar').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state['today_front'], 'Entregar')


if __name__ == '__main__':
    unittest.main()
