# Reposición de insumos · NIMUS OS v0.34

En **Inventario → Reposición de insumos** configura las cantidades mínimas de cable, foco, empaque y sus especificaciones. Se muestran las referencias del catálogo aunque todavía no tengan entradas físicas. En la misma tabla de captura puedes editar varios mínimos y pulsar **Guardar mínimos** una sola vez. Mínimo 0 desactiva el aviso por mínimo. Los saldos negativos siempre se señalan.

## Saldos y emisión de pedidos

**Disponible neto = unidades físicas en taller − reservas activas − necesidades de insumos todavía sin cubrir de los pedidos abiertos.** Cada necesidad se cuenta una sola vez. Las reservas que ya cubren una necesidad no se descuentan otra vez como faltantes.

Ejemplo: tienes 2 cables y emites un pedido de 5 lámparas que necesita 5 cables. Quedan 2 cables reservados, 3 por cubrir y saldo neto **−3**. El pedido se emite normalmente. Al registrar una entrada de 6 cables, el saldo neto pasa a **3**, aun si todavía falta ejecutar Reservar insumos disponibles en el pedido. Al reservarlos, el saldo no se vuelve a descontar.

El saldo negativo representa el faltante comprometido por comprar o registrar. El conteo físico y los movimientos de inventario conservan sus cantidades reales. Se permite emitir pedidos con faltantes; la entrega conserva las verificaciones existentes de componentes, ensamble y preparación. Las cotizaciones y ventas todavía sin pedido operativo no comprometen existencias. La captura comercial muestra una proyección del saldo al emitir producción.

## Alertas discretas

- **Ámbar · Reponer:** el saldo neto llegó al mínimo configurado o está por debajo, sin ser negativo.
- **Rojo · En negativo:** existen faltantes para los pedidos comprometidos. Tiene mayor prioridad que el aviso de mínimo.
- En Hoy e Inventario aparece únicamente un distintivo con el número de insumos por atender y un acceso a la lista. No se abre ninguna ventana ni se envían mensajes externos.
- Control de producción → Avisos permite marcar visto o posponer. Si cambia el saldo comprometido o el mínimo, se genera un contexto nuevo. La indicación en Inventario sigue representando el saldo actual.
- La reposición sugerida cubre el faltante y supera en una unidad el mínimo configurado. Con mínimo 0 sugiere solo cubrir el saldo negativo.

Usa **Registrar entrada física** al recibir unidades reales. Esto aumenta el conteo y recalcula los avisos; no genera gastos ni pagos. Después, reserva los insumos disponibles desde el pedido cuando corresponda. Cancelar correctamente un pedido o eliminar un borrador libera sus compromisos; entregar deja de contar su demanda y conserva la salida física registrada.

## Conservación de datos

El esquema 22 añade únicamente la configuración de mínimos con revisión de cambios concurrentes. No modifica movimientos, cantidades, pedidos, pagos, recetas ni datos históricos existentes. Los mínimos comienzan en 0 hasta que los configures. Las ayudas flotantes retiradas anteriormente permanecen desactivadas.

Verificación: 309 pruebas correctas, incluyendo emisión desde el carrito sin insumos, concurrencia, reservas sin doble descuento, cancelación/entrega, entradas/reversión y guardado de mínimos. Se ensayó la migración con una copia de la base actual comprobando que sus 64 tablas anteriores conservaran todos sus registros. El módulo histórico test_reset_origen.py depende del script externo cotejo.reset_origen, ausente de la instalación, y se excluyó de esta ejecución.
