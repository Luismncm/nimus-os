"""Session drafts stay separate from immutable published recipes."""
import streamlit as st
from services import recipes
from services.catalog_view import editor_lines,differences
from views.catalog_forms import component_form,component_label
from views.common import perform,table

def prefix_for(product): return f"recipe_draft_{product['id']}_{product['version'] or 0}"
def store_key(product): return prefix_for(product)+'_store'

def sync_selection(prefix,key):
    st.session_state[key]['ids']=list(st.session_state[prefix+'_pieces'])

def sync_grid(grid_key,key,rows):
    edits=st.session_state.get(grid_key,{}).get('edited_rows',{})
    for index,fields in edits.items():
        if 'quantity' in fields and 0<=int(index)<len(rows):
            st.session_state[key]['quantities'][rows[int(index)]['component_id']]=fields['quantity']

def sync_notes(prefix,key):st.session_state[key]['notes']=st.session_state.get(prefix+'_notes','')

def reset_draft(prefix,key,current):
    for field in list(st.session_state):
        if field.startswith(prefix+'_') and field!=key: st.session_state.pop(field,None)
    st.session_state[key]=dict(ids=[r['component_id'] for r in current],quantities={r['component_id']:r['quantity'] for r in current},notes='')

def publish(product_id,records,notes,expected):
    return recipes.publish_recipe(product_id,editor_lines(records),notes,expected_recipe_id=expected)

def render(product,catalog,current):
    from services.origin import load
    if product['recipe_id'] in load()['specs']:
        from views.origin_forms import lamp_form
        st.info('Configura esta receta con selección continua de pantalla, color de base e insumos. CAP y tapa se incorporan automáticamente.')
        if st.button('Abrir configurador de receta',key=f"catalog_lamp_configure_{product['id']}",type='primary'):
            lamp_form(dict(product,origin=load()['specs'][product['recipe_id']]))
        st.page_link('views/origen.py',label='Abrir Colección Origen',icon=':material/light:')
        return
    prefix=prefix_for(product);key=store_key(product)
    if key not in st.session_state:
        st.session_state[key]=dict(ids=[r['component_id'] for r in current],quantities={r['component_id']:r['quantity'] for r in current},notes='')
    draft=st.session_state[key];components={c['id']:c for c in catalog['components']}
    if any(r['component_id'] not in components for r in current):
        st.info('Las referencias retiradas se quitan del nuevo borrador. Elige su reemplazo; el historial conserva la versión anterior.')
    draft['ids']=[cid for cid in draft['ids'] if cid in components]
    if prefix+'_pieces' in st.session_state:
        st.session_state[prefix+'_pieces']=[cid for cid in st.session_state[prefix+'_pieces'] if cid in components]
    st.subheader('Editar cantidades por producto',icon=':material/edit_note:')
    st.caption(f"Borrador para {'v'+str(product['version']+1) if product['version'] else 'la primera versión'} · Se conserva al cambiar de producto o pestaña durante esta sesión.")
    if not components:
        st.info('Agrega una pieza reutilizable para empezar la receta.')
        if st.button('Crear primera pieza',key=prefix+'_first',type='primary'):component_form(context_product_id=product['id'])
        return
    st.multiselect('Piezas de este producto',list(components),default=None if prefix+'_pieces' in st.session_state else draft['ids'],format_func=lambda i:component_label(components[i]),
        key=prefix+'_pieces',on_change=sync_selection,args=(prefix,key),persist_state='session',placeholder='Busca una pieza por nombre, material o variante')
    with st.container(horizontal=True,horizontal_alignment='distribute'):
        st.caption('Cantidad por una unidad de producto. Por ejemplo: 1 base + 2 tapas.')
        if st.button('Crear pieza que falta',key=prefix+'_new_piece',icon=':material/add:',type='tertiary'):
            component_form(context_product_id=product['id'])
    selected=[cid for cid in draft['ids'] if cid in components]
    records=[dict(component_id=cid,code=components[cid]['code'],name=components[cid]['name'],material=components[cid]['material'],variant=components[cid]['variant'],quantity=draft['quantities'].get(cid,1)) for cid in selected]
    result=records
    if records:
        grid_key=prefix+'_grid_'+'_'.join(map(str,selected))
        result=st.data_editor(records,hide_index=True,width='stretch',key=grid_key,
            disabled=['component_id','code','name','material','variant'],column_order=['name','material','variant','quantity'],
            column_config={'name':st.column_config.TextColumn('Pieza'),'material':st.column_config.TextColumn('Material'),
                'variant':st.column_config.TextColumn('Variante'),'quantity':st.column_config.NumberColumn('Por producto',min_value=1,step=1,required=True)},
            on_change=sync_grid,args=(grid_key,key,records),alt='Borrador de receta con cantidades editables por producto')
        for row in result:draft['quantities'][row['component_id']]=row['quantity']
    draft['notes']=st.text_input('Motivo / notas de la nueva versión',value=draft['notes'],key=prefix+'_notes',on_change=sync_notes,args=(prefix,key),persist_state='session',placeholder='Ej. Ajuste de tapas o cambio de material')
    valid=[];error=None
    try:valid=editor_lines(result)
    except ValueError as exc:error=str(exc)
    changes=differences(current,valid,{**{r['component_id']:r for r in current},**components}) if not error else []
    if error:st.info(error)
    elif changes:
        st.badge('1 cambio sin publicar' if len(changes)==1 else f'{len(changes)} cambios sin publicar',color='orange',icon=':material/edit:')
        table(changes,{'name':'Pieza','variant':'Variante','before':'Vigente','after':'Borrador','change':'Cambio'},label='Comparación de receta vigente y borrador')
        st.caption(f"{len(valid)} referencias · {sum(r['quantity'] for r in valid)} componentes por producto")
    else:st.caption('Sin cambios en las piezas o cantidades de la receta vigente.')
    st.caption('Publicar crea una nueva versión para pedidos futuros. Los pedidos existentes conservan su receta; revisa el costeo de la nueva versión antes de usarlo en ventas.')
    with st.container(horizontal=True,gap='small'):
        if st.button('Publicar receta',key=prefix+'_publish',type='primary',icon=':material/publish:',disabled=bool(error) or not changes):
            perform(publish,product['id'],result,draft['notes'],product['recipe_id'],message='Nueva receta publicada. Disponible para próximos pedidos.')
        st.button('Restablecer borrador',key=prefix+'_reset',icon=':material/restart_alt:',on_click=reset_draft,args=(prefix,key,current))
