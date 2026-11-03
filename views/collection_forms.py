import uuid
from functools import partial

import streamlit as st

from services import inventory,inbound
from utils.dates import now
from views.common import managed_dialog, perform
from views.properties import property_select
from services.recipes import load_catalog
from models.constants import PROCESSES
from services.inventory_view import location
from views.purchase_forms import financial_fields
from views.emoji import tag


def focus_entry(movement_id,workspace=None):
    st.session_state['inventory_focus_movement']=movement_id
    if workspace:
        st.session_state['inventory_return_workspace']=workspace


def focus_inbound(identity):st.session_state['inventory_inbound_focus']=identity


def inbound_fields(prefix):
    a,b=st.columns(2)
    supplier=a.text_input('Proveedor',key=prefix+'_supplier',placeholder='Opcional')
    expected=b.date_input('Llegada prevista',value=None,key=prefix+'_expected')
    financial=financial_fields(prefix)
    with st.expander('Fecha del pedido y seguimiento · opcional'):
        ordered=st.date_input('Fecha del pedido',value=now().date(),max_value=now().date(),key=prefix+'_ordered')
        notes=st.text_input('Notas / seguimiento inicial',key=prefix+'_notes',placeholder='Guía, contacto o condiciones de entrega')
    return dict(supplier=supplier,ordered_on=ordered,expected_on=expected,notes=notes,financial=financial)


KINDS=('Piezas e insumos','Filamento y consumibles')


@managed_dialog('Agregar inventario', width='medium')
def manual_entry_form(sku_id=None,*,component_id=None,entry_type='Entrada física',default_quantity=1,return_workspace=None,
                      kind='Piezas e insumos',consumable_id=None) -> None:
    prefix = 'receipt_' + st.session_state['dialog_request_key']
    # One entry point for everything that comes in: pieces/supplies counted in units, consumables in g, ml or pieces.
    kind=st.segmented_control('Qué agregas',KINDS,default=kind,key=prefix+'_kind',width='stretch') or kind
    operation=st.segmented_control('Registrar como',('Entrada física','Pedido'),default=entry_type,key=prefix+'_operation',width='stretch', format_func=tag) or entry_type
    planned=operation=='Pedido'
    st.caption('Registra lo solicitado y confirma la recepción cuando llegue. Su estado sigue Solicitado → Confirmado → En camino → Recibido.' if planned
               else 'Registra lo que contaste físicamente: existencias iniciales, compras sin pedido o devoluciones.')
    if kind=='Filamento y consumibles':
        from views.consumables_ui import consumable_fields
        consumable_fields(prefix,planned,consumable_id)
        return
    data = inventory.load_inventory()['skus']
    catalog=load_catalog();components=catalog['components']
    active_ids={c['id'] for c in components}
    data=[s for s in data if s['component_id'] is None or s['component_id'] in active_ids]
    modes = (['Existencia actual'] if data else []) + (['Pieza del catálogo'] if components else []) + ['Nueva referencia']
    default_mode='Pieza del catálogo' if component_id in active_ids else modes[0]
    mode = st.segmented_control('Referencia', modes, default=default_mode, key=prefix + '_mode', width='stretch') or default_mode
    kwargs = {}
    if mode == 'Existencia actual':
        lookup = {s['id']: s for s in data}
        ids = list(lookup)
        selected = st.selectbox('Pieza existente', ids, index=ids.index(sku_id) if sku_id in ids else 0,
            format_func=lambda sid: f"{lookup[sid]['code']} · {lookup[sid]['product']} · {lookup[sid]['part']} · {lookup[sid]['material'] or 'Sin material'}",
            key=prefix + '_sku')
        kwargs['sku_id'] = selected
        st.caption(f"{lookup[selected]['process']} · {lookup[selected]['available_collection']} libres en colección · {lookup[selected]['available_stock']} libres en stock")
    elif mode == 'Pieza del catálogo':
        lookup = {c['id']: c for c in components}
        selected = st.selectbox('Pieza del catálogo', list(lookup),index=list(lookup).index(component_id) if component_id in lookup else 0,key=prefix + '_component',
            format_func=lambda cid: f"CMP-{cid:04d} · {lookup[cid]['name']} · {lookup[cid]['material']} · {lookup[cid]['variant']}")
        kwargs['component_id'] = selected
        st.caption('Estas existencias podrán reservarse al crear pedidos con recetas que usen esta pieza.')
    with st.form(prefix + '_form', border=False):
        if mode == 'Nueva referencia':
            kwargs['product'] = property_select('Modelo / producto *', 'product', key=prefix + '_product')
            kwargs['part'] = property_select('Pieza *', 'part', key=prefix + '_part')
            kwargs['material'] = property_select('Material', 'material', key=prefix + '_material')
            a, b = st.columns(2)
            kwargs['process'] = a.selectbox('Proceso', PROCESSES, key=prefix + '_process')
            kwargs['collection'] = b.selectbox('Línea', ('Origen', 'General'), key=prefix + '_collection')
        a, b = st.columns(2)
        quantity = a.number_input('Unidades pedidas' if planned else 'Unidades que ingresan', min_value=1,value=default_quantity,step=1, key=prefix + '_qty')
        destination = b.selectbox('Ubicación al recibir' if planned else 'Ubicación', ('Colección', 'Stock'),index=1 if planned else 0,key=prefix + ('_planned_destination' if planned else '_destination'),format_func=location)
        reason = st.text_input('Referencia del pedido *' if planned else 'Motivo / referencia *', placeholder='Número de compra o referencia interna' if planned else 'Stock inicial, compra, devolución…', key=prefix + '_reason')
        extra=inbound_fields(prefix) if planned else {}
        if not planned:st.caption('La cantidad se suma al saldo actual. Podrás corregirla con una reversión desde Movimientos.')
        if st.form_submit_button('Guardar pedido' if planned else 'Registrar entrada', type='primary', icon=':material/add:', width='stretch'):
            if planned:
                perform(inbound.create,quantity,destination,reason,request_key=st.session_state['dialog_request_key'],**extra,**kwargs,
                    after=focus_inbound,navigate='views/collection.py',message='Pedido y gasto registrados. El inventario ingresará al recibirlo.')
            else:
                perform(inventory.receive_manual, quantity, destination, reason,
                        request_key=st.session_state['dialog_request_key'], **kwargs,
                        after=partial(focus_entry,workspace=return_workspace),message=f'Entrada registrada: +{quantity} piezas en {location(destination)}.')


# Where pieces sit, said the same way in every inventory table and form.
PLACES = {'Colección': '📥 Por distribuir', 'Stock': '🏬 Almacén'}


def found_options():
    """Every piece that can turn up on a shelf: catalog pieces by their model, then references outside the catalog.

    💡 Colección Origen · 🧩 other catalog pieces · 📦 references created in inventory.
    """
    from services.inventory_view import label as piece_label
    options = {}
    for c in load_catalog()['components']:
        name = piece_label(dict(part=c['name'], variant=c['variant'], component_id=c['id']))
        options[f"{'💡' if c['collection'] == 'Origen' else '🧩'} {name} · {c['material'] or 'Sin material'} · {c['code']}"] = dict(component_id=c['id'])
    for s in inventory.load_inventory()['skus']:
        if s['component_id'] is None:
            options[f"📦 {piece_label(s)} · {s['material'] or 'Sin material'} · {s['code']}"] = dict(sku_id=s['id'])
    return options


@managed_dialog('📦 Stock encontrado', width='large')
def found_stock_form(preset=None) -> None:
    """Pieces found on the shelves, one per line, added together. `preset` starts the first line with a piece."""
    import pandas as pd
    prefix = 'found_' + st.session_state['dialog_request_key']
    options = found_options()
    if not options:
        st.info('Aún no hay piezas en el catálogo ni referencias de inventario. Crea la primera con «Pieza nueva».')
    first = next((name for name, ref in options.items() if preset and ref == preset), None)
    st.caption('Anota lo que encontraste físicamente, una pieza por renglón. Cada renglón se suma a su saldo como entrada manual; '
               'si te equivocas, se revierte desde 🧾 Movimientos.')
    rows = st.data_editor(pd.DataFrame([dict(Pieza=first or '', Cantidad=1, Ubicación=PLACES['Colección'])]), num_rows='dynamic', hide_index=True,
                          width='stretch', key=prefix + '_rows',
                          column_config={'Pieza': st.column_config.SelectboxColumn('🧩 Pieza', options=list(options), required=True, width='large'),
                                         'Cantidad': st.column_config.NumberColumn('🔢 Cantidad', min_value=1, step=1, default=1, required=True),
                                         'Ubicación': st.column_config.SelectboxColumn('📍 Ubicación', options=list(PLACES.values()),
                                                                                      default=PLACES['Colección'], required=True)})
    lines = [r for r in rows.to_dict('records') if r.get('Pieza') in options and r.get('Cantidad') == r.get('Cantidad')]
    reason = st.text_input('Motivo', value=inventory.FOUND_REASON, key=prefix + '_reason',
                           help='Queda en Movimientos. Por ejemplo: Stock encontrado, Conteo de inventario, Devolución.')
    total = sum(int(r['Cantidad']) for r in lines)
    st.markdown(f"**➕ {total} piezas en {len(lines)} {'renglón' if len(lines) == 1 else 'renglones'}**" if lines else ':gray[Elige al menos una pieza.]')
    with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        if st.button('Pieza nueva que no está en la lista', key=prefix + '_new', type='tertiary', icon=':material/add_circle:'):
            manual_entry_form()
        if st.button('📦 Sumar al inventario', key=prefix + '_save', type='primary', disabled=not lines):
            where = {v: k for k, v in PLACES.items()}
            perform(inventory.receive_found, [dict(**options[r['Pieza']], quantity=int(r['Cantidad']), destination=where[r['Ubicación']]) for r in lines],
                    reason=reason, request_key=st.session_state['dialog_request_key'], message=f'Stock encontrado registrado: +{total} piezas.')


def open_distribution(sku: dict) -> None:
    # Each new operation starts with fresh choices, never a prior client's quantity.
    prefix = f'distribute_{sku["id"]}_'
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]
    st.session_state[prefix + 'source'] = 'Colección' if sku['available_collection'] > 0 else 'Stock'
    distribution_form(sku, uuid.uuid4().hex)


@managed_dialog('Mover o asignar piezas', width='medium')
def distribution_form(sku: dict, request_key: str) -> None:
    st.write(f"**{sku['product']} · {sku['part']}**")
    st.caption(f"{sku['code']} · {sku['material'] or 'Sin material'} · {sku['process']}")
    prefix = f'distribute_{sku["id"]}_'
    origin_column, destination_column = st.columns(2)
    source = origin_column.selectbox('Desde', ('Colección', 'Stock'), key=prefix + 'source',format_func=location)
    target_options = ('Stock', 'B2B') if source == 'Colección' else ('Colección', 'B2B')
    destination = destination_column.selectbox('Hacia', target_options, format_func=location, key=prefix + source + '_destination')
    fresh = next((row for row in inventory.load_inventory()['skus'] if row['id'] == sku['id']), None)
    available = fresh['available_collection' if source == 'Colección' else 'available_stock'] if fresh else 0
    st.badge(f'{available} piezas disponibles',color='green' if available else 'orange',icon=':material/inventory_2:')
    st.caption(f'{location(source)} → {location(destination)}')
    with st.form('inventory_distribution'):
        quantity = st.number_input('Cantidad de piezas', min_value=1, value=1, step=1, key=prefix + 'quantity')
        client = property_select('Cliente B2B *', 'client', key=prefix + 'client') if destination == 'B2B' else ''
        notes = st.text_input('Referencia / notas', placeholder='Pedido, entrega o referencia interna', key=prefix + 'notes')
        if destination == 'B2B':
            st.caption('La asignación B2B registra piezas destinadas al cliente; no confirma envío ni facturación.')
        if st.form_submit_button('Guardar movimiento', type='primary', disabled=available <= 0, width='stretch', icon=':material/check:'):
            perform(inventory.distribute, sku['id'], source, destination, quantity, client=client, notes=notes,
                    request_key=request_key, message='Movimiento registrado. Saldos actualizados.')


@managed_dialog('Revertir movimiento', width='small')
def reversal_form(movement: dict) -> None:
    st.write(f"**{movement['code']} · {movement['part']} ×{movement['quantity']}**")
    st.caption(f"{movement['destination']} → {movement['source']} · {movement['client'] or movement['product']}")
    st.write('Se devolverá la cantidad completa al origen y se conservarán ambos movimientos en el historial.')
    with st.form('inventory_reversal'):
        reason = st.text_input('Motivo *', key='inventory_reversal_reason')
        if st.form_submit_button('Confirmar reversión', type='primary', width='stretch'):
            perform(inventory.reverse_movement, movement['id'], reason, message='Movimiento revertido. Historial conservado.')
