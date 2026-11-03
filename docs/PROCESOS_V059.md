# v0.59 · Procesos: horarios, entrega y cobro, rastreo

## Antes de cambiar nada

- **Respaldo de la base real:** `data/backups/nimus_production-antes-procesos-v059-20261103-014418-181521.db`.
- **Sin cambios de esquema:** no se agregó ni quitó ninguna tabla o columna. Todo cambio de datos pasa por los servicios de siempre, con control de revisión, y queda en el historial del registro.

## Lo que mostraron los datos reales

Medido con los propios servicios de la app sobre una copia de la base (solo lectura):

| Proceso | Hallazgo |
|---|---|
| Tiempos y cola | Las **5 de 5** impresiones abiertas estaban *Sin horario*: sin agenda, sin fin estimado y sin avisos de retraso. |
| Cobro | Un pedido **entregado** (ORD-0006) seguía con **$800** por cobrar en VEN-0034. Nada pedía el cobro al entregar. |
| Cobro | **2 ventas** con saldo no tenían vencimiento, así que nunca aparecían como vencidas, y no había forma de ponérselo después. |
| Rastreo | **5 de 9** pedidos activos no tenían venta ni cotización vinculada, y **5** no tenían fecha de entrega. Eso solo se veía en la pestaña Documentos o en un filtro. |

## Mejoras

### 1. Cola: «Programar N sin horario»
Un botón junto a los estados rápidos programa todas las impresiones sin horario de una vez:
- Cada una toma **el primer horario libre de su máquina**, en el orden de la cola (prioridad, luego fecha de entrega). Así la más urgente queda primero y las siguientes se forman detrás, sin encimarse.
- Usa la misma regla que ya tenía el arreglo de una sola impresión (`capture.reschedule_first_free`), así que no hay lógica nueva de choques.
- Las que no tienen máquina, no tienen duración o están en una máquina fuera de servicio se quedan como estaban, y el aviso dice por qué.
- Servicio: `capture.schedule_unscheduled`.

### 2. Entregar → cobrar
Al confirmar la entrega de un pedido cuya venta tiene saldo:
- El diálogo avisa: «VEN-0037 tiene $428.00 MXN por cobrar».
- La casilla **Registrar el cobro al confirmar la entrega** viene marcada. Si se deja marcada, al guardar la entrega se abre el registro de pago con el saldo ya puesto.
- Los lotes de stock no tienen venta y no muestran el aviso.

### 3. Rastreo del pedido, siempre a la vista
Debajo de la cabecera de cada pedido hay una línea **Rastreo**:
- El folio de la **cotización** y el de la **venta**, con su saldo («VEN-0038 · por cobrar $754.00»). Cada folio abre su registro.
- **Cobrar** registra un pago de la venta sin salir del pedido.
- **Sin venta vinculada** (naranja) en pedidos de cliente u Origen que no tienen venta ni cotización.
- **Sin fecha de entrega** (naranja) cuando falta. Se pone desde Más acciones → Editar pedido.

### 4. Vencimiento de una venta, editable
- En el detalle de la venta: **Fijar vencimiento** (o **Cambiar vencimiento**) para cualquier venta activa con saldo.
- Sin fecha aparece el aviso «Saldo sin vencimiento: nunca aparecerá como vencido».
- No acepta fechas anteriores a la venta ni guarda sobre una versión que cambió en otra ventana.
- El cambio queda en el historial de la venta («Vencimiento de pago: sin fecha → 2026-11-10»).
- Servicio: `sales.set_due_date`.

## Verificación

- **Pruebas nuevas:**
  - `test_capture`: programar en lote reserva en orden y sin encimarse en la misma máquina, y reporta la impresión sin máquina sin tocarla.
  - `test_sales`: el vencimiento se puede poner después, rechaza fechas anteriores a la venta y revisiones viejas, vuelve vencido el saldo al día siguiente y deja historial.
- **En el navegador, sobre una copia de los datos:**
  - «Programar 5 sin horario» dejó las 5 con horario y desapareció «Por resolver». A1-01 muestra sus 3 impresiones en fila desde las 02:00.
  - El pedido ORD-0019 muestra «COT-0005 · VEN-0038 · por cobrar $754.00 · Cobrar», y Cobrar abre el pago con el saldo.
  - Entregar ORD-0017 avisó «VEN-0037 tiene $428.00 por cobrar» y, al confirmar, abrió el cobro con $428.00.
  - En la venta aparece «Cambiar vencimiento».
- **Suite completa:** 509 de 510 pruebas pasan. La única falla, `test_reset_origen`, ya existía: importa un módulo `cotejo` que no está en el proyecto.
