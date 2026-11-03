# Tesorería para operación diaria

Actualizado el 11 de octubre de 2026, cotejado con las pestañas RESUMEN, TESORERÍA, MOVIMIENTOS, VENTAS, COSTOS y SOCIOS de NIMUS · Control.

| Uso en la hoja | Uso en NIMUS |
| --- | --- |
| RESUMEN: entradas, egresos y flujo | Tesorería → Resumen: flujo registrado según período y cuenta. |
| TESORERÍA: banco y caja | Tarjetas y tabla por cuenta, con entradas, salidas y flujo. |
| MOVIMIENTOS: concepto, contraparte, cuenta y comprobante | Movimientos: búsqueda, filtros por entrada/salida y categoría, exportación y acceso al registro. |
| Control de datos incompletos | Por revisar: fecha del gasto, fecha del pago, concepto, categoría, cuenta, comprobante e IVA. |
| SOCIOS: aportaciones, compras pagadas y reembolsos | Socios: entradas a cuenta, compras cubiertas, edición de aportaciones y gasto vinculado; sin duplicar salidas. |
| COSTOS: previsión mensual | Gastos → Costos recurrentes. La previsión no es un pago real. |
| Ventas cobradas y gastos pagados | Resumen usa cobros y pagos efectivos; Cobrar / pagar muestra documentos pendientes por separado. |

## Rutina sugerida

1. Selecciona Este mes o el período que vas a revisar. Todo el historial incluye pagos sin fecha; un período los excluye.
2. Revisa las tarjetas de banco y caja y los controles de captura. El flujo no equivale todavía al saldo disponible.
3. En Movimientos busca el concepto, cliente, proveedor, folio o referencia. El CSV respeta la consulta.
4. En Por revisar selecciona el pendiente, abre su gasto y completa los datos comprobados. Puedes clasificar un gasto histórico sin inventar su fecha.
5. En Cobrar / pagar abre los documentos pendientes para registrar el cobro o pago real desde su detalle.
6. Usa Socios para consultar las compras cubiertas por Ali, el reembolso vinculado y las inyecciones al banco. Editar aportación permite completar fecha y socio y corregir importe, cuenta, concepto, contraparte y comprobante.

## Fechas independientes

Editar la fecha del gasto no cambia la fecha del pago. Un gasto con pago sin fecha sigue apareciendo en Por revisar aunque ya tenga fecha de documento. Para corregir fecha, importe, método, referencia o cuenta efectiva, selecciona el movimiento y pulsa **Conciliar movimiento**, o abre **Gastos → Pagos → Conciliar pago**. El motivo es obligatorio; el historial muestra el valor anterior y el corregido.

## Corregir un gasto pagado

En el detalle del gasto, **Conciliar gasto** habilita importe, IVA, concepto, clasificación, proveedor, comprobante, fechas y notas. Si un solo pago cubre el gasto completo, puedes marcar **Ajustar también el importe del pago completo** cuando ambos importes estaban mal capturados. La fecha y cuenta del pago se corrigen por separado. Con varios abonos, corrige los pagos individualmente antes de reducir el total por debajo de lo pagado.

Las compras pagadas por un socio ajustan también el importe cubierto por él, sin crear una salida de caja o banco. Puedes corregir su fecha de pago independientemente de la fecha del gasto. Las correcciones se guardan completas en una sola transacción; si otra ventana cambió el registro, hay que volver a abrirlo. El historial y la fila original de Sheets se conservan.

## Alcance de la conciliación

Se incorporaron las cinco inyecciones autorizadas de SOCIOS, filas 26–29 y 31: $233,000 MXN como entradas de capital a Cuenta bancaria NIMUS. La de $60,000 conserva fecha y socio sin identificar porque esas celdas están vacías; la contraparte es ALI CHARRUF. Está incluida en Todo el historial y puedes completar sus datos desde Socios. Las compras cubiertas directamente por el socio no son entradas al banco.

No se importaron ventas ni se corrigieron cobros existentes automáticamente. Puedes conciliarlos manualmente desde Movimientos. Los saldos iniciales, el arqueo de caja y las transferencias internas de la hoja siguen pendientes: el flujo registrado no debe interpretarse todavía como saldo bancario conciliado. La hoja permanece como referencia de operación.

Los filtros de la cabecera afectan Resumen y Movimientos. Por revisar, Cobrar / pagar y Socios abarcan todas las fechas y muestran sus filtros propios. Las alertas del resumen son controles globales; un gasto puede participar en más de un control, pero no se duplica su importe en la consulta de pendientes.
