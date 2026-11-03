# v0.42 · Saldos y proyección de gastos

Control de gastos presenta tres tarjetas en MXN:

- **Total en cuentas:** saldos confirmados de todas las cuentas activas, incluido efectivo.
- **Gastos proyectados:** todos los gastos pendientes actuales más el adicional previsto del mes seleccionado.
- **Saldo estimado:** total en cuentas menos gastos proyectados. Puede ser negativo.

## Empezar

En **Actualizar saldos**, captura lo que ves hoy en banco y caja. Usa 0 sólo para una cuenta vacía; en blanco significa sin confirmar. Si una cuenta ya no se utiliza, archívala en Tesorería → Cuentas. El total y el saldo estimado quedan sin calcular mientras falte confirmar una cuenta activa. No se inventan saldos a partir del flujo histórico.

Los cobros, pagos y aportaciones de socios registrados después de confirmar se incorporan automáticamente. El saldo confirmado ya incluye todos los movimientos que existían al confirmarlo, incluso históricos sin fecha. Cada movimiento se cuenta una vez. La confirmación es un punto de conciliación y no crea un cobro, gasto, aportación ni transferencia.

Si realizas movimientos fuera del sistema, transferencias entre tus cuentas, o corriges o asignas registros históricos que ya estaban conciliados en banco, vuelve a confirmar las cuentas afectadas. Los saldos son un registro local y no están conectados al banco.

## Previsión sencilla

**Gastos previstos** guarda un único importe adicional por mes y una nota opcional. Captura únicamente lo que aún no esté registrado como gasto: los pendientes se incluyen automáticamente. Cuando conviertas esa previsión en un gasto registrado, reduce el adicional para no contarlo dos veces. No se toman automáticamente topes de presupuestos anteriores ni ventas por cobrar.

Los pendientes se incluyen completos, aunque correspondan a otros meses o no tengan fecha. Los pagos parciales y lo cubierto por socios ya se descuentan del pendiente. Lo pagado no se descuenta otra vez del saldo confirmado.

**Evaluar proyecto** usa las mismas cuentas y gastos proyectados. Sólo requiere el costo y, si deseas, una reserva. **Simular con otro monto** es un escenario temporal; no cambia tus saldos. Se evalúa cobertura de dinero, no rentabilidad.

## Conservación de datos

La migración 23 → 24 añade dos tablas de historial inmutable, sin modificar gastos, pagos, ventas, inventario ni presupuestos anteriores. Antes de instalar se respaldan código y base de datos y se verifica que todas las filas existentes se conserven.
