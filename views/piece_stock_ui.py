"""Inventory check before printing a piece, and extra units printed on top for stock."""
import streamlit as st
from services import piece_stock
from services.inventory import PRINT_PROCESSES
from services.timeline import when
from views.common import managed_dialog, perform
from views.kind_style import PALETTE


def coverable(order) -> list[dict]:
    """Pieces of this order still to assign that inventory can cover, at least in part."""
    return [p for i in order['items'] for p in i['parts'] if p['quantity_unassigned'] and p.get('stock_free')]


def cover_panel(order, readonly=False, view_key=None) -> None:
    """One line on the order: pieces already in inventory, and the way to the Inventario view where they are taken.

    The taking itself happens in that view only, so the order has a single place to decide it.
    """
    parts = coverable(order)
    if readonly or not parts or (view_key and st.session_state.get(view_key) == 'Inventario'):
        return
    units = sum(min(p['stock_free'], p['quantity_unassigned']) for p in parts)
    with st.container(border=True, key=f"kind-stock-cover-{order['id']}", horizontal=True, vertical_alignment='center', gap='small'):
        st.markdown(f":material/inventory_2: **{len(parts)} {'pieza' if len(parts) == 1 else 'piezas'} de este pedido ya están en inventario** "
                    f":gray[· hasta {units} unidades sin imprimir]", width='stretch')
        st.button('Revisar inventario', key=f"order_stock_review_{order['id']}", icon=':material/arrow_forward:', icon_position='right',
                  on_click=st.session_state.__setitem__, args=(view_key, 'Inventario'), disabled=not view_key)


STATES = {  # state: (badge color, icon, short meaning)
    'Disponible': ('blue', 'inventory_2', 'Hay inventario para todo'),
    'Parcial': ('blue', 'inventory_2', 'Hay inventario para una parte'),
    'En camino': ('violet', 'local_shipping', 'Viene como excedente de otra impresión'),
    'Imprimir': ('orange', 'print', 'Sin inventario: hay que imprimir'),
    'Asignada': ('gray', 'schedule', 'Ya tiene impresión'),
    'Cubierta': ('green', 'check', 'Cubierta con inventario'),
}


def availability_panel(order) -> None:
    """The order against inventory, piece by piece: needed, covered, to assign, free now and where it is."""
    rows = piece_stock.availability(order)
    if not rows:
        st.info('Este pedido no tiene piezas por fabricar.', icon=':material/inventory_2:')
        return
    order_rows = sorted(rows, key=lambda r: list(STATES).index(r['state']))
    if parts := coverable(order):
        with st.container(horizontal=True, vertical_alignment='center', gap='small'):
            st.caption(f"{len(parts)} {'pieza se puede' if len(parts) == 1 else 'piezas se pueden'} tomar de inventario en lugar de imprimirse. "
                       'Elige cuántas en una sola ventana, o usa Tomar en cada fila.', width='stretch')
            if st.button('Usar inventario', key=f"order_cover_{order['id']}", icon=':material/move_to_inbox:', type='primary',
                         help='Elige cuántas tomar de cada pieza; las que tomes ya no se imprimen.'):
                cover_form(order['id'])
    for col, label, value, icon, help in zip(st.columns(4), ('Necesarias', 'De inventario', 'Por asignar', 'Libres ahora'),
            (sum(r['required'] for r in rows), sum(r['covered'] for r in rows), sum(r['unassigned'] for r in rows), sum(r['take'] for r in rows)),
            ('format_list_numbered', 'move_to_inbox', 'call_split', 'inventory_2'),
            ('Unidades que pide el pedido.', 'Ya tomadas de inventario: no se imprimen. Puedes devolverlas.', 'Unidades sin impresión ni inventario.',
             'De las que faltan por asignar, las que se pueden tomar de inventario ahora.')):
        col.metric(label, value, border=True, icon=f':material/{icon}:', help=help)
    st.caption(f":material/warehouse: En taller ahora, de estas piezas: **{sum(r['physical'] for r in rows)}** físicas · "
               f"{sum(r['free'] for r in rows)} libres · {sum(r['reserved'] for r in rows)} reservadas (para este y otros pedidos). "
               f"Una pieza pasa por: inventario → impresión (en cola, en curso) → terminada.")
    for r in order_rows:
        color, icon, meaning = STATES[r['state']]
        uid = r['part_id'] or f"r{r['requirement_id']}"
        with st.container(border=True, gap='xsmall', key=f"kind-avail-{order['id']}-{uid}"):
            a, b = st.columns([4, 1.3], vertical_alignment='top')
            with a:
                st.markdown(f"**{r['name']}** :gray[· {r['item']} · {r['material']}]  \n:{color}-badge[:material/{icon}: {r['state']}] :gray[{meaning}]")
                stage_bar(r)
                st.caption(stage_text(r))
                st.caption(f":material/warehouse: En taller **{r['physical']}** · {r['free']} libres · {r['reserved']} reservadas"
                           + (f" · {r['where']}" if r['where'] else ''))
                if r['covered'] and not r['returnable']:
                    st.caption(':gray[Tomadas de inventario: para corregirlo, registra una entrada manual en Inventario.]')
                for host, origin in [*((h, 'excedente') for h in r['hosts'][:3]), *((h, 'stock directo') for h in r['soon'][:3])]:
                    st.caption(f":material/local_shipping: **{host['free']} por entrar** · {origin} · {host['code']} · {host['machine_code'] or 'sin máquina'} · "
                               f"{host['status'].lower()}" + (f" · termina {when(host['eta'])}" if host['eta'] else ' · sin horario'))
            with b:
                if r['take'] and st.button(f"Tomar {r['take']}", key=f"avail_take_{order['id']}_{uid}", icon=':material/move_to_inbox:', width='stretch',
                                           type='secondary', help='Elige cuántas tomar; las que tomes ya no se imprimen.'):
                    cover_form(order['id'], r['part_id'])
                if r['returnable'] and st.button(f"Devolver {r['returnable']}", key=f"avail_return_{order['id']}_{uid}", icon=':material/undo:', width='stretch',
                                                 type='secondary', help='Desasigna lo tomado de inventario: vuelve a estar libre y la pieza se imprime.'):
                    return_form(order['id'], r['part_id'], r['requirement_id'])


def stage_text(r) -> str:
    words = [f"necesita {r['required']}"]
    for key, label in (('covered', 'de inventario'), ('done', 'terminadas'), ('running', 'en curso'), ('queued', 'en cola'), ('unassigned', 'sin asignar')):
        if r[key]:
            words.append(f"**{r[key]} {label}**" if key == 'unassigned' else f"{r[key]} {label}")
    return ' · '.join(words)


def stage_bar(r) -> None:
    """Where each unit of the piece is: inventory, printed, printing, queued or still to assign."""
    cells = ''.join(f'<span style="flex:{r[key]} 0 0;background:{color}"></span>' for key, color in
                    (('covered', PALETTE['free']), ('done', PALETTE['done']), ('running', PALETTE['printing']), ('queued', PALETTE['booked']),
                     ('unassigned', PALETTE['idle'])) if r[key])
    summary = stage_text(r).replace('**', '')
    st.html(f'<div role="img" aria-label="{summary}" title="{summary}" style="display:flex;gap:2px;height:8px;border-radius:99px;'
            f'overflow:hidden;background:{PALETTE["idle"]};width:100%">{cells}</div>')


@managed_dialog('Devolver piezas a inventario', width='small')
def return_form(order_id, part_id=None, requirement_id=None):
    order = next((o for o in st.session_state['snapshot']['orders'] if o['id'] == order_id), None)
    row = next((r for r in piece_stock.availability(order) if (r['part_id'], r['requirement_id']) == (part_id, requirement_id)), None) if order else None
    if not row or not row['returnable']:
        st.success('Ya no hay piezas tomadas de inventario en esta pieza.', icon=':material/check_circle:')
        return
    uid = part_id or f'r{requirement_id}'
    st.markdown(f"**{row['name']}** :gray[· {row['item']} · {row['material']}]")
    st.caption(f"{order['code']} · {row['returnable']} de inventario. Las que devuelvas vuelven a estar libres para otros pedidos "
               'y este pedido tendrá que imprimirlas: quedan por asignar.')
    amount = int(st.number_input('Devolver', min_value=1, max_value=row['returnable'], value=row['returnable'], step=1, key=f'return_{order_id}_{uid}_qty',
                                 icon=':material/undo:'))
    if st.button(f'Devolver {amount} a inventario', type='primary', width='stretch', icon=':material/undo:', key=f'return_{order_id}_{uid}_save'):
        perform(piece_stock.return_to_stock, order_id, amount, requirement_id=requirement_id,
                message=f'{amount} piezas devueltas a inventario; ahora están por asignar en {order["code"]}.')


@managed_dialog('Usar piezas de inventario', width='large')
def cover_form(order_id, part_id=None):
    order = next((o for o in st.session_state['snapshot']['orders'] if o['id'] == order_id), None)
    parts = [p for p in coverable(order) if part_id in (None, p['id'])] if order else []
    if not parts:
        st.success('Ya no quedan piezas por asignar que estén en inventario.', icon=':material/check_circle:')
        return
    st.caption(f"{order['code']} · {order['project']}. Lo que tomes cuenta como pieza terminada del pedido y sale del inventario "
               '(las piezas del catálogo quedan reservadas hasta la entrega). El resto se sigue imprimiendo.')
    amounts, custom = [], False
    for p in parts:
        top = min(p['stock_free'], p['quantity_unassigned'])
        with st.container(border=True, gap='xxsmall'):
            a, b = st.columns([3, 1], vertical_alignment='center')
            a.markdown(f"**{p['name']}** :gray[· {p['item_name']} · {p['material'] or 'Sin material'}]  \n"
                       f":material/inventory_2: {piece_stock.stock_text(p)} · faltan {p['quantity_unassigned']} por asignar")
            amount = int(b.number_input('Tomar', min_value=0, max_value=top, value=top, step=1, key=f"cover_{order_id}_{p['id']}"))
        amounts.append((p['id'], amount))
        custom = custom or (amount and not p.get('component_id'))
    total = sum(q for _, q in amounts)
    confirmed = not custom or st.checkbox(f'Confirmo que tomo {total} piezas físicas del inventario para este pedido', key=f'cover_{order_id}_ok')
    if st.button(f'Tomar {total} piezas de inventario', type='primary', width='stretch', icon=':material/move_to_inbox:',
                 disabled=not total or not confirmed, key=f'cover_{order_id}_save'):
        perform(piece_stock.cover_from_stock, amounts, message=f'{total} piezas tomadas de inventario para {order["code"]}; ya no se imprimen.')


def stock_notice(part: dict, key: str, *, allow_take=True) -> None:
    """What of this piece already exists or is on its way, and how to use it instead of printing it again.

    In hand: catalog pieces are reserved for the order, custom ones leave inventory (with a confirmation).
    On its way (another print's extra): the units ride in that print and finish with it.
    """
    from services.timeline import when
    free, coming = part.get('stock_free', 0), part.get('stock_incoming', 0)
    if not free and not coming:
        st.caption(':material/inventory_2: Sin piezas en inventario ni en camino: hay que imprimirlas.')
        return
    st.warning(f"{piece_stock.stock_text(part)}. Úsalas antes de imprimir de nuevo para no duplicar.", icon=':material/inventory_2:')
    unassigned = part.get('quantity_unassigned', 0)
    if not allow_take or not unassigned or 'id' not in part:
        return
    if free:
        a, b = st.columns([1, 2.4], vertical_alignment='bottom')
        top = min(free, unassigned)
        amount = int(a.number_input('Tomar', min_value=1, max_value=top, value=top, step=1, key=key + '_take_qty'))
        catalog = bool(part.get('component_id'))
        confirmed = catalog or st.checkbox(f'Confirmo que uso {amount} piezas físicas del inventario para este pedido', key=key + '_take_ok')
        if b.button(f'Tomar {amount} de inventario y no imprimirlas', key=key + '_take', icon=':material/move_to_inbox:', width='stretch',
                    disabled=not confirmed):
            perform(piece_stock.use_stock, part['id'], amount,
                    message=f"{amount} piezas {'reservadas' if catalog else 'tomadas'} de inventario para el pedido; ya no se imprimen.")
    for host in part.get('incoming', [])[:3]:
        top = min(host['free'], unassigned)
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center', gap='small'):
            st.caption(f":material/local_shipping: **{host['free']} extra en {host['code']}** · {host['machine_code'] or 'sin máquina'} · "
                       f"{host['status'].lower()}" + (f" · termina {when(host['eta'])}" if host['eta'] else ''))
            if st.button(f"Sumar {top} a {host['code']}", key=f"{key}_ride_{host['job_id']}", icon=':material/add_link:',
                         help='Esas unidades se imprimen en esa impresión, no aparte; se terminan cuando termine.'):
                perform(piece_stock.ride_print, part['id'], host['job_id'], top,
                        message=f"{top} piezas van en la impresión {host['code']}: no se imprimen aparte.")


def extra_input(key: str, units: int, process: str, *, development=False) -> int:
    """Units printed beyond the order's need; they enter inventory when the print finishes."""
    if development or process not in PRINT_PROCESSES:
        return 0
    extra = int(st.number_input('Unidades extra para inventario', min_value=0, max_value=1000, value=0, step=1, key=key + '_extra',
                                help='Se imprimen además de las del pedido. Al terminar la impresión entran a Colección en Inventario.'))
    if extra:
        st.caption(f":material/add_box: Se imprimen **{units + extra}**: {units} para el pedido + {extra} a inventario al terminar.")
    return extra
