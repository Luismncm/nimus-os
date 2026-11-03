"""Histórico de ventas: every sale by period, and the percentages that say where the money comes from."""
import pandas as pd
import streamlit as st
from services import sales_history as history
from services.quotations import money
from utils.csv_export import amount, csv_bytes

CHART_COLOR='#2a78d6'
PLURAL={'Mes':'mes','Trimestre':'trimestre','Año':'año'}

def pct(v):return f'{v:.1f}%' if v is not None else '—'
def pesos(cents):return f'${cents/100:,.0f}' if cents is not None else '—'
def day(v):return f'{v[8:10]}/{v[5:7]}/{v[:4]}' if v else '—'

def share_table(rows,columns,*,label,money_fields=('sold_cents','cumulative_cents','ticket_cents')):
    """Amounts in pesos, shares as a bar from 0 to 100 %, changes with their sign."""
    if not rows:
        st.caption('Sin ventas en esta selección.');return
    frame=pd.DataFrame(rows).reindex(columns=list(columns))
    config={}
    for field,title in columns.items():
        if field in money_fields:
            frame[field]=frame[field].map(lambda v:v/100 if pd.notna(v) else None)
            config[title]=st.column_config.NumberColumn(title,format='dollar')
        elif field in ('share_percent','collected_percent'):
            config[title]=st.column_config.ProgressColumn(title,min_value=0,max_value=100,format='%.1f%%')
        elif field=='change_percent':
            # Numeric, so the first period (nothing to compare with) shows empty instead of None.
            frame[field]=pd.to_numeric(frame[field])
            config[title]=st.column_config.NumberColumn(title,format='%+.1f%%')
    st.dataframe(frame.rename(columns=columns),hide_index=True,width='stretch',column_config=config,alt=label)

def render():
    rows=history.load()
    if not rows:
        st.info('Registra ventas en Ventas y cobranza para ver su histórico.');return
    a,b=st.columns([3,2],vertical_alignment='bottom')
    years=history.years(rows)
    year=a.segmented_control('Año',('Todo',*years),default='Todo',key='hist_year',persist_state='session') or 'Todo'
    grouping=b.segmented_control('Agrupar por',history.GROUPINGS,default='Mes',key='hist_grouping',persist_state='session') or 'Mes'
    chosen=history.select(rows,None if year=='Todo' else year)
    h=history.headline(chosen)
    if not h['count']:
        st.info('Sin ventas activas en este año.');return
    st.caption(f"{h['count']} ventas activas del {day(h['first_sale'])} al {day(h['last_sale'])} · mejor mes: {h['best_month']} con {money(h['best_month_cents'])}")

    a,b,c,d=st.columns(4)
    a.metric('Vendido',pesos(h['sold_cents']),border=True,help=money(h['sold_cents'])+' en ventas activas, con IVA cuando la venta lo incluye')
    b.metric('Ventas',h['count'],border=True,help=f"{pct(h['cancelled_percent'])} de las ventas registradas se cancelaron y no suman")
    c.metric('Ticket promedio',pesos(h['ticket_cents']),border=True)
    d.metric('Saldo por cobrar',pesos(h['balance_cents']),border=True,help='Lo que falta cobrar de estas ventas')
    a,b,c,d=st.columns(4)
    a.metric('Cobrado',pct(h['collected_percent']),border=True,help='Parte del monto vendido que ya se cobró')
    b.metric('Clientes recurrentes',pct(h['repeat_percent']),border=True,help=f"Clientes con dos o más compras, de {h['clients']} clientes")
    c.metric('Top 3 clientes',pct(h['top3_percent']),border=True,help='Parte de la venta que viene de los tres clientes que más compran: entre más alta, más depende el negocio de pocos clientes')
    d.metric('Colección Origen',pct(h['origin_percent']),border=True,help='Parte del importe de partidas que son lámparas de Colección Origen')

    timeline=history.timeline(chosen,grouping)
    st.subheader(f'Vendido por {PLURAL[grouping]}',icon=':material/bar_chart:')
    st.bar_chart(pd.DataFrame([{'Periodo':r['period'],'Vendido':r['sold_cents']/100} for r in timeline]),x='Periodo',y='Vendido',
        color=CHART_COLOR,x_label='',y_label='MXN',alt=f'Vendido por {PLURAL[grouping]}')
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.caption('Variación: contra el periodo anterior. Cobrado: parte ya pagada de las ventas de ese periodo.')
        st.download_button('Exportar CSV',lambda:csv_bytes(['Periodo','Ventas','Vendido MXN','Ticket MXN','Cobrado %','Variación %','% del total','Acumulado MXN'],
            ([r['period'],r['count'],amount(r['sold_cents']),amount(r['ticket_cents']),r['collected_percent'],r['change_percent'],r['share_percent'],amount(r['cumulative_cents'])] for r in timeline)),
            file_name='NIMUS_historico_ventas.csv',mime='text/csv',icon=':material/download:',on_click='ignore')
    share_table(list(reversed(timeline)),{'period':'Periodo','count':'Ventas','sold_cents':'Vendido','ticket_cents':'Ticket','collected_percent':'Cobrado',
        'change_percent':'Variación','share_percent':'% del total','cumulative_cents':'Acumulado'},label='Histórico de ventas por periodo')

    st.subheader('De dónde viene la venta',icon=':material/donut_large:')
    a,b,c=st.columns(3)
    with a:
        st.caption('Por línea · importe de partidas')
        share_table(history.line_shares(chosen,'line'),{'name':'Línea','share_percent':'%','count':'Ventas'},label='Venta por línea de producto')
    with b:
        st.caption('Por canal')
        share_table(history.shares(chosen,'channel'),{'name':'Canal','share_percent':'%','count':'Ventas'},label='Venta por canal')
    with c:
        st.caption('Por origen')
        share_table(history.shares(chosen,'origin'),{'name':'Origen','share_percent':'%','count':'Ventas'},label='Venta directa o desde cotización')

    a,b=st.columns(2)
    with a:
        st.subheader('Productos más vendidos',icon=':material/light:')
        share_table(history.line_shares(chosen,'product',10),{'name':'Producto','units':'Unidades','sold_cents':'Importe','share_percent':'%'},label='Productos más vendidos')
        st.caption('Importe de partidas antes de descuento e IVA. Los colores de un mismo modelo se suman; las partidas de Origen capturadas sin modelo aparecen como «Origen · sin modelo».')
    with b:
        st.subheader('Clientes principales',icon=':material/group:')
        share_table([dict(r,last=day(r['last'])) for r in history.clients(chosen,10)],{'client':'Cliente','count':'Ventas','sold_cents':'Vendido','share_percent':'%','last':'Última compra'},label='Clientes con más ventas')
