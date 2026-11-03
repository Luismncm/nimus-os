# Pedidos · seguimiento visual

En **Operación → Pedidos** la vista inicial es **Tablero**. También hay **Lista** y **Tabla**. Busca por folio, cliente, proyecto, producto o etiqueta. Los filtros y la vista se conservan durante la sesión; «Limpiar filtros» vuelve a los activos.

## Etapas operativas

| Etapa | Qué muestra |
|---|---|
| Planificar | Pedidos sin avance registrado: define productos, piezas y trabajos. |
| Producir | Hay inicio o avance registrado, con piezas todavía pendientes. |
| Preparar | Todas las piezas están cubiertas; falta revisar productos, revisión final, empaque o salida. También permanece aquí un pedido completo que está bloqueado. |
| Salida | Producción cubierta, sin bloqueo y revisiones completas. Confirma la entrega. En stock, basta la revisión de productos y revisión final: se libera a existencias. |
| Entregados | Histórico de solo lectura, separado del trabajo activo. |

Las columnas se calculan a partir de los registros del sistema. Los bloqueados conservan su etapa y llevan una alerta. «Atención primero» ordena bloqueados, atrasados, entregas de hoy y prioridad; también puedes ordenar por fecha, prioridad o más recientes.

## Tarjetas y acciones

Cada tarjeta sigue la misma estructura: folio, destino, proyecto y cliente, estado y prioridad, entrega, avance de piezas, productos y revisiones, trabajos en curso y siguiente paso. La barra cuenta **piezas/componentes**, no lámparas completas ni porcentaje de todo el proceso de entrega.

- **Abrir pedido:** piezas, trabajos, documentos vinculados y ruta del pedido.
- **Seguimiento rápido:** checks de revisión y preparación, revisión de productos y edición de fecha/prioridad. Los cambios se guardan con las validaciones y el historial existentes.
- **Confirmar entrega / Liberar a stock:** abre la confirmación cuando producción permite cerrar. Los checks siguen siendo un control manual; no sustituyen las reglas de producción o inventario ni modifican por sí solos las existencias.

El tablero conserva columnas legibles de 300 píxeles y permite desplazarlas horizontalmente. Usa **Lista** para una lectura vertical en pantallas pequeñas. Se muestran seis tarjetas por columna inicialmente; **Ver 6 más** permite acceder a las restantes. Los contadores siempre incluyen todos los resultados del filtro, incluso las tarjetas aún no desplegadas. La tabla permite abrir cualquier resultado directamente.

## Trazado

En el detalle, **Ruta del pedido → Hitos e historial del pedido** muestra la creación, fechas registradas de inicio y cierre de trabajos, hasta 100 cambios recientes de checks/etiquetas y cierre del pedido. No se inventan fechas de paso entre columnas. Los entregados no generan nuevas alertas de atraso.

Esta versión no cambia importes, pedidos, producción ni inventario al consultar el tablero, y no requiere migrar la base de datos.
