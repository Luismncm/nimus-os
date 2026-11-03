# Costos de Origen y utilidad por venta

Actualizado el 11 de octubre de 2026. Referencia proporcionada: [Copia de COSTOS](https://docs.google.com/spreadsheets/d/1oqA3m98MhWdpx6rfbArNL2iCDSbJmXPjOkLRhEfT5Xo/edit#gid=2025707596).

## Costear una receta

Abre **Costos y utilidad → Recetas y costos**, o **Catálogo y recetas → Costear esta receta**. Elige el producto, corrige los costos de cada pieza y completa los adicionales.

- Material + fijo: gramos por pieza × precio por kg ÷ 1,000 + costo fijo por pieza. Usa esta opción cuando el fijo ya cubra máquina u otros trabajos.
- Material + máquina: agrega minutos del lote completo ÷ 60 × tarifa/h ÷ piezas del lote. Evita contar la misma máquina también en el fijo.
- Costo unitario: importe manual por pieza, útil para componentes comprados.
- Kit eléctrico, foco, empaque, ensamble y otros costos se capturan por producto terminado.

Un campo vacío significa **pendiente**; cero es un costo confirmado de cero. Las referencias se guardan en versiones y se pueden consultar desde el formulario de pieza. Cada versión nueva de receta requiere revisar sus adicionales.

## Referencias iniciales

Se incorporaron 12 referencias aproximadas de piezas y los adicionales de las 5 recetas actuales de Origen. Se mantienen las cantidades, recetas y trabajos existentes. La pantalla genérica antigua sin modelo identificado conserva su costo pendiente.

La hoja usa $440/kg, kit $130, foco $55 y empaque $50. En los CAP, 17.5 g × $0.44/g son $7.70 de filamento; la celda original muestra $3.00. El sistema calcula $16.70 con el fijo de $9.00 y documenta esa diferencia. Los costos capturados por producto son $400.55 para Cirrus y $407.15 para Cúmulo, antes de confirmar ensamble/mano de obra.

Si el ensamble ya está incluido en los costos fijos, indícalo en las notas y captura cero; en caso contrario, captura su costo. Estas referencias son estimaciones, no comprobantes de gastos ni valuación del inventario. Los importes deben usar una base consistente sin IVA recuperable; la hoja no acredita su tratamiento fiscal.

## Antes de cada impresión

Desde **Agenda de impresión → Programar / consumos**, registra gramos y duración del lote completo y sus tarifas. Guarda la programación y usa **Usar costo guardado en recetas** cuando el trabajo esté vinculado a una pieza del catálogo.

Confirma las piezas del lote: el costo y los gramos se dividen entre esa cantidad. Por ejemplo, 120 g capturados para una sola pieza se tratan como 120 g/pieza; no se asume que el dato venía de una tanda de cuatro. La referencia se basa en gramos estimados y tiempo planeado; los gramos reales siguen guardados en la impresión para su control.

## Utilidad por venta

Abre **Ventas → detalle → Costos y utilidad**, o **Costos y utilidad → Utilidad por venta**. Asigna a cada partida su versión de receta o un costo unitario manual documentado. Las partidas genéricas “Colección Origen” requieren identificar primero su modelo; el sistema no lo inventa. Los modelos que todavía no tengan receta deben crearse o costearse manualmente.

**Utilidad bruta estimada = venta después del descuento y antes del IVA − costo directo de todas sus partidas.** El margen divide esa utilidad entre la venta neta sin IVA. Los cobros y anticipos afectan tesorería y cuentas por cobrar, no esta fórmula.

El costeo guarda una copia de los costos de ese momento. Cambiar el filamento o la receta no altera ventas anteriores; usa **Asignar / actualizar costeo** para aprobar una nueva versión. Si cambian las partidas de una venta, el sistema marca su costeo para revisión. Si completas después un costo que estaba pendiente, vuelve a asignarlo a la venta.

La utilidad agregada incluye solo ventas con costo completo y vigente. Se excluyen canceladas y papelera. Renta, administración, comisiones, fletes u otros gastos que no se hayan incorporado expresamente a los costos directos quedan fuera: este indicador es utilidad bruta estimada, no utilidad neta del negocio ni saldo de caja.
