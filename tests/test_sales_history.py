import unittest
from services import sales_history as h

def sale(id,sold_on,total,client='A',status='Activa',paid=0,channel='Venta al público',origin='Directa',lines=None):
    return dict(id=id,code=f'VEN-{id:04d}',status=status,total_cents=total,sold_on=sold_on,channel=channel,quote_id=None,
                client=client,origin=origin,paid_cents=paid,lines=lines or [dict(product='TAP BAR',quantity=1,amount_cents=total,line=h.CUSTOM_LINE)])

ROWS=[sale(1,'2025-12-10',10000,paid=10000),
      sale(2,'2026-02-05',20000,client='B',paid=5000,origin='Cotización',
           lines=[dict(product='CIRRUS',quantity=2,amount_cents=15000,line=h.ORIGIN_LINE),dict(product='TAP BAR',quantity=1,amount_cents=5000,line=h.CUSTOM_LINE)]),
      sale(3,'2026-02-20',10000,client='a',paid=10000,channel='B2B'),
      sale(4,'2026-03-01',99999,client='C',status='Cancelada')]


class SalesHistoryTest(unittest.TestCase):
    def test_product_name_is_the_model(self):
        self.assertEqual(h.product('CIRRUS · GRIS NIEBLA'),'CIRRUS')
        self.assertEqual(h.product('tap bar 3'),'TAP BAR 3')
        self.assertEqual(h.product(None),'SIN DESCRIPCIÓN')
        self.assertEqual(h.product('Lámpara Cúmulo'),'LAMPARA CUMULO')
        models={'CIRRUS','CUMULO','STRATO'}
        self.assertEqual(h.classify('CIRRUS · BEIGE',7,{7},models),('CIRRUS',h.ORIGIN_LINE))
        self.assertEqual(h.classify('Lámpara Cúmulo Desierto (beige)',None,{7},models),('CUMULO',h.ORIGIN_LINE))
        self.assertEqual(h.classify('ORG-BD-CIR',None,{7},models),('CIRRUS',h.ORIGIN_LINE))
        self.assertEqual(h.classify('LAMAPARA ORIGEN',None,{7},models),(h.ORIGIN_UNKNOWN,h.ORIGIN_LINE))
        self.assertEqual(h.classify('Colección Origen',None,{7},models),(h.ORIGIN_UNKNOWN,h.ORIGIN_LINE))
        self.assertEqual(h.classify('TAP BAR 3 · NFC',None,{7},models),('TAP BAR 3',h.CUSTOM_LINE))
        self.assertEqual((h.bucket('2026-02-05','Mes'),h.bucket('2026-02-05','Trimestre'),h.bucket('2026-11-05','Trimestre'),h.bucket('2026-02-05','Año')),
                         ('2026-02','2026-T1','2026-T4','2026'))

    def test_timeline_fills_empty_periods_and_compares_neighbours(self):
        months=h.timeline(ROWS,'Mes')
        self.assertEqual([m['period'] for m in months],['2025-12','2026-01','2026-02'])
        self.assertEqual([m['sold_cents'] for m in months],[10000,0,30000])
        self.assertEqual([m['change_percent'] for m in months],[None,-100.0,None])
        self.assertEqual(months[2]['collected_percent'],50.0)
        self.assertEqual((months[2]['share_percent'],months[2]['cumulative_cents'],months[2]['ticket_cents']),(75.0,40000,15000))
        self.assertIsNone(months[1]['ticket_cents'])
        quarters=h.timeline(ROWS,'Trimestre')
        self.assertEqual([(q['period'],q['change_percent']) for q in quarters],[('2025-T4',None),('2026-T1',200.0)])
        self.assertEqual(h.timeline([],'Año'),[])
        self.assertEqual(h.years(ROWS),['2026','2025'])
        self.assertEqual([r['id'] for r in h.select(ROWS,'2026')],[2,3,4])

    def test_headline_percentages(self):
        s=h.headline(ROWS)
        self.assertEqual((s['sold_cents'],s['count'],s['ticket_cents'],s['balance_cents']),(40000,3,13333,15000))
        self.assertEqual((s['collected_percent'],s['cancelled_percent']),(62.5,25.0))
        # 'A' and 'a' are one client, who bought twice; B once.
        self.assertEqual((s['clients'],s['repeat_percent'],s['top3_percent']),(2,50.0,100.0))
        self.assertEqual(s['origin_percent'],round(100*15000/40000,1))
        self.assertEqual((s['best_month'],s['best_month_cents']),('2026-02',30000))

    def test_shares_products_and_clients(self):
        self.assertEqual([(r['name'],r['count'],r['share_percent']) for r in h.shares(ROWS,'channel')],[('Venta al público',2,75.0),('B2B',1,25.0)])
        self.assertEqual([(r['name'],r['share_percent']) for r in h.shares(ROWS,'origin')],[('Directa',50.0),('Cotización',50.0)])
        products=h.line_shares(ROWS,'product')
        self.assertEqual([(p['name'],p['units'],p['sold_cents'],p['count']) for p in products],[('TAP BAR',3,25000,3),('CIRRUS',2,15000,1)])
        self.assertEqual(len(h.line_shares(ROWS,'product',1)),1)
        clients=h.clients(ROWS)
        self.assertEqual([(c['client'],c['count'],c['sold_cents'],c['share_percent'],c['last']) for c in clients],
                         [('A',2,20000,50.0,'2026-02-20'),('B',1,20000,50.0,'2026-02-05')])
