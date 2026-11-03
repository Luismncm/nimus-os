"""Salud financiera: cash runway, coverage, margin and break-even, each with a plain state (Sano / Atención / Crítico)."""
import altair as alt
import pandas as pd
import streamlit as st
from services import financial_health as fh
from services.quotations import money
from utils.dates import now

# Fixed series order and colors, the same as the summary: money in first, then partner money, then money out.
SERIES=('Cobrado','Aportaciones del socio','Pagado')
SERIES_COLORS=['#2a78d6','#eda100','#eb6834']
STATE={fh.HEALTHY:('green',':material/check_circle:'),fh.WATCH:('orange',':material/warning:'),fh.CRITICAL:('red',':material/error:')}

def pesos(cents):return '—' if cents is None else ('-' if cents<0 else '')+f'${abs(cents)/100:,.0f}'
def pct(v):return f'{v:.1f}%' if v is not None else '—'

def badge(state):
    if state:
        color,icon=STATE[state];st.badge(state,color=color,icon=icon)
    else:st.badge('Sin datos',color='gray',icon=':material/help:')

def card(col,label,value,state=False,help=None,note=None):
    """A metric with its state in words and icon, never by color alone; figures without a state carry a short note instead."""
    with col.container(border=True,gap='xsmall'):
        st.metric(label,value,help=help)
        if state is not False:badge(state)
        elif note:st.caption(note)

def plain(text):return text.replace('$','\\$')  # Markdown would read two $ as a formula.

def render():
    today=now().date()
    a,b=st.columns([3,2],vertical_alignment='bottom')
    count=b.segmented_control('Promedio de',fh.WINDOWS,default=fh.WINDOWS[0],key='health_window',persist_state='session',
        format_func=lambda n:f'Últimos {n} meses') or fh.WINDOWS[0]
    data=fh.load()
    h=fh.health(data,today,count)
    a.caption(f"Promedios de {h['months'][0]} a {h['months'][-1]}: meses completos; el mes en curso no entra.")

    color,icon=STATE[h['overall']]
    with st.container(border=True):
        st.badge(f"Estado general: {h['overall']}",color=color,icon=icon)
        st.write(h['verdict'])

    avg=h['average'];tones=h['tones']
    st.subheader('Caja',icon=':material/account_balance_wallet:')
    a,b,c,d=st.columns(4)
    card(a,'Caja disponible',pesos(h['cash_cents']),help='Suma de las cuentas activas'+(' · estimada con los movimientos registrados: concilia en Tesorería' if data['cash_estimated'] else ' · conciliada'),
         note='Estimada con movimientos' if data['cash_estimated'] else 'Conciliada')
    card(b,'Consumo de caja al mes',pesos(max(0,h['burn_cents'])) if h['burn_cents']>0 else 'Sin consumo',
         help=f"Pagado {money(avg['paid'])} − cobrado {money(avg['collected'])} en promedio mensual",note='Pagado menos cobrado')
    card(c,'Meses de caja',f"{h['runway_months']:g}" if h['runway_months'] is not None else 'Sin límite',tones['runway'],
         help='Cuántos meses alcanza la caja al ritmo de consumo actual, sin nuevas aportaciones. Sano: 6 o más; atención: de 3 a 6.')
    card(d,'Dinero del socio',pct(h['partner_share_percent']),tones['partner'],
         help=f"Parte del dinero que entra a las cuentas que viene de aportaciones ({money(max(0,avg['injected']))} al mes). Sano: 20% o menos; atención: hasta 50%.")

    st.subheader('Operación',icon=':material/query_stats:')
    a,b,c,d=st.columns(4)
    card(a,'Venta al mes',pesos(avg['sold']),help='Promedio vendido en ventas activas',note='Promedio mensual')
    card(b,'Gasto al mes',pesos(avg['spent']),help=f"Promedio de gastos activos, sin los de Desarrollo / único ({money(avg['one_time'])} al mes en el periodo)",note='Sin gastos únicos')
    card(c,'Cobertura',pct(h['coverage_percent']),tones['coverage'],help='Qué parte del gasto mensual cubren las ventas. Sano: 100% o más; atención: desde 60%.')
    card(d,'Margen bruto',pct(h['margin_percent']),tones['margin'],
         help=f"De {data['margin']['costed']} de {data['margin']['sales']} ventas con costo completo, sin IVA. Sano: 40% o más; atención: desde 25%.")

    st.subheader('Punto de equilibrio',icon=':material/balance:')
    with st.container(border=True):
        if h['break_even_cents'] is None:
            st.info('Completa el costeo de algunas ventas en Costos y utilidad para calcular el margen y el punto de equilibrio.')
        else:
            st.write(plain(f"Para cubrir **{money(avg['spent'])}** de gasto mensual con un margen de **{pct(h['margin_percent'])}**, "
                     f"necesitas vender **{money(h['break_even_cents'])} al mes**"
                     +(f": **{h['break_even_multiple']:g} veces** tu venta promedio actual." if h['break_even_multiple'] else '.')))
            reached=min(1.0,avg['sold']/h['break_even_cents']) if h['break_even_cents'] else 0
            st.progress(reached,text=f"Venta actual: {pct(100*avg['sold']/h['break_even_cents'])} del punto de equilibrio")
            st.caption('Aproximado: supone que cada venta deja el margen bruto promedio y que el gasto mensual se mantiene.')

    st.subheader('Entradas y salidas de dinero',icon=':material/swap_vert:')
    rows=fh.trend(data,today)
    frame=pd.DataFrame([{'Mes':r['month'],'Serie':s,'MXN':max(0,r[f])/100} for r in rows for s,f in zip(SERIES,('collected','injected','paid'))])
    st.altair_chart(alt.Chart(frame).mark_bar(cornerRadiusTopLeft=4,cornerRadiusTopRight=4).encode(
        x=alt.X('Mes:N',title=None),xOffset=alt.XOffset('Serie:N',sort=list(SERIES)),
        y=alt.Y('MXN:Q',title='MXN',scale=alt.Scale(domainMin=0)),
        color=alt.Color('Serie:N',sort=list(SERIES),scale=alt.Scale(domain=list(SERIES),range=SERIES_COLORS),legend=alt.Legend(orient='bottom',title=None)),
        tooltip=['Mes','Serie',alt.Tooltip('MXN:Q',format='$,.2f')]),width='stretch')
    st.caption('Cobrado: pagos de clientes. Aportaciones: depósitos del socio menos reembolsos. Pagado: pagos de gastos desde las cuentas. Las compras que el socio pagó directamente no pasan por las cuentas.')

    st.subheader('Obligaciones y capital',icon=':material/handshake:')
    a,b,c,d=st.columns(4)
    card(a,'Por cobrar',pesos(h['receivable_cents']),help='Saldo pendiente de ventas activas',note='De clientes')
    card(b,'Por pagar',pesos(h['payable_cents']),help='Saldo pendiente de gastos activos',note='A proveedores')
    card(c,'Cobranza',pct(h['collection_percent']),tones['collection'],help='Parte de todo lo vendido que ya se cobró. Sano: 85% o más; atención: desde 70%.')
    card(d,'Capital del socio',pesos(h['partner_cents']),help='Aportaciones acumuladas (depósitos y compras pagadas por el socio) menos reembolsos',note='Aportado neto')
    if h['liquidity'] is not None:
        st.caption(f"Caja más por cobrar = {h['liquidity']:g} veces lo que se debe a proveedores.")

    notes=[]
    if data['unreconciled']:notes.append(('La caja es una estimación: '+', '.join(data['unreconciled'])+' sin saldo conciliado.','views/treasury.py','Conciliar en Tesorería'))
    if data['undated']:notes.append((f"{data['undated']} movimientos de dinero sin fecha no entran a los promedios.",'views/treasury.py','Revisar movimientos'))
    pending=data['margin']['sales']-data['margin']['costed']
    if pending:notes.append((f'{pending} ventas sin costo completo: el margen sale de las otras {data["margin"]["costed"]}.','views/costs.py','Completar costeo'))
    if data['unclassified']:notes.append((f"{data['unclassified']} gastos sin clasificar.",'views/expenses.py','Clasificar gastos'))
    if notes:
        with st.expander(f'Qué tan confiables son estas cifras · {len(notes)} pendientes',icon=':material/fact_check:'):
            for text,page,label in notes:
                with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
                    st.write(text);st.page_link(page,label=label,icon=':material/arrow_forward:')
