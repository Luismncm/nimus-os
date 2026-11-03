# Carrito y flujo comercial · v0.31

En **Colección Origen → Venta y pedido** selecciona modelo, color de base y cantidad. Pulsa **Agregar al pedido** y repite para el mismo cliente. Cantidades, precios, duplicar y quitar se actualizan en el resumen. La disponibilidad se reparte entre todas las combinaciones: una pantalla o insumo libre no se reserva dos veces. Las fotografías registradas de pantalla/base aparecen al seleccionar.

## Guardar y continuar

- **Cotización:** captura precios y guarda el alcance con sus recetas. Desde Cotizaciones acepta el documento y registra la venta cuando corresponda. Los cobros de cotización y venta usan el mismo registro.
- **Venta confirmada:** guarda directamente la venta y una versión de sus costos. Registra el dinero efectivamente recibido por separado.
- **Pedido operativo:** crea directamente un pedido de cliente o stock, sin venta ni cobro automático. Úsalo para necesidades internas o producción ya gestionada comercialmente.

Cotizar o confirmar una venta no aparta inventario. **Crear pedido** desde su ficha fija las recetas, reparte y reserva las piezas disponibles, genera producción solo por los faltantes fabricados y conserva los insumos por comprar. Las partidas manuales para fabricar siguen requiriendo despiece. Un documento crea como máximo un pedido.

El carrito es un borrador de sesión: se conserva al navegar, pero puede perderse al cerrar/reiniciar la sesión. **Nueva captura** lo limpia. Reutilizar una venta de Origen vuelve al carrito con sus recetas y precios; revisa fechas y autoriza el nuevo documento por separado.

## Condiciones por venta

En la captura o en **Flujo comercial → Editar condiciones** define:

- Autorización de producción, sin mínimo fijo inicial. Opcionalmente elige porcentaje o importe de anticipo para esa venta.
- Requerir o no el saldo liquidado antes de entregar.
- Origen del contacto, segmento de precio acordado, responsables, forma de entrega, fecha prometida y referencia/dirección/guía.
- Acuerdos particulares. Los cambios requieren motivo y conservan historial.

La autorización es explícita. Si se cambia después de crear el pedido, se verifica al iniciar/reanudar nuevos trabajos o terminar directamente uno nunca iniciado. El avance real de un trabajo ya iniciado puede registrarse. La entrega verifica la condición de pago y también las revisiones, ensamble e insumos requeridos. Las condiciones de una cotización vinculada se comparten con su venta.

Los documentos anteriores mantienen su comportamiento hasta incorporar condiciones explícitamente. Cambiar la fecha prometida en condiciones no reprograma trabajos ya agendados; revisa la fecha del pedido y la agenda.

## Costos y preparación

Precios unitarios, descuento, IVA, envío cobrado y costo estimado del envío se capturan explícitamente. El segmento de precio identifica el acuerdo comercial; no contiene tarifas automáticas. Una partida sin cargo requiere confirmación.

La utilidad bruta estimada descuenta costos directos y envío de la venta neta sin IVA. Solo aparece con costos completos: siete componentes, ensamble y otros directos de cada receta, más envío si se cobra. Al confirmar venta se congela una versión; ajustes posteriores de costos requieren revisar el costeo de esa venta. Completar costos actuales no cambia automáticamente la versión guardada.

El escenario de preparación usa faltantes impresos, minutos por lote/pieza, cola conocida, máquinas operativas, horas diarias, ensamble y plazo para recibir insumos. Informa los datos pendientes y no genera una fecha si faltan. Es una aproximación en días calendario para revisar la agenda; la fecha prometida se decide por separado.

## Cambios y cancelaciones

**Cambio o cancelación** registra una solicitud y su resolución con historial. Una cancelación pendiente detiene nuevas autorizaciones de producción y entrega. Resolver una solicitud de cambio documenta el acuerdo; no sustituye las cantidades de una receta ya fijada. Copia el alcance al carrito para preparar el documento revisado y gestiona el anterior según su avance.

**Aplicar cancelación y liberar reservas** solo procede sin cobros vigentes, entrega ni trabajos iniciados. Conserva pedido y documentos, libera reservas y retira el pedido de pendientes; se consulta en **Pedidos → Cancelados**.

Con cobros o producción iniciada, conserva la solicitud mientras se acuerdan devolución y destino de las piezas. Esta versión no contabiliza devoluciones de dinero. Anular un pago corrige una captura errónea y no debe usarse como devolución real. La resolución documentada sin aplicar cancelación no cancela automáticamente la operación.

La actualización migra la estructura de datos y conserva finanzas, pedidos, inventario y las nueve recetas existentes. No crea operaciones reales durante la instalación.
