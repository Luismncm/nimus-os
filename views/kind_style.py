"""Cards colored by what a print is for: customer orders, Colección Origen, stock and prototypes never look alike.

Streamlit gives a keyed container the class st-key-<key>; the stylesheet below colors every container
whose key starts with kind-<type>-, so any view can opt in by keying its card.
"""
import html
import re
import streamlit as st

# One palette for drawn status (progress bars, 24 h strips, calendar), matching .streamlit/config.toml.
PALETTE = dict(done='#0F6F78', printing='#3D6FA3', booked='#A9C3D6', idle='#E1E8EB', track='#EEF2F4', paused='#B0691F',
               danger='#B2434C', muted='#64737C', prototype='#7A5FA6', prototype_booked='#C9BCE0', free='#2F7A57',
               # Colección Origen: gold on black, its own line in the queue, the orders and its page.
               origin='#B8902F', origin_ink='#1F1C17', origin_light='#E2C275', origin_booked='#E6D3A3')
COLORS = {'Pedido': (PALETTE['free'], '#FFFFFF'), 'Origen': (PALETTE['origin'], '#FFFCF3'), 'Stock': (PALETTE['printing'], '#FFFFFF'),
          'Prototipo': (PALETTE['prototype'], '#FAF8FD')}
# One identity color per customer order, so its cards, prints and tags are told apart at a glance. They stay clear of
# the status colors (teal, blue, green, orange, red), of the prototype violet and of the Origen gold.
IDENTITY = ('#4B63C9', '#C2547A', '#6B8E23', '#D2693F', '#1E8FB0', '#8C6A4A', '#5B7088')
STATES = (('printing', PALETTE['printing']), ('free', PALETTE['free']), ('alert', PALETTE['paused']))
STYLE = '<style>' + ''.join(
    f'[class*="st-key-kind-{kind.lower()}-"]{{border-left:4px solid {edge}!important;background:{fill}!important;}}'
    for kind, (edge, fill) in COLORS.items()) + ''.join(
    f'[class*="st-key-floor-{state}-"]{{border-top:4px solid {edge}!important;}}'
    for state, edge in STATES) + (
    # The piece or printer picked in the assignment panel.
    '[class*="st-key-pick-on-"]{border:2px solid #0F6F78!important;background:#F1F8F8!important;}'
    # The printer tile picked in the queue grouped by printer keeps its state edge and gets a ring.
    '[class*="st-key-floor-"][class*="-on-"]{box-shadow:0 0 0 2px #0F6F78!important;background:#F1F8F8!important;}'
    # Section and order headings of the grouped queue.
    '[class*="st-key-qhead-"]{border-bottom:1px solid rgba(128,128,128,.25);padding-bottom:.25rem;margin-top:.5rem;}'
    '[class*="st-key-qorder-"]{padding-left:.25rem;margin-top:.25rem;}') + ''.join(
    # Printer cards of the queue keep the floor's state edge: printing blue, free green, attention orange.
    f'[class*="-mstate-{state}-"]{{border-top:4px solid {edge}!important;}}'
    for state, edge in STATES) + ''.join(
    # Orders: the edge of a card keyed with its tone (kind-pedido-o3-…, panel-order-o3-…); stock and prototypes keep their kind color.
    f'[class*="st-key-kind-pedido-{slug}-"],[class*="st-key-panel-order-{slug}-"]{{border-left:4px solid {edge}!important;}}'
    for slug, edge in [(f'o{i}', c) for i, c in enumerate(IDENTITY)] + [('stock', PALETTE['printing']), ('proto', PALETTE['prototype']), ('origen', PALETTE['origin'])]) + '</style>'


def order_tone(order_id, kind='Pedido'):
    """(key slug, hex) of an order: its own identity color; Origen, stock and prototypes keep the color of their kind."""
    if kind == 'Prototipo':
        return 'proto', PALETTE['prototype']
    if kind == 'Origen':
        return 'origen', PALETTE['origin']
    if kind == 'Stock':
        return 'stock', PALETTE['printing']
    i = int(order_id) % len(IDENTITY)
    return f'o{i}', IDENTITY[i]


def order_kind(order):
    """Kind of an order record: Prototipo, Stock straight to inventory, Origen (Colección Origen), Stock lot or Pedido."""
    if order.get('development'):
        return 'Prototipo'
    if order.get('stock_run'):
        return 'Stock'
    if is_origin_order(order):
        return 'Origen'
    return 'Stock' if order.get('fulfillment') == 'Stock' else 'Pedido'


def is_origin_order(order):
    """An order with a Colección Origen product: a lamp recipe or an item marked for the collection."""
    return any(i.get('collection') == 'Origen' or i.get('is_origin_lamp') for i in order.get('items', []))


def order_chip(text, order_id, kind='Pedido', *, help=''):
    """The order's code as a chip in its color, with a dot: the same chip wherever the order shows up.

    Colección Origen orders read as gold on black, with the dot of their own order color.
    """
    if kind == 'Origen':
        dot = IDENTITY[int(order_id) % len(IDENTITY)]
        st.html(f'<span title="{html.escape(help)}" style="display:inline-flex;align-items:center;gap:.4rem;font-size:.82rem;font-weight:650;'
                f'color:{PALETTE["origin_light"]};background:{PALETTE["origin_ink"]};border:1px solid {PALETTE["origin"]};padding:.12rem .6rem;'
                f'border-radius:99px;white-space:nowrap;letter-spacing:.01em"><span style="width:.5rem;height:.5rem;border-radius:50%;background:{dot};'
                f'box-shadow:0 0 0 1.5px {PALETTE["origin"]}"></span>{html.escape(text)}</span>')
        return
    color = order_tone(order_id, kind)[1]
    st.html(f'<span title="{html.escape(help)}" style="display:inline-flex;align-items:center;gap:.4rem;font-size:.82rem;font-weight:650;'
            f'color:{color};background:{color}1A;border:1px solid {color}55;padding:.12rem .6rem;border-radius:99px;white-space:nowrap">'
            f'<span style="width:.5rem;height:.5rem;border-radius:50%;background:{color}"></span>{html.escape(text)}</span>')


def card(kind, key, *, gap='xxsmall', order_id=None):
    """Bordered container tinted by kind: Pedido, Origen, Stock or Prototipo. A customer order's card takes its identity color."""
    kind = kind if kind in COLORS else 'Pedido'
    tone = f"{order_tone(order_id)[0]}-" if kind == 'Pedido' and order_id else ''
    return st.container(border=True, gap=gap, key=f"kind-{kind.lower()}-{tone}{re.sub(r'[^a-z0-9_-]', '-', str(key).lower())}")


def kind_of(job):
    """Kind from the queue's destination map when present, else from the job itself."""
    dest = st.session_state.get('queue_destinations', {}).get(job['order_id'])
    if dest:
        return dest['kind']
    return 'Prototipo' if job.get('development') else 'Stock' if job.get('stock_run') else 'Origen' if job.get('collection') == 'Origen' else 'Pedido'
