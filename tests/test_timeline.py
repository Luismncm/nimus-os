import unittest
from datetime import datetime,timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import production as prod,planning
from services.timeline import slot,issues,availability,availability_text,machine_timeline,attention,duration_text
from tests import test_planning as fixture

AT=datetime(2026,10,21,9,0)

def job(id,status='En cola',start=None,end=None,indefinite=False,planned=None,minutes=None,**kw):
    iso=lambda v:v.isoformat(timespec='minutes') if v else None
    return dict(dict(id=id,code=f'JOB-{id:04d}',part_name='Base',machine_id=1,order_status='Pendiente',status=status,
                reservation_start=iso(start),reservation_end=iso(end),reservation_indefinite=indefinite,
                planned_start=iso(planned or (start if status!='En producción' else None)),duration_minutes=minutes,
                schedule_conflicts=[],overdue_schedule=False,current_run_started_at=iso(start)),**kw)


class TimelineModelTest(unittest.TestCase):
    def test_each_job_has_one_timing_state(self):
        self.assertEqual(slot(job(1,'En producción',AT,AT+timedelta(hours=2),minutes=120),AT)['state'],'En marcha')
        self.assertEqual(slot(job(2,'En producción',AT,None,True,minutes=60),AT)['state'],'Sin fin')
        self.assertEqual(slot(job(3,start=AT,end=AT+timedelta(hours=1),minutes=60),AT)['state'],'Reservada')
        self.assertEqual(slot(job(4,planned=AT),AT)['state'],'Sin duración')
        self.assertEqual(slot(job(5,minutes=90),AT)['state'],'Sin horario')
        self.assertEqual(duration_text(90),'1 h 30 min');self.assertEqual(duration_text(600),'10 h');self.assertEqual(duration_text(45),'45 min')

    def test_availability_walks_bookings_from_now(self):
        later=job(1,start=AT+timedelta(hours=2),end=AT+timedelta(hours=3),minutes=60)
        free=availability([slot(later,AT)],AT)
        self.assertEqual((free['kind'],free['until']),('libre',AT+timedelta(hours=2)))
        self.assertIn('Libre ahora · hasta hoy 11:00 (JOB-0001)',availability_text(free,AT))
        running=job(2,'En producción',AT,AT+timedelta(hours=2),minutes=120)
        busy=availability([slot(running,AT),slot(later,AT)],AT)
        # Consecutive bookings merge: busy until the second one ends, then free.
        self.assertEqual((busy['kind'],busy['since'],busy['until']),('ocupada',AT+timedelta(hours=3),None))
        self.assertEqual(availability_text(busy,AT),'Ocupada hasta hoy 12:00 · luego libre')
        blocked=availability([slot(job(3,'En producción',AT,None,True,minutes=30),AT)],AT)
        self.assertEqual(blocked['kind'],'bloqueada')

    def test_problems_are_explained_and_ranked_by_what_blocks_a_machine(self):
        overdue=job(1,'En producción',AT-timedelta(hours=3),None,True,minutes=60,overdue_schedule=True)
        clash=job(2,start=AT+timedelta(hours=1),end=AT+timedelta(hours=2),minutes=60,schedule_conflicts=['JOB-0009'])
        legacy=job(3,planned=AT+timedelta(hours=5))
        fine=job(4,start=AT+timedelta(hours=6),end=AT+timedelta(hours=7),minutes=60)
        texts=issues(slot(overdue,AT))
        self.assertEqual(len(texts),1);self.assertIn('Ya pasó su fin estimado',texts[0])
        self.assertIn('JOB-0009',issues(slot(clash,AT))[0])
        self.assertEqual([s['job']['id'] for s in attention([fine,legacy,clash,overdue],AT)],[1,2,3])
        timeline=machine_timeline(dict(id=1),[overdue,clash,legacy,fine,job(5,minutes=90)],AT)
        self.assertEqual((timeline['unscheduled'],timeline['unscheduled_minutes'],timeline['problems']),(2,90,3))


class TimelineUITest(unittest.TestCase):
    setUp=fixture.PlanningTest.setUp

    def test_first_free_never_offers_a_start_that_is_already_due(self):
        from services import resources
        self.assertEqual(resources.first_free(0,1,60,at=datetime(2026,10,21,9,58)),datetime(2026,10,21,10,15))
        self.assertEqual(resources.first_free(0,1,60,at=datetime(2026,10,21,10,5)),datetime(2026,10,21,10,15))

    def test_scheduling_offers_first_free_slot_after_existing_booking(self):
        start=self.at+timedelta(hours=1)
        first=prod.create_job(self.pid,2,1,plan=dict(self.data,planned_start=start.isoformat(),duration_minutes=120))
        waiting=prod.create_job(self.pid,2,1,plan=dict(self.data,planned_start=None,duration_minutes=60))
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run().switch_page('views/queue.py').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        # A print with duration and machine but no time is flagged in Por resolver with its fix.
        self.assertEqual(app.button(key=f'queue_fix_{waiting}').label,'Programar en el primer horario libre')
        app.button(key=f'queue_{waiting}_plan').click().run()
        prefix='plan_'+app.session_state['dialog_request_key']
        # Offers start at a quarter hour 5+ minutes away, so 60 minutes no longer fit before the booking: the slot follows it.
        app.button(key=prefix+'_first_free').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        next(b for b in app.button if b.label=='Guardar programación').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertFalse(app.error,[e.value for e in app.error])
        booked=datetime.fromisoformat(planning.get(first)['planned_start'])
        self.assertEqual(datetime.fromisoformat(planning.get(waiting)['planned_start']),booked+timedelta(minutes=120))


if __name__=='__main__':
    unittest.main()
