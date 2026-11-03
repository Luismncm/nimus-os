"""One session basket for operational orders, quotes and confirmed sales."""
import uuid
from datetime import timedelta
import streamlit as st
from services import recipe_cart, lamp_options, commercial_preview, commerce, quotations as q, photos
from utils.dates import now
from views.common import perform,table
from views.navigation import select_order
from views.commerce_ui import fields as commercial_fields
from views.emoji import tag

STORE='origin_sales_cart'

def open_cart(product_id=None,model=None,base_set_id=None,mode=None,source=None):
    st.session_state['origin_cart_request']=dict(product_id=product_id,model=model,base_set_id=base_set_id,mode=mode,source=source)
    st.session_state.pop('active_dialog',None)
    st.switch_page('views/origen.py')

def initialize(data,request=None):
    request=request or {};old=st.session_state.get(STORE)
    if not old or request.get('source'):
        old=dict(token=uuid.uuid4().hex,entries=[],model=None,base_set_id=None,quantity=1,mode='Pedido operativo',
            client='',project='',discount=0.0,iva=False,shipping=None,shipping_cost=None,terms=commerce.defaults(),use_stock=True)
        if source:=request.get('source'):
            d=source['data'];old.update(client=d['client'],project=d['project'],discount=d['discount'],iva=d['iva'])
            profile=commerce.profile('quote' if source['code'].startswith('COT') else 'sale',source['id'])
            if profile:
                for field in ('source','price_segment','sales_owner','production_owner','delivery_owner','delivery_method','delivery_reference','agreement'):
                    old['terms'][field]=profile['data'][field]
                old['shipping_cost']=profile['data'].get('shipping_cost')
            for line in d['lines']:
                if line.get('recipe_id'):old['entries'].append(dict(uid=uuid.uuid4().hex,recipe_id=line['recipe_id'],quantity=int(line['quantity']),price=line['price'],label=line['description']))
                elif line['description']=='Envío':old['shipping']=line['price']
            old['omitted']=[l['description'] for l in d['lines'] if not l.get('recipe_id') and l['description']!='Envío']
        st.session_state[STORE]=old
    product=next((p for p in data['products'] if p['id']==request.get('product_id') and p['origin']),None)
    spec=product['origin'] if product else {}
    old['model']=spec.get('model',request.get('model')) or old['model']
    old['base_set_id']=spec.get('base_set_id',request.get('base_set_id')) or old['base_set_id']
    if request.get('mode'):old['mode']=request['mode']
    for field in ('model','base_set_id','mode'):st.session_state.pop('cart_'+old['token']+'_'+field,None)

def select(draft,field,label,options,**kwargs):
    key='cart_'+draft['token']+'_'+field
    if key not in st.session_state:st.session_state[key]=draft[field]
    draft[field]=st.segmented_control(label,options,key=key,width='stretch',wrap=True,**kwargs)
    return draft[field]

def sync_line(uid,field,key):
    entry=next((e for e in st.session_state[STORE]['entries'] if e['uid']==uid),None)
    if entry:entry[field]=st.session_state[key]

def text(draft,field,label,**kwargs):
    key='cart_'+draft['token']+'_'+field
    if key not in st.session_state:st.session_state[key]=draft[field]
    draft[field]=st.text_input(label,key=key,**kwargs)
    return draft[field]

def finish(kind,identity):
    st.session_state.pop(STORE,None)
    if kind=='quote':st.session_state['open_quote_id']=identity
    elif kind=='sale':st.session_state['open_sale_id']=identity
    else:select_order(identity)

def render(data,ledger):
    if STORE not in st.session_state:initialize(data)
    d=st.session_state[STORE];prefix='cart_'+d['token']
    with st.container(horizontal=True,horizontal_alignment='distribute'):
        st.subheader('Venta y pedido de Origen',icon=':material/shopping_bag:')
        if st.button('Nueva captura',key='cart_restart',type='tertiary',icon=':material/restart_alt:'):
            st.session_state.pop(STORE,None);initialize(data);st.rerun()
        if st.button('Pedido de otros productos',key='cart_other_products',type='tertiary'):
            from views.catalog_forms import general_recipe_order_form
            general_recipe_order_form()
    st.caption('Reúne modelos y colores para el mismo cliente. El cálculo conjunto reparte las piezas compartidas una sola vez.')
    if d.get('omitted'):st.info('Revisa las partidas adicionales del documento original antes de confirmar: '+', '.join(d['omitted']))
    mode=select(d,'mode','Guardar como',('Pedido operativo','Cotización','Venta confirmada')) or 'Pedido operativo'
    left,right=st.columns([1.6,1],gap='large')
    with left:
        with st.container(border=True):
            st.markdown('### Agregar lámparas')
            model=select(d,'model','Modelo de lámpara',data['shade_models']) if len(data['shade_models'])<=5 else st.selectbox('Modelo de lámpara',data['shade_models'],index=data['shade_models'].index(d['model']) if d['model'] in data['shade_models'] else None,key=prefix+'_model')
            d['model']=model
            bases={b['id']:b for b in data['bases']}
            bid=select(d,'base_set_id','Color de base',list(bases),format_func=lambda i:bases[i]['color'])
            qty=st.number_input('Lámparas a agregar',min_value=1,value=d['quantity'],step=1,key=prefix+'_quantity');d['quantity']=qty
            options=lamp_options.color_options(data,ledger,model,qty)
            option=next((o for o in options if o['base']['id']==bid),None)
            products={p['recipe_id']:p for p in option['products']} if option else {}
            rid=next(iter(products)) if len(products)==1 else st.selectbox('Especificación de receta',list(products),index=None,key=prefix+'_recipe') if products else None
            if option and option['stock']:
                stock=option['stock'];st.badge(stock['status'],color='green' if stock['ready']>=qty else 'orange')
                pending=[f"{r['to_make'] or r['to_buy']} {r['role'].lower()}" for r in stock['rows'] if r['to_make'] or r['to_buy']]
                st.caption('Faltantes antes de agregar al conjunto: '+(', '.join(pending) if pending else 'Componentes disponibles para ensamblar.'))
            if rid:
                spec=products[rid]['origin']
                for cid,label in ((spec['shade_id'],'Pantalla'),(bases[bid]['base_id'],'Base')):
                    if photo:=photos.get('component',cid):st.image(photo['content'],width=110,alt=label+' de la combinación seleccionada')
            elif model and bid:st.info('Publica la receta de esta combinación antes de agregarla al pedido.')
            if st.button('Agregar al pedido',key='cart_add',type='primary',icon=':material/add:',disabled=not rid,width='stretch'):
                same=next((e for e in d['entries'] if e['recipe_id']==rid and e['price'] is None),None)
                if same:same['quantity']+=qty;st.session_state.pop(prefix+'_'+same['uid']+'_quantity',None)
                else:d['entries'].append(dict(uid=uuid.uuid4().hex,recipe_id=rid,quantity=qty,price=None,label=f"{model} · {bases[bid]['color']}"))
                st.rerun()
        st.markdown('### Lámparas del pedido')
        if not d['entries']:st.info('Agrega una o varias combinaciones para preparar tu pedido, cotización o venta.')
        for index,entry in enumerate(list(d['entries'])):
            with st.container(border=True):
                st.markdown('**'+entry['label']+'**')
                a,b=st.columns(2)
                key=prefix+'_'+entry['uid']+'_quantity'
                if key not in st.session_state:st.session_state[key]=entry['quantity']
                entry['quantity']=a.number_input('Cantidad',min_value=1,step=1,key=key,on_change=sync_line,args=(entry['uid'],'quantity',key))
                if mode!='Pedido operativo':
                    key=prefix+'_'+entry['uid']+'_price'
                    if key not in st.session_state:st.session_state[key]=entry['price']
                    entry['price']=b.number_input('Precio unitario · MXN',min_value=0.0,step=1.0,value=None,key=key,on_change=sync_line,args=(entry['uid'],'price',key))
                with st.container(horizontal=True):
                    if st.button('Duplicar',key='cart_duplicate_'+entry['uid'],type='tertiary',icon=':material/content_copy:'):
                        d['entries'].insert(index+1,dict(entry,uid=uuid.uuid4().hex));st.rerun()
                    if st.button('Quitar',key='cart_remove_'+entry['uid'],type='tertiary',icon=':material/remove_circle_outline:'):
                        d['entries'].remove(entry);st.rerun()
        st.markdown('### Cliente y entrega')
        client=text(d,'client','Cliente / empresa *',placeholder='Un cliente para todo el pedido')
        project=text(d,'project','Proyecto / referencia')
        if mode!='Pedido operativo':
            a,b=st.columns(2)
            d['discount']=a.number_input('Descuento %',min_value=0.0,max_value=100.0,value=d['discount'],key=prefix+'_discount')
            d['iva']=b.checkbox('Agregar IVA 16%',value=d['iva'],key=prefix+'_iva')
            a,b=st.columns(2)
            d['shipping']=a.number_input('Envío cobrado · MXN (opcional)',min_value=0.0,value=d['shipping'],key=prefix+'_shipping')
            d['shipping_cost']=b.number_input('Costo estimado del envío · MXN',min_value=0.0,value=d['shipping_cost'],key=prefix+'_shipping_cost')
            st.caption('Captura los precios acordados antes del IVA. Cada combinación conserva su precio y el tipo de cliente del acuerdo.')
        with st.expander('Condiciones, responsables y entrega',expanded=False):
            d['terms']=commercial_fields(d['terms'],prefix+'_terms')
        if mode=='Pedido operativo':
            d['use_stock']=st.checkbox('Reservar piezas libres al confirmar',value=d['use_stock'],key=prefix+'_stock')
            destination=st.segmented_control('Destino',('Cliente','Stock'),default='Cliente',key=prefix+'_destination',width='stretch', format_func=tag) or 'Cliente'
        else:destination='Cliente'
    with right,st.container(border=True):
        st.markdown('### Resumen del conjunto')
        st.metric('Lámparas',sum(e['quantity'] for e in d['entries']))
        if not d['entries']:st.caption('El resumen se completa al agregar combinaciones.');return
        entries=[{k:e[k] for k in ('recipe_id','quantity','price','label')} for e in d['entries']]
        stock_policy=d['use_stock'] if mode=='Pedido operativo' else True
        fresh=recipe_cart.quote(entries,stock_policy);signature=[(e['recipe_id'],e['quantity']) for e in entries]+[stock_policy]
        if d.get('plan_signature')!=signature:d['plan']=fresh;d['plan_signature']=signature
        stale=d['plan']['fingerprint']!=fresh['fingerprint']
        if stale:
            st.warning('Las existencias cambiaron. Actualiza el plan antes de reservar.')
            if st.button('Actualizar plan',key='cart_refresh',icon=':material/refresh:'):d['plan']=fresh;st.rerun()
        plan=d['plan'];rows=[r for entry in plan['entries'] for r in entry['lines']]
        for label,field in (('Componentes a reservar','reserved'),('Piezas a fabricar','to_make'),('Insumos a comprar','to_buy')):
            st.metric(label,sum(r[field] for r in rows))
        from views.restock_ui import plan_note
        plan_note(fresh)
        with st.expander('Ver reparto y faltantes'):
            for entry in plan['entries']:
                st.markdown(f"**{entry['recipe']['name']} × {entry['quantity']}**")
                table(entry['lines'],{'role':'Componente','needed':'Necesarias','reserved':'A reservar','to_make':'A fabricar','to_buy':'A comprar'},label='Reparto conjunto de stock entre combinaciones')
        pricing=commercial_preview.prices(entries,discount=d['discount'],iva=d['iva'],shipping=d['shipping'],shipping_cost=d['shipping_cost'])
        if mode!='Pedido operativo':
            st.metric('Total · MXN',q.money(pricing['totals']['total']) if pricing['priced'] else 'Pendiente')
            st.metric('Utilidad bruta estimada',q.money(pricing['profit_cents']) if pricing['profit_cents'] is not None else 'Pendiente')
            if pricing['margin'] is not None:st.caption(f"Margen sobre venta sin IVA: {pricing['margin']:.1f}%")
            else:st.caption('La utilidad se muestra cuando están completos los costos de las recetas y del envío cobrado.')
            if any(row['missing'] for row in pricing['cost_rows']):
                with st.expander('Costos pendientes'):
                    for entry,row in zip(entries,pricing['cost_rows']):
                        if row['missing']:
                            st.markdown('**'+entry['label']+'**')
                            for missing in row['missing']:st.caption(missing)
                    st.page_link('views/costs.py',label='Capturar costos',icon=':material/calculate:')
        forecast=commercial_preview.forecast(entries,d['terms'],fresh)
        st.caption('Escenario de preparación: '+(forecast['estimated_on'] if forecast['estimated_on'] else 'Pendiente de tiempos y capacidad'))
        with st.expander('Revisar capacidad y fecha'):
            st.text(f"Máquinas operativas: {forecast['machines']} · Impresión conocida: {forecast['known_print_minutes']:.0f} min · Cola conocida: {forecast['queue_minutes']:.0f} min")
            if forecast['missing']:st.caption('Por completar: '+' · '.join(forecast['missing']))
            st.caption('Escenario con capacidad diaria declarada y tiempos registrados; revisa materiales y agenda antes de prometer una fecha.')
        free=any(e['price']==0 for e in entries)
        allow_free=st.checkbox('Confirmo las partidas sin cargo',key=prefix+'_free') if free and mode!='Pedido operativo' else True
        ready=bool(client.strip() or destination=='Stock') and (mode=='Pedido operativo' or pricing['priced']) and allow_free
        if mode=='Pedido operativo':
            if st.button('Confirmar pedido conjunto',key='cart_submit',type='primary',width='stretch',disabled=not ready or stale):
                perform(recipe_cart.create_order,entries,client=client,project=project,deadline=d['terms']['promised_on'],
                    fulfillment=destination,use_stock=d['use_stock'],expected_fingerprint=plan['fingerprint'],request_key=d['token'],
                    after=lambda oid:finish('order',oid),navigate='views/orders.py',message='Pedido conjunto creado con sus reservas y faltantes.')
        else:
            kind='quote' if mode=='Cotización' else 'sale'
            if st.button('Guardar cotización' if kind=='quote' else 'Confirmar venta',key='cart_submit',type='primary',width='stretch',disabled=not ready):
                payload=dict(client=client,project=project,issued_on=now().date().isoformat(),valid_until=(now().date()+timedelta(days=15)).isoformat(),
                    discount=d['discount'],iva=d['iva'],shipping=d['shipping'],channel='Venta al público')
                perform(commerce.create_document,kind,entries,payload,dict(d['terms'],shipping_cost=d['shipping_cost']),request_key=d['token'],after=lambda identity:finish(kind,identity),
                    navigate='views/quotations.py' if kind=='quote' else 'views/sales.py',message='Documento guardado con sus recetas y condiciones. Registra pagos y autoriza producción desde su ficha.')
        st.caption('Cotización y venta conservan el alcance. Las reservas se confirman al crear producción; el cobro se registra por separado.')
