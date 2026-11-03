import streamlit as st
from services import recipes,costing,sales
from services.quotations import money
from views.common import table
from views.costing_forms import recipe_cost_panel,sale_cost_panel
from views.emoji import icon_tabs

recipes_tab,sales_tab=icon_tabs(['Recetas y costos','Utilidad por venta'],key='cost_tabs',on_change='rerun')
with recipes_tab:
    catalog=recipes.load_catalog()
    products={p['id']:p for p in catalog['products'] if p['recipe_id']}
    if products:
        pid=st.selectbox('Receta a costear',list(products),format_func=lambda i:products[i]['name']+' · '+products[i]['variant'],key='cost_product')
        recipe_cost_panel(products[pid]['recipe_id'],'cost_recipe')
    else:st.info('Publica una receta desde Catálogo y recetas para costearla.')
    st.page_link('views/catalog.py',label='Crear o modificar receta',icon=':material/menu_book:')
with sales_tab:
    a,b=st.columns(2)
    search=a.text_input('Buscar venta o cliente',key='cost_sales_search')
    status=b.selectbox('Estado del costeo',('Todos','Completo','Pendiente','Revisar cambios'),key='cost_sales_status')
    rows=[]
    for sale in sales.list_sales():
        if sale['status']!='Activa':continue
        if search.casefold() not in f"{sale['code']} {sale['client']} {sale['project']}".casefold():continue
        m=costing.sale_margin(sale['id']);state='Revisar cambios' if m['stale'] else 'Completo' if m['complete'] else 'Pendiente'
        if status!='Todos' and state!=status:continue
        rows.append(dict(sale,net=m['net_revenue_cents'],cost=m['cost_cents'],profit=m['profit_cents'],state=state))
    complete=[r for r in rows if r['state']=='Completo']
    with st.container(horizontal=True):
        st.metric('Ventas con costo completo',f'{len(complete)} / {len(rows)}',border=True)
        st.metric('Venta neta con costo completo',money(sum(r['net'] for r in complete)),border=True)
        st.metric('Utilidad bruta · costos completos',money(sum(r['profit'] for r in complete)) if complete else 'Pendiente',border=True)
    st.caption('El total de utilidad abarca únicamente ventas con todas sus partidas costeadas. Las ventas canceladas y en papelera se excluyen. La selección muestra todas las fechas.')
    table([dict(r,net=money(r['net']),cost=money(r['cost']) if r['cost'] is not None else 'Pendiente',profit=money(r['profit']) if r['profit'] is not None else 'Pendiente') for r in rows],
        {'code':'Venta','client':'Cliente','net':'Venta neta MXN','cost':'Costo MXN','profit':'Utilidad bruta MXN','state':'Costeo'},label='Cobertura de costos y utilidad bruta por venta')
    if rows:
        by_id={r['id']:r for r in rows}
        sid=st.selectbox('Venta a costear',list(by_id),format_func=lambda i:by_id[i]['code']+' · '+by_id[i]['client'],key='cost_sale')
        sale_cost_panel(sid)
