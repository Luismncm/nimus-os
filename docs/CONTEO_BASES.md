# v0.40 · Base, CAP y tapa por color

En **Inventario → Bases por color**, consulta los tres componentes por separado. Se muestran todos los colores activos registrados en Colección Origen, incluso si todavía no existe una referencia de inventario o su saldo es cero.

El color y el material identifican cada renglón: no se mezclan piezas de materiales distintos. Las recetas que comparten una base no duplican su conteo.

- **Disponibles:** unidades físicas en Colección y Stock, menos reservas activas.
- **Físicas en taller:** existencias en Colección y Stock; incluyen las reservadas.
- **Reservadas:** piezas físicas apartadas para pedidos.
- **En B2B:** unidades asignadas a clientes, separadas del taller.

**Juegos de base disponibles** toma el menor saldo libre entre Base, CAP y Tapa de cada color y material. Indica componentes suficientes para un juego de base; no confirma ensamble ni lámparas terminadas.

Para ingresar unidades, selecciona **Color y material**, después **Pieza**, y pulsa **Agregar unidades**. La referencia, el color y el material van seleccionados. Confirma cantidad, ubicación y motivo. Al guardar, vuelves a Bases por color con el conteo actualizado. Las correcciones se registran mediante una reversión en Movimientos.

**Pedir unidades** crea un pedido pendiente de recibir. El conteo aumenta solamente al confirmar una recepción física, incluidas las recepciones parciales. La producción terminada también se refleja automáticamente en el conteo; sus reservas permanecen separadas del disponible.

La vista usa el catálogo y los movimientos existentes. Consultarla no crea inventario ni cambia datos históricos. No requiere migración; se conserva el esquema 23.
