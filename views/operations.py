import streamlit as st
from services import operations
from views.common import perform, table


def stage_checks(order, prefix):
    readonly=order['status']=='Entregado'
    with st.container(horizontal=True,gap='large'):
        for stage,label in operations.STAGES.items():
            row=order['stages'][stage]
            checked=bool(row['checked_at'])
            value=st.checkbox(label,value=checked,disabled=readonly,key=f'{prefix}_stage_{order["id"]}_{stage}_{row["revision"]}')
            if value!=checked:
                perform(operations.set_stage,order['id'],stage,value,expected_revision=row['revision'],message=f'{label}: actualizado.')


def stage_actions(order, prefix):
    readonly=order['status']=='Entregado'
    required=('revision',) if order.get('fulfillment')=='Stock' else tuple(operations.STAGES)
    st.caption('Avanza marcando los pasos realizados. Puedes corregir una marca desde sus opciones.')
    with st.container(horizontal=True,gap='small'):
        for stage in required:
            row=order['stages'][stage];checked=bool(row['checked_at']);label=operations.STAGES[stage]
            if st.button('Completado: '+label if checked else 'Marcar '+label.lower(),key=f'{prefix}_advance_{order["id"]}_{stage}_{row["revision"]}',
                         disabled=readonly or checked,type='secondary' if checked else 'primary',icon=':material/check_circle:' if checked else ':material/arrow_forward:'):
                perform(operations.set_stage,order['id'],stage,True,expected_revision=row['revision'],message=label+' registrada.')
    with st.popover('Corregir marcas de preparación',icon=':material/undo:',disabled=readonly):
        stage_checks(order,prefix)


def item_check(item, readonly, prefix):
    checked=bool(item['checked_at'])
    value=st.checkbox(f"{item['name']} · "+('ensamblado y revisado' if item.get('is_origin_lamp') else 'revisado'),value=checked,disabled=readonly,
                      key=f'{prefix}_item_check_{item["id"]}_{item["tracking_revision"]}')
    if value!=checked:
        perform(operations.update_item,item['id'],checked=value,expected_revision=item['tracking_revision'],message='Check del item actualizado.')


def item_label_form(item, readonly, prefix):
    labels=sorted({i['label'] for i in st.session_state['snapshot']['items'] if i['label']})
    with st.popover('Etiqueta',icon=':material/label:',disabled=readonly):
        with st.form(f'{prefix}_label_form_{item["id"]}'):
            label=st.selectbox('Etiqueta del item',labels,index=labels.index(item['label']) if item['label'] in labels else None,
                accept_new_options=True,placeholder='Ej. Caja 2, B2B, frágil…',key=f'{prefix}_label_{item["id"]}_{item["tracking_revision"]}')
            if st.form_submit_button('Guardar etiqueta',type='primary'):
                perform(operations.update_item,item['id'],label=label or '',expected_revision=item['tracking_revision'],message='Etiqueta guardada.')
            if item['label'] and st.form_submit_button('Quitar etiqueta'):
                perform(operations.update_item,item['id'],label='',expected_revision=item['tracking_revision'],message='Etiqueta retirada.')


def order_checklist(order, prefix, detailed=False, expanded=False, actions=False):
    if actions: stage_actions(order,prefix)
    else: stage_checks(order,prefix)
    checked=sum(bool(i['checked_at']) for i in order['items'])
    st.caption(f"{checked}/{len(order['items'])} productos revisados · control manual; no modifica producción ni inventario.")
    if actions and order['items'] and checked<len(order['items']):
        label='Confirmar lámparas ensambladas y revisadas' if any(i.get('is_origin_lamp') for i in order['items']) else 'Marcar todos los productos revisados'
        if st.button(label,key=f'{prefix}_review_all_{order["id"]}',disabled=order['status']=='Entregado',icon=':material/done_all:'):
            perform(operations.review_products,order['id'],{i['id']:i['tracking_revision'] for i in order['items']},message='Productos marcados como revisados.')
    if order['status'] not in ('Listo','Entregado') and any(s['checked_at'] for s in order['stages'].values()):
        st.caption('Hay etapas marcadas, pero todavía faltan piezas, insumos o resolver un bloqueo. Revisa ambos controles antes de entregar.')
    if detailed:
        with st.expander('Revisión de productos',expanded=expanded,key=f'{prefix}_checklist_{order["id"]}',on_change='rerun'):
            for item in order['items']:
                with st.container(horizontal=True,vertical_alignment='center'):
                    item_check(item,order['status']=='Entregado',prefix)
                    if item['label']:st.badge(item['label'],color='blue')
                    item_label_form(item,order['status']=='Entregado',prefix)
            if not order['items']:st.caption('Agrega el primer item al pedido.')
        with st.expander('Historial de checks y etiquetas',key=f'{prefix}_history_{order["id"]}',on_change='rerun'):
            if st.session_state.get(f'{prefix}_history_{order["id"]}',False):
                table(operations.history(order['id']),{'created_at':'Fecha','detail':'Cambio'},label='Historial de seguimiento')
