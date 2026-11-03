"""One status flow for every purchase order: piece/supply orders and filament spools.

Solicitado → Confirmado → En camino are set by hand as the supplier answers;
Recibido parcial and Recibido follow from receipts; Cancelado closes what is left.
"""

STAGES = ('Solicitado', 'Confirmado', 'En camino')
FLOW = (*STAGES, 'Recibido parcial', 'Recibido', 'Cancelado')
COLORS = {'Solicitado': 'gray', 'Confirmado': 'blue', 'En camino': 'violet', 'Recibido parcial': 'orange',
          'Recibido': 'green', 'Cancelado': 'gray'}
OPEN = (*STAGES, 'Recibido parcial')


def status(stage, ordered, received, cancelled):
    if cancelled:
        return 'Cancelado'
    if received >= ordered:
        return 'Recibido'
    if received:
        return 'Recibido parcial'
    return stage or 'Solicitado'
