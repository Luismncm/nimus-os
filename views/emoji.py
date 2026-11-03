"""One emoji vocabulary: the same picture says the same thing in switches, tabs, states and tables.

Emojis are added only where words are shown (format functions, badges, table cells and tab labels through
CSS), never to the stored values, so navigation, remembered choices and tests keep reading the same words.
"""
import streamlit as st

# Sections, views and modes of the pages.
EMOJI = {
    # Lists and filters
    'Activos': '🟢', 'Abiertos': '📂', 'Recibidos': '✅', 'Entregados': '✅', 'Cancelados': '🚫', 'Vencidos': '⏰', 'Sin fecha': '📅',
    'Por pagar': '💸', 'Ya pagado': '✅', 'Por pedir': '🛒', 'Por recibir': '🚚', 'Por reponer': '🟠', 'En negativo': '🔴',
    # Ways of looking at a list
    'Tablero': '🗂️', 'Tarjetas': '🃏', 'Lista': '📃', 'Tabla': '📋', 'Tabla y ficha': '📋', 'Tabla detallada': '📋', 'Lista rápida': '⚡',
    'Ficha': '📄', 'Galería': '🖼️', 'Estado': '🚦',
    # Money
    'Resumen': '📊', 'Movimientos': '🧾', 'Detalle': '📄', 'Pagos': '💳', 'Historial': '🕘', 'Factura y PDF': '📎',
    'Costos recurrentes': '🔁', 'Históricos sin fecha': '🗂️', 'Previsión': '🔮', 'Evaluar proyecto': '⚖️',
    'Cobrar / pagar': '🔄', 'Por revisar': '🔍', 'Socios': '👥', 'Cuentas': '🏦',
    'Registro de ventas': '🧾', 'Cobros del período': '💰', 'Detalle de venta': '📄', 'Pagos e historial': '💳', 'Costos y utilidad': '💹',
    'Editar cotización': '✏️', 'Vista para cliente': '👁️', 'Pagos y recibos': '💳',
    'Plan mensual': '🗓️', 'Control por categoría': '🏷️', 'Proyecciones': '📈', 'Recetas y costos': '💲', 'Utilidad por venta': '💹',
    'Crear gasto': '➕', 'Usar gasto existente': '🔗',
    # Workshop
    'Producción': '🏭', 'Insumos': '🔩', 'Preparación': '🧰', 'Documentos': '📁', 'Trabajos': '🛠️', 'Máquinas': '🖨️',
    'Piezas sin asignar': '🧩', 'Pedidos por definir': '📝', 'Una impresora': '🖨️', 'Repartir en varias': '🔀',
    'Nueva': '➕', 'Nuevo': '➕', 'Reutilizar despiece': '♻️', 'Reutilizar pieza': '♻️', 'Por lote': '📦', 'Por pieza': '🧩',
    'Entrada física': '📦', 'Pedido': '🚚', 'Piezas e insumos': '🧩', 'Filamento y consumibles': '🧵',
    # Catalog and Colección Origen
    'Productos y recetas': '📖', 'Piezas reutilizables': '🧩', 'Receta vigente': '📗', 'Editar receta': '✏️', 'Costos': '💲',
    'Recetas': '📖', 'Venta y pedido': '🛒', 'Crear receta': '✏️', 'Componentes': '🧩', 'Inventario': '📦', 'Pedidos': '📋',
    'Otros artículos': '🛍️', 'Composición': '🧱', 'Disponibilidad para pedido': '✅',
    'Base y colores': '🎨', 'Pantallas': '💡', 'Cliente': '👤', 'Stock': '🏬',
}

# States of prints, orders, printers, payments, purchases and quotations.
STATUS = {
    'En cola': '⏳', 'En producción': '🖨️', 'Pausado': '⏸️', 'Bloqueado': '⛔', 'Terminado': '✅',
    'Pendiente': '🕒', 'Listo': '📦', 'Listo para preparar': '📦', 'Entregado': '✅', 'Cancelado': '🚫',
    'Insumos pendientes': '🔩', 'Componentes pendientes': '🧩',
    'Disponible': '🟢', 'Imprimiendo': '🖨️', 'Mantenimiento': '🔧', 'Fuera de servicio': '🔴',
    'Pagado': '✅', 'Pagada': '✅', 'Parcial': '🌓', 'Vencido': '⏰', 'Activa': '🟢', 'Activo': '🟢', 'Cancelada': '🚫', 'Anulado': '🚫',
    'Solicitado': '📝', 'Confirmado': '👍', 'En camino': '🚚', 'Recibido': '✅',
    'Borrador': '📝', 'Enviada': '📤', 'Aceptada': '🤝', 'Rechazada': '❌', 'Vencida': '⏰',
}

# Table columns that hold a state; their cells get the state's emoji.
STATE_COLUMNS = ('status', 'payment_status', 'operational_status', 'state', 'collection_status')


def tag(value):
    """A section or view with its emoji: 'Movimientos' → '🧾 Movimientos'. Unknown words stay as they are."""
    mark = EMOJI.get(value) or STATUS.get(value)
    return f'{mark} {value}' if mark else value


def status(value):
    mark = STATUS.get(value)
    return f'{mark} {value}' if mark and isinstance(value, str) else value


def icon_tabs(labels, *, key, **options):
    """st.tabs whose labels show their emoji; the tab's value stays the plain word."""
    panels = st.tabs(labels, key=key, **options)
    css = ''.join(f'.st-key-{key} > div > div > [data-testid="stTab"][data-key="{i}"] [data-testid="stMarkdownContainer"] p::before'
                  f'{{content:"{EMOJI[label]} "}}' for i, label in enumerate(labels) if label in EMOJI)
    if css:
        st.html(f'<style>{css}</style>')
    return panels
