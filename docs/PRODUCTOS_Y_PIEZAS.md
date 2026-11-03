# Productos, piezas y estados · v0.23

Un **producto** es lo que solicita el cliente. Sus **piezas** son los componentes necesarios para fabricarlo. Un **trabajo** asigna una cantidad de una pieza a una máquina o proceso.

## Captura y gestión

- **Agregar producto:** nombre/modelo, cantidad y notas. Inventario Origen es un destino opcional; actívalo solo cuando quieras registrar sus piezas físicas allí.
- **Despiece rápido → Lista rápida:** nombres por línea con material, proceso y cantidad compartidos.
- **Despiece rápido → Tabla detallada:** cada fila permite nombre, unidades por producto, proceso y material distintos. Al guardar se multiplican las unidades por la cantidad del producto. Ejemplo: 3 productos con 2 bases cada uno requieren 6 bases.
- **Vista de piezas → Resumen:** tabla del despiece y selector de la pieza que quieres gestionar. **Tarjetas** muestra todas las piezas.
- **Editar producto**, **Editar pieza**, **Repartir** y **Crear trabajo** quedan junto al registro al que corresponden. Al crear una pieza, el sistema vuelve a su producto y la selecciona.

Editar la cantidad del producto conserva las cantidades totales de sus piezas; revísalas después del cambio. Una receta publicada conserva su despiece y se cambia mediante otra versión.

## Avanzar estados

En **Producción → Iniciar, pausar o terminar producción**, selecciona el trabajo y usa sus botones de estado. **Avance** registra cantidades parciales; **Terminar** registra todas las unidades pendientes como buenas. La disponibilidad de la máquina y los bloqueos siguen validándose.

En **Preparación**, usa **Marcar revisión final**, **Marcar empacado** y **Marcar listo para salida**. Estas acciones también aparecen en **Hoy → Entregar** y en el seguimiento rápido del tablero. Puedes revisar todos los productos con una sola acción después de haberlos comprobado físicamente. Los cambios conservan historial y validan ediciones concurrentes. **Corregir marcas de preparación** permite quitar una marca errónea.

La etapa del pedido se calcula con sus piezas y revisiones. **Confirmar entrega** sigue siendo una confirmación explícita. Los checks de revisión no fabrican piezas ni cambian existencias.

## Reinicio de lámparas

Por solicitud del propietario se reinician los pedidos **ORD-0001 · EXPO DECO** y **ORD-0005 · CÚMULO GRIS para stock**, sus productos, piezas, trabajos, reservas y movimientos de Inventario Origen. Se guarda un respaldo completo y el alcance de los registros retirados. Los demás pedidos, finanzas, catálogo, recetas y costos se conservan.

Inventario empieza vacío. Registra nuevas existencias únicamente cuando haya piezas físicas contadas o nueva producción registrada. Las recetas y costos conservados son definiciones, no existencias.
