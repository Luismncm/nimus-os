import streamlit as st
from services import origin,inventory
from views.common import managed_dialog,perform
from views.catalog_forms import component_label
from views.emoji import tag

def focus(panel,identity=None,group=None):st.session_state['origin_focus']=dict(panel=panel,identity=identity,group=group)

def lamp_form(product=None,template=None,shade_id=None,base_set_id=None):
    st.session_state['origin_builder_request']=dict(product=product,template=template,shade_id=shade_id,base_set_id=base_set_id)
    st.session_state.pop('active_dialog',None)
    st.switch_page('views/origen.py')

@managed_dialog('Nuevo color de base',width='medium')
def base_form():
    st.text('Modelo: '+origin.BASE_MODEL)
    st.caption('Agrega una variante de color a este modelo. Se crearán juntas BASE, CAP y TAPA del mismo color y material, compatibles con los modelos de pantalla.')
    with st.form('origin_base_form'):
        color=st.text_input('Color *',placeholder='Nombre del acabado',key='origin_base_color')
        material=st.text_input('Material *',placeholder='Filamento y acabado',key='origin_base_material')
        if st.form_submit_button('Agregar color de base',type='primary',width='stretch'):
            perform(origin.create_base_set,color,material,after=lambda _:focus('Componentes',group='Base y colores'),message='Color de base agregado al mismo modelo. Registra existencias cuando tengas piezas físicas.')

@managed_dialog('Componente de Colección Origen',width='medium')
def origin_component_form(role='Pantalla'):
    prefix='origin_component_'+st.session_state['dialog_request_key']
    if role=='Insumo':role=st.selectbox('Tipo de insumo',origin.PURCHASED,key=prefix+'_role')
    st.text(role)
    with st.form(prefix):
        shape=st.text_input('Modelo / forma *',key=prefix+'_shape') if role=='Pantalla' else ''
        color=st.text_input('Color',key=prefix+'_color') if role=='Pantalla' else ''
        material=st.text_input('Material *' if role=='Pantalla' else 'Material / especificación',key=prefix+'_material')
        variant=st.text_input('Tamaño / especificación',key=prefix+'_variant',placeholder='Detalle que diferencia esta referencia')
        if st.form_submit_button('Guardar componente',type='primary',width='stretch'):
            perform(origin.create_component,role,material=material,color=color,shape=shape,variant=variant,
                after=lambda _:focus('Componentes',group='Pantallas' if role=='Pantalla' else 'Insumos'),message='Componente registrado. Aún no tiene existencias.')

@managed_dialog('Registrar existencias Origen',width='medium')
def receipt_form(component):
    st.text(component_label(component))
    st.caption(component['role']+' · '+('Insumo comprado' if component['supply']=='Comprar' else 'Pieza fabricada'))
    operation=st.segmented_control('Registrar como',('Entrada física','Pedido'),default='Entrada física',key='origin_receipt_operation',width='stretch', format_func=tag) or 'Entrada física'
    planned=operation=='Pedido'
    with st.form('origin_receipt'):
        quantity=st.number_input('Unidades pedidas' if planned else 'Unidades físicas que ingresan',min_value=1,value=1,step=1,key='origin_receipt_qty')
        reason=st.text_input('Referencia del pedido *' if planned else 'Motivo / referencia *',placeholder='Referencia de compra' if planned else 'Compra recibida o piezas contadas',key='origin_receipt_reason')
        from views.collection_forms import inbound_fields,focus_inbound
        from services import inbound
        extra=inbound_fields('origin_pending') if planned else {}
        if not planned:st.caption('La entrada se guarda en Almacén. No crea gastos ni pagos. Los pedidos podrán reservar estas unidades.')
        if st.form_submit_button('Guardar pedido' if planned else 'Registrar entrada',type='primary',width='stretch'):
            if planned:
                perform(inbound.create,quantity,'Stock',reason,component_id=component['id'],request_key=st.session_state['dialog_request_key'],**extra,
                    after=focus_inbound,navigate='views/collection.py',message='Pedido y gasto registrados. Recíbelo al llegar.')
            else:
                perform(inventory.receive_manual,quantity,'Stock',reason,component_id=component['id'],request_key=st.session_state['dialog_request_key'],
                    after=lambda _:focus('Inventario',component['id']),message='Existencias registradas. Revisa las reservas de los pedidos pendientes.')
