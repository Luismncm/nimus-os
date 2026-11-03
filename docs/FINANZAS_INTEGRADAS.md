# v0.43 · Cuentas, gastos y previsión

## Tres cifras conectadas

**Total en cuentas** utiliza desde el inicio los datos existentes de las cuentas activas: entradas menos salidas de todo el historial asignado a cada cuenta. Incluye las aportaciones efectivas y los pagos importados sin fecha. No suma compras pagadas directamente por socios ni duplica anticipos de cotizaciones convertidas en ventas.

Si confirmaste el saldo de una cuenta, se utiliza ese saldo más los cambios posteriores en sus movimientos. Cada cuenta indica **Movimientos** o **Conciliado**. Es un saldo registrado en NIMUS; para compararlo con el saldo real bancario usa **Conciliar saldos**. El formulario viene precargado y sólo necesitas ajustar diferencias. No genera ingresos ni gastos ficticios.

**Gastos proyectados** suma todos los gastos registrados pendientes de pago, de cualquier fecha, más las previsiones del mes elegido y cualquier ajuste mensual general conservado de versiones anteriores.

**Después de gastos** es Total en cuentas menos Gastos proyectados. Conserva los negativos. No descuenta de nuevo los gastos ya pagados ni suma ventas que todavía no has cobrado.

Los tres módulos —Control de gastos, Registro de gastos y Tesorería— comparten este cálculo. Los filtros de documentos y movimientos afectan sus consultas, sin cambiar el saldo global. La navegación superior conecta los módulos. Las cuentas archivadas y los movimientos sin cuenta no suman al saldo de cuentas activas.

## Un flujo para cada gasto

1. **Todavía es una idea o compra futura:** Agregar previsto. Captura concepto, importe y, si la sabes, cuenta prevista. Fecha, categoría y proveedor son opcionales.
2. **Ya corresponde registrarlo:** desde Previsión usa Registrar gasto. Elige Por pagar o Ya pagado. El concepto y monto vienen precargados.
3. **Ya se pagó:** registra el pago desde Por pagar o el detalle del gasto. El saldo de la cuenta y el pendiente se actualizan.

La conversión de una previsión en gasto ocurre en una sola transacción: retira la previsión y crea el gasto, y el pago si corresponde. El mismo importe no queda en dos lugares. Conserva el historial y el vínculo al gasto. Los reintentos no duplican registros y una edición concurrente impide guardar datos obsoletos.

Las previsiones se pueden editar o cancelar antes de registrarlas. Cancelar conserva el historial. Los ajustes mensuales generales se mantienen en Previsión → Ajuste general e historial; son manuales y adicionales, por lo que deben reducirse cuando dejen de aplicar.

## Operación diaria

- **Resumen:** saldo por banco, efectivo y pasarela, cuenta prevista para cada pendiente y saldo después de gastos. Los compromisos sin cuenta se descuentan del total global y se identifican como pendientes de asignar.
- **Por pagar:** búsqueda y filtros de vencimiento y cuenta. Permite registrar pagos parciales y abrir comprobantes.
- **Previsión:** conceptos por gastar, conversión a gasto, edición, cancelación e historial.
- **Evaluar proyecto:** usa automáticamente el mismo dinero y los mismos gastos; sólo solicita costo y reserva. Es cobertura de dinero, no rentabilidad.
- **Registro de gastos:** captura rápida, captura completa, importes numéricos y consulta de todos los pendientes, además de comprobantes y costos recurrentes.
- **Tesorería:** cuentas, movimientos, conciliación, cobros, pagos y socios. Los filtros del historial están agrupados y el flujo queda como consulta secundaria al saldo actual.

Las previsiones no realizan pagos ni transferencias. Los movimientos fuera del sistema y las correcciones de historia ya conciliada se revisan contra banco o caja usando Conciliar saldos. Los costos recurrentes y presupuestos anteriores permanecen disponibles, sin convertirse automáticamente en compromisos.

## Datos y respaldo

La migración 24 → 25 añade dos tablas para previsiones e historial. No modifica las cuentas, cobros, pagos, ventas, inventario ni presupuestos existentes. La instalación crea respaldos del código y la base y verifica los valores almacenados.
