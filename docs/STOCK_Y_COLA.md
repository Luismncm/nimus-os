# v0.45 · Stock sin pedido y cola agrupada

## Nueva impresión: Pedido, Stock o Prototipo

**Cola de producción → Nueva impresión** pregunta primero para qué es la impresión:

- **Pedido**: una pieza de un pedido de cliente (con o sin venta), o una pieza nueva de un pedido personalizado.
- **Stock**:
  - **Directo a inventario** (sin pedido): eliges una **Pieza libre** (nombre, modelo opcional, material y proceso) o una pieza **Del catálogo**, las unidades, la impresora y el horario. No hace falta crear ni vincular un pedido.
  - **Lote de stock**: una pieza de un lote creado desde receta con destino Stock, como hasta ahora.
- **Prototipo**: un proyecto de Desarrollo y prototipos.

### Cómo funciona el stock directo

La impresión entra a la cola como cualquier otra: reserva su horario en la máquina, cuenta en el filamento previsto y tiene costo. Cada pieza buena entra a **Colección** en Inventario en cuanto se registra su avance; si corriges el avance hacia abajo, las piezas salen de nuevo. Al terminar, la impresión se cierra sola y no aparece en el tablero de Pedidos, en Hoy ni en Notificaciones, porque no hay nada que entregar.

Con una pieza **Del catálogo**, las unidades van a la línea de inventario de esa pieza: los pedidos desde receta las ven y las reservan sin imprimirlas. Con una **Pieza libre**, van a la línea del modelo, pieza y material que capturaste (o a *Stock general* si no indicas modelo).

## Usar piezas de inventario en un pedido

Una pieza de un pedido ya reconoce lo que hay en inventario de **la misma pieza, material y proceso**, aunque se haya impreso para otro modelo o como stock directo. Primero se usa la del mismo modelo. El aviso dice de dónde vienen: «Ya hay 5 en inventario (5 en Colección), incluye piezas de Stock general».

Dentro del pedido, en **Producción**, aparece el aviso **Hay piezas en inventario para este pedido** cuando alguna pieza por asignar ya existe en inventario. **Usar inventario** abre una ventana con todas esas piezas: eliges cuántas tomar de cada una y se toman juntas en una sola operación (todas o ninguna). Lo que tomas cuenta como pieza terminada del pedido y ya no se imprime:

- Las piezas libres salen del inventario (se pide confirmar que se usan piezas físicas).
- Las piezas del catálogo quedan reservadas para el pedido hasta su entrega.

El botón **Tomar de inventario** por pieza, al asignar o en Nueva impresión, sigue disponible.

## Cola de producción agrupada

Las tres agrupaciones de **Operar** comparten el mismo diseño: las tarjetas de impresoras en vivo arriba y las mismas filas a todo lo ancho abajo.

- **Máquina**: cada tarjeta tiene **Ver su cola** para ver solo esa impresora (lo que imprime ahora, su cola, su franja de 24 h y las piezas que conviene asignarle). **Todas las impresoras** muestra cada impresora como sección con su disponibilidad, carga y franja. **Sin máquina** aparece cuando hay trabajos sin impresora.
- **Estado**: Imprimiendo, En cola y Pausadas o bloqueadas, cada una con sus unidades pendientes y horas de trabajo. Las terminadas quedan plegadas al final.
- **Para qué es**: Pedidos de clientes, Stock y Prototipos. Dentro de cada grupo, las impresiones se ordenan por pedido, lote o proyecto, con su avance, fecha de entrega y un acceso al pedido. Las impresiones de stock directo van juntas.

## Datos y compatibilidad

Migración de esquema 32 a 33: agrega la tabla `stock_runs`, que marca las impresiones de stock directo, sin modificar registros anteriores. Antes de actualizar se hace un respaldo (`pre-stock-directo-v33`). Las existencias, reservas, pedidos y trabajos anteriores no cambian.
