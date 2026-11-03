"""Continuous, session-backed selection with a live seven-component summary."""
import uuid
import streamlit as st
from services import origin,origin_builder as builder,costing,photos
from services.quotations import money
from views.common import perform

STORE='origin_recipe_draft'

def initialize(data,**request):
    st.session_state[STORE]=dict(builder.new_draft(data,**request),token=uuid.uuid4().hex)

def apply_request(data,request):
    draft=st.session_state.get(STORE)
    if draft and not request.get('product') and not request.get('template') and (request.get('shade_id') or request.get('base_set_id')):
        if draft['product_id'] is not None:
            spec={k:draft[k] for k in ('shade_id','base_set_id','cable_id','bulb_id','packaging_id')}
            initialize(data,template={'origin':spec});draft=st.session_state[STORE]
        for field in ('shade_id','base_set_id'):
            if request.get(field) is not None:
                draft[field]=request[field]
                st.session_state.pop(f"origin_build_{draft['token']}_{field}",None)
        if request.get('shade_id'):
            shade=next((c for c in data['components'] if c['id']==draft['shade_id']),None)
            draft['model']=shade['shape'] if shade else None
            st.session_state.pop(f"origin_build_{draft['token']}_model",None)
    else:initialize(data,**request)

def continue_builder():
    st.session_state['origin_workspace']='Crear receta'
    st.rerun()

def open_recipe(identity):
    st.session_state['origin_focus']=dict(panel='Recetas',identity=identity)
    st.rerun()

def published(identity):
    st.session_state.pop(STORE,None)
    st.session_state['origin_focus']=dict(panel='Recetas',identity=identity)

def choice(draft,field,label,options,*,format_func=str,disabled=False,compact=True):
    key=f"origin_build_{draft['token']}_{field}"
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key]=draft.get(field) if draft.get(field) in options else None
    if compact and len(options)<=5:
        value=st.segmented_control(label,options,key=key,format_func=format_func,disabled=disabled,width='stretch',wrap=True)
    else:
        value=st.selectbox(label,options,index=None,key=key,format_func=format_func,disabled=disabled,placeholder='Selecciona una opción')
    draft[field]=value
    return value

def sync_text(key,field):
    st.session_state[STORE][field]=st.session_state[key]

def note_input(draft,field,label,**kwargs):
    key=f"origin_build_{draft['token']}_{field}"
    if key not in st.session_state:st.session_state[key]=draft[field]
    draft[field]=st.text_input(label,key=key,on_change=sync_text,args=(key,field),**kwargs)

def render(data,ledger):
    if STORE not in st.session_state:initialize(data)
    draft=st.session_state[STORE];editing=draft['product_id'] is not None
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.subheader('Configura tu receta' if not editing else f"Editar receta · {draft['product_name']}",icon=':material/tune:')
        if st.button('Empezar otra receta',key='origin_builder_restart',icon=':material/restart_alt:',type='tertiary'):
            initialize(data);st.rerun()
    st.caption('Selecciona en cualquier orden. El resumen se actualiza al momento y tu borrador se conserva al cambiar de pestaña o sección durante esta sesión.')
    if editing:
        current=next((p for p in data['products'] if p['id']==draft['product_id']),None)
        if not current or current['recipe_id']!=draft['expected_recipe_id']:
            st.warning('La receta publicada cambió en otra ventana. Tu borrador se conserva; abre la versión vigente antes de publicar.')
            if current and st.button('Cargar versión vigente',key='origin_builder_reload'):
                initialize(data,product=current);st.rerun()
        st.caption(f"Nueva versión de la receta v{draft['version']}. Para otro modelo de pantalla o color, crea otra combinación.")
    selections,summary=st.columns([1.55,1],gap='large')
    with selections:
        with st.container(border=True):
            st.markdown('### 1 · Pantalla')
            old_model=draft['model']
            model=choice(draft,'model','Modelo de pantalla',data['shade_models'],disabled=editing)
            shades=[c for c in data['components'] if c['role']=='Pantalla' and c['shape']==model]
            if model!=old_model or draft['shade_id'] not in {c['id'] for c in shades}:
                draft['shade_id']=shades[0]['id'] if len(shades)==1 else None
                st.session_state.pop(f"origin_build_{draft['token']}_shade_id",None)
            if len(shades)>1:
                lookup={c['id']:c for c in shades}
                choice(draft,'shade_id','Acabado de pantalla',list(lookup),format_func=lambda i:f"{lookup[i]['color']} · {lookup[i]['material']} · {lookup[i]['variant']}",compact=False)
            shade=next((c for c in shades if c['id']==draft['shade_id']),None)
            if shade:
                st.caption(f"{shade['color'] or 'Color sin definir'} · {shade['material']}")
                if photo:=photos.get('component',shade['id']):st.image(photo['content'],width=150,alt='Pantalla '+shade['shape'])
            else:st.caption('Elige la forma de la pantalla para comenzar.')
        with st.container(border=True):
            st.markdown('### 2 · Base y color')
            bases={b['id']:b for b in data['bases']}
            st.caption(', '.join(m['name'] for m in data['base_models'])+' · Un mismo modelo para todas las pantallas.')
            bid=choice(draft,'base_set_id','Color de base',list(bases),format_func=lambda i:bases[i]['color'],disabled=editing)
            if bid:
                base=bases[bid]
                with st.container(horizontal=True):
                    for role in ('Base','CAP','Tapa'):st.badge(role+' · '+base['color'],color='gray',icon=':material/check:')
                st.caption(base['material']+' · CAP y tapa se agregan automáticamente con el mismo color y material.')
            else:st.caption('Elige un color. Base, CAP y tapa se incorporan juntas.')
        with st.container(border=True):
            st.markdown('### 3 · Insumos')
            st.caption('Una unidad de cable, foco y empaque por lámpara. Se usan las referencias disponibles; puedes cambiar su especificación.')
            multiple=any(len([c for c in data['components'] if c['role']==role])>1 for role,_ in builder.SUPPLIES)
            with st.expander('Elegir especificaciones',expanded=multiple):
                for role,field in builder.SUPPLIES:
                    options={c['id']:c for c in data['components'] if c['role']==role}
                    choice(draft,field,role,list(options),compact=False,disabled=len(options)==1,
                        format_func=lambda i,lookup=options:lookup[i]['variant']+' · '+lookup[i]['material'])
            selected={c['id']:c for c in data['components']}
            for role,field in builder.SUPPLIES:
                c=selected.get(draft[field])
                st.text(f"{'✓' if c else '○'}  {role} · {c['variant'] if c else 'Por elegir'}")
        with st.expander('Nombre y notas (opcional)'):
            if not editing:
                note_input(draft,'name','Nombre personalizado (opcional)',placeholder='Se genera a partir de pantalla y color')
            note_input(draft,'notes','Notas de la receta',placeholder='Especificación o motivo del cambio')
    plan=builder.composition(data,draft)
    with summary,st.container(border=True):
        st.markdown('### Tu receta')
        st.badge('Nueva versión' if editing else 'Borrador de sesión',color='blue',icon=':material/edit_note:')
        st.subheader(plan['name'])
        st.progress(plan['count']/7,text=f"{plan['count']} de 7 componentes definidos")
        stock={}
        for s in ledger['skus']:stock[s['component_id']]=stock.get(s['component_id'],0)+s['available_stock']+s['available_collection']
        rows=[];costs=[]
        for row in plan['rows']:
            c=row['component'];price=None
            if c:
                profile=costing.component_profile(c['id'])
                price=costing.component_amount(profile['data'])['total_cents'] if profile else None
            costs.append(price)
            detail=(c['shape'] if row['role']=='Pantalla' else c['color'] if row['role'] in ('Base','CAP','Tapa') else c['variant']) if c else 'Por elegir'
            rows.append(dict(role=row['role'],detail=detail,quantity=1,free=stock.get(c['id'],0) if c else None))
        st.dataframe(rows,hide_index=True,width='stretch',column_order=['role','detail','free'],
            column_config={'role':st.column_config.TextColumn('Elemento',width=76),
                'detail':st.column_config.TextColumn('Selección',width=132),'free':st.column_config.NumberColumn('Libres',width=56)},
            alt='Resumen en vivo de los siete componentes de la lámpara')
        st.caption('Una unidad de cada componente por lámpara.')
        st.metric('Costo de componentes',money(sum(costs)) if all(v is not None for v in costs) else 'Por completar')
        st.caption(f"{sum(v is not None for v in costs)}/7 costos capturados. Revisa ensamble y otros directos en Costos al publicar.")
        other=next((p for p in plan['matches'] if p['id']!=draft['product_id']),None)
        unchanged=any(p['id']==draft['product_id'] for p in plan['matches'])
        stale=editing and (not current or current['recipe_id']!=draft['expected_recipe_id'])
        if other:
            st.info('Esta combinación ya tiene receta: '+other['name'])
            if st.button('Abrir receta existente',key='origin_builder_existing',type='primary',width='stretch'):
                open_recipe(other['id'])
        else:
            if unchanged:st.caption('La composición coincide con la receta vigente. Cambia una especificación para publicar otra versión.')
            if not plan['complete']:st.caption('Completa pantalla, color de base e insumos para publicar.')
            if st.button('Publicar nueva versión' if editing else 'Publicar receta',key='origin_builder_publish',type='primary',icon=':material/check:',
                         width='stretch',disabled=not plan['complete'] or unchanged or bool(stale)):
                perform(origin.publish_lamp,draft['product_id'],name=plan['name'],shade_id=draft['shade_id'],base_set_id=draft['base_set_id'],
                    expected_recipe_id=draft['expected_recipe_id'],notes=draft['notes'],**{field:draft[field] for _,field in builder.SUPPLIES},
                    after=published,message='Receta publicada. Ya puedes costearla o crear un pedido.')
        st.caption('Receta para una lámpara. Registra las existencias físicas en Inventario.')
        if editing and st.button('Crear otra combinación',key='origin_builder_copy',width='stretch',icon=':material/content_copy:'):
            spec={k:draft[k] for k in ('shade_id','base_set_id','cable_id','bulb_id','packaging_id')}
            initialize(data,template={'origin':spec});st.rerun()
