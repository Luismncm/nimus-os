# Hoy y detalle del pedido · v0.22

## Hoy

**Resumen** abre una vista de prioridades: pedidos que requieren atención, máquinas disponibles y próximos cobros/pagos. Cada grupo muestra hasta tres registros; sus enlaces llevan al tablero o al área de trabajo completa.

Los indicadores superiores abarcan todos los pendientes. **Producción lista** cuenta pedidos con piezas cubiertas, que todavía pueden requerir revisión o empaque. Los saldos mostrados son cuentas por cobrar/pagar, no saldos bancarios o efectivo contado.

Usa **Producir, Entregar, Cobrar o Pagar** para ejecutar acciones. Busca por cliente, proyecto, concepto o folio y filtra por fecha. La fecha corresponde a entrega para pedidos y a vencimiento para cobros/pagos. Los filtros se mantienen al cambiar de área; **Limpiar búsqueda y fecha** los restablece. La capacidad del taller siempre muestra las máquinas disponibles de todo el taller.

El acceso **Continuar** regresa al último registro abierto. **Herramientas del taller** conserva los controles ampliados de máquinas, revisión, reparto y planificación.

## Al abrir un pedido

El encabezado concentra identificación, cliente, prioridad, entrega, avance de piezas/componentes, productos solicitados, trabajos activos y revisiones. La ruta usa las mismas etapas del tablero.

La acción principal responde al siguiente paso: definir productos o piezas, asignar trabajos, resolver bloqueos, preparar o confirmar entrega. Cuando la producción está cubierta pero faltan checks, **Continuar preparación** abre esa pestaña.

| Pestaña | Uso |
|---|---|
| Producción | Busca productos o piezas, consulta despieces, reparte y trabaja los lotes. La captura de impresión terminada está agrupada en un desplegable. |
| Preparación | Revisa productos, revisión final, empaque y salida. Los checks siguen siendo controles manuales. |
| Documentos | Consulta venta, cobranza y cotización vinculadas. Si venta y cotización comparten pagos, sus importes no se suman. |
| Historial | Revisa la ruta y las fechas registradas de trabajos y seguimiento. |

Cada pedido conserva su pestaña seleccionada durante la sesión. Al agregar una pieza, el sistema vuelve a Producción, limpia la búsqueda y enfoca su producto. Los entregados mantienen sus documentos e historial en solo lectura.

La captura de impresión completa unidades e inventario según las reglas existentes. Confirmar entrega continúa siendo una acción explícita. Consultar estas vistas no modifica registros financieros ni producción.
