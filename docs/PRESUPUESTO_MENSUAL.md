# Presupuesto mensual · NIMUS v0.19

Actualización v0.20: el editor actualiza totales al cambiar datos y conserva borradores por mes durante la sesión. La etiqueta Borrador sin guardar identifica cambios pendientes; guarda el plan para conservarlo en la base. Los escenarios usan el borrador actual, mientras Control y la proyección mensual utilizan el plan guardado.

En **Tesorería → Presupuesto mensual**, selecciona el mes y completa la estructura por categoría. Los importes iniciales están por definir: no se cargaron metas ni topes aprobados.

1. Captura fijos y variables como **pagos totales previstos**, incluyendo IVA cuando corresponda. Una categoría puede tener ambos. Escribe el motivo y la acción del mes.
2. Revisa el uso: **Operación**, **Costo directo** o **Inversión / único**. Las categorías de producción se proponen como costo directo y Equipo / activos como inversión; puedes cambiarlas. Marca cada categoría como esencial, ajustable u opcional.
3. Captura los cobros esperados de ventas y anticipos. Las aportaciones de socios se muestran aparte del desempeño comercial.
4. Guarda el presupuesto. Copia el mes siguiente desde una versión guardada y ajusta sus topes. Cada guardado conserva un historial completo.

Puedes preparar propuestas desde costos recurrentes activos o desde los pagos del mes anterior. Las propuestas reemplazan el editor y requieren revisión y guardado. Las compras pagadas directamente por socios no se importan como pagos de caja o banco. Los costos de periodicidad Único no se repiten en la propuesta mensual. La naturaleza de gastos históricos sigue siendo un dato a revisar al preparar la propuesta.

## Control del mes

**Pagado** compara el tope con salidas reales por fecha de pago. **Gasto registrado** usa fecha del documento y puede tener pagos en otro mes. **Cubierto por socio** se muestra aparte; no se suma a Pagado. Las tres columnas describen aspectos distintos y no se deben sumar entre sí.

El disponible del presupuesto representa el tope pendiente de ejercer, no el dinero disponible en cuenta. Las categorías sin tope o excedidas aparecen para revisión; la lista de partidas ajustables ayuda a decidir qué reasignar.

Los pagos sin fecha quedan fuera del mes, con una advertencia de importe y cantidad. Las fechas deben conciliarse para lograr un control mensual completo.

## Proyecciones y rentabilidad

La proyección de 3, 6 o 12 meses utiliza los planes guardados de cada mes: cobros comerciales previstos menos todos los pagos presupuestados, incluyendo inversiones. Una meta o un mes faltante se muestra vacío y detiene el acumulado. El estado de cuenta y el arqueo físico siguen pendientes, por lo que el flujo acumulado no representa un saldo real.

Para el escenario de rentabilidad, define las **ventas netas sin IVA**, el **margen después de costos directos** y el **IVA previsto** de las partidas de operación con importes. Sustenta el margen en las recetas, precios y mezcla de productos. No se presupone un margen empresarial a partir de las pocas ventas costeadas.

El cálculo aplica:

- Resultado operativo estimado = ventas netas × margen después de costos directos − gastos fijos de operación sin IVA − variables de operación sin IVA.
- Los variables de operación se ajustan proporcionalmente a la meta de ventas; los fijos permanecen.
- Ventas de cobertura = fijos de operación / (margen − variables de operación / ventas netas de la meta).
- Si ese margen disponible es cero o negativo, no hay una meta finita que cubra los fijos bajo esos supuestos.

El margen ya incluye costos directos de recetas: las partidas marcadas Costo directo no se restan otra vez. Las inversiones afectan la proyección de pagos, pero quedan fuera del resultado operativo. Los supuestos y el uso de cada categoría deben reflejar la operación real; el resultado es una estimación, no utilidad contable.

Puedes simular variaciones de ventas y recortes en los topes de operación marcados ajustables u opcionales. La simulación conserva los topes esenciales y no guarda cambios. Para aplicar una decisión, edita el Plan mensual y guarda una nueva versión.

El presupuesto no crea gastos, cobros, pagos, aportaciones, movimientos de inventario ni transferencias.
