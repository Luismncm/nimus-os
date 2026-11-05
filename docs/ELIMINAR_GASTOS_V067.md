# v0.67 · Eliminar gastos efectuados (app local)

## Qué cambió

Un gasto ya registrado solo se podía **Cancelar** (se queda como histórico de solo lectura, visible y sumando en el conteo de la categoría aunque no cuente para el saldo). No había manera de borrarlo por completo. La base de datos lo impedía con un disparador explícito: *"Cancela el gasto para conservar su historial."*

Ahora, en **Gastos y comprobantes → detalle del gasto → Más opciones**, hay un botón **Eliminar gasto** además de Cancelar:

- **Cancelar**: se conserva, deja de contar, se puede reabrir. Para un gasto real que ya no aplica pero vale la pena recordar.
- **Eliminar**: desaparece por completo — el gasto, sus pagos y su historial — sin dejar rastro. Para una captura duplicada o equivocada. **No tiene vuelta atrás.**

El diálogo pide un motivo y deja claro, antes de confirmar, que no se puede recuperar.

## Dónde sigue bloqueado, y por qué

Eliminar se bloquea solo cuando la base de datos se quedaría con una referencia sin destino — los mismos casos que ya protegen otras tablas financieras del sistema:

| Caso | Por qué se bloquea | Mensaje |
|---|---|---|
| Un socio cubrió el gasto | Es su historial de aportación; tampoco se puede cancelar | «Un socio cubrió este gasto…» |
| Vinculado a una compra de inventario | El pedido de compra depende de ese gasto para su costo | «Está vinculado a una compra de inventario…» |
| Vinculado al costo adicional de un pedido | El pedido usa ese gasto como uno de sus costos | «Está vinculado a un costo adicional de un pedido…» |
| Vinculado a un pedido de filamento o consumibles | Igual que arriba, del lado de consumibles | «Está vinculado a un pedido de filamento o consumibles…» |
| Viene de la migración histórica de NIMUS · Control | Es el respaldo de esa importación | «Viene de la migración histórica…» |

En cualquiera de estos casos sigue disponible **Cancelar**, salvo el del socio (ese gasto queda fijo como historial de la aportación, ya sea que se cancele o no).

Un pedido o pago ya **entregado/cancelado no cambia**: esto no toca esas reglas, solo agrega una salida para el gasto en sí.

## Cómo se implementó

La base de datos ya no permitía borrar un gasto bajo ninguna circunstancia — dos disparadores (`expense_keep`, `expense_payment_keep`) lo bloqueaban siempre, sin condición. Se reemplazaron por versiones condicionadas: bloquean salvo que una tabla pequeña (`expense_delete_unlock`) tenga una fila, algo que solo ocurre durante la propia operación de borrado (dentro de su misma transacción) y nunca por accidente desde otro lugar del código. Esto es una **migración de esquema** (v33 → v34, `models/expense_delete_schema.py`), igual que las demás migraciones de NIMUS: con su respaldo automático antes de aplicarse.

Como el resto de los servicios, esta migración y el nuevo `services.expenses.delete()` funcionan igual en SQLite (app local) y en Postgres (nube) — verificado con `scripts/test_postgres.py`. **No se expuso ninguna ruta en la API ni en la web**: por ahora, eliminar un gasto solo está disponible en la app local, igual que ya pasa con editar o corregir gastos conciliados.

## Verificación

- 6 pruebas nuevas en `tests/test_expenses.py`: borrado con pagos e historial, motivo y revisión obligatorios, los tres bloqueos (socio, costo adicional de pedido, migración histórica — este último cubre también el de inventario y consumibles, que siguen el mismo patrón), la migración v33→v34 sobre una base existente (con respaldo), y el flujo completo en la interfaz.
- Suite completa: 538/540 — los 2 que no pasan son ajenos a este cambio (`test_reset_origen`, ya fallaba antes; una prueba de Hoy sensible a la hora del día).
- `scripts/test_postgres.py tests.test_expenses`: 23/23 (una prueba de migración se omite en Postgres a propósito, como las demás).
- Verificado en el navegador, contra una copia de la base real (nunca la base real en sí): se creó un gasto de prueba y se eliminó desde la interfaz, confirmando que desaparece de la lista y de los totales.
