import unittest
from datetime import date
from services import performance as perf

TODAY=date(2026,11,3)

def data(**kw):
    base=dict(sales=[],receipts=[],expenses=[],payments=[],deliveries=[],jobs=[],failures=[],
              machines=[dict(id=1,code='P1',name='Bambu',archived=0),dict(id=2,code='P2',name='Vieja',archived=1)])
    return base|kw


class PeriodTest(unittest.TestCase):
    def test_periods_and_their_comparison_spans(self):
        self.assertEqual(perf.period('Este mes',TODAY),(date(2026,11,1),TODAY))
        self.assertEqual(perf.period('Mes anterior',TODAY),(date(2026,10,1),date(2026,10,31)))
        self.assertEqual(perf.period('Últimos 90 días',TODAY),(date(2026,8,6),TODAY))
        self.assertEqual(perf.period('Este año',TODAY),(date(2026,1,1),TODAY))
        # Month to date compares with the same days of last month, clamped to its end.
        self.assertEqual(perf.previous(date(2026,11,1),TODAY),(date(2026,10,1),date(2026,10,3)))
        self.assertEqual(perf.previous(date(2026,3,1),date(2026,3,31)),(date(2026,2,1),date(2026,2,28)))
        self.assertEqual(perf.previous(date(2026,1,1),TODAY),(date(2025,1,1),date(2025,11,3)))
        self.assertEqual(perf.previous(date(2026,8,6),TODAY),(date(2026,5,8),date(2026,8,5)))


class SummaryTest(unittest.TestCase):
    def test_money_counts_active_sales_and_dated_payments(self):
        d=data(sales=[dict(id=1,status='Activa',total_cents=10000,sold_on='2026-11-02',client='A'),
                      dict(id=2,status='Cancelada',total_cents=99999,sold_on='2026-11-02',client='A'),
                      dict(id=3,status='Activa',total_cents=5000,sold_on='2026-10-30',client='B')],
               receipts=[dict(amount_cents=7000,paid_on='2026-11-01'),dict(amount_cents=500,paid_on='2026-10-31')],
               expenses=[dict(total_cents=3000,expense_on='2026-11-03')],
               payments=[dict(amount_cents=9000,paid_on='2026-11-02')])
        s=perf.summary(d,date(2026,11,1),TODAY)
        self.assertEqual((s['sold_cents'],s['sales_count'],s['ticket_cents']),(10000,1,10000))
        self.assertEqual((s['collected_cents'],s['expenses_cents'],s['paid_out_cents'],s['cash_cents']),(7000,3000,9000,-2000))

    def test_deliveries_on_time_and_production(self):
        d=data(deliveries=[dict(id=1,code='O1',client='A',deadline='2026-11-02',created_on='2026-10-28',delivered_on='2026-11-02'),
                           dict(id=2,code='O2',client='A',deadline='2026-11-01',created_on='2026-10-30',delivered_on='2026-11-03'),
                           dict(id=3,code='O3',client='A',deadline=None,created_on='2026-11-01',delivered_on='2026-11-01')],
               jobs=[dict(id=1,machine_id=1,quantity_completed=8,completed_on='2026-11-02',total_seconds=7200,tracking_complete=1),
                     dict(id=2,machine_id=1,quantity_completed=2,completed_on='2026-11-03',total_seconds=None,tracking_complete=None),
                     dict(id=3,machine_id=1,quantity_completed=50,completed_on='2026-10-02',total_seconds=3600,tracking_complete=1)],
               failures=[dict(rejected_units=2,created_on='2026-11-02',machine_id=1)])
        s=perf.summary(d,date(2026,11,1),TODAY)
        self.assertEqual((s['delivered'],s['promised'],s['on_time'],s['on_time_percent']),(3,2,1,50.0))
        self.assertEqual(s['lead_days'],round((5+4+0)/3,1))
        self.assertEqual((s['lots'],s['pieces'],s['machine_hours'],s['untimed_lots']),(2,10,2.0,1))
        self.assertEqual((s['rejected'],s['reject_percent']),(2,round(100*2/12,1)))
        empty=perf.summary(data(),date(2026,11,1),TODAY)
        self.assertIsNone(empty['on_time_percent']);self.assertIsNone(empty['reject_percent']);self.assertIsNone(empty['ticket_cents'])

    def test_months_machines_and_clients(self):
        d=data(sales=[dict(id=1,status='Activa',total_cents=6000,sold_on='2026-11-02',client='A'),
                      dict(id=2,status='Activa',total_cents=4000,sold_on='2026-11-02',client=' '),
                      dict(id=3,status='Activa',total_cents=1000,sold_on='2026-06-15',client='A')],
               jobs=[dict(id=1,machine_id=1,quantity_completed=4,completed_on='2026-11-02',total_seconds=36*3600,tracking_complete=1)])
        rows=perf.months(d,TODAY)
        self.assertEqual([r['month'] for r in rows],['2026-06','2026-07','2026-08','2026-09','2026-10','2026-11'])
        self.assertEqual((rows[0]['sold_cents'],rows[-1]['sold_cents'],rows[-1]['pieces']),(1000,10000,4))
        machines=perf.by_machine(d,date(2026,11,1),TODAY)
        # An archived machine with no work in the period is left out.
        self.assertEqual([m['code'] for m in machines],['P1'])
        self.assertEqual((machines[0]['hours'],machines[0]['use_percent']),(36.0,50.0))
        clients=perf.top_clients(d,date(2026,11,1),TODAY)
        self.assertEqual([(c['client'],c['sold_cents'],c['share_percent']) for c in clients],[('A',6000,60.0),('Sin cliente',4000,40.0)])
