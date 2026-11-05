import unittest
from datetime import datetime, timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import capture, production as p
from services.queries import load_snapshot
from services.timeline import slot
from tests import test_development as fixture
from utils.dates import now
from views import machine_agenda as agenda

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def booked(start, minutes, state='Reservada'):
    job = dict(status='En cola', reservation_start=start.isoformat(timespec='minutes'),
               reservation_end=(start + timedelta(minutes=minutes)).isoformat(timespec='minutes'), duration_minutes=minutes)
    return dict(slot(job), state=state)


class AgendaGapsTest(unittest.TestCase):
    def test_free_gaps_sit_between_bookings_and_fit_the_print(self):
        at = datetime(2026, 10, 29, 8, 0)
        rows = [booked(at + timedelta(hours=1), 60), booked(at + timedelta(hours=2, minutes=30), 90), booked(at + timedelta(hours=4, minutes=10), 30)]
        # The 10 minutes between the second and third bookings are too short to offer.
        self.assertEqual(agenda.gaps(rows, at), [(at, at + timedelta(hours=1)), (at + timedelta(hours=2), at + timedelta(hours=2, minutes=30)),
                                                 (at + timedelta(hours=4, minutes=40), None)])
        # A 45-minute print only fits in the first gap and after the last booking.
        self.assertEqual(agenda.gaps(rows, at, minutes=45), [(at, at + timedelta(hours=1)), (at + timedelta(hours=4, minutes=40), None)])
        # A print running without a finish keeps the machine taken: no gap after it.
        self.assertEqual(agenda.gaps([dict(booked(at, 60), state='Sin fin')], at), [])


class AgendaUITest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def test_assigning_shows_the_printer_agenda_and_a_free_gap_becomes_the_start(self):
        oid = p.create_order('Llaveros', 'Cliente');iid = p.create_item(oid, 'Llavero', 5)
        first = p.create_part(iid, 'Base', 5, 'Impresión 3D', 'PLA Prueba')
        second = p.create_part(iid, 'Aro', 5, 'Impresión 3D', 'PLA Prueba')
        tomorrow = (now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        capture.new_print(oid, part_id=first, quantity=5, machine_id=1, planned_start=tomorrow.isoformat(timespec='minutes'),
                          duration_minutes=120, request_key='booked')
        booked_code = next(j['code'] for j in load_snapshot()['jobs'] if j['part_id'] == first)
        loose = p.create_jobs(p.create_part(iid, 'Tapa', 2, 'Impresión 3D', 'PLA Prueba'), [dict(quantity=2, machine_id=1)])[0]
        loose_code = next(j['code'] for j in load_snapshot()['jobs'] if j['id'] == loose)
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid;app.run()
        app.button_group(key=f'order_production_view_{oid}').set_value('Asignar').run()
        key = f'order_assign_{oid}_{second}_v0'
        app.number_input(key=f'{key}_hours').set_value(1).run()
        app.button(key=f'{key}_use_1').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # The chosen printer's agenda lists the booked print and the one being set up.
        html = ' '.join(h.proto.body for h in app.get('html'))
        self.assertIn(booked_code, html)
        self.assertIn('Esta impresión · Aro ×5', html)
        self.assertIn('Programada', html)  # The booked print carries its calendar tag.
        # The print assigned to this printer without a start closes the agenda in its own block.
        self.assertIn('SIN HORA', html)
        self.assertIn(loose_code, html)
        self.assertIn('Asignada sin hora', html)
        self.assertTrue(any('Agenda de' in m.value for m in app.markdown))
        # Picking the gap after tomorrow's booking moves the start there.
        gap = app.button_group(key=f'{key}_gap_1')
        after = (tomorrow + timedelta(hours=2)).isoformat(timespec='minutes')
        self.assertIn('mañana 12:00 · libre', gap.options)
        gap.set_value(after).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state[f'{key}_when_1'], 'Otra fecha')
        app.number_input(key=f'{key}_grams').set_value(20).run()
        app.button(key=f'{key}_save').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        job = next(j for j in load_snapshot()['jobs'] if j['part_id'] == second)
        self.assertEqual((job['machine_id'], job['planned_start'], job['duration_minutes']), (1, after, 60))


if __name__ == '__main__':
    unittest.main()
