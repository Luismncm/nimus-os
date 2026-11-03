"""Consumables by unit (filament, resin, paint, hardware…), their counts and package orders."""
import streamlit as st
from services import consumables as c
from services.order_status import STAGES, COLORS, OPEN
from services.quotations import money
from views.common import managed_dialog, perform, table
from views.common import request_key as _key
from views.emoji import tag

STATE_COLORS = {'Sin existencias': 'red', 'No alcanza para la cola': 'red', 'Bajo mínimo': 'orange', 'Suficiente': 'green'}


def q(value, row):
    return c.quantity_text(value, row['unit'])


def focus(item_id):
    st.session_state['consumables_selected'] = item_id


@managed_dialog('Consumible', width='medium')
def consumable_item_form(row=None, name=None):
    prefix = 'consumable_item_' + _key()
    category = st.selectbox('Categoría', c.CATEGORIES, index=c.CATEGORIES.index(row['category']) if row else 0, key=prefix + '_category',
                            help='Define la unidad sugerida y el envase. Filamento se compara con los gramos previstos de la cola.')
    unit_default, label_default, size_default = c.DEFAULTS[category]
    # New items take the category's suggested unit and package; keys per category refresh those defaults.
    prefix += '' if row else '_' + category
    with st.form(prefix):
        value = st.text_input('Nombre *', value=row['name'] if row else name or '', key=prefix + '_name',
                              placeholder='Para filamento, el mismo material que usan las piezas: PLA MATTE IVORY')
        a, b, d = st.columns(3)
        spec = a.text_input('Tipo / especificación', value=row['spec'] if row else '', placeholder='PLA, M3×8, base agua…', key=prefix + '_spec')
        color = b.text_input('Color', value=row['color'] if row else '', key=prefix + '_color')
        brand = d.text_input('Marca', value=row['brand'] if row else '', key=prefix + '_brand')
        units = list(c.UNITS)
        unit = st.segmented_control('Unidad de control', units, default=row['unit'] if row else unit_default, format_func=lambda u: c.UNITS[u],
                                    key=prefix + '_unit', disabled=bool(row)) or unit_default
        a, b, d = st.columns(3)
        package = a.selectbox('Envase', c.PACKAGES, index=c.PACKAGES.index(row['package_label']) if row and row['package_label'] in c.PACKAGES
                              else c.PACKAGES.index(label_default), key=prefix + '_package')
        size = b.number_input(f'Contenido por envase · {unit}', min_value=1.0, value=float(row['package_size'] if row else size_default), step=1.0, key=prefix + '_size')
        minimum = d.number_input(f'Mínimo deseado · {unit}', min_value=0.0, value=float(row['minimum'] if row else 0), step=1.0, key=prefix + '_minimum')
        a, b = st.columns([1, 2])
        cost = a.number_input('Costo por envase · MXN sin IVA', min_value=0.0, step=10.0, key=prefix + '_cost',
                              value=row['package_cost_cents'] / 100 if row and row['package_cost_cents'] is not None else None,
                              help='Vacío si aún no lo sabes. Al recibir un pedido con gasto se actualiza con el precio pagado.')
        notes = b.text_input('Notas', value=row['notes'] if row else '', key=prefix + '_notes')
        st.caption('Se cuenta en la unidad elegida: gramos (puedes capturar kg), mililitros (o L) o piezas. Un mínimo de 0 desactiva el aviso. '
                   'Con el costo por envase cada consumo guarda su costo y se suma al pedido donde se usó.'
                   + (' La unidad no cambia cuando ya hay movimientos.' if row else ''))
        if st.form_submit_button('Guardar consumible', type='primary', width='stretch'):
            perform(c.save_item, value, category=category, unit=unit, spec=spec, color=color, brand=brand, package_label=package,
                    package_size=size, minimum=minimum, notes=notes, package_cost=cost, item_id=row['id'] if row else None,
                    expected_revision=row['revision'] if row else None, after=focus, message='Consumible guardado.')


def entry_unit(row, prefix, value=0.0):
    """Chosen outside the form, so the amount field relabels as soon as kg/g or L/ml changes."""
    units = list(c.ENTRY[row['unit']])
    if len(units) == 1:
        return units[0]
    return st.segmented_control('Capturar en', units, default=units[-1] if value >= 1000 else units[0], key=prefix + '_entry_unit') or units[0]


def quantity_input(row, label, prefix, entry, *, value=0.0):
    shown = value / c.ENTRY[row['unit']][entry]
    amount = st.number_input(f'{label} · {entry}', min_value=0.0, value=float(round(shown, 3)), step=1.0 if row['unit'] == 'pza' else 0.1,
                             key=f'{prefix}_amount_{entry}')
    return c.to_base(amount, entry, row['unit'])


def usage_target(row, prefix, order_id=None):
    """Which production order (and, for filament, which print job) a consumption belongs to."""
    snapshot = st.session_state['snapshot']
    orders = {o['id']: o for o in snapshot['orders'] if not o.get('commercial_cancelled')}
    if order_id is None:
        order_id = st.selectbox('Pedido donde se usó (opcional)', [None, *orders], key=prefix + '_order',
                                format_func=lambda i: 'Sin pedido · uso general del taller' if i is None else f"{orders[i]['code']} · {orders[i]['project']} · {orders[i]['client']}")
    job_code = ''
    if row['unit'] == 'g':
        jobs = {j['code']: j for j in snapshot['jobs'] if c.identity(j.get('material') or '') == row['identity'] and order_id in (None, j['order_id'])}
        if jobs:
            code = st.selectbox('Trabajo de impresión (opcional)', [None, *jobs], key=prefix + '_job',
                                format_func=lambda k: 'Sin trabajo' if k is None else f"{k} · {jobs[k]['part_name']} · {jobs[k]['status']}")
            if code:
                job_code = code
                grams = jobs[code].get('actual_consumed_grams') or jobs[code].get('estimated_grams')
                if grams:st.caption(f"Gramos {'reales' if jobs[code].get('actual_consumed_grams') else 'estimados'} del trabajo: {grams:g} g")
                st.caption('Ligado a un trabajo, este filamento queda en el historial del pedido pero no se suma otra vez: '
                           'su costo ya entra por el costo real del lote (gramos × MXN/kg).')
    if order_id is not None and not job_code:
        st.caption('Su costo se suma a los costos reales del pedido.' if c.unit_cost(row) is not None
                   else 'Sin costo de referencia: el pedido lo mostrará como costo pendiente hasta que captures el costo por envase.')
    return order_id, job_code


@managed_dialog('Consumible usado en el pedido', width='medium')
def consumable_use_form(order_id):
    """From an order: record any consumable used on it, without leaving the order."""
    rows = {r['id']: r for r in c.items(st.session_state['snapshot']['jobs'])}
    if not rows:
        st.info('Registra primero tus consumibles en Inventario → Filamento y consumibles.');return
    prefix = 'consumable_use_' + _key()
    order = next(o for o in st.session_state['snapshot']['orders'] if o['id'] == order_id)
    st.caption(f"{order['code']} · {order['project']}")
    selected = st.selectbox('Consumible', list(rows), key=prefix + '_item', format_func=lambda i: f"{rows[i]['name']} · {q(rows[i]['balance'], rows[i])} disponibles")
    row = rows[selected]
    _, job_code = usage_target(row, prefix, order_id)
    entry = entry_unit(row, prefix)
    with st.form(prefix):
        amount = quantity_input(row, 'Cantidad usada', prefix, entry)
        notes = st.text_input('Nota', key=prefix + '_notes')
        if st.form_submit_button('Registrar consumo', type='primary', width='stretch'):
            perform(c.consume, row['id'], amount, job_code=job_code, order_id=order_id, notes=notes, request_key=_key(), message='Consumo registrado en el pedido.')


@managed_dialog('Movimiento de consumible', width='medium')
def consumable_movement_form(row, kind):
    prefix = 'consumable_move_' + _key()
    st.markdown(f"**{row['name']}** · saldo registrado {q(row['balance'], row)} · {c.cost_text(row)}")
    job_code, order_id = '', None
    if kind == 'Consumo':
        order_id, job_code = usage_target(row, prefix)
    start = row['balance'] if kind == 'Conteo' else 0.0
    entry = entry_unit(row, prefix, start)
    with st.form(prefix):
        label = {'Entrada': 'Cantidad que entra', 'Consumo': 'Cantidad usada', 'Conteo': 'Cantidad contada o pesada'}[kind]
        amount = quantity_input(row, label, prefix, entry, value=start)
        notes = st.text_input('Nota', key=prefix + '_notes', placeholder='Comprobante, motivo o carrete')
        st.caption({'Entrada': 'Para lo que llega sin pedido. Las compras con pedido se reciben desde Pedidos.',
                    'Consumo': 'Descuenta lo que se usó. El saldo no puede quedar negativo; si no cuadra, haz un conteo.',
                    'Conteo': 'El saldo pasa a ser lo contado; la diferencia queda como ajuste en el historial.'}[kind])
        if st.form_submit_button({'Entrada': 'Registrar entrada', 'Consumo': 'Registrar consumo', 'Conteo': 'Guardar conteo'}[kind], type='primary', width='stretch'):
            if kind == 'Entrada':perform(c.receive, row['id'], amount, notes=notes, request_key=_key(), message='Entrada registrada.')
            elif kind == 'Consumo':perform(c.consume, row['id'], amount, job_code=job_code, order_id=order_id, notes=notes, request_key=_key(), message='Consumo registrado.')
            else:perform(c.count, row['id'], amount, notes=notes, request_key=_key(), message='Conteo guardado.')


def add_inventory(item_id=None, entry_type='Pedido'):
    """Every entry or order goes through the one "Agregar inventario" dialog, already on consumables."""
    from views.collection_forms import manual_entry_form
    manual_entry_form(kind='Filamento y consumibles', consumable_id=item_id, entry_type=entry_type)


def consumable_fields(prefix, planned, item_id=None):
    """Body of "Agregar inventario" for consumables: same order fields and expense as pieces and supplies."""
    from views.collection_forms import inbound_fields
    rows = {r['id']: r for r in c.items(st.session_state['snapshot']['jobs'])}
    if not rows:
        st.info('Registra primero el consumible en Inventario → Filamento y consumibles.', icon=':material/inventory_2:')
        return
    selected = st.selectbox('Consumible', list(rows), index=list(rows).index(item_id) if item_id in rows else 0, key=prefix + '_consumable',
                            format_func=lambda i: f"{rows[i]['name']} · {rows[i]['category']} · {q(rows[i]['balance'], rows[i])} disponibles")
    row = rows[selected]
    st.caption(c.cost_text(row) + (f" · {q(row['on_order'], row)} ya en pedido" if row['on_order'] else ''))
    entry = None if planned else entry_unit(row, prefix + '_in')
    with st.form(prefix + '_consumable_form', border=False):
        if planned:
            a, b = st.columns(2)
            packages = a.number_input(f"{row['package_label']}s pedidos", min_value=1, value=1, step=1, key=prefix + '_packages')
            size = b.number_input(f"Contenido por {row['package_label'].lower()} · {row['unit']}", min_value=1.0, value=float(row['package_size']), key=prefix + '_size')
            extra = inbound_fields(prefix)
            st.caption('El saldo aumenta al recibir; mientras tanto cuenta como «en pedido». El precio pagado actualiza el costo de referencia.')
        else:
            amount = quantity_input(row, 'Cantidad que ingresa', prefix + '_in', entry)
            notes = st.text_input('Motivo / referencia *', placeholder='Stock inicial, compra, devolución…', key=prefix + '_reason')
            st.caption('Se suma al saldo. Para corregirlo, haz un conteo desde Filamento y consumibles.')
        if st.form_submit_button('Guardar pedido' if planned else 'Registrar entrada', type='primary', icon=':material/add:', width='stretch'):
            if planned:
                perform(c.create_order, selected, int(packages), package_size=size, supplier=extra['supplier'], ordered_on=extra['ordered_on'],
                        expected_on=extra['expected_on'], notes=extra['notes'], financial=extra['financial'], request_key=_key(),
                        after=lambda _: st.session_state.update(collection_workspace='Compras', orders_kind='Filamento y consumibles'),
                        navigate='views/collection.py', message='Pedido y gasto registrados. El saldo aumentará al recibirlo.')
            elif not notes.strip():
                st.error('Indica el motivo o referencia de la entrada.')
            else:
                perform(c.receive, selected, amount, notes=notes, request_key=_key(), after=focus, message=f"Entrada registrada: +{q(amount, row)}.")


@managed_dialog('Estado del pedido', width='small')
def consumable_stage_form(row):
    prefix = 'consumable_stage_' + _key()
    st.text(f"{row['code']} · {row['item']} · ahora: {row['status']}")
    with st.form(prefix):
        options = [s for s in STAGES if s != row['stage']]
        stage = st.radio('Nuevo estado', options, key=prefix + '_stage', horizontal=True)
        notes = st.text_input('Nota (opcional)', placeholder='Confirmación, guía de envío…', key=prefix + '_notes')
        if st.form_submit_button('Guardar estado', type='primary', width='stretch'):
            perform(c.set_stage, row['id'], stage, notes=notes, expected_token=row['token'], request_key=_key(), message=f'Pedido en «{stage}».')


@managed_dialog('Recibir pedido de consumibles', width='small')
def consumable_receive_order_form(row):
    prefix = 'consumable_receive_' + _key()
    st.text(f"{row['code']} · {row['item']} · {row['pending']} {row['package_label'].lower()}(s) pendientes")
    with st.form(prefix):
        packages = st.number_input('Envases recibidos', min_value=1, max_value=row['pending'], value=row['pending'], step=1, key=prefix + '_packages')
        notes = st.text_input('Nota / comprobante', key=prefix + '_notes')
        st.caption(f"Cada envase suma {c.quantity_text(row['package_size'], row['unit'])} al saldo.")
        if st.form_submit_button('Confirmar recepción', type='primary', width='stretch'):
            perform(c.receive_order, row['id'], int(packages), notes=notes, expected_token=row['token'], request_key=_key(), message='Recepción guardada. Saldo actualizado.')


@managed_dialog('Cancelar pedido de consumibles', width='small')
def consumable_cancel_order_form(row):
    prefix = 'consumable_cancel_' + _key()
    st.text(f"{row['code']} · cancelar {row['pending']} envases pendientes")
    with st.form(prefix):
        reason = st.text_input('Motivo *', key=prefix + '_reason')
        if st.form_submit_button('Confirmar cancelación', type='primary', width='stretch'):
            perform(c.cancel_order, row['id'], reason, expected_token=row['token'], request_key=_key(), message='Pedido cancelado.')


def panel():
    snapshot = st.session_state['snapshot']
    rows = c.items(snapshot['jobs'])
    with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        st.caption('Filamento, resina, pinturas, tornillería y otros consumibles, cada uno en su unidad. Los insumos por pieza de las recetas siguen en Reposición de insumos.')
        with st.container(horizontal=True, gap='small', width='content'):
            if st.button('Nuevo consumible', key='consumables_new', icon=':material/add:', type='primary'):consumable_item_form()
            if rows and st.button('Pedir', key='consumables_order', icon=':material/local_shipping:'):add_inventory(st.session_state.get('consumables_selected'))
    missing = c.unregistered(snapshot['jobs'])
    if missing:
        with st.container(border=True, gap='xsmall'):
            st.markdown(f":orange[**{len(missing)} filamentos de la cola sin registrar**] :gray[· regístralos para saber si alcanzan]")
            with st.container(horizontal=True, gap='small'):
                for name in missing[:6]:
                    if st.button(name, key='consumables_register_' + c.identity(name), icon=':material/add:', type='tertiary'):consumable_item_form(name=name)
    if not rows:
        st.info('Aún no hay consumibles. Registra tus filamentos con el mismo nombre de material que usan las piezas.', icon=':material/inventory_2:')
        return
    attention = [r for r in rows if r['attention']]
    a, b, d = st.columns(3)
    a.metric('Consumibles', len(rows), border=True)
    b.metric('Requieren atención', len(attention), border=True, help='Sin existencias, bajo mínimo o sin filamento suficiente para la cola.')
    d.metric('Pedidos abiertos', sum(o['status'] in OPEN for o in c.list_orders()), border=True)
    categories = ('Todas', *dict.fromkeys(r['category'] for r in rows))
    category = st.segmented_control('Categoría', categories, default='Todas', key='consumables_category', persist_state='session') or 'Todas'
    shown = [r for r in rows if category in ('Todas', r['category'])]
    shown.sort(key=lambda r: (not r['attention'], r['category'], r['name']))
    table([dict(r, balance_text=q(r['balance'], r), committed_text=q(r['committed'], r) if r['committed'] else '—',
                free_text=q(r['free_after'], r) if r['committed'] else '—', minimum_text=q(r['minimum'], r) if r['minimum'] else '—',
                order_text=q(r['on_order'], r) if r['on_order'] else '—', packages_text=f"{r['packages']:g} {r['package_label'].lower()}(s)",
                cost=c.cost_text(r) if r['package_cost_cents'] is not None else '—',
                value=money(r['stock_value_cents']) if r['stock_value_cents'] is not None else '—') for r in shown],
          {'name': 'Consumible', 'category': 'Categoría', 'balance_text': 'Disponible', 'packages_text': 'Equivale a',
           'committed_text': 'Previsto en cola', 'free_text': 'Libre después', 'minimum_text': 'Mínimo', 'order_text': 'En pedido', 'state': 'Estado',
           'cost': 'Costo', 'value': 'Valor en existencia'},
          label='Consumibles por unidad: disponible, previsto, mínimo y en pedido')
    lookup = {r['id']: r for r in shown}
    if not lookup:return
    if st.session_state.get('consumables_selected') not in lookup:st.session_state['consumables_selected'] = next(iter(lookup))
    selected = st.selectbox('Consumible para gestionar', list(lookup), key='consumables_selected',
                            format_func=lambda i: f"{lookup[i]['name']} · {q(lookup[i]['balance'], lookup[i])}")
    row = lookup[selected]
    with st.container(border=True, gap='small'):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            st.markdown(f"**{row['name']}** :gray[· {' · '.join(x for x in (row['category'], row['spec'], row['color'], row['brand']) if x)}]")
            st.badge(row['state'], color=STATE_COLORS[row['state']])
        st.markdown(f"**{q(row['balance'], row)}** disponibles · ≈ {row['packages']:g} {row['package_label'].lower()}(s) de {q(row['package_size'], row)}"
                    + (f" · la cola prevé {q(row['committed'], row)} en {row['committed_jobs']} trabajo(s)" if row['committed'] else '')
                    + (f" · {q(row['on_order'], row)} en pedido" if row['on_order'] else ''))
        st.caption(c.cost_text(row) + (f" · valor en existencia {money(row['stock_value_cents'])}" if row['stock_value_cents'] else ''))
        with st.container(horizontal=True, gap='small'):
            if st.button('Registrar consumo', key='consumable_use', icon=':material/remove:'):consumable_movement_form(row, 'Consumo')
            if st.button('Contar / pesar', key='consumable_count', icon=':material/scale:'):consumable_movement_form(row, 'Conteo')
            if st.button('Entrada sin pedido', key='consumable_in', icon=':material/add:'):add_inventory(row['id'], 'Entrada física')
            if st.button('Pedir', key='consumable_order_one', icon=':material/local_shipping:'):add_inventory(row['id'])
            if st.button('Editar', key='consumable_edit', icon=':material/edit:', type='tertiary'):consumable_item_form(row)
        with st.expander('Historial', icon=':material/history:', key='consumable_history', on_change='ignore'):
            table([dict(m, quantity_text=('+' if m['quantity'] > 0 else '') + q(m['quantity'], row), balance_text=q(m['balance_after'], row),
                        day=m['created_at'][:16].replace('T', ' '), ref=' · '.join(x for x in (m['order_code'], m['job_code'], m['purchase_code']) if x),
                        cost=money(m['cost_cents']) if m['cost_cents'] is not None else '') for m in c.movements(row['id'])],
                  {'day': 'Fecha', 'kind': 'Movimiento', 'quantity_text': 'Cantidad', 'balance_text': 'Saldo', 'ref': 'Pedido / trabajo / compra',
                   'cost': 'Costo', 'notes': 'Nota'},
                  label=f"Movimientos de {row['name']}")
    st.caption('Hoy el saldo es por consumible. Más adelante cada carrete o envase podrá tener su código o QR sin cambiar estos saldos.')


def orders_panel():
    rows = c.list_orders()
    if st.button('Nuevo pedido de consumibles', key='consumable_orders_new', icon=':material/add:', type='primary'):add_inventory()
    if not rows:
        st.caption('Sin pedidos de consumibles todavía.');return
    mode = st.segmented_control('Ver pedidos de consumibles', ('Abiertos', 'Recibidos', 'Cancelados', 'Todos'), default='Abiertos', key='consumable_orders_filter', format_func=tag) or 'Abiertos'
    shown = [r for r in rows if mode == 'Todos' or (mode == 'Abiertos' and r['status'] in OPEN) or r['status'] == mode.rstrip('s')]
    table([dict(r, ordered=f"{r['packages']} × {c.quantity_text(r['package_size'], r['unit'])}", received_text=f"{r['received']}/{r['packages']}",
                expected=(r['expected_on'] or 'Sin fecha') + (' · vencida' if r['overdue'] else '')) for r in shown],
          {'code': 'Pedido', 'item': 'Consumible', 'supplier': 'Proveedor', 'ordered': 'Cantidad', 'received_text': 'Recibidos', 'expected': 'Llegada', 'status': 'Estado'},
          label='Pedidos de consumibles y su estado')
    lookup = {r['id']: r for r in shown}
    if not lookup:return
    if st.session_state.get('consumable_order_selected') not in lookup:st.session_state['consumable_order_selected'] = next(iter(lookup))
    selected = st.selectbox('Pedido para gestionar', list(lookup), key='consumable_order_selected', format_func=lambda i: f"{lookup[i]['code']} · {lookup[i]['item']} · {lookup[i]['status']}")
    row = lookup[selected]
    with st.container(border=True, gap='small'):
        with st.container(horizontal=True, horizontal_alignment='distribute'):
            st.text(f"{row['code']} · {row['item']} · {row['supplier'] or 'Sin proveedor'}")
            st.badge(row['status'], color=COLORS[row['status']])
        stepper(row['status'])
        if row['expense_id']:st.caption(f"Gasto vinculado · se gestiona en Gastos.")
        if row['pending']:
            with st.container(horizontal=True, gap='small'):
                if st.button('Recibir', key='consumable_order_receive', type='primary', icon=':material/inventory_2:'):consumable_receive_order_form(row)
                if st.button('Cambiar estado', key='consumable_order_stage', icon=':material/sync_alt:'):consumable_stage_form(row)
                if st.button('Cancelar pendientes', key='consumable_order_cancel', type='tertiary'):consumable_cancel_order_form(row)


def stepper(current):
    """Solicitado → Confirmado → En camino → Recibido, with the current one in bold."""
    if current == 'Cancelado':
        st.markdown(':gray[:material/cancel: Cancelado]');return
    flow = ('Solicitado', 'Confirmado', 'En camino', 'Recibido')
    reached = flow.index('En camino') + 0.5 if current == 'Recibido parcial' else flow.index(current)
    marks = [f":material/check_circle: :gray[{s}]" if i < reached else f":material/radio_button_checked: **{s}**" if i == reached
             else f":material/radio_button_unchecked: :gray[{s}]" for i, s in enumerate(flow)]
    if current == 'Recibido parcial':marks.insert(3, ':material/radio_button_checked: **Recibido parcial**')
    st.markdown(' :gray[→] '.join(marks))
