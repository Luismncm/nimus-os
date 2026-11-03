import unittest
from datetime import timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import capture, production as p
from services.queries import load_snapshot
from tests import test_development as fixture
from utils.dates import now
from views import queue_agenda as agenda

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class QueueAgendaTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def prints(self):
        oid = p.create_order('Llaveros', 'Cliente');iid = p.create_item(oid, 'Llavero', 9)
        base = p.create_part(iid, 'Base', 3, 'Impresión 3D', 'PLA Prueba')
        ring = p.create_part(iid, 'Aro', 3, 'Impresión 3D', 'PLA Prueba')
        tap = p.create_part(iid, 'Tapa', 3, 'Impresión 3D', 'PLA Prueba')
        tomorrow = (now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        late = (now() - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
        capture.new_print(oid, part_id=base, quantity=3, machine_id=1, planned_start=tomorrow.isoformat(timespec='minutes'), duration_minutes=90, request_key='a')
        capture.new_print(oid, part_id=ring, quantity=3, machine_id=2, planned_start=late.isoformat(timespec='minutes'), duration_minutes=60, request_key='b')
        capture.new_print(oid, part_id=tap, quantity=3, machine_id=3, request_key='c')
        jobs = {j['part_name']: j for j in load_snapshot()['jobs']}
        return oid, tomorrow, jobs

    def test_prints_fall_on_their_day_and_missed_starts_on_today(self):
        _, tomorrow, jobs = self.prints()
        at = now()
        by_day, waiting = agenda.bucket(load_snapshot()['jobs'], at.date(), 3, at)
        self.assertEqual([s['job']['code'] for s in by_day[tomorrow.date()]], [jobs['Base']['code']])
        self.assertEqual([s['job']['code'] for s in by_day[at.date()]], [jobs['Aro']['code']])  # Its start was missed two days ago.
        self.assertEqual([s['job']['code'] for s in waiting], [jobs['Tapa']['code']])
        # A day view of tomorrow alone does not carry the missed one.
        by_day, _ = agenda.bucket(load_snapshot()['jobs'], tomorrow.date(), 1, at)
        self.assertEqual(list(by_day), [tomorrow.date()])
        self.assertEqual(len(by_day[tomorrow.date()]), 1)

    def test_operar_agenda_moves_by_period_and_keeps_actions(self):
        _, tomorrow, jobs = self.prints()
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/queue.py').run()
        app.button_group(key='queue_group').set_value('Agenda').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # Today: the missed print with its actions; tomorrow's print is not in a one-day view.
        keys = {b.key for b in app.button}
        self.assertIn(f"queue_{jobs['Aro']['id']}_start", keys)
        self.assertNotIn(f"queue_{jobs['Base']['id']}_start", keys)
        app.button(key='queue_agenda_next').click().run()
        self.assertEqual(app.session_state['queue_agenda_day'], tomorrow.date())
        self.assertIn(f"queue_{jobs['Base']['id']}_start", {b.key for b in app.button})
        self.assertTrue(any('09:00 – 10:30' in m.value for m in app.markdown))
        # A three-day view from today shows both, and the print without a time waits at the end.
        app.button(key='queue_agenda_today').click().run()
        app.button_group(key='queue_agenda_period').set_value('3 días').run()
        keys = {b.key for b in app.button}
        self.assertTrue({f"queue_{jobs['Aro']['id']}_start", f"queue_{jobs['Base']['id']}_start", f"queue_{jobs['Tapa']['id']}_start"} <= keys)
        self.assertFalse(app.exception, [e.message for e in app.exception])
        # Every print says where it stands: booked, missed, or on its printer without a time (in sight, not folded).
        text = ' '.join(m.value for m in app.markdown)
        for label in ('Programada', 'Inicio vencido', 'Asignada sin hora'):
            self.assertIn(label, text)
        self.assertIn('**:material/pending_actions: Asignadas sin hora** :gray[· 1]', [m.value for m in app.markdown])
        # Divided by printer: each day lists its printers with their own prints.
        app.button_group(key='queue_agenda_layout').set_value('Por máquina').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(any(b.key == f"queue_{jobs['Base']['id']}_start" for b in app.button))
        # One printer: only its prints, with its strip, and the others are gone.
        app.button_group(key='queue_agenda_machine').set_value(1).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        keys = {b.key for b in app.button}
        self.assertIn(f"queue_{jobs['Base']['id']}_start", keys)
        self.assertNotIn(f"queue_{jobs['Aro']['id']}_start", keys)
        self.assertTrue(any('tl-track' in h.proto.body for h in app.get('html')))

    def test_every_printer_of_a_model_shares_its_color(self):
        from views.tags import family, printer_html
        a1, other_a1, p1s = ({'name': 'BAMBU LAB A1', 'code': 'A1-01', 'status': 'Disponible'}, {'name': 'BAMBU LAB A1', 'code': 'A1-03', 'status': 'Imprimiendo'},
                             {'name': 'BAMBU LAB P1S COMBO', 'code': 'P1 - 01', 'status': 'Disponible'})
        self.assertEqual(family(a1), family(other_a1))
        self.assertNotEqual(family(a1)[1], family(p1s)[1])
        self.assertEqual((family(a1)[0], family(p1s)[0]), ('A1', 'P1S'))
        self.assertIn('>P1S<', printer_html(p1s))
        self.assertIn('Sin máquina', printer_html(None))


if __name__ == '__main__':
    unittest.main()
