import altair as alt
import pandas as pd
import streamlit as st
from services import performance as perf
from services.quotations import money
from views.common import table
from views.treasury_components import financial_table

# Fixed series order and colors: Vendido, Cobrado, Gastos keep their color in every period.
SERIES_COLORS=['#2a78d6','#eb6834','#1baf7a']

def pesos(cents):return ('-' if cents<0 else '')+f'${abs(cents)/100:,.0f}'  # Whole pesos fit the card; tables keep cents.
def signed(value,fmt):return None if value is None else ('-' if value<0 else '+')+fmt(abs(value))
def delta(now,before,fmt=lambda v:f'{v:g}'):return signed(now-before,fmt) if now is not None and before is not None else None
def points(now,before):return delta(now,before,lambda v:f'{v:.1f} pts')
def pct(v):return f'{v:.1f}%' if v is not None else '—'
def day(d):return d.strftime('%d/%m/%Y')

# Three views: the period summary, the full sales history and financial health (each its own module).
view=st.segmented_control('Vista de rendimiento',('Resumen','Histórico de ventas','Salud financiera'),default='Resumen',key='perf_view',persist_state='session',
    label_visibility='collapsed',format_func=lambda v:{'Resumen':':material/speed: Resumen del periodo','Histórico de ventas':':material/history: Histórico de ventas',
                                                        'Salud financiera':':material/monitor_heart: Salud financiera'}[v]) or 'Resumen'
if view=='Histórico de ventas':
    from views.performance_history import render
    render();st.stop()
if view=='Salud financiera':
    from views.performance_health import render
    render();st.stop()

name=st.segmented_control('Período',perf.PERIODS,default=perf.PERIODS[0],key='perf_period',persist_state='session',
    width='stretch',label_visibility='collapsed') or perf.PERIODS[0]
data=perf.load()
report=perf.compare(data,*perf.period(name))
cur,old=report['current'],report['prior']
with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
    st.caption(f"Del {day(report['start'])} al {day(report['end'])} · comparado con {day(report['prior_start'])} – {day(report['prior_end'])}")
    with st.popover('Cómo se calcula',icon=':material/info:'):
        st.write('**Vendido** suma ventas activas por fecha de venta. **Cobrado** y **Pagado** usan la fecha del pago; los pagos anulados, las ventas canceladas y la papelera no cuentan. **Gastos** suma gastos activos por su fecha, con IVA.')
        st.write('**Flujo de caja** es cobrado menos pagado en el período: dinero que entró y salió, no utilidad.')
        st.write('**Entregas** cuentan pedidos de clientes cerrados en el período (fecha del despacho o del cierre). Prototipos, impresiones a stock y pedidos cancelados no cuentan. **A tiempo** compara esa fecha con la fecha compromiso; los pedidos sin fecha compromiso no entran al porcentaje.')
        st.write('**Piezas producidas** y **horas de máquina** usan la fecha en que terminó cada lote. **Rechazo** = piezas rechazadas en fallas / (producidas + rechazadas).')

st.subheader('Comercial y caja',icon=':material/point_of_sale:')
a,b,c,d=st.columns(4)
a.metric('Vendido',pesos(cur['sold_cents']),delta(cur['sold_cents'],old['sold_cents'],pesos),border=True,
    help=f"{money(cur['sold_cents'])} · {cur['sales_count']} ventas activas · ticket promedio {money(cur['ticket_cents']) if cur['ticket_cents'] is not None else '—'}")
b.metric('Cobrado',pesos(cur['collected_cents']),delta(cur['collected_cents'],old['collected_cents'],pesos),border=True,help=money(cur['collected_cents']))
c.metric('Gastos',pesos(cur['expenses_cents']),delta(cur['expenses_cents'],old['expenses_cents'],pesos),delta_color='inverse',border=True,help=money(cur['expenses_cents'])+' con IVA')
d.metric('Flujo de caja',pesos(cur['cash_cents']),delta(cur['cash_cents'],old['cash_cents'],pesos),border=True,
    help=f"Cobrado {money(cur['collected_cents'])} − pagado {money(cur['paid_out_cents'])}")

st.subheader('Taller y entregas',icon=':material/precision_manufacturing:')
a,b,c,d=st.columns(4)
a.metric('Entregados',cur['delivered'],delta(cur['delivered'],old['delivered']),border=True,
    help='Pedidos de clientes entregados'+(f" · promedio {cur['lead_days']:g} días desde que se creó el pedido" if cur['lead_days'] is not None else ''))
b.metric('A tiempo',pct(cur['on_time_percent']),points(cur['on_time_percent'],old['on_time_percent']),border=True,
    help=f"{cur['on_time']} de {cur['promised']} pedidos con fecha compromiso")
c.metric('Piezas',cur['pieces'],delta(cur['pieces'],old['pieces']),border=True,
    help=f"{cur['lots']} lotes terminados · {cur['machine_hours']:g} h de máquina")
d.metric('Rechazo',pct(cur['reject_percent']),points(cur['reject_percent'],old['reject_percent']),delta_color='inverse',border=True,
    help=f"{cur['rejected']} piezas rechazadas en fallas registradas")
if cur['untimed_lots']:
    st.caption(f"{cur['untimed_lots']} lotes terminados sin tiempo completo registrado no suman horas de máquina.")

st.subheader('Últimos 6 meses',icon=':material/monitoring:')
trend=perf.months(data,report['end'])
a,b=st.columns([3,2])
with a:
    order=['Vendido','Cobrado','Gastos']
    frame=pd.DataFrame([{'Mes':r['month'],'Serie':s,'MXN':r[f]/100} for r in trend for s,f in zip(order,('sold_cents','collected_cents','expenses_cents'))])
    # Altair, so the money axis starts at zero (the native chart padded it below zero).
    st.altair_chart(alt.Chart(frame).mark_bar(cornerRadiusTopLeft=4,cornerRadiusTopRight=4).encode(
        x=alt.X('Mes:N',title=None),xOffset=alt.XOffset('Serie:N',sort=order),
        y=alt.Y('MXN:Q',title='MXN',scale=alt.Scale(domainMin=0)),
        color=alt.Color('Serie:N',sort=order,scale=alt.Scale(domain=order,range=SERIES_COLORS),legend=alt.Legend(orient='bottom',title=None)),
        tooltip=['Mes','Serie',alt.Tooltip('MXN:Q',format='$,.2f')]),width='stretch')
with b:
    frame=pd.DataFrame([{'Mes':r['month'],'Piezas producidas':r['pieces']} for r in trend])
    st.bar_chart(frame,x='Mes',y='Piezas producidas',color=SERIES_COLORS[0],y_label='Piezas',x_label='',
        alt='Piezas producidas por mes en los últimos seis meses')
with st.expander('Ver tabla mensual',icon=':material/table:'):
    financial_table(trend,{'month':'Mes','sold_cents':'Vendido MXN','collected_cents':'Cobrado MXN','expenses_cents':'Gastos MXN','pieces':'Piezas producidas','delivered':'Pedidos entregados'},
        ['sold_cents','collected_cents','expenses_cents'],label='Indicadores por mes')

a,b=st.columns([3,2])
with a:
    st.subheader('Por máquina',icon=':material/print:')
    table([dict(r,use=pct(r['use_percent']),rejection=pct(r['reject_percent'])) for r in perf.by_machine(data,report['start'],report['end'])],
        {'code':'Máquina','lots':'Lotes','pieces':'Piezas','hours':'Horas','use':'Uso (24 h)','rejected':'Rechazos','rejection':'Rechazo'},label='Rendimiento por máquina en el período')
    st.caption('Uso = horas de impresión registradas sobre las 24 h de cada día del período.')
with b:
    st.subheader('Clientes principales',icon=':material/group:')
    clients=perf.top_clients(data,report['start'],report['end'])
    financial_table([dict(r,share=pct(r['share_percent'])) for r in clients],{'client':'Cliente','count':'Ventas','sold_cents':'Vendido MXN','share':'Participación'},
        ['sold_cents'],label='Clientes con más ventas en el período')
