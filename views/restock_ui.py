"""Quiet replenishment signals and one batch editor, with no hover help or popups."""
import hashlib,json
import streamlit as st
from services import restock
from views.common import table,perform,picks
from views.navigation import open_order
from views.emoji import tag

PANEL='Reposición de insumos'

def open_restock(component_id=None):
    """Supplies are Colección Origen components: their replenishment lives in Colección Origen → Inventario."""
    from views.inventory_ui import open_origin_inventory
    st.session_state['restock_focus_component']=component_id
    open_origin_inventory('Insumos y reposición')

def plan_note(plan):
    rows=restock.projection(plan);negative=[r for r in rows if r['net_after']<0]
    if not negative:return
    st.badge(f'{len(negative)} insumos con saldo negativo al emitir',color='red')
    st.caption('Puedes emitir el pedido. Los faltantes quedan comprometidos y se señalan para reposición; el conteo físico se conserva.')
    with st.expander('Ver saldo de insumos al emitir'):
        table(rows,{'name':'Insumo','variant':'Especificación','net':'Saldo neto actual','needed':'Este pedido','net_after':'Saldo al emitir','minimum':'Mínimo'},label='Saldo neto previsto de insumos al emitir este pedido')

def panel():
    rows=restock.rows()
    st.subheader('Reposición de insumos',icon=':material/inventory_2:')
    st.caption('Saldo neto = físico en taller − reservas − necesidades sin cubrir de pedidos abiertos. Puede ser negativo y permite emitir pedidos. Rojo: faltantes; ámbar: mínimo alcanzado. No se envían avisos emergentes.')
    if not rows:
        st.caption('Agrega insumos en Colección Origen → Componentes → Insumos para definir sus mínimos.')
        st.page_link('views/origen.py',label='Abrir Colección Origen',icon=':material/light:');return
    focus=st.session_state.get('restock_focus_component')
    mode=st.segmented_control('Ver insumos',('Todos','Por reponer','En negativo'),default='Todos',key='restock_filter',persist_state='session', format_func=tag) or 'Todos'
    shown=[r for r in rows if mode=='Todos' or mode=='Por reponer' and r['attention'] or mode=='En negativo' and r['critical']]
    table(shown,{'code':'Referencia','name':'Insumo','variant':'Especificación','physical':'Físico','reserved':'Reservado','pending':'Sin cubrir','net':'Disponible neto','minimum':'Mínimo','on_order':'En pedido','replenish':'Reposición sugerida','state':'Atención'},label='Mínimos, faltantes y saldo neto de insumos',
          open=picks('restock_selected'),key='restock_table')
    st.caption('La reposición sugerida cubre el faltante y supera el mínimo configurado en una unidad. Mínimo 0 desactiva el aviso de mínimo; un saldo negativo siempre se señala.')
    with st.expander('Configurar cantidades mínimas',key='restock_minimum_panel',expanded=not any(r['minimum'] for r in rows)):
        if 'restock_minimum_draft' not in st.session_state:
            st.session_state['restock_minimum_draft']=[dict(r) for r in sorted(rows,key=lambda r:r['id'])]
        draft=st.session_state['restock_minimum_draft']
        version=hashlib.sha256(json.dumps([(r['id'],r['minimum_revision']) for r in draft]).encode()).hexdigest()[:12]
        grid=[dict(component_id=r['id'],name=r['name'],variant=r['variant'],minimum=r['minimum']) for r in draft]
        if st.button('Actualizar mínimos guardados',key='restock_minimum_reload',type='tertiary'):
            st.session_state.pop('restock_minimum_draft',None);st.rerun()
        with st.form('restock_minimum_form'):
            edited=st.data_editor(grid,hide_index=True,num_rows='fixed',key='restock_editor_'+version,
                disabled=['component_id','name','variant'],column_order=['name','variant','minimum'],
                column_config={'name':st.column_config.TextColumn('Insumo'),'variant':st.column_config.TextColumn('Especificación'),
                    'minimum':st.column_config.NumberColumn('Cantidad mínima',min_value=0,max_value=1000000,step=1,required=True)},
                alt='Editar cantidades mínimas de insumos en una sola captura')
            if st.form_submit_button('Guardar mínimos',type='primary'):
                revisions={r['id']:r['minimum_revision'] for r in draft}
                changes=[dict(component_id=e['component_id'],minimum=e['minimum'],expected_revision=revisions[e['component_id']]) for e in edited]
                perform(restock.save_minimums,changes,after=lambda _:st.session_state.pop('restock_minimum_draft',None),message='Mínimos de reposición guardados.')
    if shown:
        by_id={r['id']:r for r in shown}
        if focus in by_id:st.session_state['restock_selected']=focus;st.session_state.pop('restock_focus_component',None)
        if st.session_state.get('restock_selected') not in by_id:st.session_state['restock_selected']=next(iter(by_id))
        cid=st.selectbox('Insumo para revisar',list(by_id),key='restock_selected',format_func=lambda i:by_id[i]['name']+' · '+by_id[i]['variant'])
        row=by_id[cid]
        if row['attention']:st.badge(row['state']+f" · saldo {row['net']}",color='red' if row['critical'] else 'orange')
        if row['on_order']:st.caption(f"{row['on_order']} unidades en pedidos pendientes de recibir. Se cuentan físicamente al llegar.")
        # The same entry form as any piece of inventory: counted now, or ordered to arrive later.
        from views.collection_forms import manual_entry_form
        with st.container(horizontal=True,gap='small'):
            if st.button('Pedir reposición',key='restock_order_supply',icon=':material/local_shipping:',type='primary' if row['attention'] else 'secondary'):
                manual_entry_form(component_id=cid,entry_type='Pedido',default_quantity=max(1,row['replenish']-row['on_order']),return_workspace='Insumos y reposición')
            if st.button('Registrar entrada física',key='restock_receive',icon=':material/add:'):
                manual_entry_form(component_id=cid,return_workspace='Insumos y reposición')
        with st.expander('Pedidos que comprometen este insumo',key='restock_orders'):
            table([dict(r,pending=max(0,r['quantity']-r['covered'])) for r in row['orders']],{'code':'Pedido','project':'Proyecto','deadline':'Entrega','quantity':'Necesarias','covered':'Cubiertas','pending':'Sin cubrir'},label='Pedidos abiertos que comprometen el insumo seleccionado')
            owners={r['order_id']:r for r in row['orders']}
            if owners:
                if st.session_state.get('restock_order') not in owners:st.session_state['restock_order']=next(iter(owners))
                oid=st.selectbox('Pedido relacionado',list(owners),key='restock_order',format_func=lambda i:owners[i]['code'])
                if st.button('Abrir pedido',key='restock_order_open'):open_order(oid)
