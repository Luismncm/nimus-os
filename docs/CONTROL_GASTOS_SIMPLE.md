# v0.41 · Control de gastos primero

**Negocio → Control de gastos** reemplaza la entrada principal a Presupuesto mensual. Su propósito diario es registrar lo gastado, conocer lo pagado y atender los saldos pendientes. No exige metas de ventas, porcentajes de margen ni topes por categoría.

## Capturar

En **Registrar gasto**, indica concepto, importe total y fecha. La categoría se puede seleccionar, reutilizar, crear o completar después. La captura parte de **Por pagar**: no produce una salida de banco ni efectivo.

Si eliges **Ya pagado**, selecciona la cuenta o caja, forma de pago y fecha efectiva. Gasto y pago se guardan en una sola operación y un segundo envío de la misma captura no los duplica. El total se registra sin inventar un desglose de IVA. Desde **Registro de gastos** puedes completar proveedor, comprobante, factura y demás detalles. La captura completa anterior continúa accesible en Más opciones.

## Revisar

- **Resumen:** gastos registrados y pagos efectivos del mes, agrupados por categoría. Los pagos por cuenta y efectivo se consultan en un desplegable.
- **Por pagar:** saldos actuales de todas las fechas, incluyendo abonos y lo cubierto por socios. Permite registrar un pago usando el mismo control existente.
- Los gastos y pagos no se suman como si fueran dos egresos: uno representa la obligación y el otro su liquidación. La fecha del pago determina la salida del mes, aunque el gasto se haya registrado antes.
- Las compras cubiertas por socios aparecen separadas de las salidas de banco/caja. Los registros sin fecha se mantienen visibles para revisión, sin asignarlos a un mes supuesto.

## Evaluar después un proyecto o compra

Esta pestaña opcional usa tres importes: dinero confirmado hoy en cuentas y efectivo, reserva que quieres conservar y costo estimado del proyecto. Descuenta además todos los saldos pendientes actuales registrados.

`Dinero confirmado − pendientes − reserva − costo del proyecto`

Sin un saldo confirmado, no presenta una disponibilidad ficticia. No incorpora ventas por cobrar, metas de ventas ni el flujo histórico como si fueran dinero disponible. La reserva debe incluir compromisos todavía no capturados. El resultado indica cobertura de dinero bajo esos supuestos; no determina rentabilidad, no registra gastos y no mueve ni aparta dinero.

## Planes anteriores

Activa **Ver planeación detallada · opcional** para consultar o continuar los presupuestos mensuales, versiones, borradores y proyecciones existentes. Sus datos se conservan; guardar un gasto no crea un presupuesto ni modifica uno anterior. No se requiere migración de la base: esquema 23.
