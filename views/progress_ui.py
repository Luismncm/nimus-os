"""One native progress treatment for order cards, products, pieces and daily views."""
import streamlit as st
from services.order_progress import manufacturing, supplies, fabrication_label, breakdown
from views.kind_style import PALETTE

# Same order and words everywhere: Terminadas · En curso · En cola · Sin asignar.
SEGMENTS = (('completed', 'terminadas', PALETTE['done']), ('running', 'en curso', PALETTE['printing']),
            ('queued', 'en cola', PALETTE['booked']), ('unassigned', 'sin asignar', PALETTE['idle']))
HELP = ('Terminadas: unidades buenas. En curso: trabajos imprimiendo. En cola: asignadas que esperan, '
        'pausadas o bloqueadas. Sin asignar: falta crear su trabajo. Los insumos comprados y las piezas '
        'tomadas de inventario se controlan por separado.')


def breakdown_text(b):
    words = [f"{b['completed']}/{b['required']} terminadas"]
    words += [f"{b[k]} {label}" for k, label, _ in SEGMENTS[1:] if b[k]]
    if b['blocked']:
        words.append(f"{b['blocked']} bloqueado" + ('s' if b['blocked'] > 1 else ''))
    return ' · '.join(words)


def stacked_bar(b, *, caption=True):
    """Units by work state in one bar; the text below carries the same numbers."""
    total = b['required'] or 1
    cells = ''.join(f'<span style="flex:{b[k]} 0 0;background:{color}"></span>' for k, _, color in SEGMENTS if b[k])
    summary = breakdown_text(b)
    st.html(f'<div role="img" aria-label="{summary}" title="{summary}" style="display:flex;gap:2px;height:8px;border-radius:99px;'
            f'overflow:hidden;background:{PALETTE["idle"]};width:100%">{cells}</div>')
    if caption:
        st.caption(f"{round(100 * b['completed'] / total)}% · {summary}", help=HELP)


def production_progress(record):
    m, s = manufacturing(record), supplies(record)
    if m['applicable']:
        stacked_bar(breakdown(record))
    else:
        st.badge(fabrication_label(record), color='gray', icon=':material/inventory_2:' if m['defined'] else ':material/edit_note:')
    stock = record.get('manufactured_from_stock', 0)
    if s['required'] or stock:
        with st.container(horizontal=True, gap='xsmall'):
            if s['required']:
                st.badge(f"Insumos · {s['covered']}/{s['required']} reservados" + (f" · faltan {s['remaining']}" if s['remaining'] else ''),
                         color='orange' if s['remaining'] else 'green', icon=':material/electrical_services:')
            if stock:
                st.badge(f"De inventario · {stock} piezas", color='gray', icon=':material/warehouse:')
    if m['complete'] and s['remaining']:
        st.caption('Fabricación resuelta · Completa los insumos antes de ensamblar y cerrar el pedido.')
