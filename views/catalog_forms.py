import streamlit as st

from models.constants import PROCESSES, PRIORITIES
from services import recipes
from views.common import managed_dialog, perform, table
from views.navigation import select_order
from views.properties import property_select


def focus_product(identity):
    st.session_state['catalog_focus_request']=dict(kind='product',identity=identity)


def focus_component(identity,context_product_id=None):
    st.session_state['catalog_focus_request']=dict(kind='component',identity=identity,context_product_id=context_product_id)


def component_label(row):
    return ' · '.join(str(row[k]) for k in ('name','material','process','variant') if row.get(k))


@managed_dialog('Pieza reutilizable', width='medium')
def component_form(context_product_id=None):
    st.caption('Define sus propiedades una vez. Podrás usar esta pieza en varias recetas.')
    with st.form('catalog_component'):
        name = property_select('Nombre de pieza *', 'part', key='component_name')
        a,b = st.columns(2)
        material = property_select('Material', 'material', key='component_material', container=a)
        process = b.selectbox('Proceso', PROCESSES, key='component_process')
        variant = st.text_input('Variante / tamaño / color', key='component_variant', placeholder='Ej. Ø 20 cm · negro')
        collection = st.selectbox('Línea', ['Origen','General'], key='component_collection')
        if st.form_submit_button('Guardar pieza reutilizable', type='primary', width='stretch'):
            perform(recipes.create_component, name, material, process, variant, collection,
                after=lambda cid:focus_component(cid,context_product_id),navigate='views/catalog.py',message='Pieza disponible para tus recetas.')


@managed_dialog('Producto del catálogo')
def product_form():
    with st.form('catalog_product'):
        name = property_select('Producto *', 'product', key='product_name')
        variant = st.text_input('Variante', key='product_variant')
        collection = st.selectbox('Línea', ['Origen','General'], key='product_collection')
        if st.form_submit_button('Crear producto', type='primary', width='stretch'):
            perform(recipes.create_product, name, variant, collection,after=focus_product,navigate='views/catalog.py',message='Producto creado. Define ahora su receta.')


@managed_dialog('Crear variante de producto',width='medium')
def variant_form(product):
    st.text('Origen: '+component_label(product))
    st.caption('La variante tendrá su propia ficha y sus propias versiones. Puedes partir de la receta vigente y ajustar sus piezas después.')
    prefix='variant_'+st.session_state['dialog_request_key']
    with st.form(prefix):
        name=st.text_input('Nombre del producto',value=product['name'],key=prefix+'_name')
        variant=st.text_input('Variante nueva',placeholder='Color, acabado o tamaño',key=prefix+'_variant')
        line=st.selectbox('Línea',('Origen','General'),index=('Origen','General').index(product['collection']),key=prefix+'_line')
        copy=st.checkbox('Copiar la receta vigente',value=bool(product['recipe_id']),disabled=not product['recipe_id'],key=prefix+'_copy')
        if st.form_submit_button('Crear variante',type='primary',width='stretch'):
            perform(recipes.duplicate_product,product['id'],name,variant,line,copy_recipe=copy,expected_recipe_id=product['recipe_id'],
                after=focus_product,navigate='views/catalog.py',message='Variante creada. Revisa receta, fotografía y costos antes de producir.')


@managed_dialog('Guardar despiece como receta', width='medium')
def import_recipe_form(item):
    st.write(f"**{item['name']} ×{item['quantity']}**")
    if any(p['quantity_required'] % item['quantity'] for p in item['parts']):
        st.warning('Las cantidades de piezas no son múltiplos del producto. Define la receta por unidad desde Catálogo.')
        return
    table([{**p, 'units': p['quantity_required']//item['quantity']} for p in item['parts']],
          {'name':'Pieza','material':'Material','process':'Proceso','units':'Por producto'}, label='Receta por unidad')
    st.caption('Se crea una versión reutilizable. El pedido original y su producción se conservan.')
    if st.button('Guardar receta', type='primary', width='stretch', key='import_recipe_save'):
        perform(recipes.import_item_recipe, item['id'], message='Receta guardada. Ya puedes crear pedidos desde ella.')


def recipe_order_form(product_id=None,model=None,base_set_id=None):
    from services import origin
    data=origin.load()
    managed={p['id'] for p in data['products'] if p['origin'] and not p['has_retired_components']}
    if managed and (product_id is None or product_id in managed):
        from views.origin_cart import open_cart
        open_cart(product_id,model,base_set_id)
    else:general_recipe_order_form(product_id)

@managed_dialog('Nuevo pedido desde receta', width='large')
def general_recipe_order_form(product_id=None):
    catalog = recipes.load_catalog()
    from services import origin
    data=origin.load()
    managed={p['id'] for p in data['products'] if p['origin'] and not p['has_retired_components']}
    products = {p['recipe_id']: p for p in catalog['products'] if p['recipe_id'] and not p['has_retired_components']}
    if managed:products={rid:p for rid,p in products.items() if p['id'] not in managed}
    if not products:
        st.info('Guarda un despiece como receta desde un pedido, o crea un producto y su receta en Catálogo.')
        return
    if product_id is not None and st.session_state.get('recipe_order_focus_request')!=st.session_state['dialog_request_key']:
        selected=next((rid for rid,p in products.items() if p['id']==product_id),None)
        if selected is None:
            st.info('Este producto necesita una receta publicada antes de crear pedidos.');return
        st.session_state['recipe_order_product']=selected
        st.session_state['recipe_order_focus_request']=st.session_state['dialog_request_key']
    if st.session_state.get('recipe_order_product') not in products:
        st.session_state['recipe_order_product']=next(iter(products))
    a,b,c = st.columns([3,1,1.5])
    rid = a.selectbox('Producto y receta', list(products), key='recipe_order_product',
        format_func=lambda k: f"{products[k]['name']} · {products[k]['variant']} · v{products[k]['version']}")
    qty = b.number_input('Productos', min_value=1, value=1, step=1, key='recipe_order_qty')
    fulfillment = c.selectbox('Destino', ['Cliente','Stock'], key='recipe_order_fulfillment')
    use_stock = st.checkbox('Reservar existencias disponibles y fabricar solo faltantes', value=True, key='recipe_order_stock')
    signature = (rid,qty,use_stock)
    if st.session_state.get('recipe_quote_signature') != signature:
        st.session_state['recipe_quote'] = recipes.quote_order(rid,qty,use_stock)
        st.session_state['recipe_quote_signature'] = signature
    if st.button('Recalcular', icon=':material/refresh:', key='recipe_recalculate'):
        st.session_state['recipe_quote'] = recipes.quote_order(rid,qty,use_stock)
    quote = st.session_state['recipe_quote']
    if any(row.get('to_buy') for row in quote['lines']):
        st.caption(f"{sum(row['to_make'] for row in quote['lines'])} piezas a fabricar · {sum(row['to_buy'] for row in quote['lines'])} insumos a comprar. Registra las compras recibidas en Colección Origen y reserva los insumos del pedido.")
    table(quote['lines'], {'name':'Pieza','material':'Material','variant':'Variante','needed':'Necesarias',
          'available':'Libres','reserved':'A reservar','to_make':'A fabricar','to_buy':'A comprar'}, label='Plan de piezas y reservas')
    from views.restock_ui import plan_note
    plan_note(quote)
    st.caption('Las reservas se confirman al crear el pedido. La receta queda fijada; el avance mide componentes, no productos ensamblados.')
    with st.form('recipe_order_confirm'):
        a,b = st.columns(2)
        project = a.text_input('Proyecto (opcional)', key='recipe_order_project', placeholder=f"{products[rid]['name']} ×{qty}")
        client = property_select('Cliente *','client',key='recipe_order_client',container=b) if fulfillment == 'Cliente' else ''
        due = a.date_input('Fecha límite', value=None, key='recipe_order_deadline')
        priority = b.selectbox('Prioridad', PRIORITIES, index=PRIORITIES.index('Media'),key='recipe_order_priority')
        if st.form_submit_button('Crear pedido y reservar piezas', type='primary', width='stretch'):
            perform(recipes.create_recipe_order, rid,qty,project=project,client=client,deadline=due.isoformat() if due else '',
                    priority=priority,fulfillment=fulfillment,use_stock=use_stock,expected_fingerprint=quote['fingerprint'],
                    request_key=st.session_state['dialog_request_key'],
                    after=select_order,navigate='views/orders.py',message='Pedido creado. Las piezas disponibles quedaron reservadas.')


@managed_dialog('Vincular existencias con una pieza', width='medium')
def link_inventory_form(sku):
    from services.recipes import identity
    options = {c['id']:c for c in recipes.load_catalog()['components']
               if identity(c['name'],c['material'],c['process']) == identity(sku['part'],sku['material'],sku['process'])}
    st.write(f"**{sku['product']} · {sku['part']} · {sku['material']}**")
    if not options:
        st.info('Crea una pieza del catálogo con el mismo nombre, material y proceso para vincular estas existencias.')
        return
    cid = st.selectbox('Pieza compatible',list(options),format_func=lambda k: component_label(options[k]),key='link_component')
    compatible = st.checkbox('Verifiqué que tamaño, color y variante son compatibles',key='link_compatible')
    st.caption('Esta relación permite reservar las existencias en futuras recetas. Se conserva el historial del modelo original.')
    if st.button('Vincular existencias',type='primary',disabled=not compatible,key='link_inventory_save'):
        perform(recipes.link_inventory,sku['id'],cid,message='Existencias vinculadas al catálogo.')
