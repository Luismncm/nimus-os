"""Native inventory controls grouped around each piece."""
import streamlit as st
from services.inventory_view import query, location, movement_state, label
from services.inventory import INVENTORY_FIELDS, MOVEMENT_FIELDS
from services.queries import csv_bytes
from utils.dates import fmt
from views.common import table,picks
from views.collection_forms import manual_entry_form, found_stock_form, open_distribution, reversal_form, PLACES
from views.catalog_forms import link_inventory_form
from views.navigation import open_order


# One emoji per state, place and kind of movement, the same in tables, badges and forms.
STATE_ICONS = {'Disponible': '🟢', 'Reservada': '🟠', 'En clientes': '🤝', 'Sin saldo': '⚪'}
PLACE_ICONS = {**PLACES, 'B2B': '🤝 Cliente B2B', 'Producción': '🏭 Producción', 'Externo': '📦 Entrada externa', 'Entregado': '✅ Entregado'}
KIND_ICONS = {'Entrada manual': '📦', 'Traslado': '🔁', 'B2B': '🤝', 'Reversión': '↩️', 'Producción': '🏭', 'Entrega': '✅', 'Corrección': '✏️'}
PHASE_ICONS = {'A punto de salir': '⏳', 'Imprimiendo': '🖨️', 'Por imprimir': '🕒'}


def found_preset(row):
    """The found-stock line for this inventory row: its catalog piece, or the reference itself."""
    return dict(component_id=row['component_id']) if row.get('component_id') else dict(sku_id=row['id'])


def reset_filters(prefix='inventory'):
    st.session_state.update({f'{prefix}_model':'Todos',f'{prefix}_search':'',f'{prefix}_line':'Todas',f'{prefix}_state':'Todos'})


def overview_help():
    with st.popover('Cómo leer los saldos',icon=':material/help_outline:'):
        st.write('**Disponibles + Reservadas = En taller.**\n\n**Disponibles:** libres para mover, reservar o tomar para un pedido.\n\n**Reservadas:** apartadas para un pedido; siguen en el taller.\n\n**En clientes B2B:** asignadas a un cliente; no cuentan en el taller.\n\n**En camino:** excedente de impresiones que aún no terminan.')
        st.caption('Las cifras cuentan componentes, no lámparas completas. Cada pieza está en Por distribuir (Colección) o en Almacén (Stock). B2B no confirma envío ni facturación.')


def balance_row(rows, incoming, *, scope='el taller'):
    """One count, read left to right: what can be moved now, what is promised to orders, and the two add up to what is in the workshop."""
    from services.inventory_view import totals
    summary=dict(totals(rows),incoming=sum(r['free'] for r in incoming))
    for col,field,label,icon,help in zip(st.columns(5),('free','reserved','physical','b2b','incoming'),
            ('Disponibles','Reservadas','En taller','En clientes B2B','En camino'),('check_circle','bookmark','inventory_2','storefront','local_shipping'),
            ('Piezas libres: se pueden mover, reservar o tomar para un pedido.','Apartadas para pedidos; siguen en el taller.',
             f'Disponibles + Reservadas: todo lo que hay físicamente en {scope}.','Asignadas a un cliente; ya no cuentan en el taller.',
             'Se imprimen ahora para inventario (excedente de pedidos y stock directo); entran al terminar.')):
        col.metric(label,summary[field],border=True,icon=f':material/{icon}:',help=help)


# Where each kind of piece is managed: Colección Origen keeps its own inventory and these panels.
ORIGIN_PANELS={'Bases por color':'Bases por color','Reposición de insumos':'Insumos y reposición'}


def open_origin_inventory(panel='Piezas', selected=None):
    """Colección Origen → Inventario, on one of its panels and optionally with a piece selected."""
    st.session_state.update(origin_workspace='Inventario',origin_inventory_view=panel)
    if selected is not None:st.session_state['origin_stock_selected']=selected
    st.switch_page('views/origen.py')


def take_focus(data, *, origin):
    """A just-registered entry selects its piece; one of the other line moves to that page first.

    Returns (sku_id, panel to show) for this page, or None.
    """
    movement_id=st.session_state.get('inventory_focus_movement')
    if not movement_id:return None
    movement=next((m for m in data['movements'] if m['id']==movement_id),None)
    sku=next((s for s in data['skus'] if movement and s['id']==movement['sku_id']),None)
    if not sku:
        st.session_state.pop('inventory_focus_movement',None);return None
    if is_origin(sku)!=origin:
        st.switch_page('views/origen.py' if is_origin(sku) else 'views/collection.py')
    st.session_state.pop('inventory_focus_movement',None)
    return sku['id'],st.session_state.pop('inventory_return_workspace',None)


def empty_inventory():
    with st.container(border=True):
        st.subheader('Empieza con tus piezas físicas',icon=':material/inventory_2:')
        st.info('Tu inventario está vacío. Anota lo que tienes en los estantes o registra la producción al terminarla.')
        a,b=st.columns(2)
        with a:
            st.markdown('**📦 Ya tengo piezas**')
            st.caption('Anota varias piezas a la vez: pieza, cantidad y dónde están.')
            if st.button('📦 Registrar stock encontrado',key='inventory_empty_receive',type='primary'): found_stock_form()
        with b:
            st.markdown('**🖨️ Voy a fabricarlas**')
            st.caption('Crea un pedido y registra las unidades terminadas. Las piezas destinadas a Origen aparecerán aquí.')
            st.page_link('views/orders.py',label='Ir a producción',icon=':material/arrow_forward:')
        st.caption('Catálogo y recetas definen componentes. Las existencias son sus unidades físicas registradas.')
        st.page_link('views/catalog.py',label='Preparar recetas y fotografías del catálogo',icon=':material/photo_library:')


# The same piece management serves the general inventory (prefix "inventory") and Colección Origen (its own prefix),
# so each page keeps its own search, filters and selected piece.
def stock_filters(rows, prefix='inventory'):
    with st.container(border=True):
        a,b=st.columns([2,1])
        search=a.text_input('Buscar en inventario',key=f'{prefix}_search',placeholder='Pieza, material, modelo o código',icon=':material/search:',persist_state='session')
        state=b.selectbox('Mostrar',('Todos','Con disponibles','Con reservas','Sin saldo'),key=f'{prefix}_state',persist_state='session')
        with st.popover('Modelo',icon=':material/filter_alt:'):
            models=['Todos',*sorted({r['product'] for r in rows})]
            names={r['product']:f"Catálogo · {r['label']} · {r['material'] or 'Sin material'} · {r['code']}" if r['component_id'] else r['product'] for r in rows}
            if st.session_state.get(f'{prefix}_model','Todos') not in models: st.session_state[f'{prefix}_model']='Todos'
            model=st.selectbox('Modelo / referencia',models,key=f'{prefix}_model',format_func=lambda v:names.get(v,v),persist_state='session')
        active=[v for v in (search,names.get(model,model),state) if v not in ('','Todos','Todas')]
        if active:
            st.caption('Consulta: '+' · '.join(active))
            st.button('Limpiar filtros',key=f'{prefix}_clear',type='tertiary',icon=':material/filter_alt_off:',on_click=reset_filters,args=(prefix,))
    return query(rows,search=search,model=model,state=state)


def piece_detail(rows, prefix='inventory'):
    if not rows:
        st.caption('Selecciona otra consulta para gestionar una pieza.'); return
    lookup={r['id']:r for r in rows}
    if st.session_state.get(f'{prefix}_selected') not in lookup: st.session_state[f'{prefix}_selected']=next(iter(lookup))
    with st.container(border=True,key=f'panel-{prefix}-piece'):
        st.subheader('Pieza seleccionada',icon=':material/category:')
        identity=st.selectbox('Pieza para gestionar',list(lookup),key=f'{prefix}_selected',format_func=lambda i:f"{lookup[i]['label']} · {lookup[i]['material'] or 'Sin material'} · {lookup[i]['code']}")
        row=lookup[identity]
        from views.photo_forms import photo_panel
        from services import photos
        photo_panel('sku',identity,row['part'],key=f'{prefix}_photo',fallback=photos.get('component',row['component_id']) if row['component_id'] else None)
        st.markdown(f"**{row['label']}** :gray[· {row['material'] or 'Sin material'} · {row['process']}]")
        st.caption(f"{row['reference']} · {row['collection']}")
        # The whole count in one line, then where it sits: no table to open.
        with st.container(horizontal=True,gap='xxsmall'):
            st.badge(f"🟢 {row['free']} libres",color='green' if row['free'] else 'gray')
            st.badge(f"🟠 {row['reserved']} reservadas",color='orange' if row['reserved'] else 'gray')
            st.badge(f"📦 {row['physical']} en taller",color='blue' if row['physical'] else 'gray')
        st.caption(f"{PLACES['Colección']} {row['unassigned']} ({row['available_collection']} libres) · {PLACES['Stock']} {row['stock']} ({row['available_stock']} libres)")
        if st.button('🔁 Mover o asignar',key=f'{prefix}_distribute',type='primary',width='stretch',disabled=row['free']<=0): open_distribution(row)
        with st.container(horizontal=True,gap='small'):
            if st.button('📦 Encontré más',key=f'{prefix}_receive_selected',width='stretch',help='Suma piezas que encontraste en los estantes.'):
                found_stock_form(found_preset(row))
            if st.button('🚚 Pedir',key=f'{prefix}_order_selected',width='stretch',help='Registra un pedido a proveedor; entra al inventario al recibirlo.'):
                manual_entry_form(row['id'],entry_type='Pedido')
        from services import inbound
        pending=[p for p in inbound.list_orders() if p['sku_id']==row['id'] and p['pending']]
        if pending:
            st.caption(f"{sum(p['pending'] for p in pending)} unidades pedidas, pendientes de recibir.")
            if st.button('Ver pedido pendiente',key=f'{prefix}_pending_open',type='tertiary'):
                from views.inbound_ui import open_order
                open_order(pending[0]['id'])
        if row['component_id']:
            with st.expander('Costo de esta pieza',icon=':material/calculate:'):
                from services import costing,recipes
                from services.quotations import money
                from views.costing_forms import component_cost_form
                profile=costing.component_profile(row['component_id'])
                estimate=costing.component_amount(profile['data'] if profile else costing.component_defaults(row['component_id']))
                st.metric('Costo estimado por pieza · MXN',money(estimate['total_cents']) if estimate['total_cents'] is not None else 'Pendiente')
                if estimate['missing']:st.caption('Por completar: '+', '.join(estimate['missing']))
                st.caption('La referencia se comparte con las recetas que usan este componente.')
                if st.button('Calcular / editar costo',key=f'{prefix}_component_cost',width='stretch',icon=':material/calculate:'):
                    component=next(c for c in recipes.load_catalog()['components'] if c['id']==row['component_id'])
                    component_cost_form(component,profile,printing=component['process'] in ('Impresión 3D','Resina'))
        with st.popover('Referencia y vínculos',icon=':material/info:',width='stretch'):
            st.caption(f"{row['b2b']} en clientes B2B · {row['delivered']} entregadas registradas\n\nReferencia: {row['code']}")
            if row['component_id']: st.caption(f"Catálogo CMP-{row['component_id']:04d}. Se comparte entre las recetas que usan este componente.")
            elif st.button('Vincular al catálogo',key=f'{prefix}_link',icon=':material/link:'): link_inventory_form(row)
        if row['free']<=0: st.caption('Necesitas unidades libres para mover esta pieza. Registra una entrada o revisa sus reservas.')


def stock_panel(rows, prefix='inventory', *, title='Piezas en inventario'):
    filtered=stock_filters(rows,prefix)
    view=st.segmented_control('Visualización',('Tabla y ficha','Galería'),default=None if f'{prefix}_view' in st.session_state else 'Tabla y ficha',key=f'{prefix}_view',persist_state='session',
                              label_visibility='collapsed',format_func=lambda v:{'Tabla y ficha':'📋 Tabla y ficha','Galería':'🖼️ Galería'}[v]) or 'Tabla y ficha'
    if view=='Galería':
        gallery(filtered,prefix)
        return
    left,right=st.columns([1.6,1],gap='medium')
    with left:
        st.subheader(f'{title} · {len(filtered)} referencias',icon=':material/inventory_2:')
        if not filtered: st.info('No hay piezas para estos filtros. Cambia la búsqueda o el modelo.')
        table([dict(r,shown_state=f"{STATE_ICONS.get(r['state'],'')} {r['state']}") for r in filtered],
              {'shown_state':'Estado','part':'Pieza','model':'Modelo','material':'Material','free':'🟢 Libres','reserved':'🟠 Reservadas','physical':'📦 En taller','b2b':'🤝 B2B'},
              label='Existencias disponibles, reservadas y asignadas por pieza',open=picks(f'{prefix}_selected'),key=f'{prefix}_stock_table')
        if filtered: st.caption('Toca una fila para verla en la ficha de la derecha, con sus ubicaciones y acciones.')
        with st.expander('Ver desglose completo y exportar',icon=':material/table_chart:'):
            table(filtered,{'code':'Referencia','reference':'Modelo / uso','part':'Pieza','model':'Modelo','material':'Material','process':'Proceso','unassigned':'Físico por distribuir','stock':'Físico almacén','available_collection':'Libre por distribuir','available_stock':'Libre almacén','reserved':'Reservadas','b2b':'B2B'},label='Desglose completo de inventario')
            st.download_button('Exportar inventario CSV',csv_bytes(filtered,INVENTORY_FIELDS),file_name=f'nimus_{prefix}.csv',mime='text/csv',icon=':material/download:',disabled=not filtered,key=f'{prefix}_export')
    with right: piece_detail(filtered,prefix)


def gallery(rows, prefix='inventory'):
    from services import photos
    from views.photo_forms import photo_panel
    if not rows: st.info('No hay referencias para estos filtros.');return
    limit=st.session_state.get(f'{prefix}_gallery_limit',12)
    for start in range(0,min(limit,len(rows)),3):
        for col,row in zip(st.columns(3),rows[start:min(start+3,limit)]):
            with col,st.container(border=True):
                st.text(row['label'])
                st.caption(f"{row['material'] or 'Sin material'} · {row['code']}")
                photo_panel('sku',row['id'],row['part'],key=f"{prefix}_gallery_photo_{row['id']}",fallback=photos.get('component',row['component_id']) if row['component_id'] else None,width='stretch',gallery=True)
                st.badge(f"🟢 {row['free']} libres · 🟠 {row['reserved']} reservadas",color='green' if row['free'] else 'gray')
                st.button('Gestionar pieza',key=f"{prefix}_gallery_open_{row['id']}",width='stretch',on_click=select_gallery_piece,args=(row['id'],prefix))
    if len(rows)>limit and st.button('Ver más referencias',key=f'{prefix}_gallery_more'):
        st.session_state[f'{prefix}_gallery_limit']=limit+12;st.rerun()


def select_gallery_piece(identity, prefix='inventory'):
    st.session_state[f'{prefix}_selected']=identity
    st.session_state[f'{prefix}_view']='Tabla y ficha'


def is_origin(row):
    """Colección Origen pieces live in their own inventory; everything else in the general one."""
    return (row.get('collection') or '')=='Origen'


PHASES=('A punto de salir','Imprimiendo','Por imprimir')


def incoming_rows(snapshot, origin=None):
    """Units on their way to inventory: the extra of prints not finished and stock printed straight to inventory.

    Phase: Por imprimir (queued), Imprimiendo, A punto de salir (printing and due within two hours).
    """
    from datetime import timedelta
    from services.piece_stock import _eta
    from services.timeline import when
    from utils.dates import now
    rows=[]
    for j in snapshot['jobs']:
        if j['status']=='Terminado' or j['order_status']=='Entregado':continue
        if origin is not None and (j.get('collection')=='Origen')!=origin:continue
        extra=j.get('extra',0) if not j.get('extra_posted') else 0
        direct=bool(j.get('stock_run'))
        if not extra and not direct:continue
        eta=_eta(j)
        phase='Por imprimir' if j['status']!='En producción' else 'A punto de salir' if eta and eta<=now()+timedelta(hours=2) else 'Imprimiendo'
        rows.append(dict(phase=phase,origin='Stock directo' if direct else 'Excedente',part=j['part_name'],material=j['material'] or 'Sin material',model=j['item_name'],
                         job=j['code'],machine=j['machine_code'] or 'Sin máquina',status=j['status'],eta=when(eta) if eta else 'Sin horario',
                         free=(j['quantity']-j['quantity_completed'] if direct else 0)+extra,riders=sum(r['quantity'] for r in j.get('riders',[]))))
    return sorted(rows,key=lambda r:(PHASES.index(r['phase']),r['job']))


def incoming_panel(snapshot, origin=None):
    rows=incoming_rows(snapshot,origin)
    if not rows:return
    st.subheader(f"Por entrar a inventario · {sum(r['free'] for r in rows)} piezas",icon=':material/local_shipping:')
    st.caption('Lo que aún se imprime y llegará a Colección al terminar: el excedente de impresiones de pedidos y el stock directo. '
               'Antes de que termine, otro pedido de la misma pieza puede sumarse a esa impresión en lugar de imprimir aparte.')
    with st.container(horizontal=True,gap='small'):
        for phase,color in zip(PHASES,('green','blue','gray')):
            units=sum(r['free'] for r in rows if r['phase']==phase)
            st.badge(f'{PHASE_ICONS[phase]} {phase} · {units}',color=color if units else 'gray')
    table([dict(r,phase=f"{PHASE_ICONS[r['phase']]} {r['phase']}") for r in rows],{'phase':'Fase','origin':'Origen','part':'Pieza','material':'Material','model':'Modelo','job':'Impresión','machine':'Máquina','eta':'Termina','free':'Entran','riders':'Ya tomadas por otros pedidos'},
          label='Piezas que todavía se imprimen y entrarán a inventario')


def reservations_panel(data,snapshot):
    rows=data['reservations']
    st.subheader('Reservas por pedido',icon=':material/bookmark:')
    st.caption('Piezas apartadas para un pedido. Siguen en el taller, pero ya no cuentan como disponibles.')
    if not rows: st.info('No hay reservas activas.')
    table([dict(r,place=location(r['location']),piece=label(r)) for r in rows],{'order_code':'Pedido','project':'Proyecto','piece':'Pieza','material':'Material','place':'Ubicación','quantity':'Reservadas'},label='Piezas reservadas para pedidos activos')
    owners={o['code']:o for o in snapshot['orders'] if any(r['order_code']==o['code'] for r in rows)}
    if owners:
        if st.session_state.get('inventory_reserved_order') not in owners: st.session_state['inventory_reserved_order']=next(iter(owners))
        code=st.selectbox('Pedido para consultar',list(owners),key='inventory_reserved_order')
        if st.button('Abrir pedido',key='inventory_reserved_open',icon=':material/arrow_forward:'): open_order(owners[code]['id'])
    st.caption('Consulta el pedido para ver cómo se reservan o consumen sus componentes.')


def clients_panel(data):
    st.subheader('Clientes B2B',icon=':material/storefront:')
    st.caption('Piezas asignadas a un cliente o distribuidor. Salen del conteo del taller.')
    search=st.text_input('Buscar cliente B2B',key='inventory_client_search',placeholder='Cliente o distribuidor',icon=':material/search:')
    rows=[r for r in data['clients'] if search.strip().casefold() in r['client'].casefold()]
    if not rows: st.info('No hay asignaciones de clientes para esta consulta.')
    table([dict(r,piece=label(r)) for r in rows],{'client':'Cliente','piece':'Pieza','material':'Material','product':'Modelo / referencia','quantity':'Asignadas'},label='Piezas asignadas a clientes B2B')
    st.caption('La asignación registra un destino. La entrega física y facturación se confirman en sus procesos correspondientes.')


def history_panel(data):
    st.subheader('Movimientos de inventario',icon=':material/history:')
    st.caption('Entradas, traslados, reservas y correcciones; cada cambio de saldo deja su registro.')
    search=st.text_input('Buscar movimiento',key='inventory_history_search',placeholder='Folio, pieza, modelo, cliente o referencia',icon=':material/search:')
    rows=[r for r in data['movements'] if search.strip().casefold() in ' '.join(str(r.get(k) or '') for k in ('code','product','part','variant','material','client','job_code','order_code','notes')).casefold()]
    table([dict(r,piece=label(r),date=fmt(r['created_at'],time=True),kind=f"{KIND_ICONS.get(r['kind'],'•')} {r['kind']}",
                route=f"{PLACE_ICONS.get(r['source'],location(r['source']))} → {PLACE_ICONS.get(r['destination'],location(r['destination']))}",state=movement_state(r)) for r in rows],{'code':'Movimiento','date':'Fecha','kind':'Tipo','piece':'Pieza','quantity':'Cantidad','route':'Trayecto','state':'Estado'},label='Entradas, traslados y correcciones de inventario')
    if not rows: st.info('No hay movimientos para esta consulta.')
    with st.expander('Detalle, correcciones y exportación',icon=':material/manage_search:'):
        table(rows,{'code':'Movimiento','product':'Modelo','material':'Material','client':'Cliente','job_code':'Trabajo','order_code':'Pedido','notes':'Referencia / notas','reversal_of':'Revierte a #','reversed_by':'Revertido por #'},label='Referencias completas de los movimientos')
        reversible={r['id']:r for r in rows if r['kind'] in ('Traslado','B2B','Entrada manual') and not r['order_id'] and not r['reversed_by']}
        if reversible:
            if st.session_state.get('inventory_reverse_selected') not in reversible: st.session_state['inventory_reverse_selected']=next(iter(reversible))
            identity=st.selectbox('Movimiento para corregir',list(reversible),key='inventory_reverse_selected',format_func=lambda i:f"{reversible[i]['code']} · {reversible[i]['quantity']} {label(reversible[i])} · {location(reversible[i]['source'])} → {location(reversible[i]['destination'])}")
            if st.button('Revertir movimiento',key='inventory_reverse',icon=':material/undo:'): reversal_form(reversible[identity])
        st.download_button('Exportar movimientos CSV',csv_bytes(rows,MOVEMENT_FIELDS),file_name='nimus_movimientos_origen.csv',mime='text/csv',icon=':material/download:',disabled=not rows)
        st.caption('La reversión conserva ambos registros. Los ingresos de producción se corrigen desde su trabajo.')
