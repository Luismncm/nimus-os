import unittest
from datetime import date
from services import financial_health as fh

TODAY=date(2026,11,3)

def month(sold=0,collected=0,spent=0,one_time=0,paid=0,injected=0):
    return dict(sold=sold,collected=collected,spent=spent,one_time=one_time,paid=paid,injected=injected)

def data(months,cash=1800000,margin=(1000000,560000),**kw):
    return dict(dict(months=months,cash_cents=cash,cash_estimated=True,unreconciled=['Banco'],undated=0,receivable_cents=700000,payable_cents=500000,
                     partner_cents=48000000,margin=dict(net=margin[0],cost=margin[1],costed=1,sales=2),unclassified=0),**kw)

# A young business: sells a third of what it spends and lives on partner money.
YOUNG={'2026-08':month(sold=600000,collected=300000,spent=4400000,paid=4400000,injected=700000),
       '2026-09':month(sold=200000,collected=200000,spent=3500000,paid=3500000,injected=6000000),
       '2026-10':month(sold=2600000,collected=2300000,spent=6200000,one_time=100000,paid=5600000,injected=5200000),
       '2026-11':month(sold=99999999,collected=99999999)}


class FinancialHealthTest(unittest.TestCase):
    def test_window_is_complete_months_before_today(self):
        self.assertEqual(fh.window(TODAY,3),['2026-08','2026-09','2026-10'])
        self.assertEqual(fh.window(date(2026,2,10),3),['2025-11','2025-12','2026-01'])
        self.assertEqual([r['month'] for r in fh.trend(data(YOUNG),TODAY,3)],['2026-09','2026-10','2026-11'])

    def test_young_business_reads_critical_with_its_reasons(self):
        h=fh.health(data(YOUNG),TODAY,3)
        avg=h['average']
        # The current month (with its huge sale) stays out of the averages.
        self.assertEqual((avg['sold'],avg['spent'],avg['collected'],avg['paid']),(1133333,4700000,933333,4500000))
        self.assertEqual(h['burn_cents'],4500000-933333)
        self.assertEqual(h['runway_months'],round(1800000/(4500000-933333),1))
        self.assertEqual(h['coverage_percent'],round(100*1133333/4700000,1))
        self.assertEqual(h['margin_percent'],44.0)
        self.assertEqual(h['break_even_cents'],round(4700000*100/44.0))
        self.assertEqual(h['break_even_multiple'],round(h['break_even_cents']/1133333,1))
        self.assertGreater(h['partner_share_percent'],50)
        self.assertEqual((h['tones']['runway'],h['tones']['coverage'],h['tones']['margin'],h['tones']['partner']),(fh.CRITICAL,fh.CRITICAL,fh.HEALTHY,fh.CRITICAL))
        self.assertEqual(h['overall'],fh.CRITICAL)
        self.assertIn('viene del socio',h['verdict']);self.assertIn('meses',h['verdict'])
        self.assertEqual(h['liquidity'],round((1800000+700000)/500000,1))

    def test_self_sustaining_business_and_missing_margin(self):
        months={m:month(sold=500000,collected=500000,spent=300000,paid=300000) for m in fh.window(TODAY,3)}
        h=fh.health(data(months),TODAY,3)
        self.assertIsNone(h['runway_months']);self.assertEqual(h['tones']['runway'],fh.HEALTHY)
        self.assertEqual((h['coverage_percent'],h['tones']['coverage'],h['partner_share_percent']),(166.7,fh.HEALTHY,0.0))
        self.assertEqual(h['overall'],fh.HEALTHY);self.assertIn('se sostiene',h['verdict'])
        blank=fh.health(data({},margin=(0,0)),TODAY,3)
        self.assertIsNone(blank['margin_percent']);self.assertIsNone(blank['break_even_cents']);self.assertIsNone(blank['tones']['margin'])
        self.assertIsNone(blank['coverage_percent']);self.assertIsNone(blank['partner_share_percent'])
