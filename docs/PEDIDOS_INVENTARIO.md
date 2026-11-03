# Pedidos de inventario · v0.38

**Agregar inventario → Registrar como → Pedido** guarda unidades solicitadas sin sumarlas a las existencias físicas.

Selecciona la referencia, cantidad, ubicación de destino, proveedor, referencia de compra y llegada prevista. Puedes usar una pieza existente, un componente del catálogo o una referencia nueva. La llegada prevista y el proveedor son opcionales. El registro de entrada de Colección Origen también permite elegir **Pedido**.

## Seguimiento y recepción

En **Inventario → Pedidos** se muestran las cantidades pedidas, recibidas y pendientes, con estados Pendiente, Parcial, Recibido y Cancelado. Filtra por estado o busca por pieza, proveedor y referencia.

- **Recibir unidades** confirma una llegada física, parcial o completa, y registra la entrada en la ubicación elegida al hacer el pedido. Solo suma lo realmente recibido. El resto sigue pendiente.
- **Seguimiento** conserva notas, proveedor y cambios de fecha prevista en un historial.
- **Más acciones → Cancelar saldo pendiente** cierra lo que falta sin quitar las unidades ya recibidas.
- Una recepción errónea se revierte desde **Movimientos**. Si sus unidades siguen libres, se resta la entrada y el pedido vuelve a mostrar esa cantidad pendiente.

Desde la ficha de una pieza, **Pedir unidades** inicia un pedido con esa referencia. En **Reposición de insumos**, la columna **En pedido** muestra lo que ya se solicitó; **Pedir reposición** propone la cantidad faltante descontando los pedidos pendientes.

Los pedidos aún no recibidos no cuentan como stock ni pueden reservarse. El saldo negativo o mínimo sigue visible hasta que llegue la reposición. Notificaciones reúne las llegadas pendientes y destaca las previstas para hoy o vencidas.

Las operaciones validan cantidades restantes, ventanas desactualizadas y reintentos. La recepción y su movimiento de inventario se guardan en una sola transacción. Crear o recibir pedidos no genera automáticamente ventas, gastos ni pagos.

## Actualización

Migración de esquema 22 a 23: agrega dos tablas de pedidos y seguimiento, sin modificar las filas anteriores. Se realiza respaldo antes de actualizar.
