"""Small read-only decisions that connect the four workshop screens."""
from __future__ import annotations

from datetime import date

from utils.dates import now, parse_deadline
from services.order_progress import manufacturing


def next_step(order: dict) -> dict:
    items = order["items"]
    if order["status"] == "Entregado":
        return {"action": "history", "label": "Pedido entregado", "detail": "Conservado en el histórico."}
    if not items:
        return {"action": "item", "label": "Agrega el primer item", "detail": "Define qué producto vas a fabricar y cuántos necesitas."}
    missing = next((i for i in items if not i["parts"] and not i.get('recipe_id')), None)
    if missing:
        return {"action": "parts", "item": missing, "label": f"Despieza {missing['name']}",
                "detail": f"Define las piezas necesarias para {missing['quantity']} unidades de producto."}
    parts = [p for i in items for p in i["parts"]]
    pending = [p for p in parts if p["quantity_unassigned"] > 0]
    if pending:
        unassigned = pending[0]
        label = (f"Asigna {unassigned['quantity_unassigned']} · {unassigned['name']}" if len(pending) == 1 else
                 f"Asigna {sum(p['quantity_unassigned'] for p in pending)} unidades de {len(pending)} piezas")
        return {"action": "split", "part": unassigned, "label": label,
                "detail": "Reparte las unidades entre máquinas o fuera de impresora; las piezas del mismo material se asignan juntas."}
    if order["status"] == "Listo":
        if order.get('fulfillment') == 'Stock':
            return {'action': 'deliver', 'label': 'Componentes listos para stock', 'detail': 'Cierra el lote para liberar sus reservas y dejar las piezas disponibles en Stock.'}
        if order.get('fulfillment') == 'Cliente':
            return {'action': 'deliver', 'label': 'Componentes cubiertos. Confirma la entrega', 'detail': 'La entrega descontará las piezas reservadas. No representa ensamble de productos terminados.'}
        return {"action": "deliver", "label": "Todo fabricado. Confirma la entrega", "detail": "El pedido quedará visible en el histórico."}
    if order["status"] == "Bloqueado":
        return {"action": "queue", "label": "Revisa el bloqueo", "detail": "Libera el pedido o el trabajo bloqueado para continuar."}
    requirements=[r for item in items for r in item.get('requirements',[])]
    bought=[r for r in requirements if r.get('supply')=='Comprar' and r['covered']<r['quantity']]
    if bought and all(r['covered']==r['quantity'] for r in requirements if r.get('supply')!='Comprar'):
        return {'action':'supplies','label':'Completa los insumos del pedido','detail':'Ingresa las compras recibidas y reserva '+str(sum(r['quantity']-r['covered'] for r in bought))+' unidades de insumos desde inventario.'}
    return {"action": "queue", "label": "Continúa la producción", "detail": f"Faltan {manufacturing(order)['remaining']} piezas por fabricar; ya tienen trabajo asignado."}


def due_label(deadline: str | None, today: date | None = None) -> tuple[str, str]:
    if not deadline:
        return "Sin fecha", "gray"
    try:
        days = (parse_deadline(deadline) - (today or now().date())).days
    except ValueError:
        return "Revisar fecha", "orange"
    if days < 0:
        return f"{abs(days)} d de atraso", "red"
    if days == 0:
        return "Entrega hoy", "orange"
    if days == 1:
        return "Entrega mañana", "orange"
    return f"Entrega en {days} d", "gray"


def even_split(quantity: int, machine_ids: list[int]) -> dict[int, int]:
    if not machine_ids:
        return {}
    quotient, remainder = divmod(quantity, len(machine_ids))
    return {mid: quotient + int(index < remainder) for index, mid in enumerate(machine_ids)}
