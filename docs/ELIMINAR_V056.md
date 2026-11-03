# v0.56 · Eliminar piezas y trabajos terminados, sin restricción general

## Qué cambió

Antes, `Eliminar pieza` / `Eliminar trabajo` / `Eliminar producto` / `Eliminar pedido` se bloqueaban con «Hay producción registrada. Conserva el histórico y corrige cantidades o estados.» en cuanto un trabajo tenía `started_at`, unidades terminadas o estado Terminado — sin importar si eso tenía alguna consecuencia real en inventario o contabilidad.

Ahora se puede eliminar un trabajo, pieza, producto o pedido completo **aunque tenga producción terminada**, incluyendo su historial. Solo quedan bloqueados dos casos, porque borrarlos dejaría datos inconsistentes de verdad:

1. **El trabajo ya movió piezas a inventario** (entró a Colección, Stock o se entregó). Esos movimientos son un libro contable que nunca se edita ni se borra — solo se revierte. Mensaje: *"Ya movió piezas a inventario (Colección, stock o entrega). Se conserva para no descuadrar las existencias."*
2. **El trabajo tiene una falla de calidad registrada.** Las fallas conservan su historial por diseño (no se pueden editar ni borrar). Mensaje: *"Tiene una falla registrada. Las fallas conservan su historial; elimina primero la falla o deja el trabajo."*

Esto cubre la gran mayoría de pedidos personalizados (que nunca mueven inventario) y dibuja la línea exactamente donde la base de datos la dibuja: en Colección Origen y en piezas del catálogo que sí entran a inventario.

Lo que no cambió:

- Un pedido **entregado o cancelado** sigue siendo de solo lectura, igual que en el resto del sistema.
- Las piezas de un pedido con receta fijada (no personalizado) siguen sin poder eliminarse una por una; hay que eliminar el pedido completo.

## Arreglo de paso: `job_consumption` y `print_reprints`

Al probarlo en el navegador apareció un error crudo de SQLite («FOREIGN KEY constraint failed») al borrar un trabajo que ya tenía una corrección de costo guardada (`Corregir costo`). La tabla `job_consumption` (y `print_reprints`) no tenía borrado en cascada, a diferencia de las demás tablas dependientes de un trabajo. Como esas dos tablas no tienen ninguna garantía de historial (no hay disparador que las proteja, a diferencia de fallas y movimientos de inventario), ahora se limpian explícitamente antes de borrar el trabajo.

## Verificación

- 25/25 pruebas de `test_production.py`, incluyendo dos nuevas: una que borra trabajos iniciados/terminados sin inventario ni fallas (con una corrección de costo guardada de por medio), y otra que confirma que un trabajo de Colección Origen con movimiento de inventario sigue bloqueado.
- En el navegador, con la copia de prueba: se eliminó una pieza terminada (CINTURON, JOB-0048) de un pedido activo sin producción en inventario, y se confirmó que un trabajo de Colección Origen con inventario ya movido (JOB-0044) se sigue bloqueando con el mensaje correcto.
- Suite completa del proyecto: ver resultado en el cierre de esta sesión.
