# Socios · NIMUS v0.20

En **Tesorería → Socios**, pulsa **Nueva aportación** para registrar dinero recibido del socio. Captura nombre, fecha efectiva, importe, cuenta receptora y referencia bancaria o folio; puedes añadir comprobante y notas. El banco NIMUS se propone cuando está activo, y puedes elegir otra cuenta activa.

La aportación aparece una sola vez como entrada de capital en Tesorería y en la relación de Socios. No se registra como venta, cobro comercial ni gasto. Si vuelve a enviarse la misma captura, se conserva el movimiento original. Se rechaza repetir una referencia con la misma cuenta, fecha e importe entre aportaciones vigentes.

Los registros manuales tienen folio SOC e historial propio. La procedencia de los registros importados de la hoja se conserva; las capturas nuevas no se presentan como filas de Google Sheets.

Puedes **Editar aportación** para conciliar sus datos con un motivo y conservar los valores anteriores. **Anular registro** elimina su efecto en las cuentas, conserva la evidencia y permite consultarlo con Estado → Anulados. Anular una captura no realiza una devolución real de dinero.

Las compras pagadas directamente por el socio y los reembolsos vinculados conservan su gasto de origen. Esta captura es para inyecciones de dinero efectivamente recibidas en cuentas del negocio.

## Mejora de UX en presupuesto

- Los totales y el flujo del borrador se actualizan al editar.
- La etiqueta Borrador sin guardar distingue los cambios pendientes del plan guardado.
- Los borradores se conservan por mes durante la sesión, incluso al consultar otro mes o volver desde otra vista. Guarda el plan para conservarlo en la base.
- Los escenarios usan el borrador actual para probar decisiones; el control real y la proyección de meses siguen utilizando planes guardados.
- Las aportaciones de socios permanecen separadas del desempeño comercial y de la rentabilidad operativa.
