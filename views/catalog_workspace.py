"""Product discovery, recipe workspace, and reusable component management."""
import streamlit as st
from services import costing,inventory
from services.catalog_view import product_rows,product_label,filter_products,usages
from views.catalog_forms import component_form,product_form,recipe_order_form,variant_form,component_label
from views.photo_forms import photo_panel
from views.costing_forms import recipe_cost_panel,component_cost_form
from views.common import table
from views.catalog_editor import render as editor,prefix_for,store_key
from utils.dates import fmt
from views.common import remembered
from views.emoji import icon_tabs
from views.emoji import tag

def workspace_tabs(labels,key):
    # Keep navigation outside widget cleanup when a product/page is unmounted.
    st.session_state[key]=st.session_state.get(key,st.session_state.get(key+'_memory',labels[0]))
    panels=icon_tabs(labels,key=key,on_change='rerun')
    st.session_state[key+'_memory']=st.session_state[key]
    return panels

def reset_products():
    st.session_state.update(catalog_product_search='',catalog_product_line='Todas',catalog_product_state='Todos')

def open_product(identity,tab='Receta vigente'):
    reset_products()
    st.session_state.update(catalog_workspace='Productos y recetas',catalog_product_selected=identity,catalog_product_view='Ficha')
    st.session_state[f'catalog_product_tabs_{identity}']=tab

def apply_focus(catalog):
    request=st.session_state.pop('catalog_focus_request',None)
    if not request:return
    identity=request['identity']
    if request['kind']=='product':
        product=next((p for p in catalog['products'] if p['id']==identity),None)
        if product:open_product(identity,'Receta vigente' if product['recipe_id'] else 'Editar receta')
    elif request.get('context_product_id'):
        product=next((p for p in catalog['products'] if p['id']==request['context_product_id']),None)
        if not product:return
        current=[r for r in catalog['lines'] if r['recipe_id']==product['recipe_id']]
        key=store_key(product);prefix=prefix_for(product)
        draft=st.session_state.setdefault(key,dict(ids=[r['component_id'] for r in current],quantities={r['component_id']:r['quantity'] for r in current},notes=''))
        if identity not in draft['ids']:draft['ids'].append(identity)
        draft['quantities'].setdefault(identity,1)
        st.session_state[prefix+'_pieces']=draft['ids'][:]
        open_product(product['id'],'Editar receta')
    else:
        st.session_state.update(catalog_workspace='Piezas reutilizables',catalog_piece_search='',catalog_piece_line='Todas',catalog_piece_process='Todos',catalog_piece_usage='Todas',catalog_component_selected=identity)

def render(catalog):
    apply_focus(catalog)
    from views.shell import actions
    with actions():
        with st.popover('Más acciones',icon=':material/more_horiz:'):
            if st.button('Nueva pieza',icon=':material/add:',key='catalog_add_component',width='stretch'):component_form()
            if st.button('Crear pedido desde receta',icon=':material/playlist_add:',key='catalog_order',width='stretch'):recipe_order_form()
        if st.button('Receta de lámpara',icon=':material/light:',key='catalog_create_lamp'):
            from views.origin_forms import lamp_form
            lamp_form()
        if st.button('Nuevo producto',icon=':material/add:',type='primary',key='catalog_add_product'):product_form()
    with st.container(horizontal=True,gap='small',vertical_alignment='center'):
        st.badge(f"{len(catalog['products'])} productos",color='gray')
        st.badge(f"{sum(bool(p['recipe_id']) for p in catalog['products'])} con receta",color='green')
        st.badge(f"{len(catalog['components'])} piezas reutilizables",color='blue')
        with st.popover('Producto, receta y pieza',icon=':material/help_outline:',type='tertiary'):
            st.write('**Producto:** lo que fabricas o vendes, con su variante y fotografía.\n\n**Receta:** componentes y cantidades para una unidad de producto.\n\n**Pieza reutilizable:** un componente que pueden compartir varias recetas.')
            st.caption('Catálogo define lo que necesitas. Inventario registra las unidades físicas disponibles. Publicar una versión conserva la receta de los pedidos existentes.')
    product_tab,piece_tab=workspace_tabs(['Productos y recetas','Piezas reutilizables'],'catalog_workspace')
    if product_tab.open:
        with product_tab:products_panel(catalog)
    if piece_tab.open:
        with piece_tab:components_panel(catalog)

def products_panel(catalog):
    rows=product_rows(catalog)
    with st.container(border=True):
        a,b,c=st.columns([2,1,1])
        search=a.text_input('Buscar producto',key='catalog_product_search',placeholder='Nombre, variante o código',icon=':material/search:',persist_state='session')
        line=b.selectbox('Línea',('Todas','Origen','General'),key='catalog_product_line',persist_state='session')
        state=c.selectbox('Receta',('Todos','Con receta','Sin receta'),key='catalog_product_state',persist_state='session')
        if search or line!='Todas' or state!='Todos':st.button('Limpiar filtros',key='catalog_products_clear',icon=':material/filter_alt_off:',type='tertiary',on_click=reset_products)
    filtered=filter_products(rows,search,line,state)
    st.caption(f'{len(filtered)}/{len(rows)} productos · Las cantidades de receta corresponden a una unidad de producto.')
    if not filtered:
        st.info('No hay productos para esta consulta. Cambia los filtros.' if rows else 'Crea un producto y define sus piezas para publicar tu primera receta.');return
    select_col,view_col=st.columns([2.5,1],vertical_alignment='bottom')
    view=view_col.segmented_control('Visualización de productos',('Ficha','Galería'),default=remembered('catalog_product_view', 'Ficha'),key='catalog_product_view',persist_state='session', format_func=tag) or 'Ficha'
    if view=='Galería':product_gallery(filtered);return
    lookup={p['id']:p for p in filtered}
    if st.session_state.get('catalog_product_selected') not in lookup:st.session_state['catalog_product_selected']=next(iter(lookup))
    pid=select_col.selectbox('Producto',list(lookup),key='catalog_product_selected',format_func=lambda i:product_label(lookup[i]),persist_state='session')
    product_detail(lookup[pid],catalog)

def product_gallery(rows):
    limit=st.session_state.get('catalog_gallery_limit',12)
    for start in range(0,min(limit,len(rows)),3):
        for col,p in zip(st.columns(3),rows[start:min(start+3,limit)]):
            with col,st.container(border=True):
                st.text(p['name']);st.caption(p['variant'] or 'Variante general')
                photo_panel('product',p['id'],p['name'],key=f"catalog_gallery_photo_{p['id']}",width='stretch',gallery=True)
                st.badge(f"Receta v{p['version']}" if p['recipe_id'] else 'Sin receta',color='green' if p['recipe_id'] else 'orange')
                st.caption(f"{p['collection']} · {p['units']} componentes / producto")
                st.button('Abrir ficha',key=f"catalog_gallery_open_{p['id']}",width='stretch',on_click=open_product,args=(p['id'],))
    if len(rows)>limit and st.button('Ver más productos',key='catalog_gallery_more'):
        st.session_state['catalog_gallery_limit']=limit+12;st.rerun()

def product_detail(product,catalog):
    pid=product['id'];current=[r for r in catalog['lines'] if r['recipe_id']==product['recipe_id']]
    versions=[v for v in catalog['versions'] if v['product_id']==pid]
    from services.origin import load
    spec=load()['specs'].get(product['recipe_id']) if product['collection']=='Origen' else None
    with st.container(border=True):
        photo,info=st.columns([1,2])
        with photo:photo_panel('product',pid,product['name'],key='catalog_product_photo',width=240,gallery=True)
        with info:
            st.subheader(product['name']);st.caption(f"{product['variant'] or 'Variante general'} · {product['collection']} · {product['code']}")
            st.badge(f"Receta vigente · v{product['version']}" if current else 'Receta pendiente',color='green' if current else 'orange')
            st.caption(f"{len(current)} referencias · {sum(r['quantity'] for r in current)} componentes por producto · {len(versions)} versiones")
            with st.container(horizontal=True,gap='small'):
                if st.button('Crear pedido de este producto',key='catalog_selected_order',type='primary',icon=':material/playlist_add:',disabled=not current or product['has_retired_components']):recipe_order_form(pid)
                if spec:
                    if st.button('Editar receta',key='catalog_selected_edit',icon=':material/edit_note:'):
                        from views.origin_forms import lamp_form
                        lamp_form(dict(product,origin=spec))
                else:st.button('Editar receta',key='catalog_selected_edit',icon=':material/edit_note:',on_click=open_product,args=(pid,'Editar receta'))
                if st.button('Crear variante',key='catalog_selected_variant',icon=':material/content_copy:'):
                    if spec:
                        from views.origin_forms import lamp_form
                        lamp_form(template=dict(product,origin=spec))
                    else:variant_form(product)
    active,edit,cost,history=workspace_tabs(['Receta vigente','Editar receta','Costos','Historial'],f'catalog_product_tabs_{pid}')
    if active.open:
        with active:
            if product['has_retired_components']:st.info('Esta versión contiene una referencia retirada. Publica una receta con componentes activos antes de crear nuevos pedidos.')
            if current:
                table(current,{'name':'Pieza','material':'Material','variant':'Variante','process':'Proceso','quantity':'Por producto'},label='Receta vigente por unidad de producto')
                version=next(v for v in versions if v['id']==product['recipe_id'])
                st.caption(f"Publicada {fmt(version['created_at'],time=True)}"+(' · '+version['notes'] if version['notes'] else ''))
                st.caption('Esta receta se fija al crear cada pedido. Revisa sus costos antes de estimar utilidad por venta.')
            else:st.info('Aún no hay receta publicada. Abre Editar receta, selecciona piezas y define las cantidades por producto.')
    if edit.open:
        with edit:editor(product,catalog,current)
    if cost.open:
        with cost:
            if product['recipe_id']:recipe_cost_panel(product['recipe_id'],f'catalog_cost_{pid}')
            else:st.info('Publica la primera receta para costear este producto.')
    if history.open:
        with history:history_panel(product,catalog,versions)

def history_panel(product,catalog,versions):
    if not versions:st.info('El historial empieza al publicar la primera receta.');return
    lookup={v['id']:v for v in versions};key=f"catalog_version_{product['id']}"
    if st.session_state.get(key) not in lookup:st.session_state[key]=next(iter(lookup))
    rid=st.selectbox('Versión para consultar',list(lookup),key=key,format_func=lambda i:f"v{lookup[i]['version']} · {fmt(lookup[i]['created_at'])}"+(' · vigente' if i==product['recipe_id'] else ''))
    v=lookup[rid];st.caption(v['notes'] or 'Sin notas de publicación.')
    table([r for r in catalog['lines'] if r['recipe_id']==rid],{'name':'Pieza','material':'Material','variant':'Variante','quantity':'Por producto'},label=f"Receta histórica v{v['version']}")
    linked=[o for o in st.session_state['snapshot']['orders'] if any(i['recipe_id']==rid for i in o['items'])]
    st.caption(f'{len(linked)} pedidos del sistema vinculados a esta versión.')
    if linked:table(linked,{'code':'Pedido','project':'Proyecto','status':'Estado'},label='Pedidos que conservan esta versión de receta')

def components_panel(catalog):
    from models.constants import PROCESSES
    with st.container(border=True):
        search=st.text_input('Buscar pieza, material o variante',key='catalog_piece_search',icon=':material/search:',persist_state='session')
        a,b,c=st.columns(3)
        line=a.selectbox('Línea de pieza',('Todas','Origen','General'),key='catalog_piece_line',persist_state='session')
        process=b.selectbox('Proceso',('Todos',*PROCESSES),key='catalog_piece_process',persist_state='session')
        usage=c.selectbox('Uso en recetas',('Todas','En uso','Sin uso'),key='catalog_piece_usage',persist_state='session')
    all_rows=[dict(r,uses=len(usages(catalog,r['id']))) for r in catalog['components']]
    rows=[r for r in all_rows if search.strip().casefold() in (component_label(r)+' '+r['code']).casefold() and (line=='Todas' or r['collection']==line)
        and (process=='Todos' or r['process']==process) and (usage=='Todas' or bool(r['uses'])==(usage=='En uso'))]
    st.caption(f'{len(rows)}/{len(all_rows)} piezas · Uso contado solo en recetas vigentes.')
    if not rows:st.info('No hay piezas para esta consulta. Cambia los filtros o crea una pieza reutilizable.');return
    left,right=st.columns([1.5,1])
    with left:table(rows,{'name':'Pieza','material':'Material','variant':'Variante','process':'Proceso','uses':'Recetas'},label='Piezas reutilizables y uso en recetas vigentes')
    lookup={c['id']:c for c in rows}
    key='catalog_component_selected'
    if st.session_state.get(key) not in lookup:st.session_state[key]=next(iter(lookup))
    with right,st.container(border=True):
        cid=st.selectbox('Pieza para gestionar',list(lookup),key=key,format_func=lambda i:component_label(lookup[i]),persist_state='session')
        component=lookup[cid]
        st.text(component['name']);st.caption(f"{component['variant'] or 'Variante general'} · {component['collection']} · {component['code']}")
        photo_panel('component',cid,component_label(component),key='catalog_component_photo',width=260,gallery=True)
        profile=costing.component_profile(cid);amount=costing.component_amount(profile['data']) if profile else None
        from services.quotations import money
        st.metric('Costo unitario',money(amount['total_cents']) if amount and amount['total_cents'] is not None else 'Pendiente')
        if st.button('Costear esta pieza',key='catalog_component_cost',icon=':material/calculate:',width='stretch'):component_cost_form(component,profile)
        stocks=[s for s in inventory.load_inventory()['skus'] if s['component_id']==cid]
        st.caption(f"{sum(s['available_stock']+s['available_collection'] for s in stocks)} libres en taller · {sum(s['reserved'] for s in stocks)} reservadas")
        st.page_link('views/collection.py',label='Gestionar existencias',icon=':material/inventory_2:')
    usage_rows=usages(catalog,cid)
    st.subheader('Productos que utilizan esta pieza',icon=':material/account_tree:')
    if not usage_rows:st.caption('Esta pieza todavía no forma parte de una receta vigente.')
    else:
        table(usage_rows,{'product':'Producto','version':'Versión vigente','quantity':'Por producto'},label='Productos que comparten la pieza seleccionada')
        owners={r['product_id']:r for r in usage_rows}
        target=st.selectbox('Producto para consultar',list(owners),key=f'catalog_component_owner_{cid}',format_func=lambda i:owners[i]['product'])
        st.button('Abrir producto',key='catalog_component_open_product',icon=':material/arrow_forward:',on_click=open_product,args=(target,))
    st.caption('Las piezas publicadas se conservan como referencia. Para otro color, material o tamaño, crea una nueva pieza y úsala en otra versión de receta.')
