import copy
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import notifications as n,sales,expenses,quotations
from tests import test_restock as fixture
from utils.dates import now


class NotificationSummaryTest(unittest.TestCase):
    at=datetime(2026,10,16,12)

    def build(self,sales=(),expenses=(),orders=(),attention=(),events=(),supplies=()):
        with patch.object(n,'daily_board',return_value=dict(orders=list(orders),attention=list(attention))):
            return n.center({},list(supplies),list(events),list(sales),list(expenses),at=self.at)

    def sale(self,identity=1,**kw):
        return dict(dict(id=identity,code=f'VEN-{identity}',client='Cliente',project='Origen',
            status='Activa',balance_cents=12000,due_on='2026-10-15'),**kw)

    def test_financial_balances_exclude_paid_cancelled_deleted_and_keep_partials(self):
        rows=[self.sale(),self.sale(2,balance_cents=0),self.sale(3,status='Cancelada'),
            self.sale(4,deleted_at='2026-10-16'),self.sale(5,balance_cents=2500)]
        data=self.build(sales=rows,expenses=[dict(id=1,code='GAS-1',concept='Material',supplier='Proveedor',status='Activo',balance_cents=900,due_on='')])
        self.assertEqual((data['total'],data['counts']['Cobros'],data['to_collect'],data['to_pay']),(3,2,14500,900))

    def test_dates_sort_overdue_today_undated_future_and_priority_filter(self):
        rows=[self.sale(1,due_on='2026-10-20'),self.sale(2,due_on=''),self.sale(3,due_on='2026-10-16'),self.sale(4)]
        data=self.build(sales=rows)
        self.assertEqual([r['record_id'] for r in data['items']],[4,3,2,1])
        self.assertEqual(data['priority_count'],2)
        self.assertIn('Sin fecha',data['items'][2]['label'])
        self.assertEqual(len(n.select(data,priority=True)),2)
        self.assertEqual(len(n.select(data,'Cobros','cliente')),4)
        self.assertEqual(n.select(data,'Pagos'),[])

    def test_order_grouping_and_packing_stage(self):
        order=dict(id=1,code='ORD-1',client='Ana',project='Lámpara',deadline='2026-10-16',status='Listo',stages={'packing':{'checked_at':None}})
        event=dict(record_kind='Pedido',record_id=1,state='Pendiente',score=80,kind='Entrega en riesgo')
        data=self.build(orders=[order],attention=[dict(order=order,reasons=['Entrega hoy','Producción lista'])],events=[event,event])
        self.assertEqual(data['total'],1)
        self.assertIn('Por empacar',data['items'][0]['detail'])
        order['stages']['packing']['checked_at']='2026-10-16'
        data=self.build(orders=[order],attention=[dict(order=order,reasons=['Producción lista'])])
        self.assertIn('Por entregar',data['items'][0]['detail'])

    def test_supplies_negative_first_and_operations_dedup_seen_hidden(self):
        supply=dict(id=1,name='Cable',variant='',attention=True,critical=True,score=100,net=-3,minimum=2,replenish=6)
        event=dict(record_kind='Trabajo',record_id=4,state='Pendiente',score=80,kind='Cruce',detail='JOB-4',severity='red')
        material=dict(event,record_kind='Material',record_id='pla',severity='orange',score=30)
        data=self.build(supplies=[supply],events=[event,event,dict(event,record_id=5,state='Visto'),material])
        self.assertEqual((data['total'],data['priority_count']),(3,2))
        self.assertEqual((data['counts']['Insumos'],data['counts']['Producción']),(2,1))
        self.assertEqual(data['items'][0]['label'],'Saldo negativo')
        self.assertEqual(self.build()['total'],0)


class NotificationUITest(unittest.TestCase):
    setUp=fixture.RestockTest.setUp
    publish=fixture.RestockTest.publish
    order=fixture.RestockTest.order

    def app(self):return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    def clean(self,a):self.assertFalse(a.exception,[e.message for e in a.exception])
    def fingerprint(self):
        with db.connect() as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {t:[tuple(r) for r in c.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}
    def finance(self):
        today=now().date()
        payload=dict(quotations.defaults(),client='Cliente aviso',project='Lámpara',lines=[dict(description='Origen',quantity=1,price=100,produce=False)])
        sid=sales.create_direct(payload,today,request_key='notice-sale',due_on=today)
        expense=dict(expenses.defaults(),concept='Filamento',supplier='Proveedor aviso',amount=300)
        eid=expenses.create(expense,request_key='notice-expense')
        return sid,eid

    def test_entry_is_first_and_drawer_filters_without_writing_records(self):
        self.order(2);self.finance();before=self.fingerprint();a=self.app();self.clean(a)
        self.assertEqual(a.sidebar.button[0].key,'notifications_open')
        a.sidebar.button(key='notifications_open').click().run();self.clean(a)
        a.button_group(key='notifications_category').set_value('Cobros').run();self.clean(a)
        self.assertEqual(len([b for b in a.button if (b.key or '').startswith('notification_open_')]),1)
        a.text_input(key='notifications_search').set_value('no coincide').run();self.clean(a)
        self.assertTrue(any('Sin pendientes' in s.value for s in a.success))
        self.assertEqual(self.fingerprint(),before)

    def test_record_navigation_sales_expenses_orders_and_restock(self):
        sid,eid=self.finance();oid=self.order(2)
        cases=[(f'Venta:{sid}','open_sale_id',sid),(f'Gasto:{eid}','open_expense_id',eid),
            (f'Pedido:{oid}','open_order_id',oid),(f"Insumo:{self.supplies['cable_id']}",'collection_workspace','Insumos y consumibles')]
        before=self.fingerprint()
        for identity,state,value in cases:
            with self.subTest(identity=identity):
                a=self.app();a.sidebar.button(key='notifications_open').click().run();self.clean(a)
                group={'Venta':'Cobros','Gasto':'Pagos','Pedido':'Pedidos','Insumo':'Insumos'}[identity.split(':')[0]]
                a.button_group(key='notifications_category').set_value(group).run();self.clean(a)
                a.button(key='notification_open_'+identity).click().run();self.clean(a)
                self.assertEqual(a.session_state[state],value)
        self.assertEqual(self.fingerprint(),before)

    def test_financial_notification_disappears_after_actual_payment(self):
        sid,eid=self.finance();sale=sales.get_sale(sid)
        sales.record_payment(sid,sale['balance_cents']/100,now().date(),'Efectivo','Liquidación',request_key='notice-payment',expected_revision=sale['revision'],expected_quote_revision=sale['quote_revision'])
        data=n.load()
        self.assertEqual(data['counts']['Cobros'],0)
        self.assertEqual(data['counts']['Pagos'],1)
