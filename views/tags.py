"""One tag vocabulary for prints: printer, sale, order, stock and prototype look the same everywhere.

Each tag has a fixed form and color, so a glance tells what something is before reading it:
  printer    a square in the color of its model (A1, P1S, X1…), its code and a dot with its state;
             shows the loaded filament when known
  sale       green, point-of-sale icon, sale code
  order      the order's own identity color, order code and client
  stock      blue, warehouse icon
  prototype  violet, flask icon, project name
  origen     gold on black, order code and client
"""
import html
import re
import streamlit as st
from views.kind_style import order_chip

MACHINE_COLORS = {'Disponible': 'green', 'Imprimiendo': 'blue', 'Mantenimiento': 'orange', 'Fuera de servicio': 'red'}
STATE_DOTS = {'Disponible': '#2F7A57', 'Imprimiendo': '#3D6FA3', 'Mantenimiento': '#B0691F', 'Fuera de servicio': '#B2434C'}
# Printer models, found in the machine's name or code; the first that matches wins (A1 mini before A1).
FAMILIES = (('A1 mini', r'A1\s*-?\s*MINI', '#0284C7'), ('A1', r'\bA1\b', '#0E7490'), ('P1S', r'\bP1S\b', '#C2410C'),
            ('P1P', r'\bP1P\b', '#9A3412'), ('X1', r'\bX1[CE]?\b', '#15803D'), ('H2D', r'\bH2D\b', '#4338CA'))
OTHER = ('Otra', '#64748B')


def family(machine):
    """(model, color) of a printer, from its name or code: every A1 shares one color, every P1S another."""
    text = f"{machine.get('name', '')} {machine.get('code', '')}".upper()
    return next(((name, color) for name, pattern, color in FAMILIES if re.search(pattern, text)), OTHER)


def printer_html(machine, *, material=True):
    """The printer as a chip: model square, code, state dot and, if wanted, the loaded filament."""
    if not machine:
        return ('<span style="display:inline-flex;align-items:center;gap:.35rem;font-size:.8rem;font-weight:600;color:#5E6E77;background:#EDF1F3;'
                'border-radius:8px;padding:.12rem .55rem;white-space:nowrap">Sin máquina</span>')
    model, color = family(machine)
    loaded = machine.get('loaded_material')
    title = f"{machine['name']} · {model} · {machine['status']}" + (f" · cargado: {loaded}" if loaded else ' · filamento cargado sin registrar')
    extra = f'<span style="color:#5E6E77;font-weight:500;overflow:hidden;text-overflow:ellipsis">· {html.escape(loaded)}</span>' if material and loaded else ''
    return (f'<span title="{html.escape(title)}" style="display:inline-flex;align-items:center;gap:.4rem;font-size:.8rem;font-weight:650;color:#18262E;'
            f'background:#fff;border:1px solid {color}66;border-radius:8px;padding:.1rem .5rem .1rem .14rem;white-space:nowrap;max-width:100%;overflow:hidden">'
            f'<span style="background:{color};color:#fff;border-radius:6px;padding:.04rem .38rem;font-size:.66rem;letter-spacing:.05em">{html.escape(model.upper())}</span>'
            f'{html.escape(machine["code"])}<span style="width:.5rem;height:.5rem;border-radius:50%;background:{STATE_DOTS.get(machine["status"], "#64737C")}"></span>{extra}</span>')


def printer_tag(machine, *, material=True):
    st.html(printer_html(machine, material=material))


def destination_tags(dest):
    """What the print is for, as separate tags: prototype or stock, else order (+ its sale)."""
    if not dest:
        return
    if dest['kind'] == 'Prototipo':
        st.badge(dest['project'], color='violet', icon=':material/science:', help='Prototipo · proyecto de desarrollo, no es venta')
    elif dest.get('direct'):
        st.badge('Directo a inventario', color='blue', icon=':material/warehouse:',
                 help=f"{dest['code']} · stock sin pedido: cada pieza buena entra a Colección en Inventario al registrarse.")
    elif dest['kind'] == 'Origen':
        order_chip(f"Origen · {dest['code']} · {dest['client'] or 'Stock'}", dest['order_id'], 'Origen', help=f"Colección Origen · {dest['project']}")
        if dest.get('sale'):st.badge(dest['sale'], color='green', icon=':material/point_of_sale:', help='Venta vinculada al pedido')
    elif dest['kind'] == 'Stock':
        st.badge(f"Stock · {dest['code']}", color='blue', icon=':material/warehouse:', help=f"Lote para stock · {dest['project']}")
    else:
        order_chip(f"{dest['code']} · {dest['client'] or 'Sin cliente'}", dest['order_id'], help=f"Pedido · {dest['project']}")
        if dest.get('sale'):st.badge(dest['sale'], color='green', icon=':material/point_of_sale:', help='Venta vinculada al pedido')


def extra_tag(job):
    """Units printed on top of the order's need, pieces of other orders riding along, or units from stock."""
    if job.get('rides_on'):
        st.badge(f"En la impresión {job['rides_on']['code']}", color='blue', icon=':material/link:',
                 help='Se imprime dentro del excedente de esa impresión y se termina cuando esa termine.')
    if job.get('riders'):
        st.badge('Lleva ' + ', '.join(f"{r['quantity']} de {r['order_code']}" for r in job['riders']), color='blue', icon=':material/add_link:',
                 help='Unidades de otros pedidos que van en esta impresión: se terminan con ella.')
    if job.get('from_stock'):
        st.badge('De inventario', color='green', icon=':material/move_to_inbox:', help='Piezas tomadas del inventario, no impresas.')
    if job.get('extra'):
        posted = job.get('extra_posted')
        st.badge(f"+{job['extra']} a inventario" + (' ✓' if posted else ''), color='blue', icon=':material/add_box:',
                 help=f"Se imprimen {job['quantity'] + job['extra']}: {job['quantity']} del pedido y {job['extra']} extra"
                      + (' que ya entraron a Colección en Inventario.' if posted else ' que entran a Colección en Inventario al terminar.'))


def priority_tag(priority):
    if priority == 'Alta':st.badge('Alta', color='orange', icon=':material/priority_high:')
