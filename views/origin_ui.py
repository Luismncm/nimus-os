"""One operational workspace for lamps, shared parts, supplies and future articles."""
import streamlit as st
from services import origin,recipes,inventory,costing,lamp_options
from views.common import table,perform,picks
from views.catalog_workspace import workspace_tabs,open_product
from views.catalog_forms import recipe_order_form,product_form,component_label
from views.origin_forms import lamp_form,base_form,origin_component_form,receipt_form
from views.photo_forms import photo_panel
from views.costing_forms import recipe_cost_panel,component_cost_form
from views.navigation import open_order
from views import origin_builder
from views import origin_cart
from services import photos
from views.emoji import tag

def stock_rows(data,ledger):
    result=[]
    from services import restock
    supplies={r['id']:r for r in restock.rows()}
    base_models={cid:b['model_name'] for b in data['bases'] for cid in (b['base_id'],b['cap_id'],b['lid_id'])}
    for c in sorted(data['components'],key=lambda c:(origin.ROLES.index(c['role']),c['shape'],c['color'],c['variant'])):
        skus=[s for s in ledger['skus'] if s['component_id']==c['id']]
        signal=supplies.get(c['id'],{})
        result.append(dict(c,model=c['shape'] or base_models.get(c['id'],''),free=sum(s['available_stock']+s['available_collection'] for s in skus),reserved=sum(s['reserved'] for s in skus),physical=sum(s['stock']+s['unassigned'] for s in skus),net=signal.get('net'),minimum=signal.get('minimum'),restock_state=signal.get('state','')))
    return result

def render():
    from views.inventory_ui import take_focus,reset_filters
    data=origin.load();ledger=inventory.load_inventory()
    legacy=st.session_state.get('origin_workspace',st.session_state.get('origin_workspace_memory'))
    if legacy in ('Lámparas','Pantallas y bases','Insumos'):
        st.session_state['origin_workspace']='Recetas' if legacy=='Lámparas' else 'Componentes'
        if legacy=='Insumos':st.session_state['origin_definition_group']='Insumos'
    if pending:=st.session_state.pop('origin_focus',None):
        panel='Recetas' if pending['panel']=='Lámparas' else pending['panel']
        st.session_state['origin_workspace']=panel
        if panel=='Recetas':st.session_state['origin_last_product']=None
        if pending.get('group'):st.session_state['origin_definition_group']=pending['group']
        if pending['panel']=='Inventario':
            # Components are focused by their catalog id; the inventory selects their inventory line.
            st.session_state['origin_inventory_view']='Piezas'
            sku=next((s['id'] for s in ledger['skus'] if s['component_id']==pending['identity']),None)
            if sku is not None:reset_filters('origin_stock');st.session_state['origin_stock_selected']=sku
        elif pending['identity'] is not None:
            st.session_state['origin_product' if panel=='Recetas' else 'origin_inventory_selected']=pending['identity']
    if focus:=take_focus(ledger,origin=True):
        reset_filters('origin_stock')
        st.session_state.update(origin_workspace='Inventario',origin_stock_selected=focus[0],
                                origin_inventory_view=focus[1] if focus[1] in INVENTORY_VIEWS else 'Piezas')
    if request:=st.session_state.pop('origin_builder_request',None):
        origin_builder.apply_request(data,request);st.session_state['origin_workspace']='Crear receta'
    if request:=st.session_state.pop('origin_cart_request',None):
        origin_cart.initialize(data,request);st.session_state['origin_workspace']='Venta y pedido'
    from views.shell import actions
    with actions():
        if st.session_state.get('origin_workspace')!='Crear receta' and st.button('Continuar receta' if origin_builder.STORE in st.session_state else 'Crear receta',key='origin_new_lamp',icon=':material/add:'):
            if origin_builder.STORE in st.session_state:origin_builder.continue_builder()
            else:lamp_form()
        if st.button('Crear pedido',key='origin_new_order',type='primary',icon=':material/playlist_add:'):recipe_order_form()
    lamps=[p for p in data['products'] if p['origin'] and not p['has_retired_components']]
    with st.container(horizontal=True):
        st.badge(f"{len(data['shade_models'])} modelos de pantalla",color='blue')
        st.badge(f"{len(data['base_models'])} modelo de base",color='gray')
        st.badge(f"{len(data['bases'])} colores de base",color='gray')
        st.badge(f"{len(lamps)} combinaciones de receta",color='green')
    panels=workspace_tabs(['Recetas','Venta y pedido','Crear receta','Componentes','Inventario','Pedidos','Otros artículos'],'origin_workspace')
    functions=(lamps_panel,origin_cart.render,origin_builder.render,definitions_panel,inventory_panel,orders_panel,articles_panel)
    for panel,fn in zip(panels,functions):
        if panel.open:
            with panel:fn(data,ledger)

def lamps_panel(data,ledger):
    st.caption('Elige modelo y variante de color. Su receta define los componentes necesarios para cada pedido.')
    lamps=[p for p in data['products'] if p['origin'] and not p['has_retired_components']]
    bases={b['id']:b for b in data['bases']};components={c['id']:c for c in data['components']}
    requested=st.session_state.get('origin_product')
    if requested!=st.session_state.get('origin_last_product'):
        p=next((p for p in lamps if p['id']==requested),None)
        if p:st.session_state.update(origin_model_filter=p['origin']['model'],origin_color_filter=bases[p['origin']['base_set_id']]['color'])
    models=data['shade_models'];colors=sorted({b['color'] for b in data['bases']})
    if not models or not colors:
        st.info('Agrega un modelo de pantalla y un color de base en Componentes.');return
    for key,choices in (('origin_model_filter',models),('origin_color_filter',colors)):
        if st.session_state.get(key) not in choices:st.session_state[key]=choices[0]
    model=st.segmented_control('Modelo de lámpara',models,key='origin_model_filter',width='stretch',wrap=True) if len(models)<=5 else st.selectbox('Modelo de lámpara',models,key='origin_model_filter')
    color=st.segmented_control('Variante de color',colors,key='origin_color_filter',width='stretch',wrap=True) if len(colors)<=5 else st.selectbox('Variante de color',colors,key='origin_color_filter')
    selected=[p for p in lamps if p['origin']['model']==model and bases[p['origin']['base_set_id']]['color']==color]
    if not selected:
        st.info('Este modelo de pantalla todavía no tiene una lámpara publicada con el color seleccionado. Puedes crear su receta completa.')
        shade=next((c['id'] for c in components.values() if c['role']=='Pantalla' and c['shape']==model),None)
        bid=next((b['id'] for b in bases.values() if b['color']==color),None)
        if st.button('Crear esta combinación',key='origin_create_combination',type='primary',icon=':material/add:'):
            lamp_form(shade_id=shade,base_set_id=bid)
        return
    lookup={p['id']:p for p in selected}
    if st.session_state.get('origin_product') not in lookup:st.session_state['origin_product']=next(iter(lookup))
    pid=st.selectbox('Especificación de receta',list(lookup),key='origin_product',format_func=lambda i:lookup[i]['name']) if len(lookup)>1 else next(iter(lookup))
    if len(lookup)==1:st.session_state['origin_product']=pid
    st.session_state['origin_last_product']=pid
    p=lookup[pid];spec=p['origin'];base=bases[spec['base_set_id']];shade=components[spec['shade_id']]
    availability=lamp_options.availability(data,ledger,p)
    with st.container(border=True):
        a,b=st.columns([1,2])
        with a:photo_panel('product',pid,p['name'],key='origin_product_photo',width=180)
        with b:
            st.subheader(spec['model']);st.caption(f"{base['color']} · Receta v{p['version']} · 7 componentes por lámpara")
            st.badge(availability['status'],color='green' if availability['ready'] else 'orange')
            st.caption(f"{availability['ready']} lámparas con componentes libres para ensamblar. Existencias compartidas entre colores.")
            if st.button('Crear pedido de lámparas',key='origin_create_order',type='primary',icon=':material/playlist_add:'):recipe_order_form(pid)
            with st.container(horizontal=True):
                if st.button('Editar receta',key='origin_configure',icon=':material/tune:'):lamp_form(p)
                if st.button('Crear otra combinación',key='origin_variant',icon=':material/content_copy:'):lamp_form(template=p)
        for col,title,detail in zip(st.columns(3),('Modelo de pantalla','Modelo de base · color','Insumos'),
            (f"{shade['shape']} · {shade['color'] or 'Color sin definir'}\n\n{shade['material']}",f"{base['model_name']} · {base['color']}\n\n{base['material']} · Base + CAP + tapa",'1 cable + 1 foco + 1 empaque')):
            with col:st.markdown('**'+title+'**');st.text(detail)
    summary,plan,cost=workspace_tabs(['Composición','Disponibilidad para pedido','Costos'],f'origin_lamp_tabs_{pid}')
    if summary.open:
        with summary:
            lines=[dict(r,role=components[r['component_id']]['role'],supply=components[r['component_id']]['supply']) for r in data['catalog']['lines'] if r['recipe_id']==p['recipe_id']]
            lines.sort(key=lambda r:origin.ROLES.index(r['role']))
            table(lines,{'role':'Componente','material':'Material','variant':'Variante','quantity':'Por lámpara','supply':'Abastecimiento'},label='Siete componentes de una lámpara completa')
    if plan.open:
        with plan:
            qty=st.number_input('Lámparas a preparar',min_value=1,value=1,step=1,key=f'origin_plan_qty_{pid}')
            quote=recipes.quote_order(p['recipe_id'],qty)
            capacity=min((r['available']//r['per_product'] for r in quote['lines']),default=0)
            st.metric('Lámparas completables con existencias libres',capacity)
            st.caption('Es disponibilidad de componentes para completar y ensamblar. Las variantes comparten existencias; sus capacidades no se suman.')
            table(quote['lines'],{'role':'Componente','variant':'Variante','needed':'Necesarias','available':'Libres','reserved':'A reservar','to_make':'A fabricar','to_buy':'A comprar'},label='Disponibilidad real de piezas e insumos para el pedido')
    if cost.open:
        with cost:recipe_cost_panel(p['recipe_id'],f'origin_cost_{pid}')

def definitions_panel(data,ledger):
    group=st.segmented_control('Gestionar componentes',('Pantallas','Base y colores','Insumos'),default='Pantallas',key='origin_definition_group',persist_state='session',width='stretch', format_func=tag) or 'Pantallas'
    if group=='Insumos':supplies_panel(data,ledger);return
    balances={c['id']:c for c in stock_rows(data,ledger)}
    if group=='Pantallas':
        st.subheader('Modelos de pantalla',icon=':material/light:')
        st.caption('La forma define el modelo. Cada pantalla se comparte entre los colores de la base.')
        if st.button('Agregar pantalla',key='origin_new_shade',icon=':material/add:'):origin_component_form('Pantalla')
        shades=[c for c in balances.values() if c['role']=='Pantalla']
        for start in range(0,len(shades),3):
            for col,c in zip(st.columns(3),shades[start:start+3]):
                with col,st.container(border=True):
                    st.subheader(c['shape'])
                    if photo:=photos.get('component',c['id']):st.image(photo['content'],width=180,alt='Pantalla '+c['shape'])
                    st.caption(c['material']+' · '+c['color'])
                    st.text(f"{c['free']} libres · {c['reserved']} reservadas")
                    if st.button('Usar esta pantalla',key=f"origin_use_shade_{c['id']}",width='stretch',icon=':material/add:'):lamp_form(shade_id=c['id'])
                    if st.button('Costear impresión',key=f"origin_shade_cost_{c['id']}",width='stretch',icon=':material/calculate:'):
                        component_cost_form(c,costing.component_profile(c['id']),printing=True)
        return
    st.subheader('Un modelo de base · elige su color',icon=':material/layers:')
    st.caption('CAP y tapa siempre siguen el color y material de la base. Las existencias de las tres piezas se cuentan por separado.')
    if st.button('Agregar color de base',key='origin_new_base',icon=':material/add:'):base_form()
    for start in range(0,len(data['bases']),3):
        for col,b in zip(st.columns(3),data['bases'][start:start+3]):
            with col,st.container(border=True):
                st.caption(b['model_name']);st.subheader(b['color'])
                if photo:=photos.get('component',b['base_id']):st.image(photo['content'],width=180,alt='Base '+b['color'])
                st.caption(b['material'])
                for role,field in (('Base','base_id'),('CAP','cap_id'),('Tapa','lid_id')):
                    st.text(f"{role} · {balances[b[field]]['free']} libres")
                if st.button('Usar este color',key=f"origin_use_base_{b['id']}",width='stretch',icon=':material/add:'):lamp_form(base_set_id=b['id'])
                with st.popover('Costear base, CAP o tapa',icon=':material/calculate:',width='stretch'):
                    for label,field in (('Base','base_id'),('CAP','cap_id'),('Tapa','lid_id')):
                        if st.button(label,key=f"origin_base_cost_{b[field]}",width='stretch'):
                            component_cost_form(balances[b[field]],costing.component_profile(b[field]),printing=True)

def supplies_panel(data,ledger):
    from views.restock_ui import open_restock
    st.button('Mínimos y reposición',key='origin_supplies_minimums',icon=':material/inventory_2:',type='tertiary',on_click=open_restock)
    if st.button('Nuevo insumo / especificación',key='origin_new_supply',icon=':material/add:'):origin_component_form('Insumo')
    st.caption('Cable, foco y empaque son insumos comprados. Se reservan para cada lámpara y no generan trabajos de impresión.')
    show_components([c for c in stock_rows(data,ledger) if c['supply']=='Comprar'],'origin_supplies')

INVENTORY_VIEWS=('Piezas','Bases por color','Insumos y reposición')


def inventory_panel(data,ledger):
    """Everything of Colección Origen in the workshop: its pieces with the full piece management, bases by color and supplies."""
    from services.inventory_view import present
    from views.inventory_ui import stock_panel,incoming_panel,incoming_rows,balance_row,is_origin
    from views.base_inventory_ui import panel as base_panel
    from views.restock_ui import panel as restock_panel
    from views.collection_forms import manual_entry_form
    rows=[r for r in present(ledger['skus']) if is_origin(r)]
    balance_row(rows,incoming_rows(st.session_state['snapshot'],origin=True),scope='Colección Origen')
    if st.session_state.get('origin_inventory_view') not in INVENTORY_VIEWS:st.session_state['origin_inventory_view']='Piezas'
    view=st.segmented_control('Inventario de Colección Origen',INVENTORY_VIEWS,key='origin_inventory_view',width='stretch',label_visibility='collapsed',
                              format_func=lambda v:{'Piezas':':material/category: Piezas','Bases por color':':material/layers: Bases por color',
                                                    'Insumos y reposición':':material/electrical_services: Insumos y reposición'}[v]) or 'Piezas'
    if view=='Bases por color':
        base_panel(ledger);return
    if view=='Insumos y reposición':
        restock_panel();return
    if rows:
        stock_panel(rows,'origin_stock',title='Piezas Origen')
    else:
        st.info('Aún no hay piezas de Colección Origen en el taller. Regístralas al contarlas o al terminar sus impresiones.',icon=':material/light:')
        if st.button('📦 Registrar stock encontrado',key='origin_stock_empty_receive',type='primary'):
            from views.collection_forms import found_stock_form
            found_stock_form()
    incoming_panel(st.session_state['snapshot'],origin=True)
    st.caption('Movimientos, compras y reservas de todas las líneas se consultan en Inventario.')


def show_components(rows,key):
    if not rows:st.info('Aún no hay componentes en este grupo.');return
    columns={'role':'Componente','model':'Modelo','color':'Color','material':'Material','variant':'Especificación','physical':'Físicas','free':'Libres físicas','reserved':'Reservadas'}
    if any(r['supply']=='Comprar' for r in rows):columns.update(net='Neto pedidos',minimum='Mínimo',restock_state='Reposición')
    selected_key=key+'_selected'
    table(rows,columns,label='Existencias de componentes e insumos Origen',open=picks(selected_key),key=key+'_table')
    lookup={c['id']:c for c in rows}
    if st.session_state.get(selected_key) not in lookup:st.session_state[selected_key]=next(iter(lookup))
    cid=st.selectbox('Componente para gestionar',list(lookup),key=selected_key,format_func=lambda i:component_label(lookup[i]))
    component=lookup[cid]
    with st.container(horizontal=True):
        if st.button('Registrar entrada física',key=key+'_receive',icon=':material/add:',type='primary'):receipt_form(component)
        if st.button('Costear componente',key=key+'_cost',icon=':material/calculate:'):component_cost_form(component,costing.component_profile(cid),printing=component['supply']=='Fabricar' and component['process'] in ('Impresión 3D','Resina'))
    with st.expander('Fotografía del componente',key=key+'_photo_panel'):
        photo_panel('component',cid,component_label(component),key=key+'_photo',width=220)

def orders_panel(data,ledger):
    specs=data['specs'];rows=[o for o in st.session_state['snapshot']['orders'] if o['status']!='Entregado' and not o.get('commercial_cancelled') and any(i['recipe_id'] in specs for i in o['items'])]
    if not rows:st.info('No hay pedidos activos de lámparas completas. Crea uno desde una receta publicada.');return
    for o in rows:
        needs=[r for i in o['items'] for r in i.get('requirements',[])]
        with st.container(border=True):
            st.text(o['code']+' · '+o['project']);st.caption(o['client']+' · '+o['status'])
            from services.queries import piece_label
            table([dict(r,name=piece_label(r['name'],(r.get('variant') or '').strip()),pending=r['quantity']-r['covered']) for r in needs],{'name':'Componente','supply':'Abastecimiento','quantity':'Necesarias','covered':'Reservadas / cubiertas','pending':'Faltantes'},label='Piezas e insumos pendientes del pedido de lámparas')
            with st.container(horizontal=True):
                if st.button('Reservar insumos disponibles',key=f"origin_order_reserve_{o['id']}",icon=':material/bookmark_add:'):perform(origin.reserve_supplies,o['id'],message='Reservas actualizadas con las existencias disponibles.')
                if st.button('Abrir pedido',key=f"origin_order_open_{o['id']}",icon=':material/arrow_forward:'):open_order(o['id'])

def articles_panel(data,ledger):
    st.caption('Otros artículos de Origen pueden tener su propia composición, sin la estructura obligatoria de una lámpara.')
    if st.button('Nuevo artículo de Origen',key='origin_new_article',icon=':material/add:'):product_form()
    rows=[p for p in data['products'] if not p['origin']]
    def open_article(row):
        open_product(row['id']);st.switch_page('views/catalog.py')
    table(rows,{'name':'Artículo','variant':'Variante','version':'Receta vigente'},label='Artículos de Origen con composición general',open=open_article,key='origin_articles_table')
    if rows:
        lookup={p['id']:p for p in rows}
        pid=st.selectbox('Artículo para gestionar',list(lookup),key='origin_article',format_func=lambda i:lookup[i]['name']+' · '+lookup[i]['variant'])
        if st.button('Abrir ficha y receta',key='origin_article_open'):
            open_product(pid);st.switch_page('views/catalog.py')
